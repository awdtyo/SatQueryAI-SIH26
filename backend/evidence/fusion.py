"""Evidence fusion — combine specialist outputs, detect conflicts."""

from __future__ import annotations

from typing import Any

from backend.evidence.models import Evidence


def fuse_evidence(evidence_lists: list[list[dict[str, Any] | Evidence]], specialist_results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Fuse evidence from multiple specialists.

    Returns dict with agreement, fused evidence, conflicts.
    Does NOT force agreement.
    """
    fused: list[dict[str, Any]] = []
    for lst in evidence_lists:
        for ev in lst:
            if isinstance(ev, Evidence):
                fused.append(ev.to_dict())
            elif isinstance(ev, dict):
                fused.append(ev)

    # Simple conflict detection: if specialists disagree on vegetation
    conflicts = []
    # Heuristic: check if one says vegetation loss and another says no change
    texts = []
    if specialist_results:
        for r in specialist_results:
            ans = (r.get("answer") or "").lower()
            texts.append(ans)
    if len(texts) >= 2:
        # Look for contradictory signals
        has_loss = any("loss" in t or "decrease" in t for t in texts)
        has_increase = any("increase" in t or "growth" in t for t in texts)
        if has_loss and has_increase:
            conflicts.append({"type": "vegetation_change_conflict", "description": "One specialist indicates loss, another indicates increase"})
        has_change = any("change" in t for t in texts)
        has_no_change = any("no change" in t or "unchanged" in t for t in texts)
        if has_change and has_no_change:
            conflicts.append({"type": "change_conflict", "description": "One specialist detects change, another reports no change"})

    agreement = "full" if not conflicts else ("partial" if len(conflicts) == 1 else "conflict")

    return {
        "fused_evidence": fused,
        "agreement": agreement,
        "conflicts": conflicts,
        "count": len(fused),
    }


def confidence_from_fusion(fusion: dict[str, Any], specialist_results: list[dict[str, Any]] | None = None) -> tuple[float | None, str]:
    """Derive confidence qualitatively if fusion shows conflict/limited evidence."""
    count = fusion.get("count", 0)
    agreement = fusion.get("agreement", "partial")
    if count == 0:
        return None, "insufficient"
    if agreement == "conflict":
        return 0.45, "limited"
    if agreement == "partial":
        return 0.65, "moderate"
    # Try to use model-provided confidence if available and consistent
    if specialist_results:
        confs = [r.get("confidence") for r in specialist_results if isinstance(r.get("confidence"), (int, float))]
        if confs:
            mean_conf = sum(confs) / len(confs)
            # Map to qualitative
            if mean_conf >= 0.75:
                qual = "strong"
            elif mean_conf >= 0.55:
                qual = "moderate"
            else:
                qual = "limited"
            return round(float(mean_conf), 3), qual
    # Fallback based on evidence coverage
    if count >= 3:
        return None, "moderate"
    return None, "limited"
