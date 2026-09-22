"""Satellite Retrieval Agent — follows existing specialist pattern (predict interface)."""

from __future__ import annotations

import logging
import time
from typing import Any

from . import cache as _cache
from .client import search_cdse
from .coverage import compute_aoi_coverage
from .models import RetrievalRequest, SatelliteScene
from .ranking import rank_scenes

logger = logging.getLogger(__name__)

# Agent metadata for registry health
_AGENT_NAME = "imadityasarkar/satquery-satellite-retrieval"
_COLLECTION = "sentinel-2-l2a"


def _request_from_params(params: dict[str, Any]) -> RetrievalRequest:
    # Accept both snake and camel, and geometry under various keys
    geom = params.get("geometry") or params.get("aoi") or params.get("intersects")
    if not geom:
        raise ValueError("geometry/AOI is required (GeoJSON Polygon)")
    # Normalize dates: allow string or date
    return RetrievalRequest(
        sensor=params.get("sensor", "sentinel-2"),
        product=params.get("product", "l2a"),
        geometry=geom,
        start_date=params["start_date"],
        end_date=params["end_date"],
        max_cloud_cover=float(params.get("max_cloud_cover", 20)),
        max_results=int(params.get("max_results", 10)),
        required_bands=params.get("required_bands"),
        required_analysis=params.get("required_analysis"),
    )


def search_satellite_data(params: dict[str, Any]) -> dict[str, Any]:
    """
    Core agent operation — search, coverage, ranking, trace.
    Returns {scenes, best_scene, trace, count}.
    """
    start_ms = time.time()
    req = _request_from_params(params)

    # Caching key
    cache_key = {
        "collection": req.collection,
        "geometry": req.geometry,
        "datetime": req.stac_datetime(),
        "cloud": req.max_cloud_cover,
        "max_results": req.max_results,
    }
    cached = _cache.get_cached(cache_key)
    if cached is not None:
        logger.info("CDSE cache hit for %s", cache_key)
        scenes: list[SatelliteScene] = cached  # type: ignore
        from_cache = True
    else:
        scenes = search_cdse(req)
        from_cache = False

    results_found = len(scenes)

    # Compute coverage per scene & re-filter if geometry is small? Keep all but annotate
    for sc in scenes:
        try:
            sc.coverage = round(compute_aoi_coverage(sc.geometry, req.geometry), 2)
        except Exception:
            sc.coverage = 0.0

    # Rank (includes selection_score calc)
    ranked = rank_scenes(scenes, start_date=req.start_date, end_date=req.end_date)

    # Cache full ranked list (with coverage+score) for TTL
    if not from_cache:
        _cache.set_cached(cache_key, ranked)

    best = ranked[0] if ranked else None

    latency_ms = int((time.time() - start_ms) * 1000)
    trace = {
        "agent": "satellite_retrieval",
        "operation": "search",
        "provider": "CDSE",
        "collection": req.collection,
        "results_found": results_found,
        "results_after_filtering": len(ranked),
        "selected_scene": best.id if best else None,
        "latency_ms": latency_ms,
        "parameters": {
            "sensor": req.sensor,
            "product": req.product,
            "start_date": str(req.start_date),
            "end_date": str(req.end_date),
            "max_cloud_cover": req.max_cloud_cover,
            "max_results": req.max_results,
        },
    }
    logger.info("Retrieval agent: found=%d best=%s latency=%dms", results_found, best.id if best else None, latency_ms)

    return {
        "scenes": ranked,
        "best_scene": best,
        "trace": trace,
        "count": len(ranked),
        "request": req,
    }


def select_best_scene(scenes: list[SatelliteScene]) -> SatelliteScene | None:
    if not scenes:
        return None
    # Assumes already ranked
    return max(scenes, key=lambda s: s.selection_score or 0)


def get_scene_metadata(scene_id: str, scenes: list[SatelliteScene]) -> SatelliteScene | None:
    for s in scenes:
        if s.id == scene_id:
            return s
    return None


def retrieve_scene_assets(scene_id: str, requested_assets: list[str] | None = None) -> dict[str, str]:
    """
    Stub for future raster download — returns asset hrefs for requested bands.
    Does NOT download rasters; just surfaces STAC asset URLs.
    For MVP, caller must pass scenes list or re-search; this helper is for API convenience.
    """
    # This is intentionally minimal for MVP — real download will need /api/satellite/assets
    # We keep interface stable for future
    if not requested_assets:
        return {}
    # In real impl, would fetch scene by id from cache/CDSE
    # For now return empty mapping and log
    logger.info("retrieve_scene_assets stub: scene=%s assets=%s (no download in MVP)", scene_id, requested_assets)
    return {}


# --- Specialist-compatible predict interface for registry integration ---
def predict(images: Any, query: str, task: str = "satellite_retrieval") -> dict[str, Any]:
    """
    Registry-compatible predict — but satellite retrieval doesn't use images.
    This is for controller routing via text query that contains AOI/dates in metadata.
    For MVP, predict expects query to contain structured JSON params after '||' or images is unused.
    Prefer direct search_satellite_data via API; this keeps interface stable.
    """
    # Try to parse query as JSON params if provided
    import json

    params: dict[str, Any] = {}
    try:
        # If query is JSON, use it
        if query.strip().startswith("{"):
            params = json.loads(query)
        else:
            # Fallback stub response for text queries without structured params
            return {
                "answer": "[STUB] Satellite retrieval requires structured AOI + dates via /api/satellite/search. Query was: " + query[:120],
                "evidence": [],
                "confidence": 0.0,
                "_latency_ms": 0,
                "_stub": True,
            }
    except Exception:
        return {
            "answer": "[STUB] Satellite retrieval parse failed for query: " + query[:120],
            "evidence": [],
            "confidence": 0.0,
            "_latency_ms": 0,
            "_stub": True,
        }

    if "geometry" not in params or "start_date" not in params or "end_date" not in params:
        return {
            "answer": "[STUB] Missing geometry/start_date/end_date for satellite retrieval.",
            "evidence": [],
            "confidence": 0.0,
            "_latency_ms": 0,
            "_stub": True,
        }

    result = search_satellite_data(params)
    best = result["best_scene"]
    scenes = result["scenes"]
    if not best:
        answer = "No Sentinel-2 scenes found for the requested AOI and date range."
    else:
        answer = f"Found {len(scenes)} Sentinel-2 L2A scenes. Best: {best.id} ({best.datetime}, cloud {best.cloud_cover}%, coverage {best.coverage}%, score {best.selection_score})"
    return {
        "answer": answer,
        "evidence": [{"type": "image_ref", "description": f"Best scene {best.id}" if best else "no scene", "image_index": 0}] if best else [],
        "confidence": 0.85 if best else 0.35,
        "_latency_ms": result["trace"]["latency_ms"],
        "_structured": {"bullets": [], "chart": []},
        "_chart": [],
        "_chart_type": "none",
        "_satellite": result,  # internal passthrough for controller trace merging
        "_stub": False,
    }


def is_real() -> bool:
    return True


def load_error() -> str | None:
    return None


def get_model_info() -> dict[str, Any]:
    return {
        "base_model": "CDSE STAC API",
        "adapter_path": CDSE_STAC_URL if (CDSE_STAC_URL := __import__("backend.satellite.client", fromlist=["CDSE_STAC_URL"]).CDSE_STAC_URL) else "https://stac.dataspace.copernicus.eu/v1",
        "is_real": True,
        "load_error": None,
        "device": "api",
        "has_cuda": False,
        "compute": "api",
        "task": "satellite_retrieval",
        "collection": _COLLECTION,
        "agent": _AGENT_NAME,
    }


def preload() -> bool:
    return True
