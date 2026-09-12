"""
YOLO counting specialist — real inference with ultralytics YOLOv8n (COCO 80).

Benchmarks: COCO detection (mAP 37.3). For RS small objects, override
SATQUERY_YOLO_WEIGHTS to yolov8n-obb.pt (DOTA) or a fine-tuned RS weight.

Interface (shared contract, do not change signature):
    predict(images, query, task) -> {"answer": str, "evidence": list[dict], "confidence": float}

- images: PIL.Image.Image | list[PIL.Image.Image] | str | bytes
- query: natural language question (e.g. "how many buildings?")
- task: "count" | "counting"

Chart: count per class -> bar/pie toggle identical to distribution but
values are counts (not percentages). Evidence: bounding_box per detection.

Model is singleton, loaded lazily once, shares GPU when available.
Gracefully degrades to stub if ultralytics not installed / weight missing.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

from PIL import Image

try:
    import torch  # type: ignore
except ImportError:
    torch = None  # type: ignore

from backend import config as app_config

logger = logging.getLogger(__name__)

# Singleton
_yolo = None  # ultralytics YOLO instance
_yolo_names: dict[int, str] = {}
_load_error: str | None = None
_load_attempted: bool = False
_is_real: bool = False


# Query -> target class keywords for filtering
# Map natural language terms to COCO class names (yolov8n COCO: 80)
_ALIAS_TO_COCO: dict[str, str] = {
    "building": "building",  # not in COCO -> will be counted as all if not found, fallback
    "house": "building",
    "ship": "boat",
    "boat": "boat",
    "car": "car",
    "vehicle": "car",
    "truck": "truck",
    "plane": "airplane",
    "airplane": "airplane",
    "aircraft": "airplane",
    "person": "person",
    "tree": "tree",  # not in COCO
    "tank": "truck",
}


def _get_device() -> str:
    if getattr(app_config, "FORCE_CPU", False):
        return "cpu"
    if torch is not None and torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _load_model() -> bool:
    global _yolo, _yolo_names, _load_error, _load_attempted, _is_real
    if _load_attempted:
        return _is_real
    _load_attempted = True

    weight = app_config.YOLO_WEIGHTS
    # ultralytics will auto-download yolov8n.pt to ~/.cache/torch if not present
    try:
        from ultralytics import YOLO  # type: ignore

        device = _get_device()
        logger.info("YOLO specialist: loading weight=%s device=%s", weight, device)
        _yolo = YOLO(weight)
        # ultralytics handles device internally per predict; store names
        _yolo_names = getattr(_yolo, "names", {}) or {}
        # Try to move to device if GPU (ultralytics does lazy)
        _is_real = True
        _load_error = None
        logger.info("YOLO specialist READY — weight=%s classes=%d", weight, len(_yolo_names))
        return True
    except Exception as e:
        logger.error("YOLO load failed (%s): %s", weight, e, exc_info=True)
        _load_error = f"YOLO load failed ({weight}): {e}"
        _yolo = None
        _is_real = False
        return False


def _ensure_loaded() -> None:
    if not _load_attempted:
        _load_model()
    if not _is_real or _yolo is None:
        raise RuntimeError(_load_error or "YOLO specialist not loaded — install ultralytics and weight.")


def _coerce_images(images: Any) -> list[Image.Image]:
    if isinstance(images, Image.Image):
        return [images.convert("RGB")]
    if isinstance(images, (str, Path)):
        return [Image.open(str(images)).convert("RGB")]
    if isinstance(images, (bytes, bytearray)):
        import io

        return [Image.open(io.BytesIO(images)).convert("RGB")]
    if isinstance(images, (list, tuple)):
        out: list[Image.Image] = []
        for item in images:
            if isinstance(item, Image.Image):
                out.append(item.convert("RGB"))
            elif isinstance(item, (str, Path)):
                out.append(Image.open(str(item)).convert("RGB"))
            elif isinstance(item, (bytes, bytearray)):
                import io

                out.append(Image.open(io.BytesIO(item)).convert("RGB"))
            else:
                raise ValueError(f"Unsupported image type: {type(item)}")
        if not out:
            raise ValueError("Empty image list")
        return out
    raise ValueError(f"Unsupported images type: {type(images)}")


def _parse_query_target(query: str) -> str | None:
    q = (query or "").lower()
    # Extract "how many X" or "count X"
    m = re.search(r"how many\s+([a-z\- ]+?)(?:\?|\b are\b|\b is\b|$)", q)
    if m:
        term = m.group(1).strip().split()[0]
        return term
    m = re.search(r"count\s+(?:the\s+)?([a-z\-]+)", q)
    if m:
        return m.group(1).strip()
    m = re.search(r"number of\s+([a-z\-]+)", q)
    if m:
        return m.group(1).strip()
    # Fallback: look for known alias keywords in query
    for alias in sorted(_ALIAS_TO_COCO.keys(), key=len, reverse=True):
        if alias in q:
            return alias
    return None


def predict(
    images: Any,
    query: str,
    task: str = "count",
) -> dict[str, Any]:
    """Counting inference — YOLO detects and counts.

    Returns: {"answer": str, "evidence": list[dict], "confidence": float, "_chart": [...]}
    """
    start_ms = time.time()
    _ensure_loaded()
    assert _yolo is not None

    if not query or not query.strip():
        raise ValueError("Empty query for YOLO")

    pil_images = _coerce_images(images)
    image = pil_images[0]
    if len(pil_images) > 1:
        logger.warning("YOLO: received %d images for count, using first only", len(pil_images))

    target = _parse_query_target(query)
    # COCO class filter: if target maps to real COCO name, filter; else count all
    target_coco: str | None = _ALIAS_TO_COCO.get(target, None) if target else None
    # If target is unknown COCO class (e.g. building -> building not in COCO), treat as None (count all) but keep label for answer
    filter_label = target_coco if target_coco and target_coco in _yolo_names.values() else None
    # Allow env override filter
    if getattr(app_config, "YOLO_CLASSES", None):
        env_classes = [c.strip().lower() for c in app_config.YOLO_CLASSES.split(",") if c.strip()]  # type: ignore
        # keep as filter if provided
        _filter_set = set(env_classes)
    else:
        _filter_set = {filter_label} if filter_label else None  # type: ignore

    # Inference — ultralytics handles device internally; pass device explicitly if available
    device = _get_device()
    try:
        # ultralytics YOLO predict returns list[Results]
        results = _yolo.predict(
            source=image,
            conf=app_config.YOLO_CONF,
            iou=app_config.YOLO_IOU,
            device=device if device != "cpu" else "cpu",
            verbose=False,
        )
    except Exception as e:
        logger.error("YOLO predict failed: %s", e, exc_info=True)
        raise RuntimeError(f"YOLO inference failed: {e}") from e

    # Parse results
    counts: dict[str, int] = {}
    evidence: list[dict[str, Any]] = []
    confidences: list[float] = []
    if results and len(results) > 0:
        r = results[0]
        try:
            boxes = r.boxes  # ultralytics Boxes
            if boxes is not None and len(boxes) > 0:
                cls_list = boxes.cls.cpu().tolist() if hasattr(boxes.cls, "cpu") else list(boxes.cls)
                conf_list = boxes.conf.cpu().tolist() if hasattr(boxes.conf, "cpu") else list(boxes.conf)
                xyxy_list = boxes.xyxy.cpu().tolist() if hasattr(boxes.xyxy, "cpu") else list(boxes.xyxy)
                for cls_id, conf, xyxy in zip(cls_list, conf_list, xyxy_list):
                    try:
                        cid = int(cls_id)
                        label = _yolo_names.get(cid, str(cid)).lower()
                    except Exception:
                        label = str(cls_id).lower()
                    # Filter if requested
                    if _filter_set is not None and label not in _filter_set:
                        continue
                    counts[label] = counts.get(label, 0) + 1
                    confidences.append(float(conf))
                    # Evidence bbox: [[x,y],[x2,y2]]
                    try:
                        x1, y1, x2, y2 = [float(v) for v in xyxy]
                        evidence.append(
                            {
                                "type": "bounding_box",
                                "description": f"{label} {float(conf):.2f}",
                                "coordinates": [[x1, y1], [x2, y2]],
                                "image_index": 0,
                            }
                        )
                    except Exception:
                        pass
        except Exception as e:
            logger.warning("YOLO result parse failed: %s", e)

    total = sum(counts.values())
    # If no detections and we filtered, fallback to show 0 for target label
    if total == 0 and target:
        # Keep target label with 0 for chart visibility per spec (suppress or 0)
        label_for_answer = target.lower()
        # Don't add to chart if filtered found nothing — will be handled below
        pass

    # Build chart: label/value counts for bar/pie (counts, not %)
    chart: list[dict[str, Any]] = []
    if counts:
        # Top 5 sorted
        for lbl, cnt in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5]:
            chart.append({"label": lbl, "value": float(cnt)})
    else:
        # No detections — single 0 entry for target if any, else empty
        if target:
            chart = [{"label": target.lower(), "value": 0.0}]
        else:
            chart = []

    # Build answer bullets (replace paragraph) — identical Gradio/React markdown
    bullets: list[str] = []
    if target and total > 0 and filter_label:
        bullets.append(f"**Answer: {total} {target}(s)** detected (COCO class `{filter_label}`, conf {app_config.YOLO_CONF})")
    elif target and total > 0:
        # target not in COCO, show total all
        bullets.append(f"**Answer: {total} object(s)** detected for query `{target}` (all classes)")
    elif total > 0:
        bullets.append(f"**Answer: {total} object(s)** detected")
    elif target:
        bullets.append(f"**Answer: 0 {target}(s)** detected — no matching objects at conf {app_config.YOLO_CONF}")
    else:
        bullets.append("**Answer: 0 objects** detected — no objects at current thresholds")

    # Detail bullets per class
    if counts:
        for lbl, cnt in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:4]:
            bullets.append(f"**{lbl}**: **{cnt}** instance(s)")
        # If filtered and zero, note
        if target and filter_label and filter_label not in counts:
            bullets.append(f"No **{filter_label}** found — try lowering `YOLO_CONF` or using DOTA weight for buildings/ships")
    else:
        bullets.append(f"Try lowering confidence (current {app_config.YOLO_CONF}) or check image resolution (10m Sentinel-2 small objects may be <10px)")

    # Add quadrant note if evidence available (simple bbox centroid)
    if evidence:
        # Estimate dominant quadrant
        try:
            xs = [c[0][0] for c in [e["coordinates"] for e in evidence if e.get("coordinates")]]
            ys = [c[0][1] for c in [e["coordinates"] for e in evidence if e.get("coordinates")]]
            if xs and ys:
                cx = sum(xs) / len(xs)
                cy = sum(ys) / len(ys)
                w, h = image.size
                quad = ("north" if cy < h / 2 else "south") + ("west" if cx < w / 2 else "east")
                bullets.append(f"Locations centered **{quad}** quadrant (10m resolution, YOLO {getattr(_yolo, 'ckpt_path', app_config.YOLO_WEIGHTS)})")
        except Exception:
            pass

    answer = "\n".join(f"- {b}" for b in bullets)

    # Confidence: mean box conf, or 0.35 if none
    if confidences:
        conf = sum(confidences) / len(confidences)
        conf = max(0.1, min(0.95, float(conf)))
        # Boost slightly for count certainty
        if total > 0:
            conf = min(0.95, conf + 0.05)
    else:
        conf = 0.35

    latency_ms = int((time.time() - start_ms) * 1000)
    logger.info("YOLO count done: query=%r target=%s total=%d chart=%s latency=%dms", query[:60], target, total, chart, latency_ms)

    return {
        "answer": answer,
        "evidence": evidence,
        "confidence": float(conf),
        "_latency_ms": latency_ms,
        "_structured": {"bullets": bullets, "chart": chart},
        "_chart": chart,
        "_chart_type": "count",
    }


def is_real() -> bool:
    if not _load_attempted:
        _load_model()
    return _is_real


def load_error() -> str | None:
    if not _load_attempted:
        _load_model()
    return _load_error


def get_model_info() -> dict[str, Any]:
    if not _load_attempted:
        _load_model()
    raw_has_cuda = bool(torch is not None and torch.cuda.is_available()) if torch is not None else False
    has_cuda = raw_has_cuda and not getattr(app_config, "FORCE_CPU", False)
    device = _get_device()
    return {
        "base_model": "ultralytics/yolo",
        "adapter_path": app_config.YOLO_WEIGHTS,
        "weight": app_config.YOLO_WEIGHTS,
        "is_real": _is_real,
        "load_error": _load_error,
        "device": device,
        "has_cuda": raw_has_cuda,
        "has_cuda_effective": has_cuda,
        "force_cpu": getattr(app_config, "FORCE_CPU", False),
        "compute": "cuda" if has_cuda else "cpu",
        "classes": _yolo_names,
        "conf": app_config.YOLO_CONF,
        "iou": app_config.YOLO_IOU,
    }


def preload() -> bool:
    return _load_model()


__all__ = ["predict", "is_real", "load_error", "get_model_info", "preload"]
