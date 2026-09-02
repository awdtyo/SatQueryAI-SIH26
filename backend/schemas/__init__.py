"""Pydantic models for SatQuery AI API — the shared contract between frontend and backend.

FROZEN CONTRACT (as of 2026-09-01):
    QueryRequest, ExecutionTrace, QueryResponse, and their nested types are the
    authoritative shapes the frontend builds against. Any changes after this point
    MUST be announced to the team before merging — silent changes break consumers.

Task types (enum TaskType):
    vqa, captioning, grounding, change_detection, optical_sar_fusion

Input modality configuration:
    - single: one image (optical or SAR)
    - optical_sar_pair: two images (optical + SAR of same scene)
    - bi_temporal: two images (same sensor, different dates)

Evidence shapes:
    - bounding_box: [x_min, y_min, x_max, y_max] normalised to [0, 1]
    - change_mask: placeholder string (actual raster data returned separately)
"""

from backend.schemas.models import (
    BoundingBox,
    EvidenceItem,
    ExecutionTrace,
    InputImage,
    InputModality,
    ModalityConfig,
    QueryRequest,
    QueryResponse,
    TaskType,
)

__all__ = [
    "BoundingBox",
    "EvidenceItem",
    "ExecutionTrace",
    "InputImage",
    "InputModality",
    "ModalityConfig",
    "QueryRequest",
    "QueryResponse",
    "TaskType",
]
