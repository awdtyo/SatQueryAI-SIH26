"""Centralized spectral index registry — add new indices here."""

from __future__ import annotations

from typing import Any

INDEX_REGISTRY: dict[str, dict[str, Any]] = {
    "NDVI": {
        "name": "NDVI",
        "description": "Normalized Difference Vegetation Index",
        "formula": "(NIR - RED) / (NIR + RED)",
        "required_bands": ["B08", "B04"],
        "band_roles": {"NIR": "B08", "RED": "B04"},
        "range": [-1.0, 1.0],
        "interpretation": {
            "<0": "Water / cloud / snow",
            "0-0.2": "Bare soil / sparse vegetation",
            "0.2-0.5": "Moderate vegetation",
            "0.5-1.0": "Dense vegetation",
        },
        "colormap": "RdYlGn",
        "visual": {"min": -1, "max": 1, "cmap": "RdYlGn", "label": "NDVI"},
        "sentinel_bands": {
            "B08": {"resolution": 10, "description": "NIR (842 nm)"},
            "B04": {"resolution": 10, "description": "Red (665 nm)"},
        },
    },
    "NDWI": {
        "name": "NDWI",
        "description": "Normalized Difference Water Index (McFeeters)",
        "formula": "(GREEN - NIR) / (GREEN + NIR)",
        "required_bands": ["B03", "B08"],
        "band_roles": {"GREEN": "B03", "NIR": "B08"},
        "range": [-1.0, 1.0],
        "interpretation": {
            "<0": "Non-water",
            "0-0.3": "Moist soil / sparse water",
            ">0.3": "Water body",
        },
        "colormap": "Blues",
        "visual": {"min": -1, "max": 1, "cmap": "Blues", "label": "NDWI"},
        "sentinel_bands": {
            "B03": {"resolution": 10, "description": "Green (560 nm)"},
            "B08": {"resolution": 10, "description": "NIR (842 nm)"},
        },
    },
    "NDBI": {
        "name": "NDBI",
        "description": "Normalized Difference Built-up Index",
        "formula": "(SWIR - NIR) / (SWIR + NIR)",
        "required_bands": ["B11", "B08"],
        "band_roles": {"SWIR": "B11", "NIR": "B08"},
        "range": [-1.0, 1.0],
        "interpretation": {
            "<0": "Vegetation / water",
            "0-0.3": "Mixed / bare",
            ">0.3": "Built-up",
        },
        "colormap": "Greys",
        "visual": {"min": -1, "max": 1, "cmap": "Greys", "label": "NDBI"},
        "sentinel_bands": {
            "B11": {"resolution": 20, "description": "SWIR (1610 nm)"},
            "B08": {"resolution": 10, "description": "NIR (842 nm)"},
        },
    },
    "NDMI": {
        "name": "NDMI",
        "description": "Normalized Difference Moisture Index",
        "formula": "(NIR - SWIR) / (NIR + SWIR)",
        "required_bands": ["B08", "B11"],
        "band_roles": {"NIR": "B08", "SWIR": "B11"},
        "range": [-1.0, 1.0],
        "interpretation": {
            "<0": "Dry / non-vegetated",
            "0-0.4": "Moderate moisture",
            ">0.4": "High canopy moisture",
        },
        "colormap": "BrBG",
        "visual": {"min": -1, "max": 1, "cmap": "BrBG", "label": "NDMI"},
        "sentinel_bands": {
            "B08": {"resolution": 10, "description": "NIR"},
            "B11": {"resolution": 20, "description": "SWIR"},
        },
    },
    "SAVI": {
        "name": "SAVI",
        "description": "Soil Adjusted Vegetation Index (L=0.5)",
        "formula": "((NIR - RED) / (NIR + RED + L)) * (1 + L), L=0.5",
        "required_bands": ["B08", "B04"],
        "band_roles": {"NIR": "B08", "RED": "B04"},
        "params": {"L": 0.5},
        "range": [-1.0, 1.0],
        "interpretation": {
            "<0": "Water / cloud",
            "0-0.2": "Bare soil",
            "0.2-0.5": "Sparse vegetation",
            ">0.5": "Dense vegetation (soil-corrected)",
        },
        "colormap": "YlGn",
        "visual": {"min": -1, "max": 1, "cmap": "YlGn", "label": "SAVI"},
        "sentinel_bands": {
            "B08": {"resolution": 10, "description": "NIR"},
            "B04": {"resolution": 10, "description": "Red"},
        },
    },
    "BSI": {
        "name": "BSI",
        "description": "Bare Soil Index",
        "formula": "((SWIR + RED) - (NIR + BLUE)) / ((SWIR + RED) + (NIR + BLUE))",
        "required_bands": ["B11", "B04", "B08", "B02"],
        "band_roles": {"SWIR": "B11", "RED": "B04", "NIR": "B08", "BLUE": "B02"},
        "range": [-1.0, 1.0],
        "interpretation": {
            "< -0.1": "Vegetation / water",
            "-0.1-0.1": "Mixed",
            ">0.1": "Bare soil / exposed",
        },
        "colormap": "YlOrBr",
        "visual": {"min": -1, "max": 1, "cmap": "YlOrBr", "label": "BSI"},
        "sentinel_bands": {
            "B11": {"resolution": 20, "description": "SWIR"},
            "B04": {"resolution": 10, "description": "Red"},
            "B08": {"resolution": 10, "description": "NIR"},
            "B02": {"resolution": 10, "description": "Blue (490 nm)"},
        },
    },
}

# Aliases for NL routing (vegetation health -> NDVI etc.)
INDEX_ALIASES: dict[str, str] = {
    "vegetation": "NDVI",
    "vegetation health": "NDVI",
    "veg": "NDVI",
    "ndvi": "NDVI",
    "water": "NDWI",
    "ndwi": "NDWI",
    "moisture": "NDMI",
    "ndmi": "NDMI",
    "built-up": "NDBI",
    "built up": "NDBI",
    "urban": "NDBI",
    "ndbi": "NDBI",
    "soil adjusted": "SAVI",
    "savi": "SAVI",
    "bare soil": "BSI",
    "bare": "BSI",
    "bsi": "BSI",
    "soil": "SAVI",
}


def get_index_info(name: str) -> dict[str, Any] | None:
    key = name.strip().upper()
    if key in INDEX_REGISTRY:
        return INDEX_REGISTRY[key]
    # try alias lookup
    low = name.strip().lower()
    if low in INDEX_ALIASES:
        return INDEX_REGISTRY[INDEX_ALIASES[low]]
    return None


def list_indices() -> list[str]:
    return sorted(INDEX_REGISTRY.keys())


def resolve_index_name(query: str) -> str | None:
    """Light NL resolver — returns canonical index name or None."""
    q = query.lower()
    # Explicit index names first
    for cand in ["ndvi", "ndwi", "ndbi", "ndmi", "savi", "bsi"]:
        if cand in q:
            return cand.upper()
    # Phrases
    if "vegetation" in q and ("health" in q or "ndvi" in q or "index" in q):
        return "NDVI"
    if "water" in q and ("index" in q or "ndwi" in q):
        return "NDWI"
    if "built" in q or "urban" in q or "ndbi" in q:
        return "NDBI"
    if "moisture" in q or "ndmi" in q:
        return "NDMI"
    if "bare soil" in q or " bsi " in f" {q} ":
        return "BSI"
    if "soil" in q and "adjusted" in q:
        return "SAVI"
    if "soil" in q and "bare" not in q:
        return "SAVI"
    return None
