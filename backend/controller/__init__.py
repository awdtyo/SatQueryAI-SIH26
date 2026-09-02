"""Agentic controller — task classification, input validation, routing.

Mandatory per AGENTS.md:
- Input modality checks are mandatory (format, band count, single/pair config)
- ExecutionTrace is first-class output (task, models, params, confidence)

Controller is the ONLY caller of registry.predict(); route handlers delegate here.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from PIL import Image
import io

from fastapi import HTTPException

from backend import config
from backend import registry
from backend.schemas import EvidenceRef, ExecutionTrace, ModelTraceEntry, QueryResponse

logger = logging.getLogger(__name__)

# --- Input validation ---

_ALLOWED_EXTS = config.SUPPORTED_FORMATS  # {".tif", ".tiff", ".png", ...}
_ALLOWED_MODES = config.SUPPORTED_INPUT_MODES

# Map extension -> friendly format name
_EXT_TO_FORMAT = {
    ".tif": "geotiff",
    ".tiff": "geotiff",
    ".png": "png",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
}


def _ext_of(filename: str | None) -> str:
    if not filename:
        return ""
    return Path(filename).suffix.lower()


def validate_inputs(images: list[Any], input_mode: str) -> list[Image.Image]:
    """Validate modality contract: format, count, mode consistency.

    Returns list[PIL.Image] (converted to RGB) or raises HTTPException(400/422).
    Band-count checks are best-effort via PIL mode/layers; full GeoTIFF
    band inspection requires rasterio (not mandatory for PNG/JPEG benchmarks).
    """
    if input_mode not in _ALLOWED_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported input_mode '{input_mode}'. Allowed: {sorted(_ALLOWED_MODES)}",
        )

    if not images:
        raise HTTPException(status_code=400, detail="At least one image is required")

    # Mode -> expected count
    expected: dict[str, int] = {"single": 1, "optical-sar": 2, "bi-temporal": 2}
    need = expected.get(input_mode, 1)
    if len(images) != need:
        raise HTTPException(
            status_code=422,
            detail=f"input_mode '{input_mode}' expects {need} image(s), got {len(images)}",
        )

    pil_images: list[Image.Image] = []
    for idx, item in enumerate(images):
        # item may be UploadFile.file (bytes) or (filename, bytes) tuple from API layer
        # Normalize to (filename, bytes)
        filename: str | None = None
        data: bytes | Image.Image | None = None

        if isinstance(item, Image.Image):
            pil_images.append(item.convert("RGB"))
            continue
        if isinstance(item, tuple) and len(item) == 2:
            filename, data = item  # type: ignore
        elif isinstance(item, dict) and "filename" in item:
            filename = item["filename"]
            data = item.get("data") or item.get("bytes")
        elif hasattr(item, "filename") and hasattr(item, "read"):
            # FastAPI UploadFile
            filename = getattr(item, "filename", None)
            data = item  # type: ignore
        else:
            # Raw bytes or unknown
            data = item  # type: ignore

        # Resolve format from filename
        ext = _ext_of(filename) if filename else ""
        # If filename missing extension, try to sniff from PIL
        if ext and ext not in _ALLOWED_EXTS:
            raise HTTPException(
                status_code=422,
                detail=f"Image {idx} has unsupported format '{ext}' (file: {filename}). Allowed: {sorted(_ALLOWED_EXTS)}",
            )

        # Load to PIL to validate it's actually an image and to get mode/bands
        try:
            if isinstance(data, (bytes, bytearray)):
                pil = Image.open(io.BytesIO(data))
            elif hasattr(data, "read"):
                # UploadFile — read bytes (may have been read already)
                # Try to seek to start if possible
                try:
                    data.seek(0)  # type: ignore
                except Exception:
                    pass
                raw = data.read()  # type: ignore
                if isinstance(raw, str):
                    raw = raw.encode()
                pil = Image.open(io.BytesIO(raw))
                # Restore for later use — caller may need fresh bytes
                try:
                    data.seek(0)  # type: ignore
                except Exception:
                    pass
            elif isinstance(data, Image.Image):
                pil = data
            else:
                raise ValueError(f"Cannot coerce image {idx} of type {type(data)} to PIL")

            # Force load to catch truncated files early
            pil.load()
            # Convert to RGB for model (handles L, RGBA, etc.)
            pil_rgb = pil.convert("RGB")
            pil_images.append(pil_rgb)

            # Band-count / mode logging (not rejecting, just validating)
            band_info = f"mode={pil.mode} size={pil.size}"
            logger.debug("Image %d (%s): %s", idx, filename or "unnamed", band_info)

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Image {idx} ({filename}) is not a valid image: {e}") from e

    return pil_images


# --- Task classification ---

def classify_task(query: str, input_mode: str) -> str:
    """Lightweight heuristic classifier — deterministic, no LLM call needed.

    In stage 1, everything except explicit change/grounding/fusion
    keywords routes to VQA/captioning (the only real adapter).
    Later stages can swap this for a learned classifier.
    """
    q = (query or "").lower()
    mode = input_mode.lower()

    # Mode-driven routing takes precedence
    if mode == "bi-temporal":
        # Bi-temporal is almost always change detection
        if any(k in q for k in ["change", "difference", "between", "before", "after", "temporal"]):
            return "change_detection"
        # Even vague queries on bi-temporal -> change (model will answer generically)
        return "change_detection"
    if mode == "optical-sar":
        if any(k in q for k in ["sar", "fusion", "radar", "optical"]):
            return "optical_sar_fusion"
        return "optical_sar_fusion"

    # Single-image routing by query keywords
    if any(k in q for k in ["where", "locate", "bounding", "ground", "point", "coordinate"]):
        return "grounding"
    if any(k in q for k in ["change", "difference", "temporal"]):
        return "change_detection"
    if any(k in q for k in ["sar", "radar"]):
        return "optical_sar_fusion"

    # Default: VQA / captioning (stage 1 real adapter)
    if any(k in q for k in ["describe", "caption", "what", "how many", "is there", "are there", "land cover", "classify"]):
        return "vqa"
    return "vqa"


# --- Orchestration ---

def handle(query: str, images: list[Any], input_mode: str = "single") -> QueryResponse:
    """Main controller entrypoint — validates, classifies, routes, merges, traces.

    Called by API route handler. Never imports backend.models directly; goes via registry.
    """
    t0 = time.time()
    logger.info("Controller: query=%r mode=%s images=%d", (query or "")[:80], input_mode, len(images) if images else 0)

    # 1. Validate
    pil_images = validate_inputs(images, input_mode)

    # 2. Classify
    task = classify_task(query, input_mode)
    logger.info("Controller: classified task=%s", task)

    # 3. Route to specialist via registry
    specialist = registry.get_specialist(task)
    specialist_name = getattr(specialist, "__name__", str(specialist))
    # Derive a friendly model name for the trace
    try:
        model_info = specialist.get_model_info()  # type: ignore
        model_label = model_info.get("adapter_path") or model_info.get("base_model") or specialist_name
        is_real = bool(model_info.get("is_real", False))
        is_stub = bool(model_info.get("stub", False))
    except Exception:
        model_label = specialist_name
        is_real = False
        is_stub = True

    # 4. Invoke specialist
    invoke_start = time.time()
    try:
        result = registry.predict(pil_images, query, task)
    except Exception as e:
        # Specialist failed — do not crash server; return a traced error answer
        logger.error("Specialist %s failed: %s", task, e, exc_info=True)
        result = {
            "answer": f"Specialist '{task}' failed: {e}",
            "evidence": [],
            "confidence": 0.0,
            "_latency_ms": int((time.time() - invoke_start) * 1000),
            "_error": str(e),
        }
        is_stub = True

    latency_ms = int((time.time() - invoke_start) * 1000)
    answer = str(result.get("answer", ""))
    confidence = float(result.get("confidence", 0.5))
    # Clamp confidence
    confidence = max(0.0, min(1.0, confidence))
    evidence_raw = result.get("evidence", [])
    # Prefer explicit _latency_ms from specialist if present
    if "_latency_ms" in result:
        latency_ms = int(result["_latency_ms"])

    total_latency = int((time.time() - t0) * 1000)

    # 5. Build execution trace
    evidence_refs: list[EvidenceRef] = []
    for ev in evidence_raw:
        try:
            evidence_refs.append(EvidenceRef(**ev))
        except Exception:
            # Be permissive — skip malformed evidence rather than failing the whole response
            logger.warning("Skipping malformed evidence: %r", ev)

    model_entry = ModelTraceEntry(
        name=model_label if isinstance(model_label, str) else specialist_name,
        role=task,
        parameters={
            "input_mode": input_mode,
            "image_count": len(pil_images),
            "adapter_path": config.ADAPTER_PATH,
            "base_model": config.BASE_MODEL,
        },
        latency_ms=latency_ms,
        is_real=is_real and not bool(result.get("_stub", False)),
        is_stub=bool(result.get("_stub", False)) or is_stub,
    )

    trace = ExecutionTrace(
        task=task,
        models_used=[model_entry],
        parameters={
            "input_mode": input_mode,
            "image_count": len(pil_images),
            "band_subset": "RGB",  # placeholder — real pipeline would report actual bands
            "spatial_resolution_m": 10,
        },
        confidence=confidence,
        evidence_refs=evidence_refs,
        total_latency_ms=total_latency,
    )

    return QueryResponse(
        answer=answer,
        confidence=confidence,
        execution_trace=trace,
        evidence=evidence_refs,
    )
