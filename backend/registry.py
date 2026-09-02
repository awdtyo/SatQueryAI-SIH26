"""Specialist model registry — the controller selects from this, never imports directly.

FROZEN INFERENCE INTERFACE (as of 2026-09-01):
    Every registered specialist must implement:

        predict(
            images: list[InputImage],
            query: str,
            task: TaskType,
            **kwargs,
        ) -> SpecialistOutput

    Where ``SpecialistOutput`` is a dataclass-like object with:
        - answer: str             (natural-language answer)
        - confidence: float       (0.0–1.0)
        - evidence: list[EvidenceItem]
        - model_name: str         (registry key of this specialist)

    The training person's model wrapper MUST match this signature exactly.
    Changes to this interface must be announced before merging.

Registry pattern:
    Specialists register via ``register_specialist(task, name, fn)`` or the
    ``@specialist(task, name)`` decorator. The controller calls
    ``get_specialist(task)`` to retrieve the first (or best) specialist for a
    given task type, or ``get_specialists(task)`` for all matches.

Stub specialists (prefixed ``_stub_``) return realistic fake outputs so the
full pipeline can be tested end-to-end before real models exist. They are
marked with TODO and must be swapped for real wrappers once adapters are ready.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from backend.schemas.models import (
    EvidenceItem,
    InputImage,
    TaskType,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Specialist output — the standard return type from every specialist
# ---------------------------------------------------------------------------


class SpecialistOutput:
    """Standard output from a specialist model's ``predict()`` call.

    Attributes:
        answer: Natural-language answer to the user's query.
        confidence: Overall confidence score (0.0–1.0).
        evidence: List of structured evidence items.
        model_name: Registry key that identifies this specialist.
    """

    def __init__(
        self,
        answer: str,
        confidence: float,
        evidence: list[EvidenceItem],
        model_name: str,
    ) -> None:
        self.answer = answer
        self.confidence = confidence
        self.evidence = evidence
        self.model_name = model_name


# ---------------------------------------------------------------------------
# Registry internals
# ---------------------------------------------------------------------------

# Maps task_type -> {name -> callable}
_registry: dict[TaskType, dict[str, Callable[..., SpecialistOutput]]] = {}


def register_specialist(
    task: TaskType,
    name: str,
) -> Callable[[Callable[..., SpecialistOutput]], Callable[..., SpecialistOutput]]:
    """Decorator to register a specialist function for a given task type.

    Usage::

        @specialist(TaskType.vqa, "my_vqa_model")
        def predict(images, query, task, **kwargs):
            ...
    """

    def decorator(
        fn: Callable[..., SpecialistOutput],
    ) -> Callable[..., SpecialistOutput]:
        _registry.setdefault(task, {})[name] = fn
        logger.info("Registered specialist '%s' for task '%s'", name, task.value)
        return fn

    return decorator


def get_specialist(
    task: TaskType, name: str | None = None
) -> tuple[str, Callable[..., SpecialistOutput]]:
    """Return ``(name, fn)`` for the given task.

    If ``name`` is provided, return that exact specialist (raises KeyError if
    missing). If ``name`` is None, return the first registered specialist for
    the task (raises KeyError if none registered).

    Raises:
        KeyError: If no specialist is registered for the task (or the named one).
    """
    candidates = _registry.get(task, {})
    if not candidates:
        raise KeyError(f"No specialist registered for task '{task.value}'")
    if name is not None:
        if name not in candidates:
            raise KeyError(
                f"Specialist '{name}' not found for task '{task.value}'. "
                f"Available: {list(candidates.keys())}"
            )
        return name, candidates[name]
    first_name = next(iter(candidates))
    return first_name, candidates[first_name]


def get_specialists(task: TaskType) -> dict[str, Callable[..., SpecialistOutput]]:
    """Return all registered specialists for a task (may be empty dict)."""
    return dict(_registry.get(task, {}))


def list_all() -> dict[str, list[str]]:
    """Return a summary of all registered specialists, keyed by task type."""
    return {task.value: list(names) for task, names in _registry.items()}


# ---------------------------------------------------------------------------
# Stub specialists — TODO: swap for real model wrappers when adapters ready
# ---------------------------------------------------------------------------


@register_specialist(TaskType.vqa, "vqa_stub")
def _stub_vqa(
    images: list[InputImage],
    query: str,
    task: TaskType,
    **kwargs: Any,
) -> SpecialistOutput:
    """Stub VQA specialist — returns a deterministic fake answer.

    TODO: Replace with real VQA model wrapper once QLoRA adapter is ready.
    The real wrapper must accept the same (images, query, task, **kwargs)
    signature and return SpecialistOutput.
    """
    return SpecialistOutput(
        answer=f"[VQA stub] Based on the satellite image, here is a response to: '{query}'",
        confidence=0.75,
        evidence=[
            EvidenceItem(
                type="text",
                text="Stub evidence: image analysed by placeholder model.",
                confidence=0.75,
            )
        ],
        model_name="vqa_stub",
    )


@register_specialist(TaskType.captioning, "captioning_stub")
def _stub_captioning(
    images: list[InputImage],
    query: str,
    task: TaskType,
    **kwargs: Any,
) -> SpecialistOutput:
    """Stub captioning specialist.

    TODO: Replace with real captioning model wrapper.
    """
    return SpecialistOutput(
        answer="[Captioning stub] A satellite image showing an area with mixed land use.",
        confidence=0.8,
        evidence=[
            EvidenceItem(
                type="caption",
                text="Stub caption: generated by placeholder model.",
                confidence=0.8,
            )
        ],
        model_name="captioning_stub",
    )


@register_specialist(TaskType.grounding, "grounding_stub")
def _stub_grounding(
    images: list[InputImage],
    query: str,
    task: TaskType,
    **kwargs: Any,
) -> SpecialistOutput:
    """Stub grounding specialist — returns a bounding-box evidence item.

    TODO: Replace with real grounding model wrapper.
    """
    from backend.schemas.models import BoundingBox

    return SpecialistOutput(
        answer=f"[Grounding stub] Located region relevant to: '{query}'",
        confidence=0.7,
        evidence=[
            EvidenceItem(
                type="bbox",
                text="Stub bounding box for queried region.",
                bbox=BoundingBox(x_min=0.2, y_min=0.3, x_max=0.8, y_max=0.7),
                confidence=0.7,
            )
        ],
        model_name="grounding_stub",
    )


@register_specialist(TaskType.change_detection, "change_detection_stub")
def _stub_change_detection(
    images: list[InputImage],
    query: str,
    task: TaskType,
    **kwargs: Any,
) -> SpecialistOutput:
    """Stub change-detection specialist.

    TODO: Replace with real change-detection model wrapper.
    """
    return SpecialistOutput(
        answer=(
            "[Change detection stub] Comparing the two images, there appear to be "
            "significant changes in land cover between the two acquisition dates."
        ),
        confidence=0.65,
        evidence=[
            EvidenceItem(
                type="change_mask",
                text="Stub change mask reference.",
                change_mask_ref="/tmp/stub_change_mask.tif",
                confidence=0.65,
            )
        ],
        model_name="change_detection_stub",
    )


@register_specialist(TaskType.optical_sar_fusion, "fusion_stub")
def _stub_fusion(
    images: list[InputImage],
    query: str,
    task: TaskType,
    **kwargs: Any,
) -> SpecialistOutput:
    """Stub optical-SAR fusion specialist.

    TODO: Replace with real fusion model wrapper.
    """
    return SpecialistOutput(
        answer=(
            f"[Fusion stub] Fusing optical and SAR data to answer: '{query}'. "
            "The combined analysis reveals features visible in both modalities."
        ),
        confidence=0.7,
        evidence=[
            EvidenceItem(
                type="text",
                text="Stub fused evidence from optical+SAR analysis.",
                confidence=0.7,
            )
        ],
        model_name="fusion_stub",
    )
