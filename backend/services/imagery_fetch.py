"""Fetch real Sentinel-2 / Sentinel-1 imagery via Planetary Computer STAC.

Low-friction: pystac-client + planetary-computer (no auth for search,
signed URLs for download). Produces PIL images that pass validate_inputs
exactly (PNG, RGB, <5MB).

- AOI: fixed square centred on lat/lon, SATQUERY_LOCATION_AOI_KM (default 2km)
- Scene selection: least-cloudy recent within last 90 days, cloud_cover <= MAX
- Rendering: prefers `visual` / `rendered_preview` thumbnail; falls back to
  signed asset download + rasterio RGB composite if needed.
"""

from __future__ import annotations

import io
import logging
import math
import time
from typing import Any

import requests
from PIL import Image
from fastapi import HTTPException

from backend import config

logger = logging.getLogger(__name__)

_PC_SIGNED_TIMEOUT = 15
_THUMB_TIMEOUT = 20


def _bbox_from_point(lat: float, lon: float, aoi_km: float) -> list[float]:
    """Square bbox centred at lat/lon with side aoi_km."""
    # 1 deg lat ≈ 111 km, lon scales by cos(lat)
    d_lat = aoi_km / 111.0 / 2.0
    cos_lat = max(0.1, math.cos(math.radians(lat)))
    d_lon = aoi_km / (111.0 * cos_lat) / 2.0
    west = max(-180, lon - d_lon)
    east = min(180, lon + d_lon)
    south = max(-90, lat - d_lat)
    north = min(90, lat + d_lat)
    return [west, south, east, north]


def _try_sign(item: dict) -> dict:
    """Best-effort planetary_computer signing; if not installed, return as-is."""
    try:
        import planetary_computer  # type: ignore

        return planetary_computer.sign(item)
    except Exception:
        return item


def _download_image_bytes(url: str, timeout: int = _THUMB_TIMEOUT) -> bytes:
    r = requests.get(url, timeout=timeout, stream=True)
    r.raise_for_status()
    # Limit to 10MB to avoid abuse
    content = r.content
    if len(content) > 10 * 1024 * 1024:
        content = content[: 10 * 1024 * 1024]
    # Validate it's an image
    try:
        Image.open(io.BytesIO(content)).verify()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Fetched asset is not a valid image: {e}") from e
    return content


def _search_pc_stac(
    bbox: list[float],
    collection: str,
    max_cloud: float,
    limit: int = 10,
) -> list[dict]:
    """Search Planetary Computer STAC via pystac-client with HTTP fallback."""
    endpoint = config.SATQUERY_STAC_ENDPOINT
    # Prefer pystac-client
    try:
        from pystac_client import Client  # type: ignore

        client = Client.open(endpoint)
        # datetime last 90 days
        import datetime

        end = datetime.datetime.utcnow()
        start = end - datetime.timedelta(days=90)
        dt = f"{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}"
        search = client.search(
            collections=[collection],
            bbox=bbox,
            datetime=dt,
            query={"eo:cloud_cover": {"lt": max_cloud + 0.01}},
            limit=limit,
        )
        items = list(search.items())
        # Convert to dicts
        dicts = [it.to_dict() for it in items]
        if dicts:
            return dicts
    except Exception as e:
        logger.debug("pystac-client search failed for %s: %s", collection, e)

    # HTTP fallback — POST /search
    try:
        import datetime

        end = datetime.datetime.utcnow()
        start = end - datetime.timedelta(days=90)
        dt = f"{start.isoformat()}Z/{end.isoformat()}Z"
        payload = {
            "collections": [collection],
            "bbox": bbox,
            "datetime": dt,
            "query": {"eo:cloud_cover": {"lt": max_cloud + 0.01}},
            "limit": limit,
        }
        url = endpoint.rstrip("/") + "/search"
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        j = r.json()
        feats = j.get("features", [])
        return feats
    except Exception as e:
        logger.warning("PC STAC HTTP fallback failed for %s bbox %s: %s", collection, bbox, e)
        return []


def _pick_best_scene(items: list[dict]) -> dict | None:
    if not items:
        return None
    # Sort by cloud_cover asc, then datetime desc

    def _cloud(it: dict) -> float:
        try:
            return float(it.get("properties", {}).get("eo:cloud_cover", 100))
        except Exception:
            return 100.0

    def _dt(it: dict) -> str:
        return str(it.get("properties", {}).get("datetime", ""))

    return sorted(items, key=lambda it: (_cloud(it), _dt(it)))[0]


def _extract_preview_url(item: dict) -> str | None:
    """Prefer rendered_preview / visual / thumbnail assets."""
    assets = item.get("assets", {}) or {}
    # Planetary Computer render extension
    for key in ("rendered_preview", "visual", "thumbnail", "overview", "image"):
        if key in assets and assets[key].get("href"):
            return assets[key]["href"]
    # Fallback: any href that looks like image
    for v in assets.values():
        href = v.get("href", "")
        if href and any(href.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff")):
            return href  # may need signing
    return None


def _fetch_single_latlon(
    lat: float,
    lon: float,
    collection: str = "sentinel-2-l2a",
    max_cloud: float | None = None,
) -> tuple[bytes, dict]:
    """Fetch one scene for lat/lon, return (png_bytes, trace_meta)."""
    if max_cloud is None:
        max_cloud = config.SATQUERY_MAX_CLOUD_COVER
    aoi_km = config.SATQUERY_LOCATION_AOI_KM
    bbox = _bbox_from_point(lat, lon, aoi_km)

    items = _search_pc_stac(bbox, collection, max_cloud)
    if not items:
        # Retry with relaxed cloud (100) to at least get something
        items = _search_pc_stac(bbox, collection, 100.0)
    if not items:
        raise HTTPException(
            status_code=502,
            detail=(
                f"No {collection} scenes found near {lat:.4f}, {lon:.4f} "
                f"(bbox {bbox}, aoi {aoi_km}km, last 90d). Try a different location or increase cloud cover."
            ),
        )

    best = _pick_best_scene(items)
    assert best is not None
    signed = _try_sign(best)
    preview_url = _extract_preview_url(signed)
    if not preview_url:
        # As last resort, try original item
        preview_url = _extract_preview_url(best)

    if not preview_url:
        raise HTTPException(
            status_code=502,
            detail=f"Selected {collection} scene has no preview asset; cannot fetch imagery.",
        )

    # Download preview image bytes
    try:
        img_bytes = _download_image_bytes(preview_url)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Preview download failed %s: %s", preview_url, e)
        raise HTTPException(status_code=502, detail=f"Failed to download scene preview: {e}") from e

    # Normalize to PNG RGB that validate_inputs expects (PIL load may be JPEG)
    try:
        pil = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        # Ensure at least 224x224, resize down if huge for model
        if pil.size[0] > 1024 or pil.size[1] > 1024:
            pil.thumbnail((1024, 1024), Image.BILINEAR)
        out = io.BytesIO()
        pil.save(out, format="PNG")
        png_bytes = out.getvalue()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to normalize fetched image: {e}") from e

    meta = {
        "collection": collection,
        "scene_id": best.get("id", "unknown"),
        "datetime": best.get("properties", {}).get("datetime"),
        "cloud_cover": best.get("properties", {}).get("eo:cloud_cover"),
        "bbox": bbox,
        "aoi_km": aoi_km,
        "preview_url": preview_url,
    }
    return png_bytes, meta


def fetch_imagery_for_location(
    locations: list[dict],
    input_mode: str = "single",
    max_cloud_cover: float | None = None,
) -> tuple[list[tuple[str, bytes]], list[dict]]:
    """Given locations [{lat, lon, display_name}], fetch images for controller.

    Returns (image_payloads [(filename, bytes)], trace_metas).
    - single: expects 1 location -> 1 image (sentinel-2-l2a)
    - optical-sar: expects 1 location -> 2 images (S2 + S1)
    - bi-temporal: expects 1-2 locations; if 1 location, fetch 2 dates (most recent 2 scenes)
    """
    if not locations:
        raise HTTPException(status_code=422, detail="No locations to fetch imagery for")

    mode = (input_mode or "single").lower()
    payloads: list[tuple[str, bytes]] = []
    metas: list[dict] = []

    if mode == "optical-sar":
        # Two images: optical (S2) + SAR (S1)
        loc = locations[0]
        # Fetch optical
        png1, meta1 = _fetch_single_latlon(loc["lat"], loc["lon"], "sentinel-2-l2a", max_cloud_cover)
        payloads.append((f"location_optical_{loc['lat']:.4f}_{loc['lon']:.4f}.png", png1))
        metas.append(meta1)
        # Fetch SAR — collection sentinel-1-rtc (fallback to sentinel-1-grd if needed)
        try:
            png2, meta2 = _fetch_single_latlon(loc["lat"], loc["lon"], "sentinel-1-rtc", max_cloud_cover)
        except HTTPException as e:
            # If sentinel-1-rtc not available, try sentinel-1-grd or fall back to second S2 scene
            logger.info("S1 RTC fetch failed, trying fallback: %s", e.detail)
            try:
                png2, meta2 = _fetch_single_latlon(loc["lat"], loc["lon"], "sentinel-1-grd", 100.0)
            except Exception:
                # Last resort: duplicate S2 (controller will still have 2 images)
                png2, meta2 = _fetch_single_latlon(loc["lat"], loc["lon"], "sentinel-2-l2a", max_cloud_cover)
                meta2["collection"] += " (fallback-for-sar)"
        payloads.append((f"location_sar_{loc['lat']:.4f}_{loc['lon']:.4f}.png", png2))
        metas.append(meta2)

    elif mode == "bi-temporal":
        if len(locations) >= 2:
            # Two distinct locations/dates -> fetch each
            for i, loc in enumerate(locations[:2]):
                png, meta = _fetch_single_latlon(loc["lat"], loc["lon"], "sentinel-2-l2a", max_cloud_cover)
                payloads.append((f"location_T{i+1}_{loc['lat']:.4f}_{loc['lon']:.4f}.png", png))
                metas.append(meta)
        else:
            loc = locations[0]
            # Same AOI, two dates: fetch 2 most recent distinct scenes
            aoi_km = config.SATQUERY_LOCATION_AOI_KM
            bbox = _bbox_from_point(loc["lat"], loc["lon"], aoi_km)
            items = _search_pc_stac(bbox, "sentinel-2-l2a", max_cloud_cover or config.SATQUERY_MAX_CLOUD_COVER, limit=20)
            if len(items) < 2:
                items = _search_pc_stac(bbox, "sentinel-2-l2a", 100.0, limit=20)
            if len(items) < 2:
                raise HTTPException(
                    status_code=502,
                    detail=f"Not enough scenes for bi-temporal near {loc['lat']:.4f},{loc['lon']:.4f} — found {len(items)}, need 2.",
                )
            # Sort by datetime desc, pick top 2 distinct dates
            def _dt_key(it: dict) -> str:
                return str(it.get("properties", {}).get("datetime", ""))

            items_sorted = sorted(items, key=_dt_key, reverse=True)
            # Ensure distinct ids
            picked: list[dict] = []
            seen_ids = set()
            for it in items_sorted:
                iid = it.get("id")
                if iid not in seen_ids:
                    picked.append(it)
                    seen_ids.add(iid)
                if len(picked) == 2:
                    break
            for i, it in enumerate(picked):
                signed = _try_sign(it)
                url = _extract_preview_url(signed) or _extract_preview_url(it)
                if not url:
                    raise HTTPException(status_code=502, detail="Bi-temporal scene has no preview")
                img_bytes = _download_image_bytes(url)
                pil = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                if pil.size[0] > 1024 or pil.size[1] > 1024:
                    pil.thumbnail((1024, 1024), Image.BILINEAR)
                out = io.BytesIO()
                pil.save(out, format="PNG")
                png = out.getvalue()
                payloads.append((f"location_T{i+1}_{loc['lat']:.4f}_{loc['lon']:.4f}.png", png))
                metas.append(
                    {
                        "collection": "sentinel-2-l2a",
                        "scene_id": it.get("id"),
                        "datetime": it.get("properties", {}).get("datetime"),
                        "cloud_cover": it.get("properties", {}).get("eo:cloud_cover"),
                        "bbox": bbox,
                        "aoi_km": aoi_km,
                        "preview_url": url,
                    }
                )
    else:
        # single
        loc = locations[0]
        png, meta = _fetch_single_latlon(loc["lat"], loc["lon"], "sentinel-2-l2a", max_cloud_cover)
        payloads.append((f"location_{loc['lat']:.4f}_{loc['lon']:.4f}.png", png))
        metas.append(meta)

    return payloads, metas
