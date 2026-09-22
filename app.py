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
from backend.satellite.models import RetrievalRequest  # for validation error messages

logger = logging.getLogger("satquery.gradio")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# Keep backend's CPU flag for Docker, but ZeroGPU needs GPU — override via env at Space runtime
# Space Variables should set SATQUERY_FORCE_CPU=0 (Docker local keeps 1 via Dockerfile:22)
# Also auto-detect ZeroGPU via SPACES_ZERO_GPU env (HF sets on zero-a10g)
if os.getenv("SPACES_ZERO_GPU") == "1":
    # On ZeroGPU, force GPU unless user explicitly set SATQUERY_FORCE_CPU=1
    if "SATQUERY_FORCE_CPU" not in os.environ:
        os.environ["SATQUERY_FORCE_CPU"] = "0"
        # Patch already-imported config and reset cached specialist loads so next predict loads on real CUDA
        # Both VQA and change (bi-temporal) must be reset — otherwise CPU-cached _load_attempted blocks GPU load inside @spaces.GPU worker
        try:
            app_config.FORCE_CPU = False  # type: ignore
            import backend.models.vqa as _vqa

            _vqa._load_attempted = False  # type: ignore
            _vqa._is_real = False  # type: ignore
            _vqa._load_error = None  # type: ignore
            import backend.models.change as _change

            _change._load_attempted = False  # type: ignore
            _change._is_real = False  # type: ignore
            _change._load_error = None  # type: ignore
            import backend.models.fusion as _fusion

            _fusion._load_attempted = False  # type: ignore
            _fusion._is_real = False  # type: ignore
            _fusion._load_error = None  # type: ignore
            # Also reset processor cache so tokenizer reloads on GPU worker if needed
            _change._processor = None  # type: ignore
            _vqa._processor = None  # type: ignore
            _fusion._processor = None  # type: ignore
        except Exception:
            pass

if os.getenv("SATQUERY_FORCE_CPU", "0").lower() in ("0", "false", "off", "no", ""):
    logger.info("Gradio Space: SATQUERY_FORCE_CPU=0 — ZeroGPU CUDA enabled")
else:
    logger.warning("Gradio Space: SATQUERY_FORCE_CPU still 1 — set Space Variable SATQUERY_FORCE_CPU=0 for ZeroGPU, else model stays on CPU")

# Warm registry health at startup — but NOT on ZeroGPU outside GPU worker (would cache CPU model)
# On ZeroGPU, health outside GPU would load model on emulated CUDA and cache as CPU, breaking real GPU fork
# Only skip when HF actually signals ZeroGPU; FORCE_CPU=0 alone (local dev default) should still warm health
_is_zerogpu = os.getenv("SPACES_ZERO_GPU") == "1"
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


# ── Live Satellite Search (CDSE STAC Sentinel-2 L2A) — no GPU needed ──
_PRESET_AOIS = {
    "Bengaluru": {"type": "Polygon", "coordinates": [[[77.45, 12.85], [77.75, 12.85], [77.75, 13.05], [77.45, 13.05], [77.45, 12.85]]]},
    "Delhi": {"type": "Polygon", "coordinates": [[[76.9, 28.4], [77.35, 28.4], [77.35, 28.85], [76.9, 28.85], [76.9, 28.4]]]},
    "Small AOI (1km)": {"type": "Polygon", "coordinates": [[[77.59, 12.97], [77.6, 12.97], [77.6, 12.98], [77.59, 12.98], [77.59, 12.97]]]},
}

def _preset_to_json(name: str) -> str:
    return json.dumps(_PRESET_AOIS.get(name, _PRESET_AOIS["Bengaluru"]), indent=2)


def satellite_search(
    geometry_text: str,
    start_date: str,
    end_date: str,
    max_cloud_cover: float,
    max_results: int,
    required_analysis: str,
) -> tuple[str, Any, Any, str, Any]:
    """Gradio handler for live CDSE Sentinel-2 L2A search — no GPU, direct agent call."""
    # Returns (status_md, scenes_json, trace_json, thumbs_html, selected_json)
    try:
        geom = json.loads(geometry_text) if geometry_text.strip() else None
    except Exception as e:
        return f"❌ Invalid GeoJSON: {e}", [], {}, "", None
    if not geom:
        return "❌ AOI geometry is required (GeoJSON Polygon). Choose a preset or paste GeoJSON.", [], {}, "", None
    if not start_date or not end_date:
        return "❌ Start and end dates are required (YYYY-MM-DD).", [], {}, "", None

    # Build params — mirrors frontend satelliteClient
    params: dict[str, Any] = {
        "sensor": "sentinel-2",
        "product": "l2a",
        "geometry": geom,
        "start_date": start_date.strip(),
        "end_date": end_date.strip(),
        "max_cloud_cover": float(max_cloud_cover),
        "max_results": int(max_results),
    }
    if required_analysis and required_analysis != "none":
        params["required_analysis"] = required_analysis
        # auto bands via model
        try:
            from backend.satellite.models import INDEX_REQUIRED_BANDS

            bands = INDEX_REQUIRED_BANDS.get(required_analysis.upper())
            if bands:
                params["required_bands"] = bands
        except Exception:
            pass

    # Validate via RetrievalRequest for nice errors (before network)
    try:
        _ = RetrievalRequest(**params)  # type: ignore[arg-type]
    except Exception as e:
        return f"❌ Validation error: {e}", [], {}, "", None

    try:
        from backend.satellite.agent import search_satellite_data

        result = search_satellite_data(params)
    except ValueError as e:
        return f"❌ Validation: {e}", [], {}, "", None
    except RuntimeError as e:
        logger.error("Satellite search provider error: %s", e)
        return "❌ Satellite data provider temporarily unavailable. Please try again in a moment.", [], {}, "", None
    except Exception as e:
        logger.exception("Satellite search failed: %s", e)
        return f"❌ Search failed: {e}", [], {}, "", None

    scenes = result.get("scenes", []) or []
    best = result.get("best_scene")
    trace = result.get("trace", {}) or {}

    if not scenes:
        status = "No Sentinel-2 scenes found for the requested AOI and date range. Try widening dates or increasing max cloud cover."
        return status, [], trace, "", None

    # Build scenes JSON serializable (Pydantic → dict via model_dump)
    scenes_json = []
    for s in scenes:
        try:
            d = s.model_dump(mode="json") if hasattr(s, "model_dump") else s.dict()  # type: ignore
            # Ensure datetime string
            if d.get("datetime"):
                d["datetime"] = str(d["datetime"])
            scenes_json.append(d)
        except Exception:
            scenes_json.append({"id": getattr(s, "id", "unknown"), "error": "serialize failed"})

    # Thumbnails HTML gallery (lightweight, no download)
    thumbs_parts = []
    for sc in scenes_json[:8]:
        thumb = sc.get("thumbnail")
        sid = sc.get("id", "")
        cloud = sc.get("cloud_cover")
        cov = sc.get("coverage")
        score = sc.get("selection_score")
        dt = sc.get("datetime", "")
        if thumb:
            thumbs_parts.append(
                f'<div style="display:inline-block;margin:4px;text-align:center;vertical-align:top;width:132px">'
                f'<img src="{thumb}" style="width:128px;height:128px;object-fit:cover;border-radius:6px;border:1px solid #334155" loading="lazy" onerror="this.style.display=\'none\'"/>'
                f'<div style="font-size:10px;color:#e2e8f0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:128px" title="{sid}">{sid[:22]}</div>'
                f'<div style="font-size:10px;color:#94a3b8">{str(dt)[:10]} · {cloud if cloud is not None else "—"}% cloud</div>'
                f'<div style="font-size:10px;color:#94a3b8">{cov if cov is not None else "—"}% cov · score {score if score is not None else "—"}</div>'
                f"</div>"
            )
        else:
            thumbs_parts.append(
                f'<div style="display:inline-block;margin:4px;width:128px;height:128px;border:1px dashed #334155;border-radius:6px;text-align:center;line-height:128px;font-size:10px;color:#64748b">no preview<br/><span title="{sid}">{sid[:12]}</span></div>'
            )
    thumbs_html = '<div style="display:flex;flex-wrap:wrap;gap:4px">' + "".join(thumbs_parts) + "</div>" if thumbs_parts else ""

    # Status markdown with best highlighted
    best_line = ""
    if best is not None:
        try:
            b = best.model_dump(mode="json") if hasattr(best, "model_dump") else best.dict()  # type: ignore
            best_line = f"**Best:** `{b.get('id')}` · {str(b.get('datetime'))[:16]} · cloud {b.get('cloud_cover')}% · coverage {b.get('coverage')}% · score {b.get('selection_score')}"
        except Exception:
            best_line = f"**Best:** `{getattr(best,'id','unknown')}`"
    status = f"✅ Found **{len(scenes)}** Sentinel-2 L2A scenes. {best_line}\n\nCDSE STAC `sentinel-2-l2a` · {trace.get('latency_ms','—')}ms · {trace.get('results_found','—')} ranked. Select a scene below for analysis → assets available for VQA/change/count (future: `retrieve_scene_assets`)."

    # Auto-select best for downstream
    selected = scenes_json[0] if scenes_json else None
    # Prefer actual best if ranked order is already best-first
    if best is not None:
        try:
            bid = best.id if hasattr(best, "id") else best.get("id")  # type: ignore
            for sj in scenes_json:
                if sj.get("id") == bid:
                    selected = sj
                    break
        except Exception:
            pass

    return status, scenes_json, trace, thumbs_html, selected


def _format_selected_scene(scene_json: Any) -> str:
    if not scene_json:
        return "*No scene selected.* Choose a result or run a search."
    try:
        sid = scene_json.get("id", "unknown")
        dt = scene_json.get("datetime", "—")
        plat = scene_json.get("platform", "—")
        cloud = scene_json.get("cloud_cover", "—")
        cov = scene_json.get("coverage", "—")
        score = scene_json.get("selection_score", "—")
        assets = scene_json.get("assets", {}) or {}
        thumb = scene_json.get("thumbnail", "")
        asset_list = ", ".join(list(assets.keys())[:8]) if assets else "—"
        thumb_md = f"![thumbnail]({thumb})" if thumb else "*No thumbnail*"
        return (
            f"**Selected Scene → Ready for Analysis**\n\n"
            f"`{sid}`\n\n"
            f"- **Datetime:** {dt} · **Platform:** {plat}\n"
            f"- **Cloud:** {cloud}% · **Coverage:** {cov}% · **Score:** {score}\n"
            f"- **Assets ({len(assets)}):** {asset_list}\n"
            f"- **Thumbnail:** {thumb_md}\n\n"
            f"> Assets are hrefs from CDSE STAC (no raster download in MVP). Future: `retrieve_scene_assets(scene_id, [B04,B08])` → AOI chip → VQA/change/count."
        )
    except Exception as e:
        return f"Selected scene parse error: {e}\n\n```json\n{json.dumps(scene_json, indent=2)[:2000]}\n```"


def _scenes_to_choices(scenes_json: Any) -> list[str]:
    if not scenes_json or not isinstance(scenes_json, list):
        return []
    return [s.get("id", f"scene-{i}") for i, s in enumerate(scenes_json) if isinstance(s, dict)]


def _pick_scene_by_id(scenes_json: Any, scene_id: str) -> Any:
    if not scenes_json or not scene_id:
        return None
    for s in scenes_json:
        if isinstance(s, dict) and s.get("id") == scene_id:
            return s
    return None


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
        is_change = data_type == "change"
        title = "Count" if is_count else "Change" if is_change else "Distribution"
        if chart_type.lower() == "pie":
            fmt = "%1.0f" if is_count else "%1.0f%%"
            # For change, pie with negative doesn't make sense — use absolute for pie
            pie_vals = [abs(v) for v in values] if is_change else values
            ax.pie(pie_vals, labels=labels, autopct=fmt, colors=colors[: len(values)], textprops={"color": "#e2e8f0", "fontsize": 8})
            ax.set_title(title + (" (YOLO)" if is_count else " (delta T2-T1)" if is_change else " (measured)"), color="#e2e8f0", fontsize=10)
        else:
            bars = ax.bar(labels, values, color=[ "#f43f5e" if is_change and v < 0 else colors[i % len(colors)] for i, v in enumerate(values)], edgecolor="#334155")
            if is_count:
                ymax = max(values) * 1.25 if values else 5
                ax.set_ylim(0, max(5, ymax))
                ax.set_ylabel("Count", color="#94a3b8", fontsize=8)
                for bar, v in zip(bars, values):
                    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1, f"{int(v)}", ha="center", va="bottom", color="#e2e8f0", fontsize=8)
            elif is_change:
                ax.set_ylim(-100, 100)
                ax.set_ylabel("Δ %", color="#94a3b8", fontsize=8)
                ax.axhline(0, color="#334155", linewidth=0.8)
                for bar, v in zip(bars, values):
                    y = v + (2 if v >= 0 else -4)
                    ax.text(bar.get_x() + bar.get_width() / 2, y, f"{v:+.0f}%", ha="center", va="bottom" if v>=0 else "top", color="#e2e8f0", fontsize=8)
            else:
                ax.set_ylim(0, 100)
                ax.set_ylabel("%", color="#94a3b8", fontsize=8)
                for bar, v in zip(bars, values):
                    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1, f"{v:.0f}%", ha="center", va="bottom", color="#e2e8f0", fontsize=8)
            ax.set_title(title + (" (YOLO)" if is_count else " (delta T2-T1)" if is_change else " (measured)"), color="#e2e8f0", fontsize=10)
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
        # Also surface specialist load error if model not ready (VQA / change / fusion)
        vqa_err = ""
        try:
            from backend.models import vqa_specialist as _vqa, change_specialist as _change, fusion_specialist as _fusion

            if mode == "bi-temporal":
                info = _change.get_model_info()
            elif mode == "optical-sar":
                info = _fusion.get_model_info()
            else:
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
    theme=gr.themes.Soft(
        font=[gr.themes.GoogleFont("Space Grotesk"), "ui-sans-serif", "system-ui"],
        font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "ui-monospace", "monospace"],
    ),
    css="""
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
        .gradio-container {max-width: 1280px !important; font-family: 'Inter', 'Space Grotesk', ui-sans-serif, system-ui, sans-serif !important}
        h1, h2, h3, .panel-label, .tag-muted {font-family: 'Space Grotesk', ui-sans-serif, system-ui, sans-serif !important; letter-spacing: -0.02em}
        .panel {border: 1px solid #2a3a4a; border-radius: 10px; background: #0f1b2a0a; padding: 12px}
        /* tighten markdown + json */
        .prose {font-family: 'Inter', sans-serif !important}
        code, pre {font-family: 'JetBrains Mono', ui-monospace, monospace !important}
        """,
) as demo:
    gr.Markdown(
        """
        # SatQuery AI — Agentic Vision-Language Assistant for Remote Sensing
        **Smart India Hackathon 2026** — Natural-language querying of single & paired satellite imagery (optical, SAR) with evidence-grounded answers and full `ExecutionTrace`. Stage-2 **VQA+grounding real QLoRA Qwen2-VL-2B `imadityasarkar/satquery-phase2-vrsbench`** (VRSBench/RSVQA SFT continuing Stage-1 BigEarthNet); Stage-3 **change real `imadityasarkar/cdvqa_change` bi-temporal**, fusion real · **Live Satellite Search (CDSE STAC Sentinel-2 L2A)** via `backend/satellite` (coverage + ranking heuristic) → **Select for Analysis** → same pipeline.
        > **ZeroGPU:** Blackwell `48GB large` via `@spaces.GPU(duration=60)` — ~1s vs `30s` CPU. **Docker local** (`make pitch-demo`, `SATQUERY_FORCE_CPU=1`) stays CPU-only for i5/16GB. **Satellite search needs no GPU** — live CDSE STAC `sentinel-2-l2a` with TTL 300s cache.
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

            # ── Live Satellite Search (CDSE STAC Sentinel-2 L2A) ──
            with gr.Accordion("Live Satellite Search — CDSE STAC Sentinel-2 L2A (no fake data)", open=False):
                gr.Markdown(
                    "Search live Sentinel-2 L2A from **CDSE STAC `https://stac.dataspace.copernicus.eu/v1`** · AOI + dates + cloud → ranked scenes → **Select for Analysis** → same VQA/change/count pipeline. No credentials, `pystac-client` → HTTP fallback, TTL 300s cache."
                )
                sat_preset = gr.Dropdown(
                    choices=list(_PRESET_AOIS.keys()),
                    value="Bengaluru",
                    label="AOI Preset",
                    info="Pick a preset to fill GeoJSON — or paste your own Polygon below",
                )
                sat_geometry = gr.Textbox(
                    label="AOI Geometry (GeoJSON Polygon EPSG:4326)",
                    value=_preset_to_json("Bengaluru"),
                    lines=6,
                    placeholder='{"type":"Polygon","coordinates":[[[lon,lat],...]]}',
                )
                with gr.Row():
                    sat_start = gr.Textbox(label="Start date (YYYY-MM-DD)", value="2026-06-01", placeholder="2026-06-01")
                    sat_end = gr.Textbox(label="End date (YYYY-MM-DD)", value="2026-06-30", placeholder="2026-06-30")
                with gr.Row():
                    sat_cloud = gr.Slider(minimum=0, maximum=100, value=20, step=1, label="Max cloud cover %")
                    sat_max_results = gr.Slider(minimum=1, maximum=20, value=10, step=1, label="Max results")
                sat_analysis = gr.Dropdown(
                    choices=["none", "NDVI", "NDWI", "NDBI"],
                    value="none",
                    label="Required analysis (future band-aware)",
                    info="NDVI→B04,B08 · NDWI→B03,B08 · NDBI→B08,B11 (retrieval stores required_bands)",
                )
                sat_search_btn = gr.Button("Search Sentinel-2 L2A (live CDSE)", variant="secondary")
                sat_status = gr.Markdown("")
                sat_thumbs = gr.HTML(label="Thumbnails (best-first)")
                sat_scenes = gr.JSON(label="Scenes (ranked, with coverage & selection_score)", value=[])
                sat_trace = gr.JSON(label="Retrieval Trace (CDSE STAC)", value={})
                # Selected scene for downstream
                sat_selected_state = gr.State(value=None)
                sat_scene_picker = gr.Dropdown(choices=[], value=None, label="Pick scene for analysis (or auto best)", visible=False)
                sat_select_btn = gr.Button("Select for Analysis", variant="primary", visible=False)
                sat_selected_md = gr.Markdown(value="*No scene selected — run a search first.*")
                # Keep raw scenes state for picker
                sat_scenes_state = gr.State(value=[])

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
        "change_adapter_path": "imadityasarkar/cdvqa_change",
        "fusion_adapter_path": "imadityasarkar/satquery-phase2-vrsbench",
        "specialists": {
            "vqa (real)": {"is_real": "pending — run a query or Refresh health"},
            "change_detection (real)": {"is_real": "pending — run a query or Refresh health"},
            "optical_sar_fusion (real)": {"is_real": "pending — run a query or Refresh health"},
        },
    }

    @spaces.GPU(duration=30)
    def _health_gpu() -> dict[str, Any]:
        try:
            h = registry.health()
            # Add adapter info for quick debug — VQA, change (bi-temporal) and fusion (optical-SAR)
            try:
                from backend.models import vqa_specialist as _vqa, change_specialist as _change, fusion_specialist as _fusion

                h["_vqa_info"] = _vqa.get_model_info()
                h["_change_info"] = _change.get_model_info()
                h["_fusion_info"] = _fusion.get_model_info()
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

    # ── Live Satellite Search wiring ──
    def _on_preset_change(preset: str):
        return _preset_to_json(preset)

    sat_preset.change(fn=_on_preset_change, inputs=[sat_preset], outputs=[sat_geometry])

    def _on_satellite_search(geom_text, s_date, e_date, cloud, max_res, analysis):
        status, scenes_json, trace_json, thumbs_html, selected = satellite_search(geom_text, s_date, e_date, cloud, max_res, analysis)
        # Build picker choices
        choices = _scenes_to_choices(scenes_json)
        # picker visible if we have scenes
        picker_update = gr.update(choices=choices, value=choices[0] if choices else None, visible=bool(choices))
        btn_update = gr.update(visible=bool(choices))
        selected_md = _format_selected_scene(selected)
        return status, scenes_json, trace_json, thumbs_html, selected, picker_update, btn_update, selected_md, scenes_json

    sat_search_btn.click(
        fn=_on_satellite_search,
        inputs=[sat_geometry, sat_start, sat_end, sat_cloud, sat_max_results, sat_analysis],
        outputs=[sat_status, sat_scenes, sat_trace, sat_thumbs, sat_selected_state, sat_scene_picker, sat_select_btn, sat_selected_md, sat_scenes_state],
        show_progress=True,
    )

    def _on_pick_scene(scene_id: str, scenes_state: Any):
        picked = _pick_scene_by_id(scenes_state, scene_id)
        md = _format_selected_scene(picked)
        return picked, md

    sat_scene_picker.change(fn=_on_pick_scene, inputs=[sat_scene_picker, sat_scenes_state], outputs=[sat_selected_state, sat_selected_md])

    def _on_select_for_analysis(selected_state: Any):
        md = _format_selected_scene(selected_state)
        # Also surface in main evidence area as quick hint
        return md

    sat_select_btn.click(fn=_on_select_for_analysis, inputs=[sat_selected_state], outputs=[sat_selected_md])

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

    def _clear_all():
        return (
            None,
            None,
            "",
            "single",
            "*Awaiting analysis — bullets will appear here*",
            0.0,
            {},
            "",
            {"data": [], "type": "distribution"},
            None,
            "",
            [],
            {},
            "",
            None,
            gr.update(choices=[], value=None, visible=False),
            gr.update(visible=False),
            "*No scene selected — run a search first.*",
            [],
        )

    clear_btn.click(
        fn=_clear_all,
        inputs=None,
        outputs=[
            image_a,
            image_b,
            query,
            input_mode,
            answer,
            confidence,
            trace,
            evidence,
            chart_state,
            chart_plot,
            sat_status,
            sat_scenes,
            sat_trace,
            sat_thumbs,
            sat_selected_state,
            sat_scene_picker,
            sat_select_btn,
            sat_selected_md,
            sat_scenes_state,
        ],
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
