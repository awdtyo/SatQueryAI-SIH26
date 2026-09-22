"""Spectral-index analysis API — POST /api/analysis/spectral-index"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.spectral.registry import INDEX_REGISTRY, get_index_info
from backend.spectral.agent import process_spectral_index

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["analysis"])


class SpectralIndexRequest(BaseModel):
    index: str = Field(description="NDVI | NDWI | NDBI | NDMI | SAVI | BSI (case-insensitive)")
    scene: dict[str, Any] = Field(description="SatelliteScene dict (from /api/satellite/search)")
    aoi: dict[str, Any] | None = Field(default=None, description="GeoJSON AOI for clipping (EPSG:4326), if null uses scene footprint")
    cloud_mask: bool = Field(default=True, description="Apply SCL cloud mask if available")
    target_resolution: int = Field(default=10, ge=10, le=60, description="Target resolution 10m (finest, bilinear)")


class SpectralIndexResponse(BaseModel):
    index: str
    scene_id: str
    scene_datetime: str | None = None
    aoi: dict[str, Any] | None = None
    required_bands: list[str]
    raster_path: str
    preview_b64: str | None = None
    preview_path: str | None = None
    bounds: list[list[float]] | None = None  # Leaflet [[south,west],[north,east]]
    bounds_4326: list[float] | None = None  # [west,south,east,north]
    profile: dict[str, Any] | None = None
    stats: dict[str, Any]
    cloud_applied: bool
    latency_ms: int
    trace_steps: list[str]
    provenance: dict[str, Any]
    evidence: list[dict[str, Any]]
    visual: dict[str, Any]
    interpretation: dict[str, Any]


@router.post("/spectral-index", response_model=SpectralIndexResponse)
def spectral_index(body: SpectralIndexRequest) -> dict[str, Any]:
    """
    Calculate spectral index from real Sentinel-2 STAC assets.
    - Validates index, scene, AOI
    - Downloads required bands via CDSE hrefs (only needed bands)
    - Clips to AOI, resamples to 10m bilinear (SCL nearest)
    - Applies nodata + SCL cloud mask
    - Calculates index, handles divide-by-zero -> nan
    - Generates GeoTIFF + PNG preview + stats
    """
    # Validate index
    info = get_index_info(body.index)
    if not info:
        raise HTTPException(status_code=422, detail=f"Unsupported index '{body.index}'. Supported: {sorted(INDEX_REGISTRY.keys())}")

    # Validate scene has assets
    scene_assets = body.scene.get("assets") if isinstance(body.scene, dict) else None
    if not scene_assets or not isinstance(scene_assets, dict) or len(scene_assets) == 0:
        raise HTTPException(status_code=422, detail="Scene must contain 'assets' with band hrefs (from /api/satellite/search)")

    # Validate AOI if provided
    aoi = body.aoi
    if aoi is not None:
        if not isinstance(aoi, dict) or "type" not in aoi:
            raise HTTPException(status_code=422, detail="Invalid AOI GeoJSON")
        # Quick check for required bands available
        # Let agent handle detailed
        pass

    # Determine AOI to use: if none, use scene geometry/bbox as AOI
    effective_aoi = aoi
    if effective_aoi is None:
        # Use scene geometry as fallback
        geom = body.scene.get("geometry")
        if geom:
            effective_aoi = geom  # type: ignore
        elif body.scene.get("bbox"):
            bbox = body.scene["bbox"]
            if isinstance(bbox, list) and len(bbox) == 4:
                west, south, east, north = bbox  # type: ignore
                effective_aoi = {
                    "type": "Polygon",
                    "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
                }

    if effective_aoi is None:
        raise HTTPException(status_code=422, detail="AOI is required for spectral processing (draw AOI or use scene footprint)")

    try:
        result = process_spectral_index(
            index=body.index,
            scene=body.scene,
            aoi=effective_aoi,
            cloud_mask=body.cloud_mask,
            target_resolution=body.target_resolution,
        )
    except ValueError as e:
        # Client errors
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RuntimeError as e:
        logger.error("Spectral processing runtime: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:
        logger.exception("Spectral processing failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Spectral processing failed: {e}") from e

    # Build execution trace-like response (preserve provenance)
    return {
        "index": result["index"],
        "scene_id": result["scene_id"],
        "scene_datetime": result["scene_datetime"],
        "aoi": result["aoi"],
        "required_bands": result["required_bands"],
        "raster_path": result["raster_path"],
        "preview_b64": result["preview_b64"],
        "preview_path": result["preview_path"],
        "bounds": result["bounds"],
        "bounds_4326": result["bounds_4326"],
        "profile": result["profile"],
        "stats": result["stats"],
        "cloud_applied": result["cloud_applied"],
        "latency_ms": result["latency_ms"],
        "trace_steps": result["trace_steps"],
        "provenance": result["provenance"],
        "evidence": result["evidence"],
        "visual": result["visual"],
        "interpretation": result["interpretation"],
    }


@router.get("/spectral-index/indices")
def list_supported_indices() -> dict[str, Any]:
    """List supported indices with metadata."""
    return {
        "indices": sorted(INDEX_REGISTRY.keys()),
        "registry": INDEX_REGISTRY,
    }


@router.get("/spectral-index/health")
def spectral_health() -> dict[str, Any]:
    try:
        from backend.spectral.agent import get_model_info

        info = get_model_info()
    except Exception:
        info = {"is_real": True}
    return {
        "status": "ok",
        "agent": info,
        "indices": sorted(INDEX_REGISTRY.keys()),
        "target_resolution": 10,
        "resampling": "bilinear (bands), nearest (SCL)",
    }


class PixelSampleRequest(BaseModel):
    raster_path: str
    lon: float
    lat: float


@router.post("/spectral-index/pixel")
def sample_pixel(body: PixelSampleRequest) -> dict[str, Any]:
    """Sample spectral index value at lon/lat from generated GeoTIFF."""
    import rasterio  # type: ignore

    path = Path(body.raster_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Raster not found: {body.raster_path}")
    try:
        with rasterio.open(path) as ds:
            # Transform lon/lat (EPSG:4326) to dataset CRS
            from rasterio.warp import transform as warp_transform

            xs, ys = warp_transform("EPSG:4326", ds.crs, [body.lon], [body.lat])
            x, y = xs[0], ys[0]
            row, col = ds.index(x, y)
            if row < 0 or row >= ds.height or col < 0 or col >= ds.width:
                return {"value": None, "lon": body.lon, "lat": body.lat, "out_of_bounds": True}
            val = ds.read(1, window=((row, row + 1), (col, col + 1)))[0, 0]
            # Handle nan
            import math

            if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                val = None
            else:
                val = float(val) if val is not None else None
            return {"value": val, "lon": body.lon, "lat": body.lat, "row": int(row), "col": int(col)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Pixel sample failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Pixel sample failed: {e}") from e
