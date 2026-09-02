"""Agentic controller for SatQuery AI.

Orchestrates the full pipeline:
    1. Input validation (modality, format, band count, image count)
    2. Task classification (keyword + modality routing)
    3. Specialist selection via registry
    4. Execution trace assembly

The controller never imports specialist models directly — it always goes
through ``backend.registry``.
"""

from __future__ import annotations

import logging

from backend.registry import (
    SpecialistOutput,
    get_specialist,
)
from backend.schemas.models import (
    ExecutionTrace,
    InputModality,
    ModalityConfig,
    QueryRequest,
    QueryResponse,
    TaskType,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

VALID_FORMATS = {"geotiff", "tiff", "png", "jpeg"}
VALID_MODALITIES = {"optical", "sar", "multispectral"}


class InputValidationError(Exception):
    """Raised when input images fail validation checks."""


def validate_input(modality: ModalityConfig) -> None:
    """Validate image format, band count, and single/pair/bi-temporal configuration.

    This is the controller's mandated input-compatibility gate, called before
    any specialist model is invoked. Format, bands, and modality configuration
    are checked here even though some are also hinted at by the schema.

    Raises:
        InputValidationError: With a human-readable reason on failure.
    """
    for i, img in enumerate(modality.images):
        if img.format not in VALID_FORMATS:
            raise InputValidationError(
                f"Image {i}: format '{img.format}' not supported. "
                f"Allowed: {sorted(VALID_FORMATS)}"
            )
        if img.modality not in VALID_MODALITIES:
            raise InputValidationError(
                f"Image {i}: modality '{img.modality}' not recognised. "
                f"Allowed: {sorted(VALID_MODALITIES)}"
            )
        if not (1 <= img.bands <= 64):
            raise InputValidationError(
                f"Image {i}: band count {img.bands} out of supported range (1-64)."
            )

    if modality.type == InputModality.optical_sar_pair:
        modalities = [img.modality for img in modality.images]
        if not (set(modalities) == {"optical", "sar"}):
            raise InputValidationError(
                f"optical_sar_pair requires one 'optical' and one 'sar' image, "
                f"got: {modalities}"
            )

    if modality.type == InputModality.bi_temporal:
        modalities = [img.modality for img in modality.images]
        if len(set(modalities)) != 1:
            raise InputValidationError(
                f"bi_temporal images must share the same modality, got: {modalities}"
            )


# ---------------------------------------------------------------------------
# Task ↔ modality compatibility
# ---------------------------------------------------------------------------

# Hard constraints: task types that fundamentally require a specific input
# configuration. A query classified to one of these must be backed by a
# modality that can actually support it, otherwise the specialist model
# cannot produce a meaningful/evidence-grounded answer.
_TASK_MODALITY_REQUIREMENTS: dict[TaskType, InputModality] = {
    TaskType.change_detection: InputModality.bi_temporal,
    TaskType.optical_sar_fusion: InputModality.optical_sar_pair,
}


def validate_task_modality_compatibility(
    task: TaskType, modality: ModalityConfig
) -> None:
    """Reject queries whose classified task cannot be served by the given input.

    e.g. a change-detection query with only a single image is invalid, as is
    an optical-SAR fusion query without an optical+SAR pair. This catches the
    mismatch between what the *query implies* and what the *input provides*,
    independently of the schema-level shape checks in ``validate_input``.

    Raises:
        InputValidationError: When the task requires a modality configuration
            the provided images do not supply.
    """
    required = _TASK_MODALITY_REQUIREMENTS.get(task)
    if required is None:
        return  # single-image tasks (vqa / captioning / grounding) have no hard constraint
    if modality.type != required:
        raise InputValidationError(
            f"Task '{task.value}' requires a '{required.value}' input "
            f"configuration, but got '{modality.type.value}' ("
            f"{len(modality.images)} image(s))."
        )


# ---------------------------------------------------------------------------
# Task classification — keyword + modality routing (rule-based, no LLM)
# ---------------------------------------------------------------------------

# Keywords mapped to candidate task types, ordered by priority.
_KEYWORD_RULES: list[tuple[list[str], TaskType | None]] = [
    # Explicit change-detection triggers
    (
        ["change", "changed", "difference", "before", "after", "compare", "temporal"],
        TaskType.change_detection,
    ),
    # Explicit fusion triggers
    (
        [
            "sar and optical",
            "optical and sar",
            "sar + optical",
            "optical + sar",
            "fuse",
            "fusion",
            "combine sar",
        ],
        TaskType.optical_sar_fusion,
    ),
    # Grounding triggers
    (
        [
            "locate",
            "where is",
            "find",
            "show me",
            "bounding box",
            "region of interest",
            "highlight",
        ],
        TaskType.grounding,
    ),
    # Captioning triggers
    (
        ["describe", "caption", "what does", "summarise", "summarize", "overview of"],
        TaskType.captioning,
    ),
    # VQA is the default catch-all
    (
        [
            "what",
            "how many",
            "is there",
            "are there",
            "count",
            "which",
            "why",
            "can you",
        ],
        TaskType.vqa,
    ),
]


def classify_task(query: str, modality: ModalityConfig) -> TaskType:
    """Classify the query into a task type using keyword + modality heuristics.

    Priority:
      1. Strong keyword match (change-detection / fusion) overrides modality.
      2. Modality-implied defaults when no strong keyword match:
            - optical_sar_pair with no change keywords -> fusion
            - bi_temporal with no caption keywords -> change_detection
      3. Keyword-based classification (grounding, captioning, vqa).
      4. Default: vqa.

    Returns:
        The classified TaskType.
    """
    query_lower = query.lower().strip()

    # Phase 1: keyword matching
    for keywords, task in _KEYWORD_RULES:
        for kw in keywords:
            if task is not None and kw in query_lower:
                return task

    # Phase 2: modality-implied defaults
    if modality.type == InputModality.optical_sar_pair:
        return TaskType.optical_sar_fusion
    if modality.type == InputModality.bi_temporal:
        return TaskType.change_detection

    # Phase 3: default
    return TaskType.vqa


# ---------------------------------------------------------------------------
# Controller orchestration
# ---------------------------------------------------------------------------


def handle_query(request: QueryRequest) -> QueryResponse:
    """Full pipeline: validate -> classify -> route -> trace -> response.

    This is the main entry point called by the API layer.

    Raises:
        InputValidationError: If input validation fails.
        KeyError: If no specialist is registered for the classified task.
    """
    # 1. Input validation
    validate_input(request.modality)

    # 2. Task classification
    task = classify_task(request.query, request.modality)
    logger.info("Classified query as task: %s", task.value)

    # 2b. Verify the classified task is compatible with the provided input
    validate_task_modality_compatibility(task, request.modality)

    # 3. Route to specialist via registry
    model_name, specialist_fn = get_specialist(task)
    logger.info("Selected specialist: %s", model_name)

    specialist_output: SpecialistOutput = specialist_fn(
        images=request.modality.images,
        query=request.query,
        task=task,
    )

    # 4. Assemble execution trace
    trace = ExecutionTrace(
        task=task,
        selected_models=[specialist_output.model_name],
        parameters={},
        confidence=specialist_output.confidence,
        evidence=specialist_output.evidence,
    )

    # 5. Build response
    return QueryResponse(
        answer=specialist_output.answer,
        trace=trace,
    )
