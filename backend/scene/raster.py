"""Selected-scene image resolution — real Sentinel-2 band assets -> PIL RGB.

Selected Satellite Image Query Mode: when the user activates a scene ("Query This
Image"), analysis queries (VQA, counting, land cover) must run against the REAL
assets of that scene, not an uploaded demo image. This module reuses the shared
band pipeline (backend.spectral.processor.process_bands) so there is exactly ONE
raster retrieval path in the codebase — no fake images, no parallel downloader.

Behavior:
- With an AOI  -> downloads B04/B03/B02 (10 m), clips to Intersection(Scene, AOI),
  resamples/aligrn to the reference band, and stacks into a PIL RGB image.
- Without an AOI -> falls back to the scene's real preview/thumbnail asset (still
  a genuine asset of the selected scene, marked source="thumbnail"). Quantitative
  workflows (spectral indices, stats) should require an AOI.
"""

from __future__ import annotations

import io
import logging
import time
from typing import Any

import numpy as np
import requests
from PIL import Image

logger = logging.getLogger(__name__)

# Sentinel-2 L2A true-color composite (all 10 m)
RGB_BANDS = ["B04", "B03", "B02"]

# L2A reflectance is 0-10000; clip at ~0.3 albedo for a natural-looking composite
_REFLECTANCE_CLIP = 3000.0


def _scene_obj(scene: Any) -> Any:
    """Normalize scene dict -> backend.satellite.models.SatelliteScene."""
    from backend.satellite.models import SatelliteScene

    if isinstance(scene, SatelliteScene):
        return scene
    if isinstance(scene, dict):
        return SatelliteScene(**scene)
    raise ValueError("scene must be a SatelliteScene dict or SatelliteScene object")


def _load_thumbnail(scene: Any) -> tuple[Image.Image, list[str]]:
    """Fetch the scene's real preview/thumbnail asset as a PIL image."""
    trace: list[str] = []
    thumb_href = scene.thumbnail
    if not thumb_href:
        raise ValueError(
            "No AOI drawn and this scene has no preview/thumbnail asset — "
            "draw a polygon AOI on the map to analyze the scene's real band data."
        )
    try:
        r = requests.get(thumb_href, stream=True, timeout=60)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGB")
        img.load()
        trace.append("No AOI — used real scene preview/thumbnail asset")
        trace.append(f"Thumbnail resolved: {thumb_href.split('?')[0][:100]}")
        return img, trace
    except Exception as e:
        raise ValueError(
            f"Could not load scene preview thumbnail: {e}. "
            "Draw a polygon AOI on the map to analyze the scene's real band data."
        ) from e


def _arr_to_rgb_image(bands: dict[str, np.ndarray]) -> Image.Image:
    """Stack B04/B03/B02 arrays -> uint8 PIL RGB with reflectance clip."""
    red = bands.get("B04")
    green = bands.get("B03")
    blue = bands.get("B02")
    missing = [b for b in RGB_BANDS if b not in bands]
    if missing:
        raise ValueError(f"Missing RGB bands {missing} — cannot compose scene image")
    assert red is not None and green is not None and blue is not None
    rgb = np.stack(
        [red.astype(np.float32), green.astype(np.float32), blue.astype(np.float32)],
        axis=-1,
    )
    rgb = np.clip(rgb / _REFLECTANCE_CLIP, 0.0, 1.0)
    arr = (rgb * 255.0).astype(np.uint8)
    return Image.fromarray(arr, mode="RGB")


def _leaflet_bounds_from_bbox(bbox: list[float] | None) -> list[list[float]] | None:
    """bbox [west,south,east,north] -> Leaflet ImageOverlay [[south,west],[north,east]]."""
    if not bbox or len(bbox) < 4:
        return None
    west, south, east, north = bbox[0], bbox[1], bbox[2], bbox[3]
    return [[south, west], [north, east]]


def _leaflet_bounds_from_profile(profile: dict[str, Any]) -> list[list[float]] | None:
    """Scene-CRS profile bounds -> EPSG:4326 Leaflet bounds."""
    try:
        import rasterio  # type: ignore
        from rasterio.warp import transform_bounds  # type: ignore

        west, south, east, north = rasterio.transform.array_bounds(
            profile["height"], profile["width"], profile["transform"]
        )
        bounds_4326 = transform_bounds(
            profile["crs"], "EPSG:4326", west, south, east, north, densify_pts=21
        )
        return [[bounds_4326[1], bounds_4326[0]], [bounds_4326[3], bounds_4326[2]]]
    except Exception as e:
        logger.warning("compute leaflet bounds failed: %s", e)
        return None


def resolve_scene_rgb(
    scene: dict[str, Any],
    aoi: dict[str, Any] | None = None,
    max_dim: int = 768,
) -> dict[str, Any]:
    """Resolve a real RGB analysis image from the active scene's band assets.

    Returns:
        {
          image: PIL.Image,          # RGB composite (AOI-clipped, or thumbnail fallback)
          source: "bands"|"thumbnail",
          scene_id: str,
          collection: str,
          bands: list[str],
          leaflet_bounds: list[[s,s],[n,e]] | None,
          profile: dict | None,
          trace_steps: list[str],
        }
    """
    start = time.time()
    trace: list[str] = []
    scene_obj = _scene_obj(scene)
    scene_assets = scene_obj.assets or {}
    trace.append(f"Active scene selected: {scene_obj.id} ({scene_obj.datetime})")

    if not aoi or not isinstance(aoi, dict) or not aoi.get("type"):
        thumb, thumb_trace = _load_thumbnail(scene_obj)
        trace.extend(thumb_trace)
        return {
            "image": thumb,
            "source": "thumbnail",
            "scene_id": scene_obj.id,
            "collection": scene_obj.collection,
            "bands": [],
            "leaflet_bounds": _leaflet_bounds_from_bbox(
                getattr(scene_obj, "bbox", None)
            ),
            "profile": None,
            "trace_steps": trace,
            "latency_ms": int((time.time() - start) * 1000),
        }

    from backend.spectral.processor import process_bands

    try:
        proc = process_bands(
            scene_assets=scene_assets,
            required_bands=RGB_BANDS,
            scene_id=scene_obj.id,
            aoi=aoi,
            target_resolution=10,
            cloud_mask=False,
        )
        trace.append(
            "Bands retrieved: B04/B03/B02 @ 10 m, clipped to AOI (Intersection(Scene, AOI))"
        )
        img = _arr_to_rgb_image(proc["bands"])
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        trace.append(
            f"True-color composite composed ({img.size[0]}x{img.size[1]}) from real asset bands"
        )
        return {
            "image": img,
            "source": "bands",
            "scene_id": scene_obj.id,
            "collection": scene_obj.collection,
            "bands": RGB_BANDS,
            "leaflet_bounds": _leaflet_bounds_from_profile(proc.get("profile") or {}),
            "profile": proc.get("profile"),
            "trace_steps": trace,
            "latency_ms": int((time.time() - start) * 1000),
        }
    except Exception as e:
        err_msg = str(e)
        # CDSE s3:// assets without HTTPS alternate are common — gracefully fall back to thumbnail
        # so VQA/count still works instead of hard failing with confusing "Draw an AOI" message.
        if "s3://" in err_msg or "No connection adapters" in err_msg or "Failed to download band" in err_msg:
            logger.warning("Band download failed for %s (%s) — falling back to thumbnail: %s", scene_obj.id, RGB_BANDS, e)
            trace.append(f"Band download failed ({err_msg[:120]}) — using real scene preview/thumbnail asset instead")
            thumb, thumb_trace = _load_thumbnail(scene_obj)
            trace.extend(thumb_trace)
            trace.append("Fallback: VQA/count can still run on thumbnail; for spectral indices try another scene or smaller AOI")
            return {
                "image": thumb,
                "source": "thumbnail",
                "scene_id": scene_obj.id,
                "collection": scene_obj.collection,
                "bands": [],
                "leaflet_bounds": _leaflet_bounds_from_bbox(getattr(scene_obj, "bbox", None)),
                "profile": None,
                "trace_steps": trace,
                "latency_ms": int((time.time() - start) * 1000),
            }
        raise
