"""Pydantic request/response + execution-trace schemas.

SHARED CONTRACT — other teammates (frontend, controller) build against these.
Flag any shape change to the team before modifying (see AGENTS.md).

Mirrors frontend/src/types/api.ts ExecutionTrace / QueryResponse shapes
so the UI can render the response verbatim.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# --- Evidence ---

class EvidenceRef(BaseModel):
    type: Literal["bounding_box", "overlay", "heatmap", "saliency", "image_ref"] = Field(
        description="Evidence modality"
    )
    description: str
    coordinates: list[list[float]] | None = None
    image_index: int | None = 0


# --- Execution trace ---

class ModelTraceEntry(BaseModel):
    name: str = Field(description="Model/adapter name, e.g. satquery-qwen2vl-stage1-bigearthnet")
    role: str = Field(description="Role in pipeline, e.g. visual_question_answering")
    parameters: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int = Field(description="Wall time for this model invocation")
    is_real: bool = Field(default=True, description="False if stubbed/degraded")
    is_stub: bool = Field(default=False)


class ExecutionTrace(BaseModel):
    task: str = Field(description="Normalized task chosen by controller")
    models_used: list[ModelTraceEntry] = Field(description="One entry per specialist invoked")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Global pipeline parameters (band_subset, resolution, etc.)",
    )
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    total_latency_ms: int


# --- API payloads ---

class QueryResponse(BaseModel):
    answer: str
    confidence: float = Field(ge=0.0, le=1.0)
    execution_trace: ExecutionTrace
    evidence: list[EvidenceRef] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    specialists: dict[str, Any]
    base_model: str
    adapter_path: str
    cuda_available: bool


__all__ = [
    "EvidenceRef",
    "ModelTraceEntry",
    "ExecutionTrace",
    "QueryResponse",
    "HealthResponse",
]
