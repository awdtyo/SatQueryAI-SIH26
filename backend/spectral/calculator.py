"""Index calculator — pure numpy, safe division, nodata aware."""

from __future__ import annotations

import numpy as np


def _safe_divide(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    """Safe divide: where den==0 -> nan, else num/den."""
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.divide(num, den, out=np.full_like(num, np.nan, dtype=np.float32), where=den != 0)
        # Also where den is 0 or nan, result stays nan
        out = np.where(np.isfinite(out), out, np.nan)
    return out.astype(np.float32)


def calc_ndvi(b08: np.ndarray, b04: np.ndarray) -> np.ndarray:
    return _safe_divide(b08.astype(np.float32) - b04.astype(np.float32), b08.astype(np.float32) + b04.astype(np.float32))


def calc_ndwi(b03: np.ndarray, b08: np.ndarray) -> np.ndarray:
    return _safe_divide(b03.astype(np.float32) - b08.astype(np.float32), b03.astype(np.float32) + b08.astype(np.float32))


def calc_ndbi(b11: np.ndarray, b08: np.ndarray) -> np.ndarray:
    return _safe_divide(b11.astype(np.float32) - b08.astype(np.float32), b11.astype(np.float32) + b08.astype(np.float32))


def calc_ndmi(b08: np.ndarray, b11: np.ndarray) -> np.ndarray:
    return _safe_divide(b08.astype(np.float32) - b11.astype(np.float32), b08.astype(np.float32) + b11.astype(np.float32))


def calc_savi(b08: np.ndarray, b04: np.ndarray, L: float = 0.5) -> np.ndarray:
    b08f = b08.astype(np.float32)
    b04f = b04.astype(np.float32)
    num = b08f - b04f
    den = b08f + b04f + L
    return _safe_divide(num, den) * (1 + L)


def calc_bsi(b11: np.ndarray, b04: np.ndarray, b08: np.ndarray, b02: np.ndarray) -> np.ndarray:
    b11f = b11.astype(np.float32)
    b04f = b04.astype(np.float32)
    b08f = b08.astype(np.float32)
    b02f = b02.astype(np.float32)
    num = (b11f + b04f) - (b08f + b02f)
    den = (b11f + b04f) + (b08f + b02f)
    return _safe_divide(num, den)


# Dispatcher

_CALCULATORS = {
    "NDVI": lambda bands: calc_ndvi(bands["B08"], bands["B04"]),
    "NDWI": lambda bands: calc_ndwi(bands["B03"], bands["B08"]),
    "NDBI": lambda bands: calc_ndbi(bands["B11"], bands["B08"]),
    "NDMI": lambda bands: calc_ndmi(bands["B08"], bands["B11"]),
    "SAVI": lambda bands: calc_savi(bands["B08"], bands["B04"], L=0.5),
    "BSI": lambda bands: calc_bsi(bands["B11"], bands["B04"], bands["B08"], bands["B02"]),
}


def calculate_index(index: str, bands: dict[str, np.ndarray]) -> np.ndarray:
    key = index.strip().upper()
    if key not in _CALCULATORS:
        raise ValueError(f"Unsupported index '{index}'. Supported: {sorted(_CALCULATORS.keys())}")
    # Validate required bands present
    # Bands are expected as float arrays already (reflectance scaled)
    try:
        return _CALCULATORS[key](bands)
    except KeyError as e:
        raise ValueError(f"Missing required band for {key}: {e}") from e
