"""Raster processing pipeline — band retrieval, alignment, resampling, clipping."""

from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import requests

logger = logging.getLogger(__name__)

# Cache for downloaded band files
_BAND_CACHE_DIR = Path(os.getenv("SATQUERY_BAND_CACHE_DIR", "/tmp/satquery_bands"))
_BAND_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Target resolution doc: 10m (finest) with bilinear
TARGET_RESOLUTIONS = {"NDVI": 10, "NDWI": 10, "NDBI": 10, "NDMI": 10, "SAVI": 10, "BSI": 10}
RESAMPLE_METHOD_BILINEAR = "bilinear"  # doc
RESAMPLE_METHOD_NEAREST = "nearest"  # for SCL

try:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import transform_geom, reproject
    from rasterio.windows import from_bounds
    from rasterio.io import MemoryFile

    _HAS_RASTERIO = True
except ImportError:
    _HAS_RASTERIO = False
    rasterio = None  # type: ignore
    Resampling = None  # type: ignore


def _s3_to_https_candidates(href: str) -> list[str]:
    """CDSE STAC often returns s3://eodata/... — try common HTTPS mirrors."""
    if not href.startswith("s3://"):
        return []
    path = href[5:]  # strip s3://
    # e.g. eodata/Sentinel-2/.../B04.jp2
    candidates: list[str] = []
    # Primary EODATA HTTPS gateway (public, used by CDSE alternate)
    candidates.append(f"https://eodata.dataspace.copernicus.eu/{path}")
    # Variant with /eodata prefix already included — dedup
    if path.startswith("eodata/"):
        candidates.append(f"https://eodata.dataspace.copernicus.eu/{path}")
    else:
        candidates.append(f"https://eodata.dataspace.copernicus.eu/eodata/{path}")
    # Zipper gateway sometimes mirrors same
    candidates.append(f"https://zipper.dataspace.copernicus.eu/{path}")
    # Deduplicate preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def _download_band(href: str, scene_id: str, band: str) -> Path:
    """Download band asset to cache, return local path. Handles s3:// via HTTPS conversion or rasterio fallback."""
    safe_scene = "".join(c if c.isalnum() else "_" for c in scene_id)[:80]
    band_dir = _BAND_CACHE_DIR / safe_scene
    band_dir.mkdir(parents=True, exist_ok=True)
    # Determine filename from href
    fname = href.split("?")[0].split("/")[-1] or f"{band}.jp2"
    if "." not in fname:
        fname = f"{band}.jp2"
    local_path = band_dir / f"{band}_{fname}"
    if local_path.exists() and local_path.stat().st_size > 1024:
        logger.info("Band cache hit: %s -> %s", band, local_path)
        return local_path

    # Build candidate hrefs: original + https mirrors for s3
    candidates = [href]
    if href.startswith("s3://"):
        https_candidates = _s3_to_https_candidates(href)
        logger.info("Band %s href is s3:// — will try HTTPS mirrors: %s", band, https_candidates[:2])
        candidates = https_candidates + [href]

    last_err: Exception | None = None
    for cand in candidates:
        is_s3 = cand.startswith("s3://")
        try:
            if is_s3:
                # Try rasterio /vsis3/ read-then-write (requires GDAL S3 creds; may fail without creds)
                # Fall back to GDAL vsis3 streaming if requests can't handle s3://
                logger.info("Attempting S3 band %s via rasterio /vsis3/: %s", band, cand[:120])
                try:
                    import rasterio  # type: ignore
                    from rasterio.io import MemoryFile  # type: ignore

                    # Configure GDAL to allow unsigned S3 reads where possible
                    # CDSE S3 is requester-pays and needs creds; without creds this will 403,
                    # but we try anyway — next candidate (https) will be attempted by outer loop
                    vsis3_path = f"/vsis3/{cand[5:]}"
                    with rasterio.Env(AWS_NO_SIGN_REQUEST="YES", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):  # type: ignore
                        with rasterio.open(vsis3_path) as src:
                            profile = src.profile.copy()
                            data = src.read(1)
                            with rasterio.open(local_path, "w", **profile) as dst:
                                dst.write(data, 1)
                    if local_path.exists() and local_path.stat().st_size > 1024:
                        logger.info("Band %s via /vsis3/ succeeded", band)
                        return local_path
                except Exception as e_s3:
                    last_err = e_s3
                    logger.warning("Band %s /vsis3/ failed: %s", band, e_s3)
                    continue
                # If vsis3 failed, fall through to try next https candidate (already in list)
                continue

            logger.info("Downloading band %s from %s", band, cand[:120])
            with requests.get(cand, stream=True, timeout=90) as r:
                r.raise_for_status()
                with open(local_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            if local_path.exists() and local_path.stat().st_size > 1024:
                if cand != href:
                    logger.info("Band %s downloaded via HTTPS mirror %s", band, cand[:80])
                return local_path
        except Exception as e:
            last_err = e
            logger.warning("Band %s download from %s failed: %s", band, cand[:80], e)
            if local_path.exists():
                try:
                    local_path.unlink()
                except Exception:
                    pass
            continue

    # All candidates exhausted
    raise RuntimeError(f"Failed to download band {band} from {href}: {last_err}. CDSE S3 assets require HTTPS alternate or S3 credentials. Try another scene with HTTPS assets or use the preview thumbnail.") from last_err


def _get_aoi_bounds_4326(aoi: dict[str, Any]) -> tuple[float, float, float, float]:
    """Return (west, south, east, north) in EPSG:4326 from AOI GeoJSON."""
    # Use geojson utils or shapely
    try:
        from shapely.geometry import shape as _shape

        geom = aoi
        if aoi.get("type") == "Feature":
            geom = aoi.get("geometry") or aoi
        shp = _shape(geom)  # type: ignore
        west, south, east, north = shp.bounds
        return float(west), float(south), float(east), float(north)
    except Exception:
        # Fallback to manual
        if aoi.get("type") == "Polygon":
            coords = aoi["coordinates"][0]  # type: ignore
            lons = [c[0] for c in coords]  # type: ignore
            lats = [c[1] for c in coords]  # type: ignore
            return min(lons), min(lats), max(lons), max(lats)
        raise ValueError("Cannot extract bounds from AOI")


def process_bands(
    scene_assets: dict[str, Any],
    required_bands: list[str],
    scene_id: str,
    aoi: dict[str, Any] | None,
    target_resolution: int = 10,
    cloud_mask: bool = True,
) -> dict[str, Any]:
    """
    Download, clip, resample, align bands.
    Returns dict: {bands: {band: np.ndarray}, profile: rasterio profile, transform, crs, cloud_mask_arr, provenance}
    - bands are float32, scaled 0-10000 (not yet normalized)
    - aligned to same shape (reference band)
    - AOI clipped if provided
    - cloud_mask_arr is boolean valid mask if available
    """
    if not _HAS_RASTERIO:
        raise RuntimeError("rasterio not installed — required for spectral processing")

    from backend.spectral.bands import resolve_band_assets, get_cloud_asset_candidates

    # Resolve hrefs
    hrefs = resolve_band_assets(scene_assets, required_bands)
    cloud_candidates = get_cloud_asset_candidates(scene_assets)

    # Download bands
    local_paths: dict[str, Path] = {}
    for band, href in hrefs.items():
        local_paths[band] = _download_band(href, scene_id, band)

    # Also download SCL if cloud masking
    scl_path = None
    scl_href = None
    if cloud_mask and cloud_candidates:
        # Prefer SCL
        for key in ["SCL", "SCL_20m"]:
            if key in cloud_candidates:
                scl_href = cloud_candidates[key]
                try:
                    scl_path = _download_band(scl_href, scene_id, "SCL")
                    break
                except Exception as e:
                    logger.warning("Failed to download SCL for masking: %s", e)
                    scl_path = None

    # Open reference band to get profile and AOI window
    ref_band = required_bands[0]
    ref_path = local_paths[ref_band]
    bands_arrays: dict[str, np.ndarray] = {}
    ref_profile = None
    ref_crs = None
    ref_transform = None
    ref_shape = None
    window = None
    aoi_geom_reproj = None

    with rasterio.open(ref_path) as ref_ds:
        ref_profile = ref_ds.profile.copy()
        ref_crs = ref_ds.crs
        ref_transform = ref_ds.transform
        # Determine window for AOI
        if aoi:
            try:
                # Transform AOI from EPSG:4326 to ref_crs
                aoi_reproj = transform_geom("EPSG:4326", ref_crs, aoi)
                aoi_geom_reproj = aoi_reproj
                # Get bounds of reprojected AOI
                from shapely.geometry import shape as _shape

                shp = _shape(aoi_reproj)  # type: ignore
                west, south, east, north = shp.bounds
                # Add small buffer (10%)
                pad_x = (east - west) * 0.02
                pad_y = (north - south) * 0.02
                west -= pad_x
                east += pad_x
                south -= pad_y
                north += pad_y
                window = from_bounds(west, south, east, north, transform=ref_ds.transform)
                # Clamp window to dataset
                window = window.round_offsets().round_lengths()
                # Ensure within bounds
                window = window.crop(height=ref_ds.height, width=ref_ds.width)
            except Exception as e:
                logger.warning("Failed to compute AOI window, using full scene: %s", e)
                window = None
        # Read reference band with window and target resolution
        # If target resolution is 10 and ref is already 10, no resampling needed for ref
        # For other bands, we will resample to ref's shape
        if window:
            # Read with window, out_shape = window shape (already clipped)
            ref_data = ref_ds.read(1, window=window, masked=False)
            # Update transform for window
            window_transform = ref_ds.window_transform(window)
        else:
            ref_data = ref_ds.read(1, masked=False)
            window_transform = ref_ds.transform
        bands_arrays[ref_band] = ref_data.astype(np.float32)
        ref_shape = ref_data.shape
        # Save updated profile for output
        ref_profile.update(
            {
                "height": ref_shape[0],
                "width": ref_shape[1],
                "transform": window_transform,
                "crs": ref_crs,
                "dtype": "float32",
                "count": 1,
            }
        )

    # For other bands, read and reproject/resample to ref shape
    for band in required_bands[1:]:
        path = local_paths[band]
        with rasterio.open(path) as ds:
            # Determine window in this band's CRS (same as ref's CRS for Sentinel-2 UTM, but may differ resolution)
            # Use same AOI bounds but in this dataset
            if aoi and aoi_geom_reproj is not None:
                try:
                    # If same CRS, reuse window logic but need to compute window for this ds
                    from shapely.geometry import shape as _shape

                    shp = _shape(aoi_geom_reproj)
                    west, south, east, north = shp.bounds
                    pad_x = (east - west) * 0.02
                    pad_y = (north - south) * 0.02
                    west -= pad_x
                    east += pad_x
                    south -= pad_y
                    north += pad_y
                    win = from_bounds(west, south, east, north, transform=ds.transform)
                    win = win.round_offsets().round_lengths().crop(height=ds.height, width=ds.width)
                except Exception:
                    win = None
            else:
                win = None

            # Read data
            if win:
                data = ds.read(1, window=win, masked=False)
                src_transform = ds.window_transform(win) if win else ds.transform
            else:
                data = ds.read(1, masked=False)
                src_transform = ds.transform

            # If shape differs from ref, resample to ref_shape
            if data.shape != ref_shape:
                # Use reproject to resample
                dst = np.empty(ref_shape, dtype=np.float32)
                reproject(
                    source=data,
                    destination=dst,
                    src_transform=src_transform,
                    src_crs=ds.crs,
                    dst_transform=window_transform,  # type: ignore
                    dst_crs=ref_crs,
                    resampling=Resampling.bilinear,
                )
                bands_arrays[band] = dst
                logger.info("Resampled band %s from %s to %s (bilinear 10m)", band, data.shape, ref_shape)
            else:
                # Same shape but still need to ensure CRS alignment (if same, just copy)
                if ds.crs != ref_crs:
                    dst = np.empty(ref_shape, dtype=np.float32)
                    reproject(
                        source=data,
                        destination=dst,
                        src_transform=src_transform,
                        src_crs=ds.crs,
                        dst_transform=window_transform,  # type: ignore
                        dst_crs=ref_crs,
                        resampling=Resampling.bilinear,
                    )
                    bands_arrays[band] = dst
                else:
                    bands_arrays[band] = data.astype(np.float32)

    # Handle SCL cloud mask
    cloud_mask_arr = None
    cloud_applied = False
    if scl_path and scl_path.exists():
        try:
            with rasterio.open(scl_path) as scl_ds:
                # SCL is 20m, need to resample to ref_shape
                if aoi and aoi_geom_reproj is not None:
                    from shapely.geometry import shape as _shape

                    shp = _shape(aoi_geom_reproj)
                    west, south, east, north = shp.bounds
                    pad_x = (east - west) * 0.02
                    pad_y = (north - south) * 0.02
                    west -= pad_x
                    east += pad_x
                    south -= pad_y
                    north += pad_y
                    win = from_bounds(west, south, east, north, transform=scl_ds.transform)
                    win = win.round_offsets().round_lengths().crop(height=scl_ds.height, width=scl_ds.width)
                    scl_data = scl_ds.read(1, window=win, masked=False)
                    scl_transform = scl_ds.window_transform(win) if win else scl_ds.transform
                else:
                    scl_data = scl_ds.read(1, masked=False)
                    scl_transform = scl_ds.transform

                if scl_data.shape != ref_shape:
                    scl_resampled = np.empty(ref_shape, dtype=np.uint8)
                    reproject(
                        source=scl_data,
                        destination=scl_resampled,
                        src_transform=scl_transform,
                        src_crs=scl_ds.crs,
                        dst_transform=window_transform,  # type: ignore
                        dst_crs=ref_crs,
                        resampling=Resampling.nearest,
                    )
                    scl_data = scl_resampled

                from backend.spectral.masking import mask_from_scl

                cloud_mask_arr = mask_from_scl(scl_data, cloud_only=False)
                cloud_applied = True
                logger.info("Cloud mask applied from SCL, valid %.1f%%", float(cloud_mask_arr.mean() * 100))
        except Exception as e:
            logger.warning("Failed to process SCL mask: %s", e)
            cloud_mask_arr = None

    return {
        "bands": bands_arrays,
        "profile": ref_profile,
        "transform": window_transform,
        "crs": ref_crs,
        "shape": ref_shape,
        "cloud_mask": cloud_mask_arr,
        "cloud_applied": cloud_applied,
        "aoi_geom_reproj": aoi_geom_reproj,
        "window": window,
    }
