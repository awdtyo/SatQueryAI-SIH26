"""Answer synthesis — detailed, evidence-grounded, no hallucination."""

from __future__ import annotations

from typing import Any

from backend.utils.spatial import describe_spatial_output


def synthesize_answer(
    query: str,
    task: str,
    specialist_results: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    confidence: float | None,
    image_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build final intelligence response from structured specialist outputs.

    Returns dict with:
      answer: natural language
      findings: list[dict]
      limitations: list[str]
      metrics: dict
      artifacts: list
    Never fabricates scientific measurements; only uses real specialist outputs.
    """
    import logging

    logger = logging.getLogger(__name__)
    logger.info("[ANSWER SYNTHESIS INPUT] query=%r task=%r specialist_answer=%r", query, task, str(specialist_results[0].get("answer", "") if specialist_results else "")[:200])
    findings: list[dict[str, Any]] = []
    limitations: list[str] = []
    metrics: dict[str, Any] = {}
    artifacts: list[dict[str, Any]] = []

    # Collect metrics and artifacts from specialists
    for res in specialist_results:
        if isinstance(res.get("metrics"), dict):
            metrics.update(res["metrics"])
        if isinstance(res.get("artifacts"), list):
            artifacts.extend(res["artifacts"])
        if isinstance(res.get("limitations"), list):
            limitations.extend(res["limitations"])
        if isinstance(res.get("findings"), list):
            findings.extend(res["findings"])

    # Generate findings from evidence if not provided
    if not findings and evidence:
        for ev in evidence[:4]:
            typ = ev.get("type", "unknown")
            desc = ev.get("description", "")
            # Create finding from evidence without hallucinating
            if typ == "bounding_box" and desc:
                # Extract label if present
                label = desc.split()[0].lower() if desc else "object"
                if label not in ("[stub]", "object", "region"):
                    findings.append({
                        "label": label.title(),
                        "description": f"{label.title()} detected — {desc[:80]}",
                        "confidence": None,
                    })
                else:
                    findings.append({
                        "label": "Detected region",
                        "description": desc[:120] or "Spatial region detected",
                    })
            elif typ == "image_ref":
                findings.append({
                    "label": "Image analyzed",
                    "description": desc or "Input imagery processed",
                })
            elif typ == "coordinate_geometry":
                # Use spatial description if available
                spatial_desc = ev.get("spatial_description") or desc
                findings.append({
                    "label": "Spatial analysis",
                    "description": spatial_desc[:150] if spatial_desc else "Spatial regions identified",
                })

    # For VQA, ensure we have at least one finding from answer
    if not findings:
        # Use answer's first sentence as finding
        for res in specialist_results:
            ans = str(res.get("answer", "") or "")
            if ans and len(ans) > 20:
                # Take first bullet or sentence
                first = ans.split("\n")[0].lstrip("- ").strip()[:120]
                findings.append({
                    "label": "Observation",
                    "description": first,
                })
                break

    # Limitations: check for missing bands, metadata, etc.
    # Check if any specialist reported unsupported
    for res in specialist_results:
        if res.get("status") == "unsupported" and res.get("limitations"):
            limitations.extend(res["limitations"])
        # Check for RGB-only trying NDVI
        if "NIR" in str(res.get("limitations", "")) or "NIR band unavailable" in str(res.get("answer", "")):
            limitations.append("NDVI requires NIR band which was unavailable for the provided RGB image; accurate vegetation index could not be calculated.")

    # Deduplicate limitations
    limitations = list(dict.fromkeys(limitations))

    # Add generic limitation if no quantitative measurement but query was quantitative
    q_low = query.lower()
    if any(k in q_low for k in ["how much", "percentage", "percent", "area", "coverage"]) and not metrics:
        if not any("not calculated" in lim.lower() for lim in limitations):
            limitations.append("Exact quantitative percentages were not calculated for this query; answer is based on visual observations and available evidence.")

    # Build detailed answer: prioritize specialist answer, add key findings, evidence summary
    base_answer = ""
    for res in specialist_results:
        ans = str(res.get("answer", "") or "").strip()
        if ans and len(ans) > 10 and "did not produce" not in ans.lower():
            base_answer = ans
            break
    if not base_answer:
        for res in specialist_results:
            ans = str(res.get("answer", "") or "").strip()
            if ans:
                base_answer = ans
                break
    if not base_answer:
        base_answer = "The model did not produce a usable natural-language answer for this query."
        limitations.append("Model output was empty or unparseable; no natural-language answer could be generated.")

    # Ensure answer is not raw coordinates
    import re
    nums = re.findall(r"[-+]?\d*\.?\d+", base_answer)
    has_brackets = "[" in base_answer and "]" in base_answer
    words = len(base_answer.split())
    if has_brackets and len(nums) >= 4 and words < 20:
        # Raw detected in final answer — replace via spatial
        try:
            from backend.utils.spatial import describe_graph_output
            # Try to get image dims from metadata
            dims = None
            if image_metadata and "width" in image_metadata and "height" in image_metadata:
                dims = (int(image_metadata["width"]), int(image_metadata["height"]))
            spatial = describe_graph_output(base_answer, image_dimensions=dims)
            base_answer = spatial["description"]
        except Exception:
            base_answer = "The model did not produce a usable natural-language answer for this query."

    # Add confidence/evidence quality note only for low confidence (avoid verbosity for high/moderate)
    confidence_note = ""
    if confidence is not None and isinstance(confidence, (int, float)):
        if confidence < 0.45:
            confidence_note = f" Model confidence is low ({confidence:.2f}); verify with additional evidence."
            limitations.append(f"Low confidence ({confidence:.2f}) — results should be verified.")

    # Final answer is base_answer (already detailed via specialist bullets); append confidence note if needed
    if confidence_note and confidence_note.strip() not in base_answer:
        if "confidence" not in base_answer.lower():
            base_answer = base_answer.rstrip() + "\n\n" + confidence_note.strip()

    import logging

    logger = logging.getLogger(__name__)
    logger.info("[ANSWER SYNTHESIS OUTPUT] answer=%r findings=%d limitations=%d", base_answer[:500], len(findings), len(limitations))
    return {
        "answer": base_answer,
        "findings": findings[:6],
        "limitations": limitations[:5],
        "metrics": metrics,
        "artifacts": artifacts,
    }


__all__ = ["synthesize_answer"]
