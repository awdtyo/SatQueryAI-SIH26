"""Model/tool registry the controller selects from.

This is the ONLY place specialist models are imported. Route handlers and
controller must call registry.get_specialist(task) or registry.predict(...),
never import backend.models.* directly.

Stage 1: VQA/captioning is real (Qwen2-VL-2B + BigEarthNet adapter).
All others are stubbed — see backend/models/*.py.

Changes to this file are high-stakes (shared contract). Flag to team before
modifying the interface.
"""

from __future__ import annotations

import logging
from typing import Any

from backend import config
from backend.models import (
    change_specialist,
    fusion_specialist,
    grounding_specialist,
    vqa_specialist,
)

logger = logging.getLogger(__name__)

# Registry — task key -> specialist module (each exposes predict + is_real etc)
_REGISTRY: dict[str, Any] = {
    "vqa": vqa_specialist,
    "captioning": vqa_specialist,
    "visual_question_answering": vqa_specialist,
    # Aliases that controller may emit
    "vqa_captioning": vqa_specialist,
    "describe": vqa_specialist,
    # Stubbed specialists
    "grounding": grounding_specialist,
    "visual_grounding": grounding_specialist,
    "change_detection": change_specialist,
    "change": change_specialist,
    "cdvqa": change_specialist,
    "optical_sar_fusion": fusion_specialist,
    "fusion": fusion_specialist,
    "sar": fusion_specialist,
}

# Also respect config.TASK_MODEL_MAP overrides at import time
# e.g. TASK_MODEL_MAP = {"vqa": "vqa"} -> already covered; but env overrides
# may map a task to a different registry key.
_TASK_ALIAS: dict[str, str] = {k.lower(): v for k, v in config.TASK_MODEL_MAP.items()}


def _normalize_task(task: str) -> str:
    t = task.strip().lower()
    # Check alias via config first
    if t in _TASK_ALIAS:
        mapped = _TASK_ALIAS[t]
        # mapped is a specialist key like "vqa" / "grounding_stub"
        # Normalize the "stub" suffix
        if mapped == "vqa":
            return "vqa"
        if mapped in ("grounding_stub", "grounding"):
            return "grounding"
        if mapped in ("change_stub", "change_detection"):
            return "change_detection"
        if mapped in ("fusion_stub", "optical_sar_fusion"):
            return "optical_sar_fusion"
        return mapped
    return t


def get_specialist(task: str):
    """Return the specialist module for a task. Raises KeyError if unknown."""
    key = _normalize_task(task)
    if key in _REGISTRY:
        return _REGISTRY[key]
    # Fallback: try raw task
    if task in _REGISTRY:
        return _REGISTRY[task]
    raise KeyError(f"Unknown task '{task}' — registered: {sorted(_REGISTRY.keys())}")


def predict(images: Any, query: str, task: str) -> dict[str, Any]:
    """Delegate predict to the specialist for the given task.

    This is the inference interface shared contract:
        predict(image(s), query, task) -> {answer, evidence, confidence}
    """
    specialist = get_specialist(task)
    return specialist.predict(images, query, task=task)


def is_real(task: str) -> bool:
    try:
        return get_specialist(task).is_real()  # type: ignore
    except Exception:
        return False


def get_model_info(task: str) -> dict[str, Any]:
    try:
        mod = get_specialist(task)
        if hasattr(mod, "get_model_info"):
            return mod.get_model_info()
        return {"is_real": False}
    except Exception as e:
        return {"is_real": False, "load_error": str(e)}


def list_specialists() -> dict[str, dict[str, Any]]:
    """For /health and startup logging — de-duplicated by module."""
    seen: dict[int, str] = {}
    out: dict[str, dict[str, Any]] = {}
    for task, mod in _REGISTRY.items():
        mid = id(mod)
        if mid in seen:
            continue
        seen[mid] = task
        # Use get_model_info if available
        info = mod.get_model_info() if hasattr(mod, "get_model_info") else {}
        out[task] = info
    # Add a human-friendly summary keyed by specialist name
    return {
        "vqa (real)": vqa_specialist.get_model_info(),
        "grounding (stub)": grounding_specialist.get_model_info(),
        "change_detection (stub)": change_specialist.get_model_info(),
        "optical_sar_fusion (stub)": fusion_specialist.get_model_info(),
    }


def health() -> dict[str, Any]:
    """Aggregated health for startup logging and /health endpoint."""
    return {
        "registry": list_specialists(),
        "task_map": _TASK_ALIAS,
    }


def preload_all() -> dict[str, bool]:
    """Eagerly load all specialists at startup (only VQA does real work)."""
    results: dict[str, bool] = {}
    for name, mod in {
        "vqa": vqa_specialist,
        "grounding": grounding_specialist,
        "change": change_specialist,
        "fusion": fusion_specialist,
    }.items():
        try:
            if hasattr(mod, "preload"):
                results[name] = bool(mod.preload())
            else:
                results[name] = False
        except Exception as e:
            logger.warning("Preload failed for %s: %s", name, e)
            results[name] = False
    return results
