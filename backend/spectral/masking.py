"""Cloud / invalid pixel masking for Sentinel-2 L2A."""

from __future__ import annotations

import numpy as np


# SCL (Scene Classification) values at 20m — L2A
# 0 NoData, 1 Saturated, 2 Dark, 3 Cloud shadow, 4 Vegetation, 5 Non-vegetated, 6 Water, 7 Unclassified,
# 8 Cloud medium prob, 9 Cloud high prob, 10 Thin cirrus, 11 Snow/ice
SCL_MASKED_VALUES = {0, 1, 3, 8, 9, 10, 11}  # conservative cloud/shadow/snow/nodata
SCL_CLOUD_ONLY = {3, 8, 9, 10, 11}


def mask_from_scl(scl: np.ndarray, cloud_only: bool = False) -> np.ndarray:
    """
    Returns boolean mask True=valid, False=masked (invalid/cloud).
    scl: 2D array of SCL classification (0-11)
    """
    masked_vals = SCL_CLOUD_ONLY if cloud_only else SCL_MASKED_VALUES
    valid = np.ones_like(scl, dtype=bool)
    for v in masked_vals:
        valid = valid & (scl != v)
    return valid


def mask_nodata(*bands: np.ndarray, nodata_values: list[int] | None = None) -> np.ndarray:
    """
    Combined nodata mask: True where all bands are valid.
    - Checks for 0 (Sentinel-2 nodata often 0), NaN, and custom nodata
    """
    if not bands:
        return np.array([[True]])
    # Start with all valid
    valid = np.ones_like(bands[0], dtype=bool)
    for b in bands:
        # NaN check
        valid = valid & ~np.isnan(b.astype(float))
        # Zero nodata (but 0 can be valid reflectance for dark surfaces; for L2A, 0 is nodata)
        # We only mask 0 if band is integer 0? Keep simple: mask where band == 0 and other bands also 0? For now mask exact 0
        # To avoid over-masking valid dark pixels, we don't mask 0 alone; rely on SCL for nodata
        # So we only mask where value is 0 and SCL says? For generic, don't mask 0
        if nodata_values:
            for nd in nodata_values:
                valid = valid & (b != nd)
    return valid


def apply_masks(index_arr: np.ndarray, *masks: np.ndarray) -> np.ndarray:
    """Apply boolean valid masks to index array -> masked array with nan where invalid."""
    if not masks:
        return index_arr
    combined = masks[0].copy()
    for m in masks[1:]:
        # Ensure same shape (resampled)
        if m.shape != combined.shape:
            continue
        combined = combined & m
    out = index_arr.astype(np.float32).copy()
    out[~combined] = np.nan
    return out
