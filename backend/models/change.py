"""
Change-detection specialist — real inference with Qwen2-VL-2B + CDVQA QLoRA (bi-temporal).

Benchmarks: CDVQA (bi-temporal change). Adapter trained in stage 3 on
paired T1/T2 + change QA, continuing from stage2 VRSBench.

Interface (shared contract, do not change signature):
    predict(images, query, task) -> {"answer": str, "evidence": list[dict], "confidence": float}

- images: [PIL.Image.Image T1, PIL.Image.Image T2] | str | bytes | list
- query: natural language change question (e.g. "What changed between T1 and T2?")
- task: "change_detection" | "change" | "cdvqa"

Model is singleton, loaded once at startup on appropriate device with 4-bit if GPU.
Expects 2 images; fails gracefully if count !=2.
"""

from __future__ import annotations

import logging
import math
import time
from pathlib import Path
from typing import Any

from PIL import Image

try:
    import torch  # type: ignore
except ImportError:
    torch = None  # type: ignore

from backend import config as app_config

logger = logging.getLogger(__name__)

# Singleton state — separate from VQA (own adapter)
_model = None  # Qwen2VLForConditionalGeneration + PeftModel (change)
_processor = None  # AutoProcessor
_load_error: str | None = None
_load_attempted: bool = False
_is_real: bool = False

# Generation defaults — reuse global knobs but allow change-specific suffix
_MAX_NEW_TOKENS = app_config.MAX_NEW_TOKENS
_MIN_NEW_TOKENS = app_config.MIN_NEW_TOKENS
_TEMPERATURE = app_config.TEMPERATURE
_TOP_P = app_config.TOP_P
_REPETITION_PENALTY = app_config.REPETITION_PENALTY
_NO_REPEAT_NGRAM_SIZE = app_config.NO_REPEAT_NGRAM_SIZE

# Change-specific prompt
_CHANGE_SYSTEM_PROMPT = (
    "You are SatQuery AI, an expert remote-sensing change-detection analyst. "
    "You receive two co-registered satellite images T1 (earlier) and T2 (later). "
    "Respond ONLY in markdown bullets (3-6 bullets, each 1 sentence, 18-30 words). "
    "Bullets replace paragraphs. Each bullet: what changed (e.g. urban expansion, deforestation), "
    "quadrant/location, magnitude, 10m Sentinel-2 context. "
    "If asked yes/no (did urban expand?), first bullet is **Answer: Yes/No** then context. "
    "Note uncertainty in last bullet. Do not include JSON — chart is measured separately."
)
_CHANGE_DETAIL_SUFFIX = " Respond with bullet points describing the change between T1 and T2."


def _get_compute_dtype():  # type: ignore[no-untyped-def]
    if torch is None:
        return None
    return torch.float16


def _is_gpu_available() -> bool:
    if getattr(app_config, "FORCE_CPU", False):
        return False
    if hasattr(app_config, "is_gpu_available"):
        try:
            return bool(app_config.is_gpu_available())
        except Exception:
            pass
    return bool(torch is not None and torch.cuda.is_available())


def _load_model() -> bool:
    global _model, _processor, _load_error, _load_attempted, _is_real
    if _load_attempted:
        return _is_real
    _load_attempted = True

    base_id = app_config.CHANGE_BASE_MODEL
    adapter_id = app_config.CHANGE_ADAPTER_PATH
    hf_token = app_config.HF_TOKEN

    logger.info("Change specialist: loading base=%s adapter=%s", base_id, adapter_id)

    try:
        from transformers import AutoProcessor, BitsAndBytesConfig, Qwen2VLForConditionalGeneration
        from peft import PeftModel

        try:
            _processor = AutoProcessor.from_pretrained(
                base_id,
                min_pixels=app_config.IMAGE_MIN_PIXELS,
                max_pixels=app_config.IMAGE_MAX_PIXELS,
                trust_remote_code=True,
                token=hf_token,
            )
        except Exception as e:
            logger.warning("Change processor load with min/max failed (%s), retrying plain", e)
            _processor = AutoProcessor.from_pretrained(base_id, trust_remote_code=True, token=hf_token)

        has_cuda = _is_gpu_available()
        raw_has_cuda = bool(torch is not None and torch.cuda.is_available())
        if not has_cuda and raw_has_cuda and getattr(app_config, "FORCE_CPU", False):
            logger.info("Change: FORCE_CPU=1 — ignoring CUDA")
        if has_cuda:
            try:
                gpu_name = torch.cuda.get_device_name(0) if torch is not None else "cuda"
                logger.info("Change: GPU detected — %s", gpu_name)
            except Exception:
                logger.info("Change: GPU detected")
        else:
            logger.info("Change: no GPU or FORCE_CPU — CPU")

        has_bnb = True
        try:
            import bitsandbytes  # noqa: F401
        except Exception:
            has_bnb = False
        if getattr(app_config, "FORCE_CPU", False):
            has_bnb = False

        if not has_cuda:
            device_map_value: Any = "cpu"
        else:
            device_map_value = "auto"
        model_kwargs: dict[str, Any] = {
            "trust_remote_code": True,
            "device_map": device_map_value,
            "token": hf_token,
        }
        if not has_cuda:
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
            logger.info("Change: using 4-bit NF4")
        elif has_cuda and not has_bnb:
            logger.warning("Change: GPU but no bitsandbytes — fp16")
            model_kwargs["torch_dtype"] = _get_compute_dtype()
        else:
            model_kwargs["torch_dtype"] = _get_compute_dtype()

        base_model = Qwen2VLForConditionalGeneration.from_pretrained(base_id, **model_kwargs)

        try:
            import os

            offload_kwargs = {}
            if not has_cuda:
                os.makedirs("/tmp/satquery_offload", exist_ok=True)
                offload_kwargs = {"offload_folder": "/tmp/satquery_offload"}
            _model = PeftModel.from_pretrained(base_model, adapter_id, token=hf_token, **offload_kwargs)
            _is_real = True
            logger.info("Change: adapter loaded from %s", adapter_id)
        except Exception as e:
            logger.error("Change: adapter load failed (%s): %s", adapter_id, e, exc_info=True)
            _load_error = f"Adapter load failed ({adapter_id}): {e}"
            _model = None
            _is_real = False
            return False

        _model.eval()
        _is_real = True
        _load_error = None
        if not has_cuda:
            try:
                _model = _model.to("cpu")  # type: ignore
            except Exception:
                pass
        else:
            try:
                if hasattr(_model, "device") and str(_model.device) == "cpu":
                    _model = _model.to("cuda")  # type: ignore
            except Exception:
                pass
        logger.info("Change specialist READY — %s device_map=%s", "GPU" if has_cuda else "CPU", device_map_value)
        return True

    except Exception as e:
        logger.error("Change base load failed (%s): %s", base_id, e, exc_info=True)
        _load_error = f"Base load failed ({base_id}): {e}"
        _model = None
        _processor = None
        _is_real = False
        return False


def _ensure_loaded() -> None:
    if torch is None:
        raise RuntimeError(_load_error or "torch not installed")
    if not _load_attempted:
        _load_model()
    if not _is_real or _model is None or _processor is None:
        raise RuntimeError(_load_error or "Change specialist not loaded")


def _coerce_images(images: Any) -> list[Image.Image]:
    if images is None:
        raise ValueError("No images for change specialist")
    if isinstance(images, Image.Image):
        return [images.convert("RGB")]
    if isinstance(images, (str, Path)):
        return [Image.open(str(images)).convert("RGB")]
    if isinstance(images, (bytes, bytearray)):
        import io

        return [Image.open(io.BytesIO(images)).convert("RGB")]
    if isinstance(images, (list, tuple)):
        out: list[Image.Image] = []
        for item in images:
            if isinstance(item, Image.Image):
                out.append(item.convert("RGB"))
            elif isinstance(item, (str, Path)):
                out.append(Image.open(str(item)).convert("RGB"))
            elif isinstance(item, (bytes, bytearray)):
                import io

                out.append(Image.open(io.BytesIO(item)).convert("RGB"))
            else:
                raise ValueError(f"Unsupported image type: {type(item)}")
        if not out:
            raise ValueError("Empty image list")
        return out
    raise ValueError(f"Unsupported images type: {type(images)}")


def predict(
    images: Any,
    query: str,
    task: str = "change_detection",
) -> dict[str, Any]:
    start_ms = time.time()
    _ensure_loaded()
    assert _model is not None and _processor is not None

    if not query or not query.strip():
        raise ValueError("Empty query for change specialist")

    pil_images = _coerce_images(images)
    if len(pil_images) != 2:
        raise ValueError(f"Change detection expects 2 images (T1,T2), got {len(pil_images)}")

    t1, t2 = pil_images[0], pil_images[1]

    q_text = query.strip()
    if len(q_text.split()) <= 6:
        q_text = q_text + _CHANGE_DETAIL_SUFFIX

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": [{"type": "text", "text": _CHANGE_SYSTEM_PROMPT}]},
        {
            "role": "user",
            "content": [
                {"type": "image", "image": t1},
                {"type": "image", "image": t2},
                {"type": "text", "text": q_text},
            ],
        },
    ]

    try:
        prompt_text = _processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = _processor(text=[prompt_text], images=[t1, t2], return_tensors="pt", padding=True)

        assert torch is not None
        try:
            if hasattr(_model, "device"):
                model_device = _model.device  # type: ignore
            else:
                model_device = next(_model.parameters()).device  # type: ignore
        except Exception:
            model_device = torch.device("cuda" if _is_gpu_available() else "cpu")
        if _is_gpu_available() and str(model_device) == "cpu" and not getattr(app_config, "FORCE_CPU", False):
            try:
                model_device = torch.device("cuda")
            except Exception:
                pass
        for k, v in list(inputs.items()):
            if isinstance(v, torch.Tensor):
                try:
                    inputs[k] = v.to(model_device)
                except Exception:
                    inputs[k] = v.to("cpu") if not _is_gpu_available() else v.to("cuda")

        with torch.no_grad():
            input_len = int(inputs["input_ids"].shape[1])
            do_sample = _TEMPERATURE > 0
            try:
                outputs = _model.generate(
                    **inputs,
                    max_new_tokens=_MAX_NEW_TOKENS,
                    min_new_tokens=_MIN_NEW_TOKENS if _MIN_NEW_TOKENS > 0 else None,
                    do_sample=do_sample,
                    temperature=_TEMPERATURE if do_sample else None,
                    top_p=_TOP_P if do_sample else None,
                    repetition_penalty=_REPETITION_PENALTY,
                    no_repeat_ngram_size=_NO_REPEAT_NGRAM_SIZE,
                    output_scores=True,
                    return_dict_in_generate=True,
                )
                if hasattr(outputs, "sequences"):
                    gen_ids = outputs.sequences
                    scores = getattr(outputs, "scores", None)
                elif isinstance(outputs, tuple) and len(outputs) == 2:
                    gen_ids, scores = outputs  # type: ignore
                else:
                    gen_ids = outputs  # type: ignore
            except TypeError:
                gen_ids = _model.generate(
                    **inputs,
                    max_new_tokens=_MAX_NEW_TOKENS,
                    do_sample=do_sample,
                    temperature=_TEMPERATURE if do_sample else 0.0,
                    top_p=_TOP_P if do_sample else None,
                )
                scores = None

            if gen_ids is None:
                raise RuntimeError("Change generate returned no ids")
            gen_trimmed = gen_ids[0][input_len:]  # type: ignore
            answer = _processor.decode(gen_trimmed, skip_special_tokens=True).strip()

            if not answer:
                answer = "(no answer generated)"
                confidence = 0.3
            else:
                confidence = None
                if scores is not None:
                    try:
                        import torch.nn.functional as F  # type: ignore

                        log_probs: list[float] = []
                        for idx, logit in enumerate(scores):  # type: ignore
                            if not hasattr(logit, "shape"):
                                continue
                            try:
                                lp_dist = F.log_softmax(logit, dim=-1)  # type: ignore
                            except Exception:
                                continue
                            try:
                                tok_tensor = gen_ids[0][input_len + idx]  # type: ignore
                                tok = int(tok_tensor.item()) if hasattr(tok_tensor, "item") else int(tok_tensor)  # type: ignore
                            except Exception:
                                continue
                            try:
                                if hasattr(lp_dist, "dim") and lp_dist.dim() == 2:  # type: ignore
                                    lp = float(lp_dist[0, tok].item())  # type: ignore
                                else:
                                    lp = float(lp_dist[tok].item())  # type: ignore
                                log_probs.append(lp)
                            except Exception:
                                continue
                        if log_probs:
                            mean_lp = sum(log_probs) / len(log_probs)
                            base_prob = math.exp(mean_lp)
                            conf = 0.35 + 0.6 * float(base_prob)
                            if "I cannot" in answer or "sorry" in answer.lower():
                                conf = min(conf, 0.35)
                            confidence = max(0.1, min(0.95, conf))
                    except Exception as e:
                        logger.debug("Change logprob failed: %s", e)
                        confidence = None
                if confidence is None:
                    base = 0.72
                    if len(answer.split()) > 12:
                        base += 0.08
                    if "I cannot" in answer or "sorry" in answer.lower():
                        base = 0.35
                    confidence = min(0.95, max(0.1, base))

    except Exception as e:
        logger.error("Change predict failed (query=%r): %s", query[:80], e, exc_info=True)
        raise RuntimeError(f"Change inference failed: {e}") from e

    latency_ms = int((time.time() - start_ms) * 1000)

    # Bullets parse
    import re

    bullets: list[str] = []
    for line in answer.splitlines():
        s = line.strip()
        if s.startswith("- ") or s.startswith("• ") or s.startswith("* "):
            bullets.append(s[2:].strip()[:180])
    if not bullets and "•" in answer:
        bullets = [b.strip()[:180] for b in answer.split("•") if b.strip()][:6]
    if "```json" in answer:
        answer = re.sub(r"```json\s*\{.*?\}\s*```", "", answer, flags=re.DOTALL).strip()
    if not bullets and answer.strip():
        sents = re.split(r"(?<=[.!?])\s+", answer.strip())
        bullets = [s.strip()[:180] for s in sents if s.strip()][:6]
        if bullets:
            answer = "\n".join(f"- {b}" for b in bullets)
    elif bullets:
        answer = "\n".join(f"- {b}" for b in bullets)

    # Chart — delta distribution T1 vs T2 (heuristic measured, not LLM)
    chart: list[dict[str, Any]] = []
    if getattr(app_config, "CHART_ENABLED", True):
        try:
            from backend.utils.chart import compute_chart

            c1 = compute_chart(t1)
            c2 = compute_chart(t2)
            # Build delta per label: T2 - T1
            m1 = {d["label"]: float(d["value"]) for d in c1}
            m2 = {d["label"]: float(d["value"]) for d in c2}
            labels = set(m1.keys()) | set(m2.keys())
            for lbl in labels:
                v1 = m1.get(lbl, 0.0)
                v2 = m2.get(lbl, 0.0)
                delta = round(v2 - v1, 1)
                if abs(delta) >= 1.0:  # only meaningful change
                    chart.append({"label": lbl, "value": delta})
            # Top 5 absolute delta
            chart = sorted(chart, key=lambda x: abs(float(x["value"])), reverse=True)[:5]
            if not chart:
                chart = [{"label": "no significant change", "value": 0.0}]
        except Exception as e:
            logger.warning("Change chart failed: %s", e)
            chart = [{"label": "change", "value": 0.0}]
    else:
        chart = []

    # Evidence: overlay (change) + bounding boxes if YOLO-style? Use heuristic bbox from diff
    evidence: list[dict[str, Any]] = []
    # Overlay description
    changed_ratio = 0.0
    try:
        # Quick changed pixel ratio for evidence description
        import numpy as np

        a1 = np.array(t1.resize((128, 128)))
        a2 = np.array(t2.resize((128, 128)))
        diff = np.mean(np.abs(a1.astype(int) - a2.astype(int)), axis=2)
        changed_ratio = float(np.mean(diff > 30) * 100)
    except Exception:
        pass
    evidence.append(
        {
            "type": "overlay",
            "description": f"Change between T1 and T2 — {changed_ratio:.1f}% pixels changed (measured)",
            "image_index": 1,
        }
    )
    # Also image_ref for T1/T2?
    evidence.append({"type": "image_ref", "description": "T1 (before)", "image_index": 0})
    evidence.append({"type": "image_ref", "description": "T2 (after)", "image_index": 1})

    logger.info("Change predict done: query=%r latency=%dms bullets=%d chart=%d", query[:60], latency_ms, len(bullets), len(chart))

    return {
        "answer": answer,
        "evidence": evidence,
        "confidence": float(confidence),
        "_latency_ms": latency_ms,
        "_structured": {"bullets": bullets, "chart": chart, "chart_type": "change"},
        "_chart": chart,
        "_chart_type": "change",
    }


def is_real() -> bool:
    if not _load_attempted:
        _load_model()
    return _is_real


def load_error() -> str | None:
    if not _load_attempted:
        _load_model()
    return _load_error


def get_model_info() -> dict[str, Any]:
    if not _load_attempted:
        _load_model()
    raw_has_cuda = bool(torch is not None and torch.cuda.is_available()) if torch is not None else False
    has_cuda = raw_has_cuda and not getattr(app_config, "FORCE_CPU", False)
    device = (app_config.get_device() if hasattr(app_config, "get_device") else ("cuda" if has_cuda else "cpu")) if _is_real else "unloaded"
    # Try to get real device string
    try:
        if _model is not None and hasattr(_model, "parameters"):
            device = str(next(_model.parameters()).device)  # type: ignore
    except Exception:
        pass
    return {
        "base_model": app_config.CHANGE_BASE_MODEL,
        "adapter_path": app_config.CHANGE_ADAPTER_PATH,
        "is_real": _is_real,
        "load_error": _load_error,
        "device": device,
        "has_cuda": raw_has_cuda,
        "has_cuda_effective": has_cuda,
        "force_cpu": getattr(app_config, "FORCE_CPU", False),
        "compute": "cuda" if has_cuda else "cpu",
        "task": "change_detection",
        "chart_type": "change",
    }


def preload() -> bool:
    return _load_model()


__all__ = ["predict", "is_real", "load_error", "get_model_info", "preload"]
