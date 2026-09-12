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

# --- Patch gradio_client bool schema bug (HF Spaces: TypeError: argument of type 'bool' is not iterable) ---
# gradio JSON schema may emit "additionalProperties": false (bool). gradio_client 1.7.0's
# utils.get_type / _json_schema_to_python_type assumes dict and crashes in get_api_info().
# We monkey-patch before any Blocks are built so /api/info no longer 500s.
try:
    import gradio_client.utils as _gcu  # type: ignore

    _orig_get_type = _gcu.get_type

    def _safe_get_type(schema):  # type: ignore[no-untyped-def]
        if isinstance(schema, bool):
            return "bool" if schema else "Any"
        if not isinstance(schema, dict):
            return {}
        return _orig_get_type(schema)

    _gcu.get_type = _safe_get_type  # type: ignore[method-assign]

    _orig_json = _gcu._json_schema_to_python_type

    def _safe_json(schema, defs=None):  # type: ignore[no-untyped-def]
        if isinstance(schema, bool):
            return "bool" if schema else "Any"
        return _orig_json(schema, defs)

    _gcu._json_schema_to_python_type = _safe_json  # type: ignore[method-assign]
except Exception:
    pass

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

if os.getenv("SATQUERY_FORCE_CPU", "0").lower() in ("0", "false", "off", "no", ""):
    logger.info("Gradio Space: SATQUERY_FORCE_CPU=0 — ZeroGPU CUDA enabled")
else:
    logger.warning("Gradio Space: SATQUERY_FORCE_CPU still 1 — set Space Variable SATQUERY_FORCE_CPU=0 for ZeroGPU, else model stays on CPU")

# Warm registry health at startup — but NOT on ZeroGPU outside GPU worker (would cache CPU model)
# On ZeroGPU, health outside GPU would load model on emulated CUDA and cache as CPU, breaking real GPU fork
_is_zerogpu = os.getenv("SPACES_ZERO_GPU") == "1" or os.getenv("SATQUERY_FORCE_CPU", "0").lower() in ("0", "false", "off", "no", "")
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


def _chart_to_plot(chart_state: Any, chart_type: str = "Bar"):  # type: ignore[no-untyped-def]
    """Identical to frontend ChartPanel — bar/pie toggle, question-aware (count vs distribution)."""
    # chart_state may be list (legacy) or dict {"data": [...], "type": "count"}
    data_type = "distribution"
    if isinstance(chart_state, dict) and "data" in chart_state:
        chart_data = chart_state.get("data", []) or []
        data_type = str(chart_state.get("type", "distribution")).lower()
    elif isinstance(chart_state, list):
        chart_data = chart_state
        # Heuristic fallback: if task was count, treat as count (small ints)
        data_type = "distribution"
    else:
        return None
    if not chart_data:
        return None
    try:
        import matplotlib.pyplot as plt  # type: ignore

        labels = [str(d.get("label", ""))[:12] for d in chart_data]
        values = [float(d.get("value", 0)) for d in chart_data]
        colors = ["#38bdf8", "#22c55e", "#f59e0b", "#a78bfa", "#f43f5e", "#14b8a6"]
        fig, ax = plt.subplots(figsize=(4, 2.2))
        fig.patch.set_facecolor("#0f172a")
        ax.set_facecolor("#0f172a")
        is_count = data_type == "count"
        title = "Count" if is_count else "Distribution"
        if chart_type.lower() == "pie":
            fmt = "%1.0f" if is_count else "%1.0f%%"
            ax.pie(values, labels=labels, autopct=fmt, colors=colors[: len(values)], textprops={"color": "#e2e8f0", "fontsize": 8})
            ax.set_title(title + (" (YOLO)" if is_count else " (measured)"), color="#e2e8f0", fontsize=10)
        else:
            bars = ax.bar(labels, values, color=colors[: len(values)], edgecolor="#334155")
            if is_count:
                ymax = max(values) * 1.25 if values else 5
                ax.set_ylim(0, max(5, ymax))
                ax.set_ylabel("Count", color="#94a3b8", fontsize=8)
                for bar, v in zip(bars, values):
                    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1, f"{int(v)}", ha="center", va="bottom", color="#e2e8f0", fontsize=8)
            else:
                ax.set_ylim(0, 100)
                ax.set_ylabel("%", color="#94a3b8", fontsize=8)
                for bar, v in zip(bars, values):
                    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1, f"{v:.0f}%", ha="center", va="bottom", color="#e2e8f0", fontsize=8)
            ax.set_title(title + (" (YOLO)" if is_count else " (measured)"), color="#e2e8f0", fontsize=10)
            ax.tick_params(colors="#94a3b8", labelsize=8)
            plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
        plt.tight_layout()
        return fig
    except Exception:
        return None


@spaces.GPU(duration=60)  # ZeroGPU: 60s fits free quota, cold pull via cache; 90s exceeds anon quota and hangs UI
def predict(
    query: str,
    input_mode: str,
    image_a: Any,
    image_b: Any | None = None,
    progress: Any = None,
) -> tuple[str, float, dict[str, Any], str, dict[str, Any]]:
    """Gradio handler — decorated for ZeroGPU scheduling.

    Args:
        query: natural language question
        input_mode: single | optical-sar | bi-temporal (from gr.Radio)
        image_a: first image (PIL from gr.Image)
        image_b: second image for optical-sar / bi-temporal (PIL or None)

    Returns:
        (answer_markdown_bullets, confidence, execution_trace_json, evidence_md, chart_data)
        Gradio outputs: Markdown, Number, JSON, Markdown, State (for Plot toggle bar/pie identical to React)
    """
    started = time.time()
    if not query or not query.strip():
        return "Please enter a query.", 0.0, {}, "No query provided.", {"data": [], "type": "none"}

    # Validate mode
    mode = (input_mode or "single").strip().lower()
    if mode not in app_config.SUPPORTED_INPUT_MODES:
        return f"Unsupported input_mode '{mode}'. Allowed: {sorted(app_config.SUPPORTED_INPUT_MODES)}", 0.0, {}, "", {"data": [], "type": "none"}

    # Collect images per mode
    images: list[Any] = []
    try:
        if mode == "single":
            if image_a is None:
                return "Upload one image for single mode.", 0.0, {}, "", {"data": [], "type": "none"}
            images.append(_coerce_gradio_image(image_a, "image.png"))
        elif mode in ("optical-sar", "bi-temporal"):
            if image_a is None or image_b is None:
                return f"Upload two images for {mode} (both slots required).", 0.0, {}, "", {"data": [], "type": "none"}
            images.append(_coerce_gradio_image(image_a, "image0.png"))
            images.append(_coerce_gradio_image(image_b, "image1.png"))
        else:
            return f"Unknown mode {mode}", 0.0, {}, "", {"data": [], "type": "none"}
    except Exception as e:
        logger.exception("Image coercion failed: %s", e)
        return f"Image error: {e}", 0.0, {}, "", {"data": [], "type": "none"}

    # Delegate to controller (reuses validate_inputs, classify_task, registry.predict, ExecutionTrace)
    try:
        resp = controller_handle(query=query.strip(), images=images, input_mode=mode)
    except Exception as e:
        # Controller already catches specialist failures, but validate_inputs raises HTTPException
        # which we surface as user-visible error with full detail
        import traceback as _tb
        try:
            from fastapi import HTTPException as _HTTPException

            if isinstance(e, _HTTPException):
                return f"Validation error ({e.status_code}): {e.detail}", 0.0, {}, f"Validation failed: {e.detail}", {"data": [], "type": "none"}
        except Exception:
            pass
        logger.exception("Controller failed: %s", e)
        # Also surface vqa load error if model not ready
        vqa_err = ""
        try:
            from backend.models import vqa_specialist as _vqa
            info = _vqa.get_model_info()
            if not info.get("is_real"):
                vqa_err = f" | Model not ready: {info.get('load_error') or 'adapter not loaded'} (adapter={info.get('adapter_path')}, device={info.get('device')})"
        except Exception:
            pass
        return f"Controller error: {e}{vqa_err}", 0.0, {"error": str(e), "traceback": _tb.format_exc()[:3000], "vqa_info": vqa_err}, f"Error: {e}\n{ _tb.format_exc()[:1500]}", {"data": [], "type": "none"}

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

    # Chart data for identical bar/pie toggle — question-aware (count vs distribution)
    chart_data: list[dict[str, Any]] = []
    chart_type_data: str = "distribution"
    try:
        # Prefer flat chart, else structured
        if getattr(resp, "chart", None):
            chart_data = [{"label": c.label, "value": float(c.value)} for c in resp.chart]  # type: ignore[attr-defined]
        elif getattr(resp, "structured", None) and resp.structured and resp.structured.chart:  # type: ignore[attr-defined]
            chart_data = [{"label": c.label, "value": float(c.value)} for c in resp.structured.chart]  # type: ignore[attr-defined]
        # Chart type: from response field, else infer from task
        ct = getattr(resp, "chart_type", None)
        if ct:
            chart_type_data = str(ct)
        elif getattr(resp, "structured", None) and resp.structured and getattr(resp.structured, "chart_type", None):  # type: ignore[attr-defined]
            chart_type_data = str(resp.structured.chart_type)  # type: ignore[attr-defined]
        else:
            chart_type_data = "count" if trace_dict.get("task") == "count" else "distribution"
    except Exception:
        chart_data = []
        chart_type_data = "distribution"

    chart_state = {"data": chart_data, "type": chart_type_data}

    return resp.answer, conf, trace_dict, evidence_md, chart_state


# ── Gradio UI — 3-zone parity with frontend/src/App.tsx but in Blocks ──
with gr.Blocks(
    title="SatQuery AI — Agentic Remote-Sensing VLM",
    theme=gr.themes.Soft(),
    css="""
        .gradio-container {max-width: 1280px !important}
        .panel {border: 1px solid #2a3a4a; border-radius: 10px; background: #0f1b2a0a; padding: 12px}
        """,
) as demo:
    gr.Markdown(
        """
        # SatQuery AI — Agentic Vision-Language Assistant for Remote Sensing
        **Smart India Hackathon 2026** — Natural-language querying of single & paired satellite imagery (optical, SAR) with evidence-grounded answers and full `ExecutionTrace`. Stage-2 **VQA+grounding real QLoRA Qwen2-VL-2B `imadityasarkar/satquery-phase2-vrsbench`** (VRSBench/RSVQA SFT continuing Stage-1 BigEarthNet); change/fusion stubbed until Stage-3 CDVQA.
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
            gr.Markdown("### Intelligence Result — bullets replace paragraph (3-6 bullets, chart below)")
            answer = gr.Markdown(label="Answer (bullets)", value="*Awaiting analysis — bullets will appear here*")
            confidence = gr.Number(label="Confidence (0–1)", precision=3)
            evidence = gr.Markdown(label="Evidence")
            # Chart — identical to React (bar/pie toggle, question-aware count/distribution)
            chart_type = gr.Radio(choices=["Bar", "Pie"], value="Bar", label="Chart type", info="Bar/Pie toggle")
            chart_plot = gr.Plot(label="Distribution")
            chart_state = gr.State(value={"data": [], "type": "distribution"})

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

    # Health helper — prefilled placeholder at startup (no GPU, no model load)
    # Real health (with model load) is on-demand via Refresh button inside ZeroGPU
    _health_prefilled: dict[str, Any] = {
        "status": "Space ready — click Refresh health or run a query",
        "compute": "zero-a10g (SATQUERY_FORCE_CPU=0)",
        "note": "Health with model load is on-demand to avoid No CUDA at startup",
        "adapter_path": "imadityasarkar/satquery-phase2-vrsbench",
        "specialists": {"vqa (real)": {"is_real": "pending — run a query or Refresh health"}},
    }

    @spaces.GPU(duration=30)
    def _health_gpu() -> dict[str, Any]:
        try:
            h = registry.health()
            # Add adapter info for quick debug
            try:
                from backend.models import vqa_specialist as _vqa
                h["_vqa_info"] = _vqa.get_model_info()
            except Exception:
                pass
            return h
        except Exception as e:
            import traceback
            return {"error": str(e), "traceback": traceback.format_exc()[:2000]}

    def _health_placeholder() -> dict[str, Any]:
        # No GPU, no model load — safe at startup
        return _health_prefilled

    def _update_chart(chart_state: Any, chart_type: str):  # type: ignore[no-untyped-def]
        return _chart_to_plot(chart_state or {"data": [], "type": "distribution"}, chart_type or "Bar")

    refresh_health.click(fn=_health_gpu, outputs=[health])
    # Initial health load — prefilled, no GPU quota cost
    demo.load(fn=_health_placeholder, outputs=[health])

    # Wire predict — queue required for @spaces.GPU; show status updates; identical bullets+charts
    run_btn.click(
        fn=predict,
        inputs=[query, input_mode, image_a, image_b],
        outputs=[answer, confidence, trace, evidence, chart_state],
        show_progress=True,
    ).then(fn=_update_chart, inputs=[chart_state, chart_type], outputs=[chart_plot])

    chart_type.change(fn=_update_chart, inputs=[chart_state, chart_type], outputs=[chart_plot])

    gr.Markdown(
        """
        ---
        **Local Docker (CPU-only, i5/16GB):** `make pitch-demo` or `SATQUERY_FORCE_CPU=1 uvicorn backend.main:app --port 8000` + `npm run dev` (`5173`). **HF Spaces Gradio ZeroGPU:** this `app.py` on `zero-a10g` with `SATQUERY_FORCE_CPU=0` (`Spaces → Settings → Variables`). See `docs/hf_spaces.md` (Docker) and `docs/hf_spaces_gradio.md` (ZeroGPU).
        If **Execute Analysis** does nothing, check `Spaces → Logs` for `Gradio startup health: deferred` and `Spaces → Settings → Hardware` is `zero-a10g`. First click cold-pulls ~4GB (30-60s), warm ~1.2s. Anon quota is 60s – `duration=60` fits.
        """
    )

    clear_btn.click(
        fn=lambda: (None, None, "", "single", "*Awaiting analysis — bullets will appear here*", 0.0, {}, "", {"data": [], "type": "distribution"}, None),
        inputs=None,
        outputs=[image_a, image_b, query, input_mode, answer, confidence, trace, evidence, chart_state, chart_plot],
    )

# Required for @spaces.GPU scheduling — without queue the GPU worker never drains and UI hangs
demo.queue(max_size=20)

if __name__ == "__main__":
    # HF Spaces injects GRADIO_SERVER_NAME/PORT; locally default 7860 for parity with Docker PORT
    port = int(os.getenv("PORT") or os.getenv("GRADIO_SERVER_PORT") or 7860)
    # theme/css are on Blocks (not launch) for compat with older launch() that rejects theme
    try:
        demo.launch(
            server_name="0.0.0.0",
            server_port=port,
            show_error=True,
        )
    except TypeError:
        # fallback for very old Gradio where show_error not supported
        demo.launch(
            server_name="0.0.0.0",
            server_port=port,
        )
