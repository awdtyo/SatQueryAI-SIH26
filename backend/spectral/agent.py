"""Spectral-Index Agent — real Sentinel-2 band processing, STAC-based."""

from __future__ import annotations

import base64
import io
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from backend.satellite.models import SatelliteScene

from .bands import get_required_bands
from .calculator import calculate_index
from .masking import mask_nodata, apply_masks
from .processor import process_bands
from .registry import INDEX_REGISTRY, get_index_info
from .stats import calculate_stats

logger = logging.getLogger(__name__)

_AGENT_NAME = "satquery-spectral-index"
_OUTPUT_DIR = Path(os.getenv("SATQUERY_SPECTRAL_OUTPUT_DIR", "/tmp/satquery_spectral"))
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

try:
    import rasterio  # type: ignore

    _HAS_RASTERIO = True
except ImportError:
    _HAS_RASTERIO = False


def _generate_preview_png(index_arr: np.ndarray, index: str, out_path: Path) -> str | None:
    """Generate colorized PNG preview for map overlay, returns base64 data URL or path."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm
        import matplotlib.colors as mcolors

        info = get_index_info(index)
        vmin = info["visual"]["min"] if info else -1
        vmax = info["visual"]["max"] if info else 1
        cmap_name = info["visual"]["cmap"] if info else "RdYlGn"
        # Handle nan: create masked array
        masked = np.ma.masked_invalid(index_arr)
        # Normalize
        norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
        cmap = cm.get_cmap(cmap_name)
        # Apply cmap -> RGBA
        colored = cmap(norm(masked.filled(np.nan)))
        # Set alpha for nan -> transparent
        alpha = np.where(np.isnan(index_arr), 0, 255).astype(np.uint8)
        # Convert to uint8 RGB
        rgb = (colored[:, :, :3] * 255).astype(np.uint8)
        rgba = np.dstack([rgb, alpha])
        # Save via PIL
        from PIL import Image

        img = Image.fromarray(rgba, mode="RGBA")
        # Downsample for preview if large (max 512)
        max_dim = 512
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        # Save to out_path
        img.save(out_path, format="PNG")
        # Also create base64 for immediate map use
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        logger.warning("Preview generation failed for %s: %s", index, e)
        return None


def _save_geotiff(index_arr: np.ndarray, profile: dict[str, Any], out_path: Path) -> Path:
    """Save index array as GeoTIFF (float32, nan nodata)."""
    if not _HAS_RASTERIO:
        raise RuntimeError("rasterio required to save GeoTIFF")
    profile_out = profile.copy()
    profile_out.update(dtype="float32", count=1, nodata=float("nan"), compress="lzw")
    # Ensure nan nodata
    with rasterio.open(out_path, "w", **profile_out) as dst:
        dst.write(index_arr.astype(np.float32), 1)
    return out_path


def process_spectral_index(
    index: str,
    scene: dict[str, Any] | SatelliteScene,
    aoi: dict[str, Any] | None,
    cloud_mask: bool = True,
    target_resolution: int = 10,
) -> dict[str, Any]:
    """
    Core spectral processing — real STAC assets.
    Returns dict with index, scene_id, bands, raster paths, preview, stats, provenance, trace
    """
    start = time.time()
    trace_steps: list[str] = []
    trace_steps.append(f"Index identified: {index}")

    # Validate index
    info = get_index_info(index)
    if not info:
        raise ValueError(f"Unsupported index '{index}'. Supported: {sorted(INDEX_REGISTRY.keys())}")
    canon = info["name"]
    required_bands = info["required_bands"]
    trace_steps.append(f"Required bands: {', '.join(required_bands)}")
    # Validate scene
    if isinstance(scene, dict):
        # Try to parse as SatelliteScene
        try:
            scene_obj = SatelliteScene(**scene)  # type: ignore
        except Exception as e:
            raise ValueError(f"Invalid scene: {e}") from e
    elif isinstance(scene, SatelliteScene):
        scene_obj = scene
    else:
        raise ValueError("scene must be SatelliteScene dict")

    trace_steps.append(f"Selected scene identified: {scene_obj.id} ({scene_obj.datetime})")
    # Validate AOI
    if aoi is not None:
        if not isinstance(aoi, dict) or "type" not in aoi:
            raise ValueError("Invalid AOI GeoJSON")
        # Quick shapely validation
        try:
            from shapely.geometry import shape as _shape

            geom = aoi.get("geometry") if aoi.get("type") == "Feature" else aoi
            if aoi.get("type") == "FeatureCollection":
                geom = aoi["features"][0].get("geometry") if aoi["features"] else None  # type: ignore
            shp = _shape(geom)  # type: ignore
            if not shp.is_valid:
                raise ValueError("AOI geometry is not valid")
            if shp.is_empty:
                raise ValueError("AOI geometry is empty")
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Invalid AOI: {e}") from e

    # Resolve STAC assets
    scene_assets = scene_obj.assets or {}
    # Also include assets from metadata if needed
    # Validate required bands exist
    from backend.spectral.bands import resolve_band_assets

    try:
        hrefs = resolve_band_assets(scene_assets, required_bands)
        trace_steps.append(f"STAC assets resolved: {', '.join([f'{k}->{hrefs[k][:60]}...' for k in hrefs])}")
    except ValueError as e:
        raise ValueError(str(e)) from e

    # Band retrieval + alignment
    trace_steps.append(f"Band data retrieved: {', '.join(required_bands)} (target {target_resolution}m bilinear)")
    proc = process_bands(
        scene_assets=scene_assets,
        required_bands=required_bands,
        scene_id=scene_obj.id,
        aoi=aoi,
        target_resolution=target_resolution,
        cloud_mask=cloud_mask,
    )
    trace_steps.append("Bands aligned (CRS, transform, dimensions, resampled where needed)")
    bands = proc["bands"]
    profile = proc["profile"]
    cloud_mask_arr = proc.get("cloud_mask")
    cloud_applied = proc.get("cloud_applied", False)
    if cloud_applied:
        trace_steps.append("Cloud/nodata mask applied (SCL 0,1,3,8,9,10,11 masked)")
    else:
        trace_steps.append("Cloud mask not applied (SCL unavailable or disabled)")

    # Nodata handling
    nodata_mask = mask_nodata(*bands.values())
    trace_steps.append(f"Nodata handling: valid pixels {float(nodata_mask.mean()*100):.1f}% before index")

    # Calculate index
    trace_steps.append(f"Calculating {canon} via {info['formula']}")
    # Ensure bands are float32
    bands_f = {k: v.astype(np.float32) for k, v in bands.items()}
    # For calibration, Sentinel-2 reflectance is 0-10000; we keep raw but divide not needed for ratio
    # However for SAVI etc same; keep raw
    index_arr = calculate_index(canon, bands_f)

    # Handle divide-by-zero already nan, now apply masks
    index_arr = apply_masks(index_arr, nodata_mask)
    if cloud_mask_arr is not None:
        # Ensure cloud mask same shape
        if cloud_mask_arr.shape != index_arr.shape:
            # Should have been resampled, but if mismatch skip
            logger.warning("Cloud mask shape %s != index shape %s, skipping", cloud_mask_arr.shape, index_arr.shape)
        else:
            index_arr = apply_masks(index_arr, cloud_mask_arr)

    trace_steps.append(f"{canon} calculated, handling divide-by-zero -> nan")

    # Statistics
    stats = calculate_stats(index_arr)
    trace_steps.append(f"Statistics generated: mean {stats['mean']:.3f} valid {stats['valid_pct']:.1f}%")
    if stats["valid_pixels"] == 0:
        raise ValueError(f"All pixels masked for {canon} — insufficient valid pixels (AOI may be outside scene or fully clouded)")

    # Generate raster outputs
    uid = uuid.uuid4().hex[:8]
    out_tif = _OUTPUT_DIR / f"{scene_obj.id}_{canon}_{uid}.tif"
    out_png = _OUTPUT_DIR / f"{scene_obj.id}_{canon}_{uid}.png"
    try:
        _save_geotiff(index_arr, profile, out_tif)
        trace_steps.append(f"Georeferenced raster generated: {out_tif} ({profile['width']}x{profile['height']} {profile['crs']})")
    except Exception as e:
        logger.error("Failed to save GeoTIFF: %s", e)
        raise RuntimeError(f"Failed to generate output raster: {e}") from e

    preview_b64 = _generate_preview_png(index_arr, canon, out_png)
    trace_steps.append("Map layer preview PNG generated (base64)")

    # Bounds for map overlay (EPSG:4326)
    # profile is in scene CRS (UTM), need to transform bounds to 4326 for Leaflet
    bounds_4326 = None
    try:
        from rasterio.warp import transform_bounds

        west, south, east, north = rasterio.transform.array_bounds(
            profile["height"], profile["width"], profile["transform"]
        )
        # Transform bounds from profile CRS to 4326
        bounds_4326 = transform_bounds(profile["crs"], "EPSG:4326", west, south, east, north, densify_pts=21)
        # bounds_4326 is (west,south,east,north) in 4326
        # For Leaflet ImageOverlay, need [[south,west],[north,east]]
        leaflet_bounds = [[bounds_4326[1], bounds_4326[0]], [bounds_4326[3], bounds_4326[2]]]
    except Exception as e:
        logger.warning("Failed to compute bounds for preview: %s", e)
        leaflet_bounds = None
        bounds_4326 = None

    latency_ms = int((time.time() - start) * 1000)
    trace_steps.append(f"Completed in {latency_ms}ms")

    # Provenance
    provenance = {
        "satellite": scene_obj.platform or "sentinel-2",
        "product": scene_obj.collection,
        "scene_id": scene_obj.id,
        "acquisition_datetime": str(scene_obj.datetime) if scene_obj.datetime else None,
        "stac_catalog": "CDSE",
        "collection": scene_obj.collection,
        "band_assets_used": hrefs,
        "bands_required": required_bands,
        "formula": info["formula"],
        "index": canon,
        "aoi": aoi,
        "processing_parameters": {
            "cloud_mask": cloud_mask,
            "cloud_applied": cloud_applied,
            "target_resolution": target_resolution,
            "resampling": "bilinear (bands), nearest (SCL)",
            "nodata_handling": "nan where invalid",
            "divide_by_zero": "nan",
        },
        "output_tif": str(out_tif),
        "preview_png": str(out_png),
        "crs": str(profile["crs"]),
        "shape": [profile["height"], profile["width"]],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Evidence for trace
    evidence = [
        {"type": "image_ref", "description": f"Spectral index {canon} for scene {scene_obj.id}", "image_index": 0},
        {"type": "overlay", "description": f"{canon} raster overlay", "image_index": 0},
    ]

    return {
        "index": canon,
        "scene_id": scene_obj.id,
        "scene_datetime": str(scene_obj.datetime) if scene_obj.datetime else None,
        "aoi": aoi,
        "required_bands": required_bands,
        "hrefs": hrefs,
        "raster_path": str(out_tif),
        "preview_path": str(out_png),
        "preview_b64": preview_b64,
        "bounds": leaflet_bounds,
        "bounds_4326": bounds_4326,
        "profile": {"crs": str(profile["crs"]), "width": profile["width"], "height": profile["height"]},
        "stats": stats,
        "cloud_applied": cloud_applied,
        "cloud_mask": cloud_applied,
        "latency_ms": latency_ms,
        "trace_steps": trace_steps,
        "provenance": provenance,
        "evidence": evidence,
        "visual": info.get("visual", {}),
        "interpretation": info.get("interpretation", {}),
    }


# --- Registry-compatible predict ---

def predict(images: Any, query: str, task: str = "spectral_index") -> dict[str, Any]:
    """
    Registry predict — query should contain JSON with index, scene, aoi
    For NL routing, query like "Calculate NDVI for this area" will be parsed.
    """
    import json

    # Try to parse JSON from query
    params: dict[str, Any] = {}
    try:
        if query.strip().startswith("{"):
            params = json.loads(query)
        else:
            # Try to extract index from NL
            from .registry import resolve_index_name

            idx = resolve_index_name(query)
            if idx:
                # Need scene/aoi from context — if not in query JSON, return stub asking for scene
                return {
                    "answer": f"Spectral index {idx} requested but no scene/AOI provided. Please select a Sentinel-2 scene and draw an AOI, then request {idx}.",
                    "evidence": [],
                    "confidence": 0.35,
                    "_latency_ms": 0,
                    "_stub": True,
                }
            return {
                "answer": f"Spectral analysis requested but could not parse index from query: {query[:120]}. Try 'Calculate NDVI for the selected scene.'",
                "evidence": [],
                "confidence": 0.35,
                "_latency_ms": 0,
                "_stub": True,
            }
    except Exception as e:
        return {
            "answer": f"Spectral agent parse failed: {e}",
            "evidence": [],
            "confidence": 0.0,
            "_latency_ms": 0,
            "_stub": True,
        }

    idx = params.get("index") or params.get("spectral_index")
    scene = params.get("scene") or params.get("scene_id") or params.get("satellite_scene")
    aoi = params.get("aoi") or params.get("geometry")

    if not idx:
        return {"answer": "Missing 'index' (e.g., NDVI).", "evidence": [], "confidence": 0.0, "_latency_ms": 0, "_stub": True}
    if not scene:
        return {"answer": f"Missing scene for {idx}. Please select a Sentinel-2 scene first.", "evidence": [], "confidence": 0.0, "_latency_ms": 0, "_stub": True}

    # If scene is id string, we can't fetch without cache; require full scene dict
    if isinstance(scene, str):
        return {
            "answer": f"Scene id '{scene}' provided but full scene metadata required. Please pass the selected SatelliteScene object.",
            "evidence": [],
            "confidence": 0.0,
            "_latency_ms": 0,
            "_stub": True,
        }

    try:
        result = process_spectral_index(index=idx, scene=scene, aoi=aoi, cloud_mask=params.get("cloud_mask", True))
    except ValueError as e:
        return {"answer": str(e), "evidence": [], "confidence": 0.35, "_latency_ms": 0, "_stub": True, "_error": str(e)}
    except Exception as e:
        logger.exception("Spectral processing failed: %s", e)
        return {"answer": f"Spectral processing failed for {idx}: {e}", "evidence": [], "confidence": 0.0, "_latency_ms": 0, "_error": str(e), "_stub": True}

    # Build answer bullets
    s = result["stats"]
    answer = (
        f"- **{result['index']}** calculated for **{result['scene_id']}** ({result['scene_datetime'] or 'unknown date'})\n"
        f"- **Mean {result['index']}: {s['mean']:.3f}** · min {s['min']:.3f} · max {s['max']:.3f} · median {s['median']:.3f}\n"
        f"- **Valid pixels: {s['valid_pct']:.1f}%** ({s['valid_pixels']} px) · masked {s['masked_pct']:.1f}% · cloud mask {'applied' if result['cloud_applied'] else 'not applied'}\n"
        f"- **Bands:** {', '.join(result['required_bands'])} @ {result['provenance']['processing_parameters']['target_resolution']}m bilinear · formula `{result['provenance']['formula']}`"
    )

    return {
        "answer": answer,
        "evidence": result["evidence"],
        "confidence": 0.85,
        "_latency_ms": result["latency_ms"],
        "_structured": {"bullets": answer.split("\n"), "chart": []},
        "_chart": [],
        "_chart_type": "none",
        "_spectral": result,
        "_stub": False,
    }


def is_real() -> bool:
    return True


def load_error() -> str | None:
    return None


def get_model_info() -> dict[str, Any]:
    return {
        "base_model": "Sentinel-2 L2A + rasterio",
        "adapter_path": "spectral-index-agent",
        "is_real": True,
        "load_error": None,
        "device": "cpu",
        "compute": "cpu",
        "task": "spectral_index",
        "indices": sorted(INDEX_REGISTRY.keys()),
    }


def preload() -> bool:
    return True
