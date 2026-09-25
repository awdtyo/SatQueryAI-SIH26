"""Heuristic chart from PIL image — deterministic, no LLM hallucination.

Computes land-cover distribution via pixel color thresholds (RGB) on a
downsampled 256×256 image. No sklearn, no torch, ~0.02s on CPU.
Maps to simplified 5 bins that align with BigEarthNet taxonomy but are
human-readable for bar/pie charts. Values sum to 100.

Bullets remain LLM-generated; chart is measured.

This module is the single source of truth for class coverage percentages:
the same RGB threshold classifier feeds the chart, the VQA grounding
context and the execution trace (see compute_chart + compute_grid).
"""

from __future__ import annotations

from typing import Any

from PIL import Image
import numpy as np


# BigEarthNet-simplified labels for chart
_LABELS = ["vegetation", "water", "urban", "bare", "other"]

# Downsample resolution shared by compute_chart and compute_grid so that
# per-cell counts sum to the global counts exactly.
_GRID_SIZE_PX = 256


def _prepare(pil: Image.Image) -> np.ndarray:
    """Downsample to the shared 256×256 RGB working array (int16, HWC)."""
    img = pil.convert("RGB").resize((_GRID_SIZE_PX, _GRID_SIZE_PX), Image.BILINEAR)
    return np.array(img, dtype=np.int16)


def _class_masks(arr: np.ndarray) -> dict[str, np.ndarray]:
    """RGB threshold classification — SINGLE source of truth.

    Used by compute_chart (global coverage percentages) and compute_grid
    (coarse 3×3 spatial heuristic), so both always agree.

    Heuristic rules (RGB thresholds, fast numpy):
      vegetation: G dominant, G>80
      water:      B dominant, B>60
      urban:      low saturation gray 60<R<180, |R-G|<15, |G-B|<15
      bare/brown: R dominant, R>G, R>B, R>80, 40<G<120, B<80
      other:      remainder
    """
    r = arr[:, :, 0]
    g = arr[:, :, 1]
    b = arr[:, :, 2]

    veg = (g > r + 18) & (g > b + 8) & (g > 75)
    water = (b > r + 18) & (b > g + 8) & (b > 60)
    # urban gray: low saturation
    urban = (np.abs(r - g) < 14) & (np.abs(g - b) < 14) & (r > 55) & (r < 185) & (~veg) & (~water)
    # bare/brown: reddish/brownish
    bare = (r > g + 10) & (r > b + 10) & (r > 80) & (g > 35) & (g < 125) & (b < 85) & (~veg) & (~water) & (~urban)
    # other is remainder
    other = ~(veg | water | urban | bare)

    return {
        "vegetation": veg,
        "water": water,
        "urban": urban,
        "bare": bare,
        "other": other,
    }


def compute_grid(
    pil: Image.Image,
    grid_size: int = 3,
    min_cell_share: float = 0.4,
) -> list[dict[str, Any]]:
    """Coarse grid classification — SAME classifier as compute_chart.

    Splits the shared 256×256 working array into grid_size×grid_size cells and
    applies _class_masks once over the whole image, so per-cell counts sum to
    the global counts. No extra model, no pixel-level segmentation.

    Returns one entry per cell whose dominant named class (everything except
    "other") occupies at least min_cell_share of that cell — cells without
    that much evidence are omitted (never invent a location).

    Each entry: {"row": int, "col": int, "label": str,
                 "cell_percent": float, "image_percent": float}
    """
    try:
        arr = _prepare(pil)
        h, w = int(arr.shape[0]), int(arr.shape[1])
        total = h * w
        if total == 0 or grid_size < 1:
            return []
        masks = _class_masks(arr)
        named = {k: v for k, v in masks.items() if k != "other"}

        out: list[dict[str, Any]] = []
        for row in range(grid_size):
            r0, r1 = row * h // grid_size, (row + 1) * h // grid_size
            for col in range(grid_size):
                c0, c1 = col * w // grid_size, (col + 1) * w // grid_size
                cell_total = (r1 - r0) * (c1 - c0)
                if cell_total <= 0:
                    continue
                counts = {k: int(np.count_nonzero(v[r0:r1, c0:c1])) for k, v in named.items()}
                if not counts:
                    continue
                label = max(counts, key=lambda k: counts[k])  # dominant named class
                share = counts[label] / cell_total
                if share < min_cell_share:
                    continue  # insufficient evidence for this cell
                out.append(
                    {
                        "row": row,
                        "col": col,
                        "label": label,
                        "cell_percent": round(share * 100.0, 1),
                        "image_percent": round(counts[label] / total * 100.0, 1),
                    }
                )
        return out
    except Exception:
        return []


def compute_chart(pil: Image.Image, max_entries: int = 4) -> list[dict[str, float | str]]:
    """Return list[{'label': str, 'value': float}] percentages sum ~100.

    Classification thresholds live in _class_masks (shared with compute_grid).

    Sorted descending, top max_entries, tiny <2% merged into other.
    """
    try:
        # Downsample for speed
        arr = _prepare(pil)
        masks = _class_masks(arr)

        total = int(masks["other"].size)
        if total == 0:
            return [{"label": "other", "value": 100.0}]

        counts = {k: int(np.count_nonzero(v)) for k, v in masks.items()}

        # Convert to percentages
        perc = {k: (v / total) * 100.0 for k, v in counts.items()}

        # Merge tiny <2.5% into other (except keep at least 2 entries for visibility)
        # Keep other separate
        filtered: dict[str, float] = {}
        other_extra = 0.0
        for k, v in perc.items():
            if k == "other":
                continue
            if v < 2.5 and len([x for x in perc.values() if x >= 2.5]) >= 2:
                other_extra += v
            else:
                filtered[k] = v
        filtered["other"] = perc["other"] + other_extra

        # Remove zero entries
        filtered = {k: v for k, v in filtered.items() if v >= 0.8}

        # Sort descending, take top max_entries, merge rest into other
        sorted_items = sorted(filtered.items(), key=lambda x: x[1], reverse=True)
        if len(sorted_items) > max_entries:
            top = sorted_items[: max_entries - 1]
            rest = sorted_items[max_entries - 1 :]
            other_val = sum(v for _, v in rest)
            # Merge rest into other if other already exists, else keep label "other"
            has_other = any(k == "other" for k, _ in top)
            if has_other:
                top = [(k, v + (other_val if k == "other" else 0)) for k, v in top]
                # if other was not in top, need to add
                if not has_other and other_val > 0:
                    top.append(("other", other_val))
            else:
                top.append(("other", other_val))
            sorted_items = top

        # Renormalize to 100
        s = sum(v for _, v in sorted_items)
        if s == 0:
            return [{"label": "other", "value": 100.0}]
        chart = [{"label": k, "value": round((v / s) * 100.0, 1)} for k, v in sorted_items]
        # Adjust rounding drift to 100.0
        drift = round(100.0 - sum(d["value"] for d in chart), 1)  # type: ignore
        if chart and drift != 0:
            chart[0]["value"] = round(float(chart[0]["value"]) + drift, 1)  # type: ignore

        # Clamp 1-90 for display (keep 100 if single)
        if len(chart) == 1:
            chart[0]["value"] = 100.0
        else:
            for c in chart:
                c["value"] = max(1.0, min(90.0, float(c["value"])))  # type: ignore

        # Re-renormalize after clamp drift (simple proportional)
        if len(chart) > 1:
            s2 = sum(float(c["value"]) for c in chart)  # type: ignore
            if abs(s2 - 100.0) > 0.6:
                factor = 100.0 / s2
                for c in chart:
                    c["value"] = round(float(c["value"]) * factor, 1)  # type: ignore
                # fix drift again
                drift2 = round(100.0 - sum(float(c["value"]) for c in chart), 1)  # type: ignore
                if drift2 != 0:
                    chart[0]["value"] = round(float(chart[0]["value"]) + drift2, 1)  # type: ignore

        return chart  # type: ignore
    except Exception:
        # Fallback: never crash chart, return single other
        return [{"label": "other", "value": 100.0}]
