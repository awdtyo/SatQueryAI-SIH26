"""Visualization fallback pipeline — ensures EVERY successful query has a valid graph.

Priority:
1. Specialist-provided visualization (counting, spectral, change, etc.)
2. Specialist metrics
3. Evidence-derived
4. Metadata
5. Confidence
6. Last-resort evidence-status
Never plots raw coordinate arrays as chart data.
"""

from __future__ import annotations

from typing import Any

from backend.schemas import ChartEntry


SUPPORTED_TYPES = {"bar", "pie", "line", "donut", "scatter"}


def validate_visualization(viz: Any) -> bool:
    """Strict validation — returns True only if visualization is renderable."""
    if not isinstance(viz, dict):
        return False
    typ = viz.get("type")
    if typ not in SUPPORTED_TYPES:
        return False
    title = viz.get("title")
    if not isinstance(title, str) or not title.strip():
        return False
    data = viz.get("data")
    if not isinstance(data, list) or len(data) == 0:
        return False
    for item in data:
        if not isinstance(item, dict):
            return False
        label = item.get("label")
        value = item.get("value")
        if not isinstance(label, str) or not label.strip():
            return False
        if not isinstance(value, (int, float)):
            return False
        # Check finite, not NaN, not inf, not raw array, no undefined
        if value != value:  # NaN
            return False
        if value in (float("inf"), float("-inf")):
            return False
        # Reject raw tensor-like arrays accidentally serialized
        if isinstance(value, (list, tuple)):
            return False
        # Also reject values that look like coordinate arrays (e.g., [0.0, 0.5])
        if label in ("undefined", "null", "NaN"):
            return False
    return True


def validate_chart_entries(entries: Any) -> bool:
    """Validate ChartEntry list."""
    if not isinstance(entries, list) or len(entries) == 0:
        return False
    for e in entries:
        if not isinstance(e, dict) and not hasattr(e, "label"):
            # Could be ChartEntry object
            try:
                label = e.label if hasattr(e, "label") else e.get("label")
                value = e.value if hasattr(e, "value") else e.get("value")
            except Exception:
                return False
        else:
            try:
                label = e["label"] if isinstance(e, dict) else e.label
                value = e["value"] if isinstance(e, dict) else e.value
            except Exception:
                return False
        if not isinstance(label, str) or not label.strip():
            return False
        if not isinstance(value, (int, float)) or value != value or value in (float("inf"), float("-inf")):
            return False
        if -1000 <= value <= 10000:
            continue
        else:
            return False
    return True


def _chart_to_viz(chart: list[ChartEntry] | list[dict[str, Any]], chart_type: str | None, title: str | None = None) -> dict[str, Any] | None:
    """Convert internal chart to canonical visualization object."""
    if not chart or len(chart) == 0:
        return None
    # Validate
    valid = []
    for c in chart:
        try:
            label = c.label if hasattr(c, "label") else c.get("label")  # type: ignore
            value = c.value if hasattr(c, "value") else c.get("value")  # type: ignore
            if isinstance(label, str) and isinstance(value, (int, float)) and value == value and value not in (float("inf"), float("-inf")):
                valid.append({"label": str(label), "value": float(value)})
        except Exception:
            continue
    if not valid:
        return None
    typ = "bar"
    if chart_type == "count":
        typ = "bar"
    elif chart_type == "change":
        typ = "bar"
    elif chart_type == "distribution":
        typ = "bar"
    # For pie, frontend toggles, but backend type is bar
    return {
        "type": typ,
        "title": title or ("Object counts" if chart_type == "count" else "Distribution" if chart_type == "distribution" else "Analysis"),
        "data": valid,
    }


def build_fallback_visualization(
    task: str,
    query: str,
    result: dict[str, Any],
    pil_images: list[Any] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    confidence: float | None = None,
    scene: dict[str, Any] | None = None,
    aoi: dict[str, Any] | None = None,
) -> tuple[list[ChartEntry] | None, str | None, dict[str, Any] | None]:
    """
    Implements 6-step fallback hierarchy.
    Returns (chart_list, chart_type, visualization)
    Always returns a valid visualization for successful queries, never None for success (except actual failure).
    """
    from backend.schemas import ChartEntry

    evidence = evidence or result.get("evidence", []) or []
    # 1. Specialist-provided visualization — check structured chart
    structured = result.get("_structured") or {}
    chart = result.get("_chart")
    chart_type = result.get("_chart_type") or (structured.get("chart_type") if isinstance(structured, dict) else None) if structured else None
    # Try to build from structured
    candidate_chart = None
    candidate_type = None
    if isinstance(structured, dict) and structured.get("chart"):
        cand = []
        for c in structured["chart"][:5]:
            if isinstance(c, dict) and "label" in c and "value" in c:
                try:
                    # Reject raw coordinate arrays
                    if isinstance(c["value"], (list, tuple)):
                        continue
                    cand.append(ChartEntry(label=str(c["label"]), value=float(c["value"])))
                except Exception:
                    continue
        if cand and validate_chart_entries([{"label": e.label, "value": e.value} for e in cand]):
            candidate_chart = cand
            candidate_type = structured.get("chart_type") or chart_type
    elif isinstance(chart, list) and chart:
        cand = []
        for c in chart[:5]:
            if isinstance(c, dict) and "label" in c and "value" in c:
                try:
                    if isinstance(c["value"], (list, tuple)):
                        continue
                    cand.append(ChartEntry(label=str(c["label"]), value=float(c["value"])))
                except Exception:
                    continue
        if cand and validate_chart_entries([{"label": e.label, "value": e.value} for e in cand]):
            candidate_chart = cand
            candidate_type = chart_type

    if candidate_chart:
        # For ordinary VQA without quantitative intent, do not use heuristic distribution
        if task in ("vqa", "captioning", "visual_question_answering"):
            q_low = (query or "").lower()
            is_quant = any(k in q_low for k in ["how many", "count", "number of", "chart", "graph", "distribution", "percentage", "percent", "spectral", "ndvi", "ndwi", "ndbi", "ndmi", "savi", "bsi", "nbr", "mndwi", "change", "compare", "plot", "statistic", "histogram", "bar", "pie"])
            if not is_quant:
                heuristic_labels = {"vegetation", "water", "urban", "bare", "other"}
                if any(c.label.lower() in heuristic_labels for c in candidate_chart):
                    candidate_chart = None
                    candidate_type = None
        if candidate_chart:
            viz = _chart_to_viz(candidate_chart, candidate_type)
            if viz and validate_visualization(viz):
                return candidate_chart, candidate_type, viz

    # Also check confidence even if not in metrics — store for later lower priority
    conf_fallback = None
    if confidence is not None and isinstance(confidence, (int, float)) and confidence == confidence:
        if 0 <= confidence <= 1 and confidence not in (float("inf"), float("-inf")):
            conf_chart = [ChartEntry(label="Confidence", value=round(float(confidence) * 100, 1))]
            try:
                viz_conf = _chart_to_viz(conf_chart, "bar", title="Confidence")
                if viz_conf and validate_visualization(viz_conf):
                    conf_fallback = (conf_chart, "distribution", viz_conf)
            except Exception:
                conf_fallback = None

    # 3. Evidence-derived visualization (higher priority than generic metrics for VQA)
    # Count evidence by type or label
    if evidence:
        # For bounding boxes, group by label derived from description
        label_counts: dict[str, int] = {}
        for ev in evidence:
            if not isinstance(ev, dict):
                continue
            typ = ev.get("type")
            if typ == "bounding_box":
                # Try to extract label from description: first word before space, lower
                desc = str(ev.get("description", "") or "")
                # Don't use raw coordinates as label
                first = desc.split()[0].lower() if desc.strip() else "object"
                # Filter out generic/stub
                if first in ("[stub]", "region", "object", "a", "the"):
                    first = "object"
                # Normalize
                label = first.strip(".,:;()[]").lower()
                if not label or label in ("undefined", "null"):
                    label = "object"
                # If label looks like coordinate, skip
                if "[" in label or "]" in label:
                    label = "object"
                label_counts[label] = label_counts.get(label, 0) + 1
            elif typ == "coordinate_geometry":
                # Count actual regions inside coordinates, not just evidence items
                coords = ev.get("coordinates") or (ev.get("spatial_provenance", {}) or {}).get("input_coordinates") or []
                if isinstance(coords, list) and len(coords) > 0 and isinstance(coords[0], (list, tuple)):
                    # Each coordinate pair is a region
                    label_counts["Regions"] = label_counts.get("Regions", 0) + len(coords)
                elif isinstance(coords, list) and len(coords) > 0:
                    label_counts["Regions"] = label_counts.get("Regions", 0) + 1
                else:
                    label_counts["Evidence"] = label_counts.get("Evidence", 0) + 1
            elif typ in ("image_ref", "image_region"):
                label_counts["Evidence"] = label_counts.get("Evidence", 0) + 1
            elif typ in ("overlay", "heatmap"):
                label_counts[typ] = label_counts.get(typ, 0) + 1
        # Also handle evidence with explicit label field
        for ev in evidence:
            if isinstance(ev, dict) and "label" in ev and isinstance(ev["label"], str):
                lbl = ev["label"].strip().lower()
                if lbl and lbl not in ("undefined", "null") and "[" not in lbl:
                    label_counts[lbl] = label_counts.get(lbl, 0) + 1

        if label_counts:
            # Create chart from counts — ensure not from raw x1/y1 values
            chart_entries = []
            for lbl, cnt in sorted(label_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                if isinstance(cnt, (int, float)) and cnt == cnt:
                    chart_entries.append(ChartEntry(label=lbl.title(), value=float(cnt)))
            if chart_entries and validate_chart_entries([{"label": e.label, "value": e.value} for e in chart_entries]):
                viz = _chart_to_viz(chart_entries, "bar", title="Objects detected" if any("building" in k.lower() or "vehicle" in k.lower() for k in label_counts) else "Evidence summary")
                if viz and validate_visualization(viz):
                    return chart_entries, ("count" if task in ("count", "counting") else "distribution"), viz

    # 2b. Specialist metrics (after evidence for VQA, but before metadata for spectral/change)
    metrics = result.get("metrics") or result.get("_metrics") or {}
    metric_chart: list[ChartEntry] = []
    for k in ["objects", "count", "changed_pixels", "unchanged_pixels", "changed_area", "score", "mean_ndvi", "mean", "min", "max"]:
        if k in result and isinstance(result[k], (int, float)) and result[k] == result[k]:
            if -1000 <= result[k] <= 10000 and not isinstance(result[k], (list, tuple)):
                metric_chart.append(ChartEntry(label=k.replace("_", " ").title(), value=float(result[k])))
    for k, v in metrics.items():
        if isinstance(v, (int, float)) and v == v and v not in (float("inf"), float("-inf")):
            if isinstance(v, (list, tuple)):
                continue
            if -1000 <= v <= 10000:
                if not any(c.label.lower() == k.lower() for c in metric_chart):
                    metric_chart.append(ChartEntry(label=str(k).replace("_", " ").title(), value=float(v)))
    if metric_chart and validate_chart_entries([{"label": e.label, "value": e.value} for e in metric_chart]):
        viz = _chart_to_viz(metric_chart, "bar", title="Metrics")
        if viz and validate_visualization(viz):
            return metric_chart, "distribution", viz

    # 4. Metadata visualization
    # Use pil_images metadata
    if pil_images and len(pil_images) > 0:
        try:
            meta_entries: list[ChartEntry] = []
            for idx, img in enumerate(pil_images[:2]):
                if hasattr(img, "size"):
                    w, h = img.size
                    # Only use real metadata
                    meta_entries.append(ChartEntry(label=f"Image {idx+1} width" if len(pil_images) > 1 else "Width", value=float(w)))
                    meta_entries.append(ChartEntry(label=f"Image {idx+1} height" if len(pil_images) > 1 else "Height", value=float(h)))
                    # Number of bands - check mode
                    try:
                        mode = getattr(img, "mode", "RGB")
                        channels = len(mode) if mode not in ("P", "L") else 3
                        meta_entries.append(ChartEntry(label="Channels", value=float(channels)))
                    except Exception:
                        pass
                    # File size if available
                    try:
                        import io
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        size_kb = len(buf.getvalue()) / 1024
                        meta_entries.append(ChartEntry(label="File size (KB)", value=round(size_kb, 1)))
                    except Exception:
                        pass
                    break  # Only first image for metadata to avoid duplication
            # Also check result for image metadata
            for k in ["width", "height", "bands", "channels"]:
                if k in result and isinstance(result[k], (int, float)):
                    if not any(e.label.lower() == k for e in meta_entries):
                        meta_entries.append(ChartEntry(label=k.title(), value=float(result[k])))
            if meta_entries and validate_chart_entries([{"label": e.label, "value": e.value} for e in meta_entries]):
                # Limit to 4-5 entries for readability
                viz = _chart_to_viz(meta_entries[:4], "bar", title="Image metadata")
                if viz and validate_visualization(viz):
                    return meta_entries[:4], "distribution", viz
        except Exception:
            pass

    # Check scene metadata for live queries
    if scene and isinstance(scene, dict):
        scene_entries: list[ChartEntry] = []
        for k in ["cloud_cover", "coverage", "selection_score"]:
            if k in scene and isinstance(scene[k], (int, float)) and scene[k] == scene[k]:
                label = k.replace("_", " ").title()
                scene_entries.append(ChartEntry(label=label, value=float(scene[k])))
        # Number of retrieved scenes - check result
        if "scenes" in result and isinstance(result["scenes"], list):
            scene_entries.append(ChartEntry(label="Scenes retrieved", value=float(len(result["scenes"]))))
        if scene_entries and validate_chart_entries([{"label": e.label, "value": e.value} for e in scene_entries]):
            viz = _chart_to_viz(scene_entries, "bar", title="Scene metadata")
            if viz and validate_visualization(viz):
                return scene_entries, "distribution", viz

    # 5. Confidence visualization (if available and not fabricated)
    if conf_fallback:
        chart_c, typ_c, viz_c = conf_fallback
        if viz_c and validate_visualization(viz_c):
            return chart_c, typ_c, viz_c

    # Also check evidence count as fallback
    if evidence:
        ev_chart = [ChartEntry(label="Evidence items", value=float(len(evidence)))]
        viz = _chart_to_viz(ev_chart, "bar", title="Evidence summary")
        if viz and validate_visualization(viz):
            return ev_chart, "distribution", viz

    # 6. Last-resort evidence-status / pipeline execution chart
    # Use real execution info
    last_chart = [
        ChartEntry(label="Evidence", value=float(len(evidence) if evidence else 0)),
        ChartEntry(label="Confidence", value=round(float(confidence) * 100, 1) if isinstance(confidence, (int, float)) and confidence == confidence else 0),
    ]
    # Filter to only valid
    last_chart = [c for c in last_chart if isinstance(c.value, (int, float)) and c.value == c.value]
    if not last_chart or all(c.value == 0 for c in last_chart):
        # Pipeline execution chart
        last_chart = [
            ChartEntry(label="Ingestion", value=1),
            ChartEntry(label="Planning", value=1),
            ChartEntry(label="Specialist", value=1),
            ChartEntry(label="Evidence", value=1 if evidence else 0),
        ]
    viz = _chart_to_viz(last_chart, "bar", title="Pipeline execution")
    if viz and validate_visualization(viz):
        return last_chart, "distribution", viz

    # Ultimate fallback — should never happen, but ensure something valid
    fallback = [ChartEntry(label="Evidence", value=float(len(evidence) if evidence else 1))]
    viz = _chart_to_viz(fallback, "bar", title="Evidence summary")
    return fallback, "distribution", viz

