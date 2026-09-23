"""Band resolver — maps index -> required STAC assets (real, no fake download)."""

from __future__ import annotations

import logging
from typing import Any

from .registry import INDEX_REGISTRY, get_index_info

logger = logging.getLogger(__name__)

# Known STAC asset aliases (case-insensitive, CDSE variations)
_ASSET_ALIASES = {
    "B02": ["B02", "B02_10m", "blue", "BLUE"],
    "B03": ["B03", "B03_10m", "green", "GREEN"],
    "B04": ["B04", "B04_10m", "red", "RED"],
    "B08": ["B08", "B08_10m", "nir", "NIR", "B8A"],  # B8A is 20m different band, fallback only if B08 missing? Keep strict
    "B11": ["B11", "B11_20m", "swir", "SWIR", "SWIR1"],
    "B02_60": ["B02"],
}

# Resolution hint per band (for resampling doc)
BAND_RESOLUTIONS = {"B02": 10, "B03": 10, "B04": 10, "B08": 10, "B11": 20}


def resolve_band_assets(scene_assets: dict[str, Any], required_bands: list[str]) -> dict[str, str]:
    """
    Resolve required bands to hrefs from scene.assets (real STAC).
    - Case-insensitive key match
    - Validates all required bands exist
    - Raises ValueError with clear message if missing
    """
    # Normalize scene assets to upper keys
    norm = {k.upper(): v for k, v in scene_assets.items()}
    # Also handle href dicts vs strings
    def get_href(val: Any) -> str | None:
        if isinstance(val, str):
            return val
        if isinstance(val, dict) and "href" in val:
            return str(val["href"])
        return None

    resolved: dict[str, str] = {}
    missing: list[str] = []
    for band in required_bands:
        band_up = band.upper()
        candidates = _ASSET_ALIASES.get(band_up, [band_up])
        href = None
        for cand in candidates:
            if cand.upper() in norm:
                raw = norm[cand.upper()]
                href = get_href(raw) or (raw if isinstance(raw, str) else None)
                if href:
                    break
            # Also try direct case-sensitive
            if cand in scene_assets:
                raw = scene_assets[cand]
                href = get_href(raw) or (raw if isinstance(raw, str) else None)
                if href:
                    break
        if href:
            resolved[band_up] = href
        else:
            missing.append(band_up)

    if missing:
        available = sorted(scene_assets.keys())
        raise ValueError(
            f"Missing required band(s) {missing} for index. Available assets: {available}. "
            f"Scene may not have all bands at expected keys; check STAC collection sentinel-2-l2a."
        )
    logger.info("BandResolver: resolved %s -> %s", required_bands, list(resolved.keys()))
    return resolved


def get_required_bands(index: str) -> list[str]:
    info = get_index_info(index)
    if not info:
        raise ValueError(f"Unsupported index '{index}'. Supported: {sorted(INDEX_REGISTRY.keys())}")
    return list(info["required_bands"])


def get_cloud_asset_candidates(scene_assets: dict[str, Any]) -> dict[str, str]:
    """Inspect STAC for cloud/quality assets (SCL, QA60, etc.)."""
    candidates = {}
    for key in ["SCL", "SCL_20m", "QA60", "MSK_CLDPRB", "MSK_SNWPRB"]:
        for k, v in scene_assets.items():
            if k.upper() == key.upper():
                href = v if isinstance(v, str) else v.get("href") if isinstance(v, dict) else None
                if href:
                    candidates[key] = str(href)
    return candidates
