"""Heuristic chart from PIL image — deterministic, no LLM hallucination.

Computes land-cover distribution via pixel color thresholds (RGB) on a
downsampled 256×256 image. No sklearn, no torch, ~0.02s on CPU.
Maps to simplified 5 bins that align with BigEarthNet taxonomy but are
human-readable for bar/pie charts. Values sum to 100.

Bullets remain LLM-generated; chart is measured.
"""

from __future__ import annotations

from PIL import Image
import numpy as np


# BigEarthNet-simplified labels for chart
_LABELS = ["vegetation", "water", "urban", "bare", "other"]


def compute_chart(pil: Image.Image, max_entries: int = 4) -> list[dict[str, float | str]]:
    """Return list[{'label': str, 'value': float}] percentages sum ~100.

    Heuristic rules (RGB thresholds, fast numpy):
      vegetation: G dominant, G>80
      water:      B dominant, B>60
      urban:     low saturation gray 60<R<180, |R-G|<15, |G-B|<15
      bare/brown: R dominant, R>G, R>B, R>80, 40<G<120, B<80
      other:     remainder

    Sorted descending, top max_entries, tiny <2% merged into other.
    """
    try:
        # Downsample for speed
        img = pil.convert("RGB").resize((256, 256), Image.BILINEAR)
        arr = np.array(img, dtype=np.int16)  # HWC 0-255
        r = arr[:, :, 0]
        g = arr[:, :, 1]
        b = arr[:, :, 2]

        total = r.size
        if total == 0:
            return [{"label": "other", "value": 100.0}]

        # Masks — vectorized boolean arrays
        veg = (g > r + 18) & (g > b + 8) & (g > 75)
        water = (b > r + 18) & (b > g + 8) & (b > 60)
        # urban gray: low saturation
        urban = (np.abs(r - g) < 14) & (np.abs(g - b) < 14) & (r > 55) & (r < 185) & (~veg) & (~water)
        # bare/brown: reddish/brownish
        bare = (r > g + 10) & (r > b + 10) & (r > 80) & (g > 35) & (g < 125) & (b < 85) & (~veg) & (~water) & (~urban)

        # other is remainder
        other = ~(veg | water | urban | bare)

        counts = {
            "vegetation": int(np.count_nonzero(veg)),
            "water": int(np.count_nonzero(water)),
            "urban": int(np.count_nonzero(urban)),
            "bare": int(np.count_nonzero(bare)),
            "other": int(np.count_nonzero(other)),
        }

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
