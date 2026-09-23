"""Deterministic spatial description utility — no LLM, CPU-safe, coordinate-system aware.

Converts raw coordinates / bboxes / polygons into human-readable image-relative descriptions
while preserving raw numerical evidence. Never hallucinates semantics.

Supports: normalized (0-1), pixel, geographic (lat/lon), unknown.
"""

from __future__ import annotations

from typing import Any, Literal

CoordinateSystem = Literal["normalized", "pixel", "geographic", "unknown", "auto"]


def _h_label(x: float) -> str:
    if x < 0.33:
        return "left"
    elif x < 0.66:
        return "center"
    else:
        return "right"


def _v_label(y: float) -> str:
    if y < 0.33:
        return "upper"
    elif y < 0.66:
        return "middle"
    else:
        return "lower"


def _combine_hv(x: float, y: float) -> str:
    h = _h_label(x)
    v = _v_label(y)
    if h == "center" and v == "middle":
        return "center"
    if h == "center":
        return f"{v}-center"
    if v == "middle":
        return f"middle-{h}"
    return f"{v}-{h}"


def _extent_phrase(w: float, h: float) -> str:
    # Normalized extent
    area = w * h
    max_side = max(w, h)
    if area > 0.5 or max_side > 0.75:
        return "occupies a large portion of the image"
    if area > 0.12 or max_side > 0.4:
        return "occupies a moderate area"
    if area > 0.03:
        return "occupies a small area"
    return "occupies a very small area"


def _detect_coordinate_system(
    coords: Any,
    hint: CoordinateSystem = "auto",
    image_dimensions: tuple[int, int] | None = None,
) -> CoordinateSystem:
    if hint != "auto":
        return hint
    # Flatten numeric values
    flat: list[float] = []
    try:
        def _collect(c):
            if isinstance(c, (list, tuple)):
                for v in c:
                    _collect(v)
            elif isinstance(c, (int, float)):
                flat.append(float(c))
        _collect(coords)
    except Exception:
        return "unknown"
    if not flat:
        return "unknown"
    # Geographic heuristic: lat -90..90 and lon -180..180, typically both ranges appear and values may be >1 but within geo
    # Pixel: any value >1.5 and integer-like and exceeds 1, or exceeds image dimensions if provided
    # Normalized: all values in [0,1]
    all_in_01 = all(0.0 <= v <= 1.0 for v in flat)
    if all_in_01:
        # Could still be geographic small area near equator (e.g., 0.5 lat) but normalized is more likely for image
        # If image_dimensions is None and values look like lat/lon fractional but not integer, we stay normalized unless caller says geographic
        return "normalized"
    # Check geographic: lat in -90..90, lon in -180..180, and at least one value has decimal and range suggests geo
    # But pixel coordinates also can be in that range for small images (e.g., 10,10) — disambiguate via magnitude
    # If any value absolute > 180, must be pixel
    if any(abs(v) > 180 for v in flat):
        return "pixel"
    if image_dimensions is not None:
        w, h = image_dimensions
        # If any value > w or > h significantly, pixel
        if any(v > max(w, h) * 1.2 for v in flat if v > 1):
            return "pixel"
        # Pixel if any value clearly exceeds normalized range (e.g., >5) — small overflow like 2.05 stays normalized
        if any(v > 5 for v in flat):
            return "pixel"
    # Small overflow (e.g., 0-2.5) is likely normalized with slight out-of-range, treat as normalized
    if flat and max(flat) < 5 and min(flat) >= 0 and any(0 <= v <= 1 for v in flat):
        return "normalized"
    # If values are outside 0-1 but within geo range, unknown unless image dims clarify
    # Heuristic: if flat contains pairs where one in -90..90 and other -180..180 and we have even count >=2, could be geographic
    # But without hint, default to unknown to avoid guessing
    if any(v < 0 or v > 1 for v in flat):
        # Check if plausible geographic: first pair
        if len(flat) >= 2:
            # If any value is negative and within geo range, geographic plausible but we shouldn't assume
            # So mark unknown per spec if not explicitly geographic
            return "unknown"
        return "unknown"
    return "unknown"


def _normalize_to_01(
    coords: Any,
    system: CoordinateSystem,
    image_dimensions: tuple[int, int] | None,
) -> list[list[float]]:
    """Convert any coord structure to list of normalized center points for grouping."""
    # Returns list of [x01,y01] centers
    points: list[list[float]] = []
    try:
        if system == "normalized":
            # coords may be [x,y], [[x1,y1],[x2,y2]], [x1,y1,x2,y2], list thereof
            # Try to parse
            if isinstance(coords, (list, tuple)) and len(coords) == 0:
                return []
            # Single point
            if isinstance(coords, (list, tuple)) and len(coords) == 2 and all(isinstance(v, (int, float)) for v in coords):
                return [[float(coords[0]), float(coords[1])]]
            # Single bbox flat 4
            if isinstance(coords, (list, tuple)) and len(coords) == 4 and all(isinstance(v, (int, float)) for v in coords):
                x1, y1, x2, y2 = [float(v) for v in coords]
                return [[(x1 + x2) / 2, (y1 + y2) / 2]]
            # List of points or bboxes
            for item in coords:  # type: ignore
                if isinstance(item, (list, tuple)):
                    if len(item) == 2 and all(isinstance(v, (int, float)) for v in item):
                        points.append([float(item[0]), float(item[1])])
                    elif len(item) == 4 and all(isinstance(v, (int, float)) for v in item):
                        x1, y1, x2, y2 = [float(v) for v in item]
                        points.append([(x1 + x2) / 2, (y1 + y2) / 2])
                    elif len(item) == 2 and isinstance(item[0], (list, tuple)):
                        # [[x1,y1],[x2,y2]]
                        try:
                            x1, y1 = float(item[0][0]), float(item[0][1])  # type: ignore
                            x2, y2 = float(item[1][0]), float(item[1][1])  # type: ignore
                            points.append([(x1 + x2) / 2, (y1 + y2) / 2])
                        except Exception:
                            continue
                    else:
                        # polygon or nested
                        # take centroid approx as mean of vertices
                        flat_pts: list[list[float]] = []
                        for pt in item:  # type: ignore
                            if isinstance(pt, (list, tuple)) and len(pt) == 2:
                                flat_pts.append([float(pt[0]), float(pt[1])])  # type: ignore
                        if flat_pts:
                            cx = sum(p[0] for p in flat_pts) / len(flat_pts)
                            cy = sum(p[1] for p in flat_pts) / len(flat_pts)
                            points.append([cx, cy])
            return points
        elif system == "pixel":
            if image_dimensions is None:
                # Cannot normalize without dims -> return unknown scaling but still attempt
                w, h = 1000, 1000  # fallback
            else:
                w, h = image_dimensions
            # Similar parsing but divide by w/h
            if isinstance(coords, (list, tuple)) and len(coords) == 2 and all(isinstance(v, (int, float)) for v in coords):
                return [[float(coords[0]) / w, float(coords[1]) / h]]
            if isinstance(coords, (list, tuple)) and len(coords) == 4 and all(isinstance(v, (int, float)) for v in coords):
                x1, y1, x2, y2 = [float(v) for v in coords]
                return [[(x1 + x2) / 2 / w, (y1 + y2) / 2 / h]]
            for item in coords:  # type: ignore
                if isinstance(item, (list, tuple)):
                    if len(item) == 2 and all(isinstance(v, (int, float)) for v in item):
                        points.append([float(item[0]) / w, float(item[1]) / h])
                    elif len(item) == 4 and all(isinstance(v, (int, float)) for v in item):
                        x1, y1, x2, y2 = [float(v) for v in item]
                        points.append([(x1 + x2) / 2 / w, (y1 + y2) / 2 / h])
                    elif len(item) == 2 and isinstance(item[0], (list, tuple)):
                        try:
                            x1, y1 = float(item[0][0]), float(item[0][1])  # type: ignore
                            x2, y2 = float(item[1][0]), float(item[1][1])  # type: ignore
                            points.append([(x1 + x2) / 2 / w, (y1 + y2) / 2 / h])
                        except Exception:
                            continue
            return points
        elif system == "geographic":
            return []
    except Exception:
        pass
    return points


def _describe_single_point(x01: float, y01: float, system: CoordinateSystem, with_extent: bool = False, w01: float | None = None, h01: float | None = None) -> str:
    loc = _combine_hv(x01, y01)
    # Map to phrase
    phrase_map = {
        "upper-left": "upper-left portion of the image",
        "upper-center": "upper-center portion of the image",
        "upper-right": "upper-right portion of the image",
        "middle-left": "middle-left portion of the image",
        "center": "central area of the image",
        "middle-right": "middle-right portion of the image",
        "lower-left": "lower-left portion of the image",
        "lower-center": "lower-center portion of the image",
        "lower-right": "lower-right portion of the image",
    }
    loc_phrase = phrase_map.get(loc, f"{loc} portion of the image")
    if with_extent and w01 is not None and h01 is not None:
        ext = _extent_phrase(w01, h01)
        return f"located toward the {loc_phrase} and {ext}"
    return f"located toward the {loc_phrase}"


def describe_spatial_output(
    coordinates: Any,
    coordinate_system: CoordinateSystem = "auto",
    image_dimensions: tuple[int, int] | None = None,
    labels: list[str] | None = None,
    bbox_format: str | None = None,
) -> dict[str, Any]:
    """Describe spatial output deterministically.

    Returns dict with:
      - description: natural language
      - coordinate_system: detected
      - input_coordinates: raw preserved
      - image_dimensions
      - description_source, count, regions
    Never hallucinates semantics; labels only used if provided.
    """
    raw = coordinates
    # Handle empty / invalid
    if coordinates is None or (isinstance(coordinates, (list, tuple)) and len(coordinates) == 0):
        return {
            "description": "No spatial regions were detected.",
            "coordinate_system": "unknown",
            "input_coordinates": raw,
            "image_dimensions": image_dimensions,
            "description_source": "derived_from_coordinates",
            "count": 0,
        }
    # Validate numeric
    try:
        # Check if coordinates contain non-numeric junk
        def _is_numeric(c):
            if isinstance(c, (list, tuple)):
                return all(_is_numeric(v) for v in c)
            return isinstance(c, (int, float))

        if not _is_numeric(coordinates):
            # Try to see if it's something like strings or None
            return {
                "description": "Spatial coordinates were provided but could not be interpreted due to invalid values.",
                "coordinate_system": "unknown",
                "input_coordinates": raw,
                "image_dimensions": image_dimensions,
                "description_source": "derived_from_coordinates",
                "count": 0,
            }
    except Exception:
        return {
            "description": "Spatial coordinates were provided but could not be interpreted due to invalid values.",
            "coordinate_system": "unknown",
            "input_coordinates": raw,
            "image_dimensions": image_dimensions,
            "description_source": "derived_from_coordinates",
            "count": 0,
        }

    system = _detect_coordinate_system(coordinates, hint=coordinate_system, image_dimensions=image_dimensions)

    if system == "geographic":
        # Count regions
        try:
            count = len(coordinates) if isinstance(coordinates, (list, tuple)) else 1
            # Heuristic: if list of pairs, count accordingly
            if isinstance(coordinates, (list, tuple)) and len(coordinates) > 0 and isinstance(coordinates[0], (list, tuple)):
                count = len(coordinates)
            else:
                count = 1
        except Exception:
            count = 1
        if count == 1:
            desc = "The detected region is centered near the provided geographic coordinates."
        else:
            desc = f"{count} spatial regions were detected near the provided geographic coordinates."
        return {
            "description": desc,
            "coordinate_system": "geographic",
            "input_coordinates": raw,
            "image_dimensions": image_dimensions,
            "description_source": "derived_from_coordinates",
            "count": count,
        }

    if system == "unknown":
        try:
            # Try to count
            if isinstance(coordinates, (list, tuple)) and len(coordinates) > 0 and isinstance(coordinates[0], (list, tuple)):
                # Could be list of bboxes or points
                count = len(coordinates)
                # Check if flat list like [0.0,0.5,0,1.0] not list of lists — then treat as 1 region with multiple points
                # Our earlier _is_numeric ensures we have nesting; if flat 4 numbers, count 1
                if isinstance(coordinates, (list, tuple)) and all(isinstance(v, (int, float)) for v in coordinates):
                    count = 1
            elif isinstance(coordinates, (list, tuple)) and all(isinstance(v, (int, float)) for v in coordinates):
                count = 1
            else:
                count = len(coordinates) if isinstance(coordinates, (list, tuple)) else 1
        except Exception:
            count = 1
        if count == 0:
            desc = "No spatial regions were detected."
        elif count == 1:
            desc = "A spatial coordinate region was detected, but its coordinate reference system is not available, so its precise image location cannot be determined."
        else:
            desc = f"{count} spatial coordinate regions were detected, but their coordinate reference system is not available, so their geographic or image locations cannot be determined."
        return {
            "description": desc,
            "coordinate_system": "unknown",
            "input_coordinates": raw,
            "image_dimensions": image_dimensions,
            "description_source": "derived_from_coordinates",
            "count": count,
        }

    # Normalized or Pixel — derive points
    points = _normalize_to_01(coordinates, system, image_dimensions)
    if not points:
        return {
            "description": "Spatial regions were detected, but their positions could not be determined from the available coordinates.",
            "coordinate_system": system,
            "input_coordinates": raw,
            "image_dimensions": image_dimensions,
            "description_source": "derived_from_coordinates",
            "count": 0,
        }

    count = len(points)
    # Also compute bbox extents if available for single region
    # For bboxes we can estimate extent
    # Try to extract w/h for extent phrase
    extents: list[tuple[float, float]] = []
    try:
        if system == "normalized":
            # Check if coordinates represent bboxes
            if isinstance(coordinates, (list, tuple)) and len(coordinates) == 4 and all(isinstance(v, (int, float)) for v in coordinates):
                w = abs(float(coordinates[2]) - float(coordinates[0]))
                h = abs(float(coordinates[3]) - float(coordinates[1]))
                extents = [(w, h)]
            elif isinstance(coordinates, (list, tuple)) and isinstance(coordinates[0], (list, tuple)):
                for item in coordinates:  # type: ignore
                    if isinstance(item, (list, tuple)) and len(item) == 4 and all(isinstance(v, (int, float)) for v in item):
                        w = abs(float(item[2]) - float(item[0]))
                        h = abs(float(item[3]) - float(item[1]))
                        # If normalized, keep; if pixel, normalize by dims already done but extent also needs normalization
                        if system == "pixel" and image_dimensions:
                            w = w / image_dimensions[0] if system == "pixel" else w
                            h = h / image_dimensions[1] if system == "pixel" else h
                        extents.append((w, h))
                    elif isinstance(item, (list, tuple)) and len(item) == 2 and isinstance(item[0], (list, tuple)):
                        # [[x1,y1],[x2,y2]]
                        try:
                            x1, y1 = float(item[0][0]), float(item[0][1])  # type: ignore
                            x2, y2 = float(item[1][0]), float(item[1][1])  # type: ignore
                            w = abs(x2 - x1)
                            h = abs(y2 - y1)
                            if system == "pixel" and image_dimensions:
                                w = w / image_dimensions[0]
                                h = h / image_dimensions[1]
                            extents.append((w, h))
                        except Exception:
                            extents.append((0.1, 0.1))
                    else:
                        extents.append((0.1, 0.1))
        elif system == "pixel" and image_dimensions:
            w_img, h_img = image_dimensions
            if isinstance(coordinates, (list, tuple)) and len(coordinates) == 4 and all(isinstance(v, (int, float)) for v in coordinates):
                w = abs(float(coordinates[2]) - float(coordinates[0])) / w_img
                h = abs(float(coordinates[3]) - float(coordinates[1])) / h_img
                extents = [(w, h)]
            elif isinstance(coordinates, (list, tuple)) and isinstance(coordinates[0], (list, tuple)):
                for item in coordinates:  # type: ignore
                    if isinstance(item, (list, tuple)) and len(item) == 4 and all(isinstance(v, (int, float)) for v in item):
                        w = abs(float(item[2]) - float(item[0])) / w_img
                        h = abs(float(item[3]) - float(item[1])) / h_img
                        extents.append((w, h))
                    elif isinstance(item, (list, tuple)) and len(item) == 2 and isinstance(item[0], (list, tuple)):
                        try:
                            x1, y1 = float(item[0][0]), float(item[0][1])  # type: ignore
                            x2, y2 = float(item[1][0]), float(item[1][1])  # type: ignore
                            w = abs(x2 - x1) / w_img
                            h = abs(y2 - y1) / h_img
                            extents.append((w, h))
                        except Exception:
                            extents.append((0.05, 0.05))
                    else:
                        extents.append((0.05, 0.05))
    except Exception:
        extents = []

    # Build descriptions per region
    loc_phrases: list[str] = []
    for idx, (x, y) in enumerate(points):
        loc = _combine_hv(x, y)
        # Map to phrase without "portion" duplication
        phrase_map_short = {
            "upper-left": "upper-left",
            "upper-center": "upper-center",
            "upper-right": "upper-right",
            "middle-left": "middle-left",
            "center": "center",
            "middle-right": "middle-right",
            "lower-left": "lower-left",
            "lower-center": "lower-center",
            "lower-right": "lower-right",
        }
        loc_phrases.append(phrase_map_short.get(loc, loc))

    # Determine labels handling
    use_labels = labels is not None and len(labels) == count and all(isinstance(l, str) and l.strip() for l in labels)  # type: ignore

    # Single region
    if count == 1:
        x, y = points[0]
        w01, h01 = extents[0] if extents and len(extents) >= 1 else (None, None)
        # Check extent description if bbox
        has_extent = w01 is not None and h01 is not None and (w01 is not None and h01 is not None)
        # Provide detailed single
        loc_desc = _describe_single_point(x, y, system, with_extent=has_extent, w01=w01, h01=h01)  # type: ignore
        if use_labels:
            label = labels[0].strip().lower()  # type: ignore
            description = f"One {label} was detected {loc_desc}."
        else:
            # No semantic label
            if has_extent and w01 is not None and h01 is not None:
                # bbox extent phrasing
                description = f"A detected region {loc_desc}."
            else:
                description = f"A detected region is {loc_desc}."
        return {
            "description": description,
            "coordinate_system": system,
            "input_coordinates": raw,
            "image_dimensions": image_dimensions,
            "description_source": "derived_from_coordinates",
            "count": 1,
            "regions": [{"center": points[0], "location": loc_phrases[0]}],
        }

    # Multiple regions
    # Summarize distribution
    # Count by region? Provide grouped description
    # Build phrase like "Three spatial regions were identified in the image. One region is located toward the upper-left portion..."
    # Determine plural label
    if use_labels:
        # Group labels: e.g., vehicles, buildings
        # Assume all same label if provided; if mixed, mention
        unique_labels = list(dict.fromkeys([l.strip().lower() for l in labels]))  # type: ignore
        if len(unique_labels) == 1:
            plural = unique_labels[0] + "s" if not unique_labels[0].endswith("s") else unique_labels[0]
            # Special plural handling simple
            intro = f"{count} {plural} were detected."
        else:
            intro = f"{count} objects were detected with multiple types."
    else:
        intro = f"{count} spatial regions were identified in the image."

    # Distribution sentence
    # List locations
    # For 2-3 regions, enumerate each; for more, summarize distribution across scene
    if count <= 3:
        loc_sentences: list[str] = []
        # Use labels if available to pair
        for i, loc in enumerate(loc_phrases):
            if use_labels:
                lbl = labels[i].strip().lower()  # type: ignore
                if i == 0:
                    loc_sentences.append(f"One {lbl} is located toward the {loc} portion of the image")
                elif i == count - 1:
                    loc_sentences.append(f"and one toward the {loc} portion")
                else:
                    loc_sentences.append(f"another toward the {loc} portion")
            else:
                if i == 0:
                    loc_sentences.append(f"One region is located toward the {loc} portion of the scene")
                elif i == count - 1:
                    loc_sentences.append(f"and one toward the {loc} portion")
                else:
                    loc_sentences.append(f"another occupies the {loc} area")
        # Join
        if count == 2:
            detail = loc_sentences[0] + ", " + loc_sentences[1] + "."
        else:
            detail = ", ".join(loc_sentences[:-1]) + ", " + loc_sentences[-1] + "."
        # For 3, our detail already has "and one ..."; adjust punctuation
        if count == 3 and use_labels:
            detail = loc_sentences[0] + ", " + loc_sentences[1] + ", " + loc_sentences[2] + "."
        elif count == 3 and not use_labels:
            # loc_sentences[0] already "One region is located...", then "another occupies...", "and one toward..."
            detail = loc_sentences[0] + ", " + loc_sentences[1] + ", " + loc_sentences[2] + "."
        description = intro + " " + detail
    else:
        # More than 3: summarize distribution across scene
        # Find distinct horizontal/vertical coverage
        # Simple: list unique loc_phrases
        uniq = list(dict.fromkeys(loc_phrases))
        # Provide generic distribution
        if len(uniq) >= 3:
            description = intro + " Their positions are distributed across different portions of the scene, including areas toward the " + ", ".join(uniq[:3]) + " portions of the image."
        else:
            description = intro + " Their positions are distributed across the scene, with detected regions extending across the available coordinate space."

    return {
        "description": description,
        "coordinate_system": system,
        "input_coordinates": raw,
        "image_dimensions": image_dimensions,
        "description_source": "derived_from_coordinates",
        "count": count,
        "regions": [{"center": pt, "location": loc} for pt, loc in zip(points, loc_phrases)],
    }


# Convenience wrapper for graph-style raw arrays like "[0.0 0.5, 0 1.0]" etc.
def describe_graph_output(graph_data: Any, image_dimensions: tuple[int, int] | None = None, coordinate_system: CoordinateSystem = "auto") -> dict[str, Any]:
    """Handle graph output that may be list of arrays or string representation."""
    # Try to parse if string
    if isinstance(graph_data, str):
        import re

        # Prefer bracket groups: each [ ... ] is one spatial region
        bracket_groups = re.findall(r"\[([^\]]+)\]", graph_data)
        if bracket_groups:
            region_centers: list[list[float]] = []
            for group in bracket_groups:
                nums = re.findall(r"[-+]?\d*\.?\d+", group)
                try:
                    floats = [float(n) for n in nums]
                    if len(floats) >= 2 and len(floats) % 2 == 0:
                        xs = floats[0::2]
                        ys = floats[1::2]
                        cx = sum(xs) / len(xs)
                        cy = sum(ys) / len(ys)
                        region_centers.append([cx, cy])
                    elif len(floats) >= 2:
                        region_centers.append([floats[0], floats[1]])
                except Exception:
                    continue
            if region_centers:
                return describe_spatial_output(region_centers, coordinate_system=coordinate_system, image_dimensions=image_dimensions)
        # Fallback: plain numbers
        nums = re.findall(r"[-+]?\d*\.?\d+", graph_data)
        try:
            floats = [float(n) for n in nums]
            # Group into pairs
            if len(floats) % 2 == 0 and len(floats) >= 2:
                pairs = [[floats[i], floats[i + 1]] for i in range(0, len(floats), 2)]
                return describe_spatial_output(pairs, coordinate_system=coordinate_system, image_dimensions=image_dimensions)
        except Exception:
            pass
        return {
            "description": "Graph data was generated, but its coordinate interpretation is ambiguous without additional context.",
            "coordinate_system": "unknown",
            "input_coordinates": graph_data,
            "image_dimensions": image_dimensions,
            "description_source": "derived_from_coordinates",
            "count": 0,
        }
    return describe_spatial_output(graph_data, coordinate_system=coordinate_system, image_dimensions=image_dimensions)


__all__ = ["describe_spatial_output", "describe_graph_output", "_detect_coordinate_system"]
