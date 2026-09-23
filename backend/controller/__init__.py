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

# Retrieval keywords — triggers satellite_retrieval agent (Step 8)
_RETRIEVAL_KEYWORDS = [
    "find sentinel", "sentinel-2", "sentinel 2", "sentinel-1", "sentinel 1",
    "find satellite", "satellite imagery", "satellite image", "find imagery",
    "best satellite", "retrieve scene", "search scene", "get the best",
    "aoi", "area of interest",
]

def _is_retrieval_query(q: str) -> bool:
    ql = q.lower()
    # Explicit retrieval intent phrases
    if any(k in ql for k in _RETRIEVAL_KEYWORDS):
        # Must also hint at finding/searching or temporal/cloud filters to avoid false positives on VQA with sentinel mention
        if any(w in ql for w in ["find", "search", "retrieve", "get", "best", "less than", "cloud", "from", "between", "june", "july", "202", "vegetation analysis", "suitable for"]):
            return True
        # Short sentinel-only query still qualifies as retrieval for explicit tests
        if "sentinel" in ql and any(w in ql for w in ["find", "sentinel"]):
            return True
    # Fallback: "find ... imagery" without sentinel explicitly
    if "find" in ql and "imagery" in ql:
        return True
    return False


# Spectral index keywords — triggers spectral_index agent
_SPECTRAL_KEYWORDS = [
    "ndvi", "ndwi", "ndbi", "ndmi", "savi", "bsi",
    "vegetation health", "vegetation index", "show vegetation",
    "water index", "built-up", "built up", "moisture", "bare soil",
]

def _is_spectral_query(q: str) -> bool:
    ql = q.lower()
    # Explicit index names
    if any(k in ql for k in ["ndvi", "ndwi", "ndbi", "ndmi", "savi", "bsi"]):
        return True
    # Phrases that imply index calculation
    if any(k in ql for k in _SPECTRAL_KEYWORDS):
        if any(w in ql for w in ["calculate", "show", "find", "display", "compute", "index", "health", "vegetation", "water", "soil", "moisture", "built"]):
            return True
    # Compare NDVI between dates
    if "compare" in ql and "ndvi" in ql:
        return True
    return False


def parse_spectral_params(query: str) -> dict[str, Any]:
    """Extract index name from NL query for spectral routing."""
    q = query.lower()
    # Direct
    for cand in ["ndvi", "ndwi", "ndbi", "ndmi", "savi", "bsi"]:
        if cand in q:
            return {"index": cand.upper(), "intent": "spectral_index"}
    if "vegetation" in q or "veg " in f" {q} ":
        return {"index": "NDVI", "intent": "spectral_index"}
    if "water" in q and ("index" in q or "bodies" in q or "body" in q or "how much" in q or "% water" in q or "water present" in q):
        return {"index": "NDWI", "intent": "spectral_index"}
    if "built" in q or "urban" in q:
        return {"index": "NDBI", "intent": "spectral_index"}
    if "moisture" in q:
        return {"index": "NDMI", "intent": "spectral_index"}
    if "bare soil" in q:
        return {"index": "BSI", "intent": "spectral_index"}
    if "soil" in q:
        return {"index": "SAVI", "intent": "spectral_index"}
    return {"index": "NDVI", "intent": "spectral_index"}


def parse_retrieval_params(query: str) -> dict[str, Any]:
    """
    Lightweight structured param extractor for retrieval queries.
    Returns dict suitable for RetrievalRequest partial (sensor/product/dates/cloud).
    Never builds STAC URLs — just extracts fields.
    """
    import re

    q = query.lower()
    params: dict[str, Any] = {}
    # sensor
    if "sentinel-1" in q or "sentinel 1" in q:
        params["sensor"] = "sentinel-1"
        params["product"] = "l1"
    elif "sentinel-2" in q or "sentinel 2" in q or "sentinel" in q:
        params["sensor"] = "sentinel-2"
        params["product"] = "l2a"
    elif "landsat" in q:
        params["sensor"] = "landsat"
        params["product"] = "l2"
    else:
        params["sensor"] = "sentinel-2"
        params["product"] = "l2a"

    # cloud cover: "less than 10% cloud" / "max 20%" / "<10% cloud"
    m = re.search(r"(?:less than|max(?:imum)?|<\s*)\s*(\d{1,3})\s*%?\s*cloud", q)
    if m:
        try:
            params["max_cloud_cover"] = float(m.group(1))
        except Exception:
            pass
    else:
        m2 = re.search(r"cloud.*?(\d{1,2})\s*%", q)
        if m2:
            try:
                params["max_cloud_cover"] = float(m2.group(1))
            except Exception:
                pass

    # date range: "between June 1 and June 30" / "from 2026-06-01 to 2026-06-30" / "June 2026" / "2026-06"
    # Try ISO dates first
    iso_dates = re.findall(r"20\d{2}-\d{2}-\d{2}", query)
    if len(iso_dates) >= 2:
        params["start_date"] = iso_dates[0]
        params["end_date"] = iso_dates[1]
    elif len(iso_dates) == 1:
        params["start_date"] = iso_dates[0]
        params["end_date"] = iso_dates[0]
    else:
        # Month-year heuristic: "June 2026"
        months = {"january": "01", "february": "02", "march": "03", "april": "04", "may": "05", "june": "06", "july": "07", "august": "08", "september": "09", "october": "10", "november": "11", "december": "12"}
        for name, num in months.items():
            if name in q:
                # find year
                ym = re.search(r"20\d{2}", q)
                year = ym.group(0) if ym else "2026"
                # try to find day range
                dm = re.findall(rf"{name}\s*(\d{{1,2}})", q)
                if len(dm) >= 2:
                    d1, d2 = dm[0].zfill(2), dm[1].zfill(2)
                    params["start_date"] = f"{year}-{num}-{d1}"
                    params["end_date"] = f"{year}-{num}-{d2}"
                else:
                    # whole month
                    import calendar

                    last = calendar.monthrange(int(year), int(num))[1]
                    params["start_date"] = f"{year}-{num}-01"
                    params["end_date"] = f"{year}-{num}-{last:02d}"
                break

    # intent marker
    params["intent"] = "satellite_retrieval"
    return params


def classify_task(query: str, input_mode: str) -> str:
    """Lightweight heuristic classifier — deterministic, no LLM call needed.

    In stage 1, everything except explicit change/grounding/fusion
    keywords routes to VQA/captioning (the only real adapter).
    Later stages can swap this for a learned classifier.
    """
    q = (query or "").lower()
    mode = input_mode.lower()

    # Spectral index takes precedence for explicit index queries
    if _is_spectral_query(query):
        return "spectral_index"

    # Satellite retrieval takes precedence for explicit NL requests (Step 8)
    # Only when query clearly asks to FIND/SEARCH imagery — not generic VQA
    if _is_retrieval_query(query):
        return "satellite_retrieval"

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


# --- Selected Satellite Image Query Mode: scene-aware routing ---

def _classify_scene_query(query: str, base_task: str, scene: dict[str, Any] | None, aoi: dict[str, Any] | None) -> str:
    """Reroute quantitative cover/water/built queries when a scene is ACTIVE.

    Selected Satellite Image Query Mode: asking "How much vegetation?", "Are there
    water bodies?" or "% built-up" about a selected scene is a real raster question,
    so it routes to the spectral-index agent (real band math) instead of a VQA model
    hallucinating numbers. Plain uploaded-image VQA is untouched (scene is None).
    """
    if not scene:
        return base_task
    q = query.lower()
    # Explicit index / retrieval intents keep their routing
    if base_task in ("spectral_index", "satellite_retrieval"):
        return base_task

    quant = ["how much", "how many", "%", "percent", "amount", "area", "coverage", "present", "there", "calculate", "index"]
    if ("vegetation" in q or f"veg " in f" {q} ") and any(w in q for w in quant):
        return "spectral_index"
    if "water" in q and any(w in q for w in ["bodies", "body", *quant]):
        return "spectral_index"
    if ("built-up" in q or "built up" in q or "builtup" in q or "urban" in q) and any(w in q for w in ["how much", "how many", "%", "percent", "area", "cover", "calculate"]):
        return "spectral_index"
    if "bare soil" in q or ("soil" in q and "bare" in q):
        if any(w in q for w in ["%", "how much", "area", "there"]):
            return "spectral_index"
    return base_task


def _scene_ctx(scene: dict[str, Any] | Any, aoi: dict[str, Any] | None = None, source: str | None = None) -> dict[str, Any]:
    """Flatten a scene (dict or SatelliteScene) into a small context dict for the trace."""
    if isinstance(scene, dict):
        scene_id = str(scene.get("id") or scene.get("scene_id") or "unknown")
        collection = str(scene.get("collection") or "sentinel-2-l2a")
        dt = scene.get("datetime")
        platform = scene.get("platform")
        cloud = scene.get("cloud_cover")
        bbox = scene.get("bbox")
        thumb = scene.get("thumbnail")
    else:
        scene_id = str(getattr(scene, "id", "unknown"))
        collection = str(getattr(scene, "collection", "sentinel-2-l2a"))
        dt = getattr(scene, "datetime", None)
        platform = getattr(scene, "platform", None)
        cloud = getattr(scene, "cloud_cover", None)
        bbox = getattr(scene, "bbox", None)
        thumb = getattr(scene, "thumbnail", None)
    out: dict[str, Any] = {
        "scene_id": scene_id,
        "collection": collection,
        "datetime": str(dt) if dt else None,
        "platform": platform,
        "cloud_cover": cloud,
        "bbox": bbox,
        "thumbnail": thumb,
    }
    if aoi:
        out["aoi"] = aoi
    if source:
        out["analysis_source"] = source
    return out


def _build_structured(result: dict[str, Any], task: str) -> tuple[Any, list[Any] | None, str | None]:
    """Extract StructuredOutput/ChartEntry from a specialist result (shared by all paths)."""
    from backend.schemas import ChartEntry, StructuredOutput

    structured = result.get("_structured")
    chart = result.get("_chart")
    chart_type_raw = result.get("_chart_type") or (structured.get("chart_type") if isinstance(structured, dict) else None)
    structured_obj: StructuredOutput | None = None
    chart_list: list[ChartEntry] | None = None
    chart_type: str | None = None
    try:
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
            bullets = [str(b) for b in structured.get("bullets", [])[:6]]
            chart_entries: list[ChartEntry] = []
            for c in structured.get("chart", [])[:5]:
                if isinstance(c, dict) and "label" in c and "value" in c:
                    try:
                        chart_entries.append(ChartEntry(label=str(c["label"]), value=float(c["value"])))
                    except Exception:
                        continue
            if isinstance(structured.get("chart_type"), str):
                chart_type = structured.get("chart_type")
            structured_obj = StructuredOutput(bullets=bullets, chart=chart_entries, chart_type=chart_type)  # type: ignore
            chart_list = chart_entries
        elif isinstance(chart, list) and chart:
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
            structured_obj = StructuredOutput(bullets=[], chart=[], chart_type=chart_type)  # type: ignore
    except Exception as e:
        logger.warning("Structured parse failed: %s", e)
    return structured_obj, chart_list, chart_type  # type: ignore


# --- Orchestration ---

def handle(query: str, images: list[Any], input_mode: str = "single", retrieval_geometry: dict[str, Any] | None = None, retrieval_params: dict[str, Any] | None = None, scene: dict[str, Any] | None = None, aoi: dict[str, Any] | None = None) -> QueryResponse:
    """Main controller entrypoint — validates, classifies, routes, merges, traces.

    Called by API route handler. Never imports backend.models directly; goes via registry.
    For satellite_retrieval, images are optional if retrieval_geometry is provided.
    For selected-satellite-image mode, an active `scene` (SatelliteScene dict) replaces
    uploaded images: NL queries are analyzed against that scene's real band assets.
    """
    t0 = time.time()
    logger.info("Controller: query=%r mode=%s images=%d scene=%s", (query or "")[:80], input_mode, len(images) if images else 0, "yes" if scene else "no")

    # 2. Classify first (needed to decide if validation can be skipped for retrieval)
    task = classify_task(query, input_mode)
    # Scene-aware rerouting — quantitative cover/water/built NL on an ACTIVE scene -> spectral
    task = _classify_scene_query(query, task, scene, aoi)
    logger.info("Controller: classified task=%s", task)

    # Satellite retrieval path — no image validation required, needs AOI
    if task == "satellite_retrieval":
        # Try to build structured params from query if not provided
        structured = retrieval_params or parse_retrieval_params(query)
        # If geometry supplied via extra arg, inject
        if retrieval_geometry and "geometry" not in structured:
            structured["geometry"] = retrieval_geometry
        elif retrieval_geometry:
            structured["geometry"] = retrieval_geometry
        # If still no geometry, we cannot search — return graceful trace
        if "geometry" not in structured or not structured.get("geometry"):
            # Fallback: ask user for AOI
            total_latency = int((time.time() - t0) * 1000)
            trace = ExecutionTrace(
                task=task,
                models_used=[
                    ModelTraceEntry(
                        name="CDSE STAC API",
                        role=task,
                        parameters={"input_mode": input_mode, "error": "missing AOI geometry"},
                        latency_ms=0,
                        is_real=True,
                        is_stub=False,
                    )
                ],
                parameters={"input_mode": input_mode, "image_count": 0, "band_subset": "sentinel-2-l2a", "spatial_resolution_m": 10},
                confidence=0.35,
                evidence_refs=[],
                total_latency_ms=total_latency,
            )
            return QueryResponse(
                answer="To retrieve satellite imagery, please provide an AOI (GeoJSON Polygon) and a date range. Example: `Find Sentinel-2 imagery for this region from 2026-06-01 to 2026-06-30 with <20% cloud.`",
                confidence=0.35,
                execution_trace=trace,
                evidence=[],
                structured=None,
                chart=None,
                chart_type=None,
            )
        # Inject images-pil placeholder for trace image_count =0
        pil_images: list[Any] = []
        # Route to satellite agent via registry
        specialist = registry.get_specialist(task)
        specialist_name = getattr(specialist, "__name__", str(specialist))
        try:
            model_info = specialist.get_model_info()  # type: ignore
            model_label = model_info.get("adapter_path") or model_info.get("base_model") or specialist_name
            is_real = bool(model_info.get("is_real", False))
            is_stub = bool(model_info.get("stub", False))
        except Exception:
            model_label = specialist_name
            is_real = True
            is_stub = False

        invoke_start = time.time()
        try:
            # Pass structured JSON as query to agent's predict
            import json as _json

            agent_query = _json.dumps(structured)
            result = registry.predict([], agent_query, task)
        except Exception as e:
            logger.error("Satellite retrieval failed: %s", e, exc_info=True)
            result = {"answer": f"Satellite retrieval failed: {e}", "evidence": [], "confidence": 0.0, "_latency_ms": int((time.time() - invoke_start) * 1000), "_error": str(e)}
            is_stub = True

        latency_ms = int(result.get("_latency_ms", int((time.time() - invoke_start) * 1000)))
        answer = str(result.get("answer", ""))
        confidence = float(result.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
        evidence_raw = result.get("evidence", [])
        total_latency = int((time.time() - t0) * 1000)
        evidence_refs: list[EvidenceRef] = []
        for ev in evidence_raw:
            try:
                evidence_refs.append(EvidenceRef(**ev))
            except Exception:
                logger.warning("Skipping malformed evidence: %r", ev)
        # Merge satellite trace if present
        sat_trace = result.get("_satellite", {}).get("trace") if isinstance(result.get("_satellite"), dict) else None
        model_entry = ModelTraceEntry(
            name=model_label if isinstance(model_label, str) else specialist_name,
            role=task,
            parameters={
                "input_mode": input_mode,
                "image_count": 0,
                "collection": sat_trace.get("collection") if sat_trace else "sentinel-2-l2a",
                "provider": "CDSE",
                "results_found": sat_trace.get("results_found", 0) if sat_trace else 0,
                "selected_scene": sat_trace.get("selected_scene") if sat_trace else None,
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
                "image_count": 0,
                "band_subset": "sentinel-2-l2a",
                "spatial_resolution_m": 10,
                "satellite_retrieval": structured,
            },
            confidence=confidence,
            evidence_refs=evidence_refs,
            total_latency_ms=total_latency,
        )
        # Structured for retrieval: we can pass trace as structured for UI
        from backend.schemas import StructuredOutput

        structured_obj = StructuredOutput(bullets=[], chart=[], chart_type=None)
        return QueryResponse(
            answer=answer,
            confidence=confidence,
            execution_trace=trace,
            evidence=evidence_refs,
            structured=structured_obj,
            chart=None,
            chart_type=None,
        )

    # Spectral-index path — no image validation, needs scene + AOI
    if task == "spectral_index":
        # Retrieve index and scene from params or query
        spec_params = dict(retrieval_params or {})
        # Merge active-scene context (Selected Satellite Image Query Mode)
        if scene:
            spec_params.setdefault("scene", scene)
        if aoi:
            spec_params.setdefault("aoi", aoi)
        # Try to parse index from query if not in params
        parsed = parse_spectral_params(query)
        index = spec_params.get("index") or spec_params.get("spectral_index") or parsed.get("index") or "NDVI"
        scene = spec_params.get("scene") or spec_params.get("scene_id") or spec_params.get("satellite_scene")
        aoi = spec_params.get("aoi") or spec_params.get("geometry") or retrieval_geometry
        # If still missing scene/AOI, return instructional
        if not scene or not aoi:
            total_latency = int((time.time() - t0) * 1000)
            trace = ExecutionTrace(
                task=task,
                models_used=[
                    ModelTraceEntry(
                        name="Spectral Index Agent",
                        role=task,
                        parameters={"index": index, "error": "missing scene or AOI"},
                        latency_ms=0,
                        is_real=True,
                        is_stub=False,
                    )
                ],
                parameters={"input_mode": input_mode, "image_count": 0, "index": index},
                confidence=0.35,
                evidence_refs=[],
                total_latency_ms=total_latency,
            )
            return QueryResponse(
                answer=f"To calculate {index}, please select a Sentinel-2 scene and draw an AOI. Example: `Calculate NDVI for the selected scene.` (scene + AOI required)",
                confidence=0.35,
                execution_trace=trace,
                evidence=[],
                structured=None,
                chart=None,
                chart_type=None,
                scene_context=_scene_ctx(scene, aoi=aoi) if scene else None,
                analysis={"type": "spectral_error", "index": index, "error": "missing scene or AOI"},
            )
        # Route to spectral agent
        specialist = registry.get_specialist(task)
        specialist_name = getattr(specialist, "__name__", str(specialist))
        try:
            model_info = specialist.get_model_info()  # type: ignore
            model_label = model_info.get("adapter_path") or model_info.get("base_model") or specialist_name
            is_real = bool(model_info.get("is_real", False))
            is_stub = bool(model_info.get("stub", False))
        except Exception:
            model_label = specialist_name
            is_real = True
            is_stub = False
        invoke_start = time.time()
        try:
            import json as _json

            # Pass full scene + AOI + index as JSON query to agent
            agent_query = _json.dumps({"index": index, "scene": scene, "aoi": aoi, "cloud_mask": spec_params.get("cloud_mask", True)})
            result = registry.predict([], agent_query, task)
        except Exception as e:
            logger.error("Spectral agent failed: %s", e, exc_info=True)
            result = {"answer": f"Spectral processing failed for {index}: {e}", "evidence": [], "confidence": 0.0, "_latency_ms": int((time.time() - invoke_start) * 1000), "_error": str(e)}
            is_stub = True
        latency_ms = int(result.get("_latency_ms", int((time.time() - invoke_start) * 1000)))
        answer = str(result.get("answer", ""))
        confidence = float(result.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
        evidence_raw = result.get("evidence", [])
        total_latency = int((time.time() - t0) * 1000)
        evidence_refs: list[EvidenceRef] = []
        for ev in evidence_raw:
            try:
                evidence_refs.append(EvidenceRef(**ev))
            except Exception:
                logger.warning("Skipping malformed evidence: %r", ev)
        # Include spectral trace if present
        spec_data = result.get("_spectral", {}) if isinstance(result.get("_spectral"), dict) else {}
        model_entry = ModelTraceEntry(
            name=model_label if isinstance(model_label, str) else specialist_name,
            role=task,
            parameters={
                "input_mode": input_mode,
                "image_count": 0,
                "index": index,
                "scene_id": spec_data.get("scene_id", str(scene)[:80] if isinstance(scene, str) else getattr(scene, "get", lambda *a, **k: None)("id", "unknown")),
                "required_bands": spec_data.get("required_bands", []),
                "cloud_applied": spec_data.get("cloud_applied", False),
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
                "image_count": 0,
                "index": index,
                "aoi": aoi,
                "spectral": spec_data,
            },
            confidence=confidence,
            evidence_refs=evidence_refs,
            total_latency_ms=total_latency,
        )
        from backend.schemas import StructuredOutput

        structured_obj = StructuredOutput(bullets=[], chart=[], chart_type=None)
        return QueryResponse(
            answer=answer,
            confidence=confidence,
            execution_trace=trace,
            evidence=evidence_refs,
            structured=structured_obj,
            chart=None,
            chart_type=None,
            scene_context=_scene_ctx(scene, aoi=aoi, source="bands"),
            analysis={**spec_data, "type": "spectral_index"},
        )

    # Selected Satellite Image Query Mode — analysis against a live scene's real assets.
    # No uploaded images required: the active scene (from the satellite search) is the input.
    if scene and not images:
        return _handle_active_scene(
            query=query, task=task, input_mode=input_mode, scene=scene, aoi=aoi, t0=t0
        )

    # 1. Validate (non-retrieval path)
    pil_images = validate_inputs(images, input_mode)

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

    # Structured bullets/chart from specialist (question-aware)
    structured_obj, chart_list, chart_type = _build_structured(result, task)

    return QueryResponse(
        answer=answer,
        confidence=confidence,
        execution_trace=trace,
        evidence=evidence_refs,
        structured=structured_obj,
        chart=chart_list,
        chart_type=chart_type,  # type: ignore
    )


def _handle_active_scene(
    query: str,
    task: str,
    input_mode: str,
    scene: dict[str, Any],
    aoi: dict[str, Any] | None,
    t0: float,
) -> QueryResponse:
    """Analyze the SELECTED satellite scene (Selected Satellite Image Query Mode).

    Resolves a real RGB composite from the scene's band assets (B04/B03/B02,
    AOI-clipped) or falls back to the scene preview thumbnail, then routes to the
    specialist with that image. The response carries an explicit `scene_context`
    so the trace/provenance clearly records WHICH scene was analyzed.
    """
    from backend.scene.raster import resolve_scene_rgb

    # Scene-based analysis is single-image only; change/fusion need uploaded pairs.
    if task in ("change_detection", "change", "optical_sar_fusion", "fusion"):
        total_latency = int((time.time() - t0) * 1000)
        trace = ExecutionTrace(
            task=task,
            models_used=[
                ModelTraceEntry(
                    name="Active Scene Router",
                    role="scene_analysis",
                    parameters={"error": "change/fusion require bi-temporal or optical-sar image pairs"},
                    latency_ms=0,
                    is_real=True,
                    is_stub=False,
                )
            ],
            parameters={"input_mode": input_mode, "image_count": 1, "scene_context": _scene_ctx(scene, aoi=aoi)},
            confidence=0.35,
            evidence_refs=[],
            total_latency_ms=total_latency,
        )
        return QueryResponse(
            answer=f"Change detection / SAR fusion needs an image pair. Upload the T1/T2 (or optical+SAR) images, or ask a single-scene question about this active scene (e.g. describe, count, or a spectral index).",
            confidence=0.35,
            execution_trace=trace,
            evidence=[],
            structured=None,
            chart=None,
            chart_type=None,
            scene_context=_scene_ctx(scene, aoi=aoi),
            analysis=None,
        )

    # Resolve a real analysis image from the active scene's assets.
    resolve_start = time.time()
    try:
        resolved = resolve_scene_rgb(scene, aoi=aoi)
    except Exception as e:
        err_str = str(e)
        # Distinguish missing AOI vs. band download failure (s3://) for actionable message
        has_aoi = bool(aoi and isinstance(aoi, dict) and aoi.get("type"))
        if "No AOI drawn" in err_str or "no preview/thumbnail" in err_str.lower():
            hint = "Draw an AOI polygon on the map for the active scene to analyze its real band data."
        elif "s3://" in err_str or "No connection adapters" in err_str or "Failed to download band" in err_str:
            hint = "This scene's band assets are stored as s3:// (CDSE) without an HTTPS alternate and could not be downloaded from this environment. Try another scene from the search results, or use the preview thumbnail — VQA/count will still work on thumbnail when bands are unavailable. For spectral indices (NDVI etc.), select a scene that exposes https:// assets."
        elif not has_aoi:
            hint = "Draw an AOI polygon on the map for the active scene to analyze its real band data."
        else:
            hint = "Try a different scene or redraw the AOI (smaller area) and retry. If the issue persists, the scene's assets may be temporarily unavailable from CDSE."
        logger.warning("Active scene resolution failed for %s: %s", _scene_ctx(scene)["scene_id"], e)
        total_latency = int((time.time() - t0) * 1000)
        trace = ExecutionTrace(
            task=task,
            models_used=[
                ModelTraceEntry(
                    name="Active Scene Resolver",
                    role="scene_asset_resolution",
                    parameters={"error": err_str},
                    latency_ms=int((time.time() - resolve_start) * 1000),
                    is_real=True,
                    is_stub=False,
                )
            ],
            parameters={"input_mode": input_mode, "image_count": 1, "scene_context": _scene_ctx(scene, aoi=aoi)},
            confidence=0.3,
            evidence_refs=[],
            total_latency_ms=total_latency,
        )
        return QueryResponse(
            answer=f"{e}\n\n{hint}",
            confidence=0.3,
            execution_trace=trace,
            evidence=[],
            structured=None,
            chart=None,
            chart_type=None,
            scene_context=_scene_ctx(scene, aoi=aoi),
            analysis={"type": "active_scene_error", "error": err_str},
        )

    pil_image = resolved["image"]
    image_source = resolved["source"]  # "bands" (AOI-clipped) or "thumbnail" fallback

    # Route to the specialist with the resolved scene image.
    specialist = registry.get_specialist(task)
    specialist_name = getattr(specialist, "__name__", str(specialist))
    try:
        model_info = specialist.get_model_info()  # type: ignore
        model_label = model_info.get("adapter_path") or model_info.get("base_model") or specialist_name
        is_real = bool(model_info.get("is_real", False))
        is_stub = bool(model_info.get("stub", False))
    except Exception:
        model_label = specialist_name
        is_real = False
        is_stub = True

    invoke_start = time.time()
    try:
        result = registry.predict([pil_image], query, task)
    except Exception as e:
        logger.error("Specialist %s failed on active scene: %s", task, e, exc_info=True)
        result = {
            "answer": f"Specialist '{task}' failed on the selected scene: {e}",
            "evidence": [],
            "confidence": 0.0,
            "_latency_ms": int((time.time() - invoke_start) * 1000),
            "_error": str(e),
        }
        is_stub = True

    latency_ms = int(result.get("_latency_ms", int((time.time() - invoke_start) * 1000)))
    answer = str(result.get("answer", ""))
    confidence = float(result.get("confidence", 0.5))
    confidence = max(0.0, min(1.0, confidence))
    evidence_raw = result.get("evidence", [])
    total_latency = int((time.time() - t0) * 1000)

    evidence_refs: list[EvidenceRef] = []
    for ev in evidence_raw:
        try:
            evidence_refs.append(EvidenceRef(**ev))
        except Exception:
            logger.warning("Skipping malformed evidence: %r", ev)

    # The analysis image came from the scene's real assets, not a user upload.
    evidence_refs.append(
        EvidenceRef(
            type="image_ref",
            description=f"Analysis image resolved from active scene {_scene_ctx(scene)['scene_id']} ({resolved.get('bands', []) or 'preview'} via {'real band assembly' if image_source == 'bands' else 'scene preview thumbnail'})",
            image_index=0,
        )
    )

    scene_ctx = _scene_ctx(scene, aoi=aoi, source=image_source)
    model_entry = ModelTraceEntry(
        name=model_label if isinstance(model_label, str) else specialist_name,
        role=task,
        parameters={
            "input_mode": input_mode,
            "image_count": 1,
            "scene_context": scene_ctx,
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
            "image_count": 1,
            "band_subset": resolved.get("bands") or ["preview"],
            "spatial_resolution_m": 10,
            "scene_context": scene_ctx,
        },
        confidence=confidence,
        evidence_refs=evidence_refs,
        total_latency_ms=total_latency,
    )

    structured_obj, chart_list, chart_type = _build_structured(result, task)

    return QueryResponse(
        answer=answer,
        confidence=confidence,
        execution_trace=trace,
        evidence=evidence_refs,
        structured=structured_obj,
        chart=chart_list,
        chart_type=chart_type,  # type: ignore
        scene_context=scene_ctx,
        analysis={
            "type": "active_scene_image",
            "scene_id": _scene_ctx(scene)["scene_id"],
            "source": image_source,
            "bands": resolved.get("bands") or [],
            "leaflet_bounds": resolved.get("leaflet_bounds"),
        },
    )
