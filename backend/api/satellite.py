"""Satellite retrieval API — POST /api/satellite/search."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.satellite.agent import search_satellite_data
from backend.satellite.models import RetrievalRequest, SatelliteScene

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/satellite", tags=["satellite"])


class SatelliteSearchBody(BaseModel):
    geometry: dict[str, Any] = Field(description="GeoJSON Polygon/MultiPolygon AOI EPSG:4326")
    start_date: str = Field(description="YYYY-MM-DD")
    end_date: str = Field(description="YYYY-MM-DD")
    max_cloud_cover: float = Field(default=20, ge=0, le=100)
    sensor: str = Field(default="sentinel-2")
    product: str = Field(default="l2a")
    max_results: int = Field(default=10, ge=1, le=100)
    required_bands: list[str] | None = None
    required_analysis: str | None = None


class SatelliteSearchResponseAPI(BaseModel):
    count: int
    scenes: list[SatelliteScene]
    best_scene: SatelliteScene | None = None
    provider: str = "CDSE"
    collection: str = "sentinel-2-l2a"
    query: dict[str, Any] | None = None
    trace: dict[str, Any] | None = None
    # execution trace snippet for UI
    execution_trace: dict[str, Any] | None = None


@router.post("/search", response_model=SatelliteSearchResponseAPI)
def satellite_search(body: SatelliteSearchBody) -> dict[str, Any]:
    """
    Live CDSE STAC search for Sentinel-2 L2A.
    Validates via RetrievalRequest, returns ranked scenes with coverage+score.
    """
    # Build validated request
    try:
        req = RetrievalRequest(
            sensor=body.sensor,
            product=body.product,
            geometry=body.geometry,
            start_date=body.start_date,  # type: ignore[arg-type]
            end_date=body.end_date,  # type: ignore[arg-type]
            max_cloud_cover=body.max_cloud_cover,
            max_results=body.max_results,
            required_bands=body.required_bands,
            required_analysis=body.required_analysis,
        )
    except Exception as e:
        # Pydantic validation error -> 422
        raise HTTPException(status_code=422, detail=str(e)) from e

    params = {
        "sensor": req.sensor,
        "product": req.product,
        "geometry": req.geometry,
        "start_date": str(req.start_date),
        "end_date": str(req.end_date),
        "max_cloud_cover": req.max_cloud_cover,
        "max_results": req.max_results,
        "required_bands": req.required_bands,
        "required_analysis": req.required_analysis,
    }

    try:
        result = search_satellite_data(params)
    except ValueError as e:
        # Validation inside agent
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RuntimeError as e:
        # Provider unavailable
        logger.error("Satellite search provider error: %s", e)
        raise HTTPException(status_code=502, detail="Satellite data provider temporarily unavailable.") from e
    except Exception as e:
        logger.exception("Satellite search unexpected: %s", e)
        raise HTTPException(status_code=500, detail=f"Search failed: {e}") from e

    scenes: list[SatelliteScene] = result["scenes"]
    best = result["best_scene"]
    trace = result["trace"]

    # Build execution-trace snippet consistent with existing schemas
    exec_trace = {
        "task": "satellite_retrieval",
        "agent": trace.get("agent"),
        "operation": trace.get("operation"),
        "provider": trace.get("provider"),
        "collection": trace.get("collection"),
        "results_found": trace.get("results_found"),
        "results_after_filtering": trace.get("results_after_filtering"),
        "selected_scene": trace.get("selected_scene"),
        "latency_ms": trace.get("latency_ms"),
        "parameters": trace.get("parameters"),
    }

    # Graceful empty
    if not scenes:
        # Not an error — return 200 with count 0 and helpful message via trace
        logger.info("Satellite search: no scenes for %s %s", req.collection, req.stac_datetime())

    return {
        "count": len(scenes),
        "scenes": scenes,
        "best_scene": best,
        "provider": "CDSE",
        "collection": req.collection,
        "query": params,
        "trace": trace,
        "execution_trace": exec_trace,
    }


@router.get("/health")
def satellite_health() -> dict[str, Any]:
    from backend.satellite.client import CDSE_STAC_URL

    try:
        from backend.satellite.agent import get_model_info

        info = get_model_info()
    except Exception:
        info = {"is_real": True}
    return {
        "status": "ok",
        "provider": "CDSE",
        "stac_url": CDSE_STAC_URL,
        "collection": "sentinel-2-l2a",
        "supported_sensors": ["sentinel-2"],
        "supported_products": ["l2a", "l1c"],
        "agent": info,
    }


# Keep-alive for future asset retrieval (stub, no raster download)
class AssetRequest(BaseModel):
    scene_id: str
    requested_assets: list[str] = Field(default_factory=lambda: ["B02", "B03", "B04", "B08"])


@router.post("/assets")
def satellite_assets(body: AssetRequest) -> dict[str, Any]:
    """
    Return asset hrefs for a scene (no download). MVP stub.
    Future: will fetch scene by id from cache/CDSE and return signed URLs.
    """
    # For MVP, we can't resolve without a cached search; return guidance
    return {
        "scene_id": body.scene_id,
        "requested_assets": body.requested_assets,
        "assets": {},  # To be populated when scene cache is wired
        "note": "Asset download not yet implemented — use scene.assets from /search response. Future: retrieve_scene_assets(scene_id, requested_assets).",
    }
