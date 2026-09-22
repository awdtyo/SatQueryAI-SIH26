"""Statistics calculator for index rasters — valid pixels only."""

from __future__ import annotations

import numpy as np


def calculate_stats(arr: np.ndarray) -> dict[str, float | int]:
    """
    arr: 2D float32 with nan for masked/nodata
    Returns dict with min, max, mean, median, std, valid_pixels, masked_pixels, valid_pct
    """
    flat = arr.flatten()
    # Remove nan
    valid = flat[np.isfinite(flat)]
    total = flat.size
    valid_count = int(valid.size)
    masked = total - valid_count
    valid_pct = float(valid_count / total * 100) if total else 0.0
    masked_pct = float(masked / total * 100) if total else 0.0

    if valid_count == 0:
        return {
            "min": float("nan"),
            "max": float("nan"),
            "mean": float("nan"),
            "median": float("nan"),
            "std": float("nan"),
            "valid_pixels": 0,
            "masked_pixels": int(masked),
            "valid_pct": 0.0,
            "masked_pct": masked_pct,
        }

    return {
        "min": float(np.nanmin(valid)),
        "max": float(np.nanmax(valid)),
        "mean": float(np.nanmean(valid)),
        "median": float(np.nanmedian(valid)),
        "std": float(np.nanstd(valid)),
        "valid_pixels": valid_count,
        "masked_pixels": int(masked),
        "valid_pct": float(round(valid_pct, 2)),
        "masked_pct": float(round(masked_pct, 2)),
    }
