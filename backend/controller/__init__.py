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
    Band-count checks are best-effort via PIL mode/layers; when rasterio is
    installed and the input is GeoTIFF/TIFF, the true band count (dataset.count)
    is inspected via MemoryFile and logged/reported.
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
        raw_bytes: bytes | None = None
        try:
            if isinstance(data, (bytes, bytearray)):
                raw_bytes = bytes(data)
                pil = Image.open(io.BytesIO(raw_bytes))
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
                raw_bytes = bytes(raw) if isinstance(raw, (bytes, bytearray)) else None
                pil = Image.open(io.BytesIO(raw_bytes) if raw_bytes is not None else io.BytesIO(b""))
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
            # For GeoTIFF/TIFF, prefer rasterio's true band count when available
            rasterio_band_info: str | None = None
            if ext in (".tif", ".tiff") and raw_bytes is not None:
                try:
                    import rasterio  # type: ignore
                    from rasterio.io import MemoryFile  # type: ignore

                    with MemoryFile(raw_bytes) as mem:
                        with mem.open() as ds:
                            rasterio_band_info = (
                                f"rasterio bands={ds.count} dtype={ds.dtypes[0] if ds.dtypes else 'unknown'} "
                                f"size={ds.width}x{ds.height} crs={ds.crs}"
                            )
                            # Basic sanity: reject empty or absurd band counts
                            if ds.count == 0:
                                raise HTTPException(
                                    status_code=422,
                                    detail=f"Image {idx} ({filename}) has 0 bands — not a valid GeoTIFF",
                                )
                except HTTPException:
                    raise
                except ImportError:
                    logger.debug("rasterio not installed — skipping GeoTIFF band validation for image %d", idx)
                except Exception as e:
                    # rasterio failed to open (e.g. PNG mislabeled as .tif) — fall back to PIL info
                    logger.debug("rasterio open failed for image %d (%s): %s", idx, filename, e)

            band_info = rasterio_band_info or f"mode={pil.mode} size={pil.size}"
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

    # Question-aware counting: YOLO for count queries (charts = counts, not distribution)
    if any(k in q for k in ["how many", "count", "number of", "how much"]):
        return "count"

    # Single-image routing by query keywords
    if any(k in q for k in ["where", "locate", "bounding", "ground", "point", "coordinate"]):
        return "grounding"
    if any(k in q for k in ["change", "difference", "temporal"]):
        return "change_detection"
    if any(k in q for k in ["sar", "radar"]):
        return "optical_sar_fusion"

    # Default: VQA / captioning (stage 1 real adapter)
    if any(k in q for k in ["describe", "caption", "what", "is there", "are there", "land cover", "classify"]):
        return "vqa"
    return "vqa"


# --- Location resolution (search by place name) ---

def _resolve_location_to_images(
    images: list[Any],
    input_mode: str,
    location_query: str | None = None,
    coordinates: dict | None = None,
    location_query_2: str | None = None,
    coordinates_2: dict | None = None,
) -> tuple[list[Any], list[dict]]:
    """If images are missing but location is provided, fetch via Nominatim + Planetary Computer.

    Returns (image_payloads, imagery_metas). If images already present, returns them unchanged.
    Raises HTTPException on geocode/fetch failure.
    """
    if images:
        return images, []

    # Determine if location path was requested
    has_loc1 = bool((location_query and location_query.strip()) or coordinates)
    has_loc2 = bool((location_query_2 and location_query_2.strip()) or coordinates_2)

    if not has_loc1 and not has_loc2:
        return images, []

    # Lazy imports to avoid circular deps and keep optional deps soft
    from backend.services.geocode import geocode_place, parse_coordinates  # type: ignore
    from backend.services.imagery_fetch import fetch_imagery_for_location  # type: ignore

    locations: list[dict] = []

    def _resolve_one(lq: str | None, coords: dict | None) -> dict | None:
        if coords and isinstance(coords, dict) and "lat" in coords and "lon" in coords:
            try:
                lat = float(coords["lat"])
                lon = float(coords["lon"])
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    raise ValueError("lat/lon out of range")
                return {"lat": lat, "lon": lon, "display_name": f"{lat}, {lon}"}
            except Exception as e:
                raise HTTPException(status_code=422, detail=f"Invalid coordinates {coords}: {e}") from e
        if lq and lq.strip():
            # Handle direct lat,lon string via geocode's parse_coordinates
            parsed = parse_coordinates(lq)
            if parsed:
                return {"lat": parsed["lat"], "lon": parsed["lon"], "display_name": lq.strip()}
            return geocode_place(lq.strip())
        return None

    loc1 = _resolve_one(location_query, coordinates)
    if loc1:
        locations.append(loc1)

    loc2 = _resolve_one(location_query_2, coordinates_2)
    if loc2:
        locations.append(loc2)

    if not locations:
        raise HTTPException(status_code=422, detail="Location query provided but could not be resolved to coordinates")

    # Validate mode vs locations count (fetch will handle bi-temporal single-location -> 2 dates)
    # Don't error here; let fetch_imagery handle mode logic
    payloads, metas = fetch_imagery_for_location(locations, input_mode=input_mode)
    # Attach display names + lat/lon to metas for trace/preview (handle bi-temporal single-location -> 2 scenes)
    for i, meta in enumerate(metas):
        loc = locations[min(i, len(locations) - 1)] if locations else {}
        meta["display_name"] = meta.get("display_name") or loc.get("display_name")
        meta["lat"] = meta.get("lat") or loc.get("lat")
        meta["lon"] = meta.get("lon") or loc.get("lon")

    logger.info("Location resolution: %s -> %d images (mode=%s)", locations, len(payloads), input_mode)
    return payloads, metas


# --- Orchestration ---

def handle(
    query: str,
    images: list[Any],
    input_mode: str = "single",
    location_query: str | None = None,
    coordinates: dict | None = None,
    location_query_2: str | None = None,
    coordinates_2: dict | None = None,
) -> QueryResponse:
    """Main controller entrypoint — validates, classifies, routes, merges, traces.

    Called by API route handler. Never imports backend.models directly; goes via registry.
    If location_query/coordinates is present and images is not, resolves to images via
    geocode + Planetary Computer STAC, then falls through to existing pipeline unchanged.
    """
    t0 = time.time()
    logger.info(
        "Controller: query=%r mode=%s images=%d location_query=%r coordinates=%r",
        (query or "")[:80],
        input_mode,
        len(images) if images else 0,
        location_query,
        coordinates,
    )

    # 0. Location resolution (alternative to upload)
    imagery_metas: list[dict] = []
    if (not images or len(images) == 0) and (location_query or coordinates or location_query_2 or coordinates_2):
        images, imagery_metas = _resolve_location_to_images(
            images, input_mode, location_query, coordinates, location_query_2, coordinates_2
        )

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

    loc_params: dict[str, Any] = {}
    if imagery_metas:
        loc_params["location_resolved"] = True
        loc_params["location_metas"] = imagery_metas
        if location_query:
            loc_params["location_query"] = location_query
        if coordinates:
            loc_params["coordinates"] = coordinates
        if location_query_2:
            loc_params["location_query_2"] = location_query_2
        if coordinates_2:
            loc_params["coordinates_2"] = coordinates_2

    model_entry = ModelTraceEntry(
        name=model_label if isinstance(model_label, str) else specialist_name,
        role=task,
        parameters={
            "input_mode": input_mode,
            "image_count": len(pil_images),
            "adapter_path": config.ADAPTER_PATH,
            "base_model": config.BASE_MODEL,
            **loc_params,
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
            **loc_params,
        },
        confidence=confidence,
        evidence_refs=evidence_refs,
        total_latency_ms=total_latency,
    )

    # Structured bullets/chart from specialist (question-aware)
    structured = result.get("_structured")
    chart = result.get("_chart")
    chart_type_raw = result.get("_chart_type") or (structured.get("chart_type") if isinstance(structured, dict) else None)
    # Normalize to StructuredOutput shape
    structured_obj = None
    chart_list = None
    chart_type: str | None = None
    try:
        # Determine chart_type from specialist or task
        if isinstance(chart_type_raw, str) and chart_type_raw in ("distribution", "count", "change", "none"):
            chart_type = chart_type_raw
        elif task == "count":
            chart_type = "count"
        elif task in ("change_detection", "change"):
            chart_type = "change"
        elif task in ("vqa", "captioning", "visual_question_answering"):
            chart_type = "distribution"
        else:
            chart_type = None

        if isinstance(structured, dict) and (structured.get("bullets") or structured.get("chart")):
            from backend.schemas import ChartEntry, StructuredOutput

            bullets = [str(b) for b in structured.get("bullets", [])[:6]]
            chart_entries = []
            for c in structured.get("chart", [])[:5]:
                if isinstance(c, dict) and "label" in c and "value" in c:
                    try:
                        chart_entries.append(ChartEntry(label=str(c["label"]), value=float(c["value"])))
                    except Exception:
                        continue
            # Honor chart_type from structured if present
            if isinstance(structured.get("chart_type"), str):
                chart_type = structured.get("chart_type")
            structured_obj = StructuredOutput(bullets=bullets, chart=chart_entries, chart_type=chart_type)  # type: ignore
            chart_list = chart_entries
        elif isinstance(chart, list) and chart:
            from backend.schemas import ChartEntry, StructuredOutput

            chart_entries = []
            for c in chart[:5]:
                if isinstance(c, dict) and "label" in c and "value" in c:
                    try:
                        chart_entries.append(ChartEntry(label=str(c["label"]), value=float(c["value"])))
                    except Exception:
                        continue
            if chart_entries:
                structured_obj = StructuredOutput(bullets=[], chart=chart_entries, chart_type=chart_type)  # type: ignore
                chart_list = chart_entries
        # If structured still None but we have chart_type, create empty structured for type propagation
        if structured_obj is None and chart_type is not None:
            from backend.schemas import StructuredOutput

            structured_obj = StructuredOutput(bullets=[], chart=[], chart_type=chart_type)  # type: ignore
    except Exception as e:
        logger.warning("Structured parse failed: %s", e)

    # Build resolved image previews for location path (so frontend can show fetched imagery in viewer)
    resolved_previews = None
    if imagery_metas and pil_images:
        try:
            import base64

            resolved_previews = []
            for idx, pil in enumerate(pil_images):
                try:
                    # Thumb for preview payload (limit 512px to keep JSON <1MB)
                    thumb = pil.copy()
                    thumb.thumbnail((512, 512), Image.BILINEAR)
                    buf = io.BytesIO()
                    thumb.save(buf, format="PNG")
                    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                    data_url = f"data:image/png;base64,{b64}"
                except Exception:
                    data_url = None
                meta = imagery_metas[idx] if idx < len(imagery_metas) else {}
                resolved_previews.append(
                    {
                        "display_name": meta.get("display_name"),
                        "lat": meta.get("lat"),
                        "lon": meta.get("lon"),
                        "scene_id": meta.get("scene_id"),
                        "collection": meta.get("collection"),
                        "preview_b64": data_url,
                        "bbox": meta.get("bbox"),
                    }
                )
        except Exception as e:
            logger.debug("Failed to build resolved previews: %s", e)
            resolved_previews = None

    return QueryResponse(
        answer=answer,
        confidence=confidence,
        execution_trace=trace,
        evidence=evidence_refs,
        structured=structured_obj,
        chart=chart_list,
        chart_type=chart_type,  # type: ignore
        resolved_images=resolved_previews,  # type: ignore
    )
