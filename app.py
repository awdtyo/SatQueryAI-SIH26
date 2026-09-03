"""Gradio + ZeroGPU entry for HF Spaces — keeps Docker local CPU intact.

- Gradio SDK (sdk: gradio, hardware: zero-a10g) runs this file as `app.py` on 7860.
- Docker local (`Dockerfile`, `SATQUERY_FORCE_CPU=1`) is untouched — `make pitch-demo` still works.
- Reuses backend/controller + registry + specialist contracts (no HTTP, direct controller.handle).
- Model is loaded at module scope on CUDA (ZeroGPU emulation outside @spaces.GPU, real CUDA inside decorated handler).
- Frontend 3-zone React is replaced by gr.Blocks for Spaces; local React (5173) stays for dev.

Usage locally (no ZeroGPU hardware, decorator is no-op):
    python app.py  # opens http://localhost:7860

On HF Spaces ZeroGPU:
    sdk: gradio + hardware: zero-a10g + @spaces.GPU does the scheduling.
"""

from __future__ import annotations

# spaces must be imported before torch (backend) so ZeroGPU can patch CUDA
try:
    import spaces  # type: ignore  # pip: spaces — not in requirements.txt, provided by HF Gradio image
except ImportError:  # local dev without spaces package — no-op decorator
    class _SpacesStub:
        def GPU(self, *args, **kwargs):  # type: ignore
            def deco(fn):
                return fn

            # Support both @spaces.GPU and @spaces.GPU(duration=30)
            if args and callable(args[0]) and not kwargs:
                return args[0]
            return deco

    spaces = _SpacesStub()  # type: ignore

import io
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import gradio as gr
from PIL import Image

from backend import config as app_config
from backend.controller import handle as controller_handle
from backend import registry

logger = logging.getLogger("satquery.gradio")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# Keep backend's CPU flag for Docker, but ZeroGPU needs GPU — override via env at Space runtime
# Space Variables should set SATQUERY_FORCE_CPU=0 (Docker local keeps 1 via Dockerfile:22)
# Also auto-detect ZeroGPU via SPACES_ZERO_GPU env (HF sets on zero-a10g)
if os.getenv("SPACES_ZERO_GPU") == "1":
    # On ZeroGPU, force GPU unless user explicitly set SATQUERY_FORCE_CPU=1
    if "SATQUERY_FORCE_CPU" not in os.environ:
        os.environ["SATQUERY_FORCE_CPU"] = "0"
        # Patch already-imported config and reset cached vqa load so next predict loads on real CUDA
        try:
            app_config.FORCE_CPU = False  # type: ignore
            import backend.models.vqa as _vqa

            _vqa._load_attempted = False  # type: ignore
            _vqa._is_real = False  # type: ignore
            _vqa._load_error = None  # type: ignore
        except Exception:
            pass

if os.getenv("SATQUERY_FORCE_CPU", "1").lower() in ("0", "false", "off", "no", ""):
    logger.info("Gradio Space: SATQUERY_FORCE_CPU=0 — ZeroGPU CUDA enabled")
else:
    logger.warning("Gradio Space: SATQUERY_FORCE_CPU still 1 — set Space Variable SATQUERY_FORCE_CPU=0 for ZeroGPU, else model stays on CPU")

# Warm registry health at startup — but NOT on ZeroGPU outside GPU worker (would cache CPU model)
# On ZeroGPU, health outside GPU would load model on emulated CUDA and cache as CPU, breaking real GPU fork
_is_zerogpu = os.getenv("SPACES_ZERO_GPU") == "1" or os.getenv("SATQUERY_FORCE_CPU", "1").lower() in ("0", "false", "off", "no", "")
if not _is_zerogpu:
    try:
        h = registry.health()
        logger.info("Gradio startup health: %s", json.dumps({k: v.get("is_real") for k, v in h.get("registry", {}).items()}))
    except Exception as e:
        logger.warning("Gradio startup health failed: %s", e)
else:
    logger.info("Gradio startup health: deferred (ZeroGPU — will load on first @spaces.GPU call)")


def _pil_to_bytes(img: Image.Image, fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _coerce_gradio_image(img: Any, filename: str | None = None) -> tuple[str | None, bytes] | Image.Image:
    """Gradio gr.Image(type='pil') gives PIL.Image; gr.File gives dict/filepath.
    Return a (filename, bytes) tuple for controller (filename preserves extension for validation)
    or PIL.Image directly (controller also accepts PIL).
    """
    if img is None:
        raise ValueError("No image provided")
    if isinstance(img, Image.Image):
        return img
    if isinstance(img, dict) and "name" in img:
        # gr.File returns {'name': '/tmp/...', 'orig_name': '...', 'size': ...} in some gradio versions
        # or filepath string
        path = img.get("name") or img.get("path") or img.get("orig_name")
        if path and Path(path).exists():
            data = Path(path).read_bytes()
            fname = img.get("orig_name") or Path(path).name
            return (fname, data)
        raise ValueError(f"Cannot read image dict: {img}")
    if isinstance(img, str) and Path(img).exists():
        # filepath
        return (Path(img).name, Path(img).read_bytes())
    if isinstance(img, (bytes, bytearray)):
        return (filename or "upload.png", bytes(img))
    # numpy array from gr.Image(type='numpy')
    try:
        import numpy as np  # type: ignore

        if isinstance(img, np.ndarray):
            pil = Image.fromarray(img.astype("uint8"))
            return pil
    except Exception:
        pass
    raise ValueError(f"Unsupported Gradio image type: {type(img)}")


@spaces.GPU(duration=30)  # ZeroGPU: 30s worst-case (VQA ~1-2s on Blackwell, avoid 60s quota pre-check fail)
def predict(
    query: str,
    input_mode: str,
    image_a: Any,
    image_b: Any | None = None,
) -> tuple[str, float, dict[str, Any], str]:
    """Gradio handler — decorated for ZeroGPU scheduling.

    Args:
        query: natural language question
        input_mode: single | optical-sar | bi-temporal (from gr.Radio)
        image_a: first image (PIL from gr.Image)
        image_b: second image for optical-sar / bi-temporal (PIL or None)

    Returns:
        (answer, confidence, execution_trace_json, evidence_md)
        Gradio outputs: Textbox, Number, JSON, Markdown
    """
    started = time.time()
    if not query or not query.strip():
        return "Please enter a query.", 0.0, {}, "No query provided."

    # Validate mode
    mode = (input_mode or "single").strip().lower()
    if mode not in app_config.SUPPORTED_INPUT_MODES:
        return f"Unsupported input_mode '{mode}'. Allowed: {sorted(app_config.SUPPORTED_INPUT_MODES)}", 0.0, {}, ""

    # Collect images per mode
    images: list[Any] = []
    try:
        if mode == "single":
            if image_a is None:
                return "Upload one image for single mode.", 0.0, {}, ""
            images.append(_coerce_gradio_image(image_a, "image.png"))
        elif mode in ("optical-sar", "bi-temporal"):
            if image_a is None or image_b is None:
                return f"Upload two images for {mode} (both slots required).", 0.0, {}, ""
            images.append(_coerce_gradio_image(image_a, "image0.png"))
            images.append(_coerce_gradio_image(image_b, "image1.png"))
        else:
            return f"Unknown mode {mode}", 0.0, {}, ""
    except Exception as e:
        logger.exception("Image coercion failed: %s", e)
        return f"Image error: {e}", 0.0, {}, ""

    # Delegate to controller (reuses validate_inputs, classify_task, registry.predict, ExecutionTrace)
    try:
        resp = controller_handle(query=query.strip(), images=images, input_mode=mode)
    except Exception as e:
        # Controller already catches specialist failures, but validate_inputs raises HTTPException
        # which we surface as user-visible error
        try:
            from fastapi import HTTPException as _HTTPException

            if isinstance(e, _HTTPException):
                return f"Validation error ({e.status_code}): {e.detail}", 0.0, {}, ""
        except Exception:
            pass
        logger.exception("Controller failed: %s", e)
        return f"Controller error: {e}", 0.0, {}, ""

    # Build evidence markdown for display
    evidence_md_parts: list[str] = []
    for ev in resp.evidence:
        icon = {"bounding_box": "▢", "overlay": "◈", "heatmap": "▣", "saliency": "◎", "image_ref": "▣"}.get(ev.type, "•")
        line = f"{icon} **{ev.type.replace('_', ' ').upper()}** — {ev.description}"
        if ev.coordinates:
            line += f" `coords={ev.coordinates}`"
        evidence_md_parts.append(line)
    evidence_md = "\n\n".join(evidence_md_parts) if evidence_md_parts else "No evidence."

    # Execution trace as JSON-serializable dict (Pydantic → dict)
    try:
        trace_dict = resp.execution_trace.model_dump()  # pydantic v2
    except Exception:
        trace_dict = resp.execution_trace.dict()  # fallback v1

    # Confidence gauge text
    conf = float(resp.confidence)
    wall_ms = int((time.time() - started) * 1000)

    # Append wall time to trace for transparency (not part of schema, just info)
    trace_dict["_gradio_wall_ms"] = wall_ms

    logger.info("Gradio predict: mode=%s task=%s conf=%.3f wall=%dms answer_len=%d", mode, trace_dict.get("task"), conf, wall_ms, len(resp.answer))

    return resp.answer, conf, trace_dict, evidence_md


# ── Gradio UI — 3-zone parity with frontend/src/App.tsx but in Blocks ──
with gr.Blocks(
    title="SatQuery AI — Agentic Remote-Sensing VLM",
) as demo:
    gr.Markdown(
        """
        # SatQuery AI — Agentic Vision-Language Assistant for Remote Sensing
        **Smart India Hackathon 2026** — Natural-language querying of single & paired satellite imagery (optical, SAR) with evidence-grounded answers and full `ExecutionTrace`. Stage-1 VQA **real QLoRA Qwen2-VL-2B + BigEarthNet**; grounding/change/fusion stubbed until Stage-2/3.
        > **ZeroGPU:** Blackwell `48GB large` via `@spaces.GPU(duration=30)` — ~1s vs `30s` CPU. **Docker local** (`make pitch-demo`, `SATQUERY_FORCE_CPU=1`) stays CPU-only for i5/16GB.
        """
    )

    with gr.Row():
        with gr.Column(scale=2, min_width=300):
            gr.Markdown("### Imagery Input")
            input_mode = gr.Radio(
                choices=[("SINGLE", "single"), ("OPTICAL+SAR", "optical-sar"), ("BI-TEMPORAL", "bi-temporal")],
                value="single",
                label="Input mode",
                info="single=1 image, optical-sar=2 (Optical+SAR), bi-temporal=2 (T1+T2)",
            )
            image_a = gr.Image(label="Image / Optical / T1", type="pil", sources=["upload", "clipboard"], height=280)
            image_b = gr.Image(label="Second image (SAR / T2) — required for optical-sar / bi-temporal", type="pil", sources=["upload"], height=280, visible=False)
            gr.Markdown("`GeoTIFF/TIFF/PNG/JPEG` accepted (`.tif/.tiff/.png/.jpg/.jpeg`). Controller validates `single→1` `optical-sar→2` `bi-temporal→2` and `Geotiff` bands via `rasterio` when installed.")

            # Toggle second image visibility by mode
            def _toggle_second(mode: str):
                return gr.update(visible=mode in ("optical-sar", "bi-temporal"))

            input_mode.change(fn=_toggle_second, inputs=[input_mode], outputs=[image_b])

            gr.Markdown("### Query")
            query = gr.Textbox(
                label="Natural-language query",
                placeholder="Describe the land cover in this satellite image.",
                lines=3,
            )
            gr.Examples(
                examples=[
                    ["Describe the land cover in this satellite image.", "single"],
                    ["What changed between these two dates?", "bi-temporal"],
                    ["Where is the building? Locate it.", "single"],
                    ["Fuse optical and SAR — detect flooded areas", "optical-sar"],
                ],
                inputs=[query, input_mode],
                label="Suggestions (click to fill)",
            )
            run_btn = gr.Button("Execute Analysis", variant="primary")
            clear_btn = gr.Button("Clear", variant="secondary")
            status = gr.Markdown("")

        with gr.Column(scale=3):
            gr.Markdown("### Intelligence Result")
            answer = gr.Textbox(label="Answer", lines=6, buttons=["copy"])
            confidence = gr.Number(label="Confidence (0–1)", precision=3)
            evidence = gr.Markdown()

        with gr.Column(scale=2, min_width=320):
            gr.Markdown("### Execution Trace (graded)")
            trace = gr.JSON(label="ExecutionTrace — task, models_used[{is_real,is_stub}], parameters, total_latency_ms", value={})
            gr.Markdown(
                """
                **Trace contract:** `docs/execution_trace_schema.md` (`backend/schemas` ↔ `frontend/src/types/api.ts`).
                `confidence` mirrors top-level `confidence` (`log_softmax` when available, else heuristic). `is_real` = adapter loaded.
                """
            )
            health = gr.JSON(label="Health (live, from registry.health)", value={})
            refresh_health = gr.Button("Refresh health", size="sm")

    # Health helper (no GPU needed, not decorated)
    def _health() -> dict[str, Any]:
        try:
            return registry.health()
        except Exception as e:
            return {"error": str(e)}

    refresh_health.click(fn=_health, outputs=[health])
    # Initial health load
    demo.load(fn=_health, outputs=[health])

    # Wire predict
    run_btn.click(
        fn=predict,
        inputs=[query, input_mode, image_a, image_b],
        outputs=[answer, confidence, trace, evidence],
    )

    gr.Markdown(
        """
        ---
        **Local Docker (CPU-only, i5/16GB):** `make pitch-demo` or `SATQUERY_FORCE_CPU=1 uvicorn backend.main:app --port 8000` + `npm run dev` (`5173`). **HF Spaces Gradio ZeroGPU:** this `app.py` on `zero-a10g` with `SATQUERY_FORCE_CPU=0` (`Spaces → Settings → Variables`). See `docs/hf_spaces.md` (Docker) and `docs/hf_spaces_gradio.md` (ZeroGPU).
        """
    )

    clear_btn.click(fn=lambda: (None, None, "", "single", "", 0.0, {}, ""), inputs=None, outputs=[image_a, image_b, query, input_mode, answer, confidence, trace, evidence])

if __name__ == "__main__":
    # HF Spaces injects GRADIO_SERVER_NAME/PORT; locally default 7860 for parity with Docker PORT
    port = int(os.getenv("PORT") or os.getenv("GRADIO_SERVER_PORT") or 7860)
    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        show_error=True,
        theme=gr.themes.Soft(),
        css="""
        .gradio-container {max-width: 1280px !important}
        .panel {border: 1px solid #2a3a4a; border-radius: 10px; background: #0f1b2a0a; padding: 12px}
        """,
    )
