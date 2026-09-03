"""
VQA / Captioning specialist wrapper — real inference with Qwen2-VL-2B + QLoRA.

Benchmarks: RSVQA, VRSBench (captioning/VQA). Stage 1 adapter trained on
BigEarthNet Sentinel-2 image-caption pairs (see training/notebooks/).

Interface (shared contract — high-stakes, do not change signature):
    predict(images, query, task) -> {"answer": str, "evidence": list[dict], "confidence": float}

- images: PIL.Image.Image | list[PIL.Image.Image] | str (path) | bytes
- query: natural language question/caption prompt
- task: "vqa" | "captioning" | "visual_question_answering" (affects evidence labeling)

Model is loaded ONCE at server startup as a module-level singleton. Per-request
loading would be unusably slow and OOM under load.
"""

from __future__ import annotations

import logging
import math
import time
from pathlib import Path
from typing import Any

from PIL import Image

# torch is optional at import time — CI may not have it; inference will fail
# gracefully with a clear error if predict() is called without torch.
try:
    import torch  # type: ignore
except ImportError:  # pragma: no cover - CI without GPU
    torch = None  # type: ignore

from backend import config as app_config

logger = logging.getLogger(__name__)

# Singleton state
_model = None  # Qwen2VLForConditionalGeneration + PeftModel
_processor = None  # AutoProcessor
_load_error: str | None = None
_load_attempted: bool = False
_is_real: bool = False  # True if adapter actually loaded, False if stub/degraded

# Generation defaults
_MAX_NEW_TOKENS = app_config.MAX_NEW_TOKENS


def _get_compute_dtype():  # type: ignore[no-untyped-def]
    """T4 (sm_75) is fp16-optimal; bf16 is emulated/slow. Always use fp16 for inference unless A100+."""
    if torch is None:
        return None
    # We intentionally keep fp16 even when bf16 is available — matches training notebook.
    return torch.float16


def _load_model() -> bool:
    """Load base 4-bit quantized + adapter once. Returns True if real model ready."""
    global _model, _processor, _load_error, _load_attempted, _is_real
    if _load_attempted:
        return _is_real
    _load_attempted = True

    base_id = app_config.BASE_MODEL
    adapter_id = app_config.ADAPTER_PATH
    hf_token = app_config.HF_TOKEN

    logger.info("VQA specialist: loading base=%s adapter=%s", base_id, adapter_id)

    try:
        from transformers import AutoProcessor, BitsAndBytesConfig, Qwen2VLForConditionalGeneration
        from peft import PeftModel

        # Processor — always succeeds (small download)
        try:
            _processor = AutoProcessor.from_pretrained(
                base_id,
                min_pixels=app_config.IMAGE_MIN_PIXELS,
                max_pixels=app_config.IMAGE_MAX_PIXELS,
                trust_remote_code=True,
                token=hf_token,
            )
        except Exception as e:
            # Fallback without min/max if processor doesn't support it
            logger.warning("VQA processor load with min/max pixels failed (%s), retrying plain", e)
            _processor = AutoProcessor.from_pretrained(
                base_id, trust_remote_code=True, token=hf_token
            )

        # Determine quantization strategy — CPU-only if FORCE_CPU
        raw_has_cuda = bool(torch is not None and torch.cuda.is_available())
        if app_config.FORCE_CPU and raw_has_cuda:
            logger.info("VQA: FORCE_CPU=1 — ignoring available CUDA, running on CPU only")
            has_cuda = False
        else:
            has_cuda = raw_has_cuda
        has_bnb = True
        try:
            import bitsandbytes  # noqa: F401
        except Exception:
            has_bnb = False
        # FORCE_CPU also disables 4-bit even if bitsandbytes present
        if app_config.FORCE_CPU:
            has_bnb = False

        # CPU-only: force device_map to cpu to avoid offload_dir dispatch error
        if app_config.FORCE_CPU:
            device_map_value: Any = "cpu"
        else:
            device_map_value = "auto"
        model_kwargs: dict[str, Any] = {
            "trust_remote_code": True,
            "device_map": device_map_value,
            "token": hf_token,
        }
        # Helpful for large CPU load — allow low-mem and offload to /tmp if still needed
        if app_config.FORCE_CPU:
            model_kwargs["low_cpu_mem_usage"] = True

        if has_cuda and has_bnb:
            compute_dtype = _get_compute_dtype()
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=compute_dtype,
            )
            model_kwargs["quantization_config"] = bnb_config
            logger.info("VQA: using 4-bit NF4 + double_quant (compute=%s)", compute_dtype)
        else:
            # CPU fallback or missing bitsandbytes — load in fp16/bf16 without quant
            reason = "no CUDA" if not has_cuda else "bitsandbytes not available"
            logger.warning("VQA: %s — loading without 4-bit quant (fp16)", reason)
            model_kwargs["torch_dtype"] = _get_compute_dtype()

        base_model = Qwen2VLForConditionalGeneration.from_pretrained(base_id, **model_kwargs)

        # Attach LoRA adapter — works for Hub id or local path transparently
        # CPU-only large model needs offload folder for accelerate dispatch (15GB RAM tight for 2B)
        try:
            import tempfile, os

            offload_kwargs = {}
            if app_config.FORCE_CPU:
                tmp_offload = "/tmp/satquery_offload"
                os.makedirs(tmp_offload, exist_ok=True)
                offload_kwargs = {"offload_folder": tmp_offload}
            _model = PeftModel.from_pretrained(base_model, adapter_id, token=hf_token, **offload_kwargs)
            # Merge is optional for inference; keep adapter separate for clarity
            _is_real = True
            logger.info("VQA: adapter loaded successfully from %s", adapter_id)
        except Exception as e:
            # Adapter failed (auth, network, path, OOM) — degrade gracefully
            # Keep base model as fallback? Per AGENTS.md we must not bypass RS adaptation
            # with a generic fallback, so we mark degraded and raise at predict time.
            # But keep base_model so health check can report the error clearly.
            logger.error("VQA: adapter load failed from %s: %s", adapter_id, e, exc_info=True)
            _load_error = f"Adapter load failed ({adapter_id}): {e}"
            # Keep degraded: do not set _model to base alone — would bypass adaptation
            _model = None
            _is_real = False
            return False

        _model.eval()
        _is_real = True
        _load_error = None
        # Restrict tensors to CPU if forced — avoids accidental CUDA placement via device_map auto
        if app_config.FORCE_CPU:
            try:
                _model = _model.to("cpu")  # type: ignore[attr-defined]
            except Exception:
                pass
        if has_cuda and torch is not None and not app_config.FORCE_CPU:
            logger.info(
                "VQA specialist READY — GPU=%s mem=%.1fGB",
                torch.cuda.get_device_name(0),
                torch.cuda.memory_allocated() / 1024**3,
            )
        else:
            mode = "CPU-ONLY (forced)" if app_config.FORCE_CPU else "CPU mode (no CUDA)"
            logger.info("VQA specialist READY — %s", mode)
        return True

    except Exception as e:
        logger.error("VQA: base model load failed (%s): %s", base_id, e, exc_info=True)
        _load_error = f"Base model load failed ({base_id}): {e}"
        _model = None
        _processor = None
        _is_real = False
        return False


def _ensure_loaded() -> None:
    if torch is None:
        raise RuntimeError(
            _load_error or "torch not installed — cannot run VQA inference. Install torch to use real adapter."
        )
    if not _load_attempted:
        _load_model()
    if not _is_real or _model is None or _processor is None:
        raise RuntimeError(
            _load_error or "VQA specialist not loaded — adapter unavailable. "
            "Backend is in degraded/stub mode. Check ADAPTER_PATH / HF_TOKEN / GPU memory."
        )


def _coerce_images(images: Any) -> list[Image.Image]:
    """Normalize various image input forms to list[PIL.Image]."""
    if images is None:
        raise ValueError("No images provided to VQA specialist")

    # Single item -> list
    if isinstance(images, (str, Path)):
        # Path string
        return [Image.open(str(images)).convert("RGB")]
    if isinstance(images, Image.Image):
        return [images.convert("RGB")]
    if isinstance(images, (bytes, bytearray)):
        import io

        return [Image.open(io.BytesIO(images)).convert("RGB")]

    # List/tuple
    if isinstance(images, (list, tuple)):
        out: list[Image.Image] = []
        for idx, item in enumerate(images):
            if isinstance(item, Image.Image):
                out.append(item.convert("RGB"))
            elif isinstance(item, (str, Path)):
                out.append(Image.open(str(item)).convert("RGB"))
            elif isinstance(item, (bytes, bytearray)):
                import io

                out.append(Image.open(io.BytesIO(item)).convert("RGB"))
            elif isinstance(item, dict) and "image" in item:
                # e.g. {"image": PIL.Image}
                img = item["image"]
                if isinstance(img, Image.Image):
                    out.append(img.convert("RGB"))
                else:
                    raise ValueError(f"Unsupported image dict entry at index {idx}: {type(img)}")
            else:
                raise ValueError(f"Unsupported image type at index {idx}: {type(item)}")
        if not out:
            raise ValueError("Empty image list provided")
        return out

    raise ValueError(f"Unsupported images type: {type(images)}")


def predict(
    images: Any,
    query: str,
    task: str = "vqa",
) -> dict[str, Any]:
    """Shared inference interface — see module docstring.

    Returns: {"answer": str, "evidence": list[dict], "confidence": float}

    Evidence is minimal for stage 1 (echoes input). Confidence is derived from
    length-normalized log-probs when the model exposes scores, otherwise falls
    back to a heuristic.

    This function is thread-safe for concurrent FastAPI requests because the
    underlying model is read-only after load (no gradient). GPU memory is shared.
    """
    start_ms = time.time()

    _ensure_loaded()
    assert _model is not None and _processor is not None

    if not query or not query.strip():
        raise ValueError("Empty query provided to VQA specialist")

    pil_images = _coerce_images(images)
    # Stage 1 is single-image only — use first image, warn if more
    if len(pil_images) > 1:
        logger.warning("VQA: received %d images for task=%s, using first only (stage 1 single-image)", len(pil_images), task)

    image = pil_images[0]

    # Build Qwen2-VL chat messages
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": query.strip()},
            ],
        }
    ]

    try:
        prompt_text = _processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = _processor(text=[prompt_text], images=[image], return_tensors="pt", padding=True)

        # Move to model device
        assert torch is not None
        device = next(_model.parameters()).device if hasattr(_model, "parameters") else torch.device("cuda" if torch.cuda.is_available() else "cpu")
        # For device_map="auto" the device may be meta-dispatch; get from inputs
        model_device = _model.device if hasattr(_model, "device") else device
        # Move tensors
        for k, v in list(inputs.items()):
            if isinstance(v, torch.Tensor):
                inputs[k] = v.to(model_device)

        # Generate — request scores for logprob-based confidence when available
        with torch.no_grad():
            # Qwen2-VL may need image_grid_thw handling — processor already sets it
            input_len = int(inputs["input_ids"].shape[1])
            scores = None
            gen_ids = None
            # Try to get scores; fall back to plain generate for mocked tests / old transformers
            try:
                outputs = _model.generate(
                    **inputs,
                    max_new_tokens=_MAX_NEW_TOKENS,
                    do_sample=False,
                    temperature=0.0,
                    top_p=None,
                    output_scores=True,
                    return_dict_in_generate=True,
                )
                # HuggingFace GenerateOutput has .sequences and .scores
                if hasattr(outputs, "sequences"):
                    gen_ids = outputs.sequences
                    scores = getattr(outputs, "scores", None)
                elif isinstance(outputs, tuple) and len(outputs) == 2:
                    gen_ids, scores = outputs  # type: ignore
                else:
                    gen_ids = outputs  # type: ignore
            except TypeError:
                # Older transformers or mocked generate that doesn't accept those kwargs
                gen_ids = _model.generate(
                    **inputs,
                    max_new_tokens=_MAX_NEW_TOKENS,
                    do_sample=False,
                    temperature=0.0,
                    top_p=None,
                )
                scores = None
            # Normalize gen_ids to tensor-like with shape [batch, seq_len]
            if gen_ids is None:
                raise RuntimeError("VQA generate returned no ids")
            # Trim prompt — handle both torch.Tensor and mocked _SimpleTensor
            try:
                seq_len = int(gen_ids.shape[1])  # type: ignore
            except Exception:
                seq_len = len(gen_ids[0]) if hasattr(gen_ids, "__getitem__") else 0  # type: ignore
            # Slice generated tokens
            try:
                gen_trimmed = gen_ids[0][input_len:]  # type: ignore
            except Exception:
                # Fallback for unexpected tensor types
                gen_trimmed = gen_ids[0][input_len:]  # type: ignore
            answer = _processor.decode(gen_trimmed, skip_special_tokens=True).strip()

            if not answer:
                answer = "(no answer generated)"
                confidence = 0.3
            else:
                confidence = None
                # Logprob-based confidence when scores are available
                if scores is not None:
                    try:
                        import torch.nn.functional as F  # type: ignore

                        log_probs: list[float] = []
                        # scores is tuple of [batch, vocab] per generated token
                        for idx, logit in enumerate(scores):  # type: ignore
                            if not hasattr(logit, "shape"):
                                continue
                            # log_softmax over vocab
                            try:
                                lp_dist = F.log_softmax(logit, dim=-1)  # type: ignore
                            except Exception:
                                continue
                            # token id for this step
                            try:
                                tok_tensor = gen_ids[0][input_len + idx]  # type: ignore
                                # tok_tensor may be int or 0-d tensor
                                tok = int(tok_tensor.item()) if hasattr(tok_tensor, "item") else int(tok_tensor)  # type: ignore
                            except Exception:
                                continue
                            try:
                                # lp_dist shape [batch, vocab] or [vocab]
                                if hasattr(lp_dist, "dim") and lp_dist.dim() == 2:  # type: ignore
                                    lp = float(lp_dist[0, tok].item())  # type: ignore
                                else:
                                    lp = float(lp_dist[tok].item())  # type: ignore
                                log_probs.append(lp)
                            except Exception:
                                continue
                        if log_probs:
                            mean_lp = sum(log_probs) / len(log_probs)
                            base_prob = math.exp(mean_lp)  # geometric mean prob in (0,1]
                            # Map to calibrated confidence: 0.35 + 0.6*prob, with apology penalty
                            conf = 0.35 + 0.6 * float(base_prob)
                            if "I cannot" in answer or "sorry" in answer.lower():
                                conf = min(conf, 0.35)
                            confidence = max(0.1, min(0.95, conf))
                    except Exception as e:
                        logger.debug("Logprob confidence failed, falling back to heuristic: %s", e)
                        confidence = None
                if confidence is None:
                    # Heuristic fallback (covers mocked tests where scores is None)
                    base = 0.72
                    if len(answer.split()) > 12:
                        base += 0.08
                    if "I cannot" in answer or "sorry" in answer.lower():
                        base = 0.35
                    confidence = min(0.95, max(0.1, base))

    except Exception as e:
        logger.error("VQA predict failed (query=%r): %s", query[:80], e, exc_info=True)
        raise RuntimeError(f"VQA inference failed: {e}") from e

    latency_ms = int((time.time() - start_ms) * 1000)

    # Minimal evidence for stage 1 — echo input
    evidence = [
        {
            "type": "image_ref",
            "description": f"Input image for task={task}",
            "image_index": 0,
        }
    ]

    logger.info("VQA predict done: task=%s latency=%dms answer_len=%d", task, latency_ms, len(answer))

    return {
        "answer": answer,
        "evidence": evidence,
        "confidence": float(confidence),
        "_latency_ms": latency_ms,  # internal, stripped by controller if needed
    }


# Public helpers for registry/startup check
def is_real() -> bool:
    """Whether the real adapter is loaded (vs degraded/stub)."""
    if not _load_attempted:
        _load_model()
    return _is_real


def load_error() -> str | None:
    """Human-readable load error if degraded, else None."""
    if not _load_attempted:
        _load_model()
    return _load_error


def get_model_info() -> dict[str, Any]:
    """For /health and startup logging."""
    if not _load_attempted:
        _load_model()
    has_cuda = bool(torch is not None and torch.cuda.is_available())
    try:
        device = str(next(_model.parameters()).device) if _model is not None and hasattr(_model, "parameters") else "unloaded"
    except Exception:
        device = "unloaded"
    # Surface forced CPU so health badge can render correctly
    if app_config.FORCE_CPU:
        device = "cpu"
        has_cuda = False
    return {
        "base_model": app_config.BASE_MODEL,
        "adapter_path": app_config.ADAPTER_PATH,
        "is_real": _is_real,
        "load_error": _load_error,
        "device": device,
        "has_cuda": has_cuda,
        "force_cpu": app_config.FORCE_CPU,
        "compute": "cpu-only" if app_config.FORCE_CPU else ("cuda" if has_cuda else "cpu"),
    }


def preload() -> bool:
    """Explicit preload for app startup — returns is_real."""
    return _load_model()


__all__ = ["predict", "is_real", "load_error", "get_model_info", "preload"]
