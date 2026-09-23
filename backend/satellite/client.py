"""CDSE STAC client — pystac-client with fallback to plain HTTP."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from .models import RetrievalRequest, SatelliteScene

logger = logging.getLogger(__name__)

CDSE_STAC_URL = os.getenv("SATQUERY_STAC_URL", "https://stac.dataspace.copernicus.eu/v1")
DEFAULT_TIMEOUT = int(os.getenv("SATQUERY_STAC_TIMEOUT", "20"))

# Preferred assets to surface first (but we return all)
_PREFERRED_ASSETS = ["B02", "B03", "B04", "B08", "B11", "B12", "visual", "preview", "thumbnail", "overview", "rendered_preview"]


def _extract_thumbnail(assets: dict[str, Any]) -> str | None:
    # Try common thumbnail keys
    for k in ("thumbnail", "preview", "overview", "rendered_preview", "visual"):
        if k in assets and isinstance(assets[k], dict):
            href = assets[k].get("href")
            if href:
                return href
    # fallback: any asset with type image
    for v in assets.values():
        if isinstance(v, dict) and "href" in v:
            href = v["href"]
            t = v.get("type", "")
            if "image" in t:
                return href
    return None


def _parse_stac_item(item: dict[str, Any]) -> SatelliteScene | None:
    try:
        item_id = str(item.get("id") or item.get("properties", {}).get("id") or "unknown")
        collection = str(item.get("collection") or item.get("properties", {}).get("collection") or "sentinel-2-l2a")
        props = item.get("properties") or {}
        # datetime
        dt_raw = props.get("datetime") or item.get("datetime")
        dt = None
        if dt_raw:
            try:
                from datetime import datetime

                # Handle Z suffix
                s = str(dt_raw).replace("Z", "+00:00")
                dt = datetime.fromisoformat(s)
            except Exception:
                dt = None
        platform = props.get("platform") or props.get("constellation") or props.get("sat:platform")
        # processing level: try various keys
        proc = props.get("processing:level") or props.get("s2:processing_level") or props.get("processingLevel") or None
        if not proc and "l2a" in collection.lower():
            proc = "L2A"
        # cloud cover
        cloud = props.get("eo:cloud_cover")
        if cloud is None:
            cloud = props.get("cloud_cover") or props.get("s2:cloud_cover")
        try:
            cloud_f = float(cloud) if cloud is not None else None
        except Exception:
            cloud_f = None

        geometry = item.get("geometry")
        bbox = item.get("bbox")
        assets_raw = item.get("assets") or {}
        assets: dict[str, str] = {}
        for k, v in assets_raw.items():
            href: str | None = None
            if isinstance(v, dict):
                # Prefer HTTPS alternate if the primary href is s3:// (CDSE often provides both)
                # Structure: {"href": "s3://...", "alternate": {"https": {"href": "https://..."}, "s3": {...}}}
                raw_href = v.get("href")
                # Check alternate for https
                alt = v.get("alternate")
                if isinstance(alt, dict):
                    for alt_key in ("https", "HTTPS", "http"):
                        alt_entry = alt.get(alt_key)
                        if isinstance(alt_entry, dict) and alt_entry.get("href"):
                            alt_href = str(alt_entry["href"])
                            if alt_href.startswith("https://"):
                                href = alt_href
                                break
                    # Fallback: any alternate with https href
                    if not href:
                        for alt_val in alt.values():
                            if isinstance(alt_val, dict) and isinstance(alt_val.get("href"), str) and alt_val["href"].startswith("https://"):
                                href = str(alt_val["href"])
                                break
                if not href and isinstance(raw_href, str):
                    href = str(raw_href)
                # If href is still s3:// and alternate had https, prefer https (already handled)
                # Otherwise keep s3 href — processor will try https conversion / rasterio fallback
            elif isinstance(v, str):
                href = v
            if href:
                assets[k] = href
        thumb = _extract_thumbnail(assets_raw)

        # metadata passthrough useful fields
        meta = {k: v for k, v in props.items() if k in ("eo:cloud_cover", "platform", "instruments", "s2:datastrip_id", "s2:product_uri", "created", "updated")}

        return SatelliteScene(
            id=item_id,
            collection=collection,
            datetime=dt,
            platform=str(platform) if platform else None,
            processing_level=str(proc) if proc else None,
            cloud_cover=cloud_f,
            geometry=geometry,
            bbox=[float(x) for x in bbox] if isinstance(bbox, (list, tuple)) else None,
            thumbnail=thumb,
            assets=assets,
            metadata=meta,
        )
    except Exception as e:
        logger.warning("Failed to parse STAC item %s: %s", item.get("id"), e)
        return None


def _search_via_pystac(req: RetrievalRequest) -> list[dict[str, Any]]:
    """Try pystac_client first."""
    try:
        from pystac_client import Client  # type: ignore

        client = Client.open(CDSE_STAC_URL, timeout=DEFAULT_TIMEOUT)
        search = client.search(
            collections=[req.collection],
            intersects=req.geometry,
            datetime=req.stac_datetime(),
            query={"eo:cloud_cover": {"lte": float(req.max_cloud_cover)}},
            max_items=req.max_results,
        )
        # Use get_items or item_collection
        items = list(search.items())
        # Convert pystac Items to dicts via to_dict()
        out: list[dict[str, Any]] = []
        for it in items:
            try:
                d = it.to_dict() if hasattr(it, "to_dict") else dict(it)  # type: ignore
                out.append(d)
            except Exception:
                # Fallback: treat as dict
                out.append(dict(it))  # type: ignore
        logger.info("CDSE pystac search: %d items for %s %s", len(out), req.collection, req.stac_datetime())
        return out
    except Exception as e:
        logger.debug("pystac_client search failed, falling back to HTTP: %s", e)
        raise


def _search_via_http(req: RetrievalRequest) -> list[dict[str, Any]]:
    """Plain HTTP POST to /search."""
    try:
        import requests  # type: ignore
    except ImportError as e:
        raise RuntimeError("requests not installed and pystac_client unavailable") from e

    url = f"{CDSE_STAC_URL.rstrip('/')}/search"
    body: dict[str, Any] = {
        "collections": [req.collection],
        "intersects": req.geometry if req.geometry.get("type") not in ("Feature", "FeatureCollection") else _extract_geometry_for_search(req.geometry),
        "datetime": req.stac_datetime(),
        "query": {"eo:cloud_cover": {"lte": float(req.max_cloud_cover)}},
        "limit": int(req.max_results),
    }
    # Clean Feature wrappers for intersects
    if body["intersects"] and body["intersects"].get("type") in ("Feature", "FeatureCollection"):
        body["intersects"] = _extract_geometry_for_search(body["intersects"])
    logger.info("CDSE HTTP search POST %s collection=%s dt=%s cloud<=%s limit=%s", url, req.collection, body["datetime"], req.max_cloud_cover, req.max_results)
    resp = requests.post(url, json=body, timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    # STAC FeatureCollection
    features = data.get("features") or data.get("items") or []
    logger.info("CDSE HTTP search: %d features", len(features))
    return features


def _extract_geometry_for_search(g: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(g, dict):
        return g
    t = g.get("type")
    if t == "Feature":
        return g.get("geometry") or g
    if t == "FeatureCollection":
        feats = g.get("features") or []
        if feats:
            return feats[0].get("geometry") or feats[0]
    return g


def search_cdse(req: RetrievalRequest) -> list[SatelliteScene]:
    """
    Unified CDSE search — tries pystac_client, falls back to HTTP.
    Returns parsed SatelliteScene list (may be empty).
    Raises on network/provider failure with descriptive message.
    """
    start = time.time()
    raw_items: list[dict[str, Any]] = []
    last_err: Exception | None = None

    # Try pystac first if available
    try:
        raw_items = _search_via_pystac(req)
    except Exception as e:
        last_err = e
        logger.info("pystac fallback to HTTP due to: %s", e)
        try:
            raw_items = _search_via_http(req)
        except Exception as e2:
            last_err = e2
            logger.error("CDSE search failed (both pystac and HTTP): %s", e2)
            raise RuntimeError(f"Satellite data provider temporarily unavailable: {e2}") from e2

    scenes: list[SatelliteScene] = []
    for it in raw_items:
        sc = _parse_stac_item(it)
        if sc:
            scenes.append(sc)

    elapsed = int((time.time() - start) * 1000)
    logger.info("CDSE parse: %d scenes parsed in %dms (raw %d)", len(scenes), elapsed, len(raw_items))
    return scenes
