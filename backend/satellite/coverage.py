"""AOI coverage calculation — shapely-based, EPSG:4326 planar approximation."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from shapely.geometry import shape as _shape
    from shapely.validation import make_valid as _make_valid

    _HAS_SHAPELY = True
except ImportError:
    _HAS_SHAPELY = False
    _shape = None  # type: ignore
    _make_valid = None  # type: ignore


def _extract_geometry(geojson: dict[str, Any]) -> dict[str, Any]:
    """Unwrap Feature/FeatureCollection to raw geometry dict."""
    if not isinstance(geojson, dict):
        return geojson
    t = geojson.get("type")
    if t == "Feature":
        return geojson.get("geometry") or geojson
    if t == "FeatureCollection":
        feats = geojson.get("features") or []
        if feats:
            first = feats[0]
            if isinstance(first, dict) and "geometry" in first:
                return first["geometry"]
            return first  # type: ignore[return-value]
    return geojson


def compute_aoi_coverage(scene_geometry: dict[str, Any] | None, aoi_geometry: dict[str, Any]) -> float:
    """
    coverage = intersection(scene, AOI) / AOI  * 100

    Returns 0-100 float. Falls back to 100 if shapely unavailable or geometries missing.
    Uses planar EPSG:4326 approximation (good enough for ranking, not geodesy).
    """
    if not _HAS_SHAPELY:
        logger.debug("shapely not installed — coverage fallback 100")
        return 100.0
    if scene_geometry is None:
        return 0.0
    try:
        aoi_raw = _extract_geometry(aoi_geometry)
        scene_raw = _extract_geometry(scene_geometry)

        aoi_shape = _shape(aoi_raw)  # type: ignore[arg-type]
        scene_shape = _shape(scene_raw)  # type: ignore[arg-type]

        # Make valid if needed (self-intersections)
        if not aoi_shape.is_valid and _make_valid is not None:
            aoi_shape = _make_valid(aoi_shape)
        if not scene_shape.is_valid and _make_valid is not None:
            scene_shape = _make_valid(scene_shape)

        if aoi_shape.is_empty:
            return 0.0
        aoi_area = aoi_shape.area
        if aoi_area == 0:
            return 0.0
        inter = aoi_shape.intersection(scene_shape)
        if inter.is_empty:
            return 0.0
        cov = (inter.area / aoi_area) * 100.0
        return max(0.0, min(100.0, float(cov)))
    except Exception as e:
        logger.warning("coverage calc failed: %s", e)
        return 0.0
