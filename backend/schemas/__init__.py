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
    model_config = {"extra": "allow"}  # allow provenance fields like spatial_description without breaking

    type: Literal[
        "bounding_box",
        "overlay",
        "heatmap",
        "saliency",
        "image_ref",
        "coordinate_geometry",
        "image_region",
        "segmentation_mask",
        "change_mask",
        "derived_measurement",
        "metadata",
        "model_output",
        "source_scene",
        "execution_step",
    ] = Field(
        description="Evidence modality"
    )
    description: str
    coordinates: list[list[float]] | None = None
    image_index: int | None = 0
    # Spatial interpretation provenance — additive, preserves raw coordinates
    spatial_description: str | None = Field(default=None, description="Natural-language interpretation of coordinates")
    spatial_provenance: dict[str, Any] | None = Field(default=None, description="Provenance for spatial description")
    bbox: list[float] | None = None
    metric: str | None = None
    value: float | None = None
    source: str | None = None
    metadata: dict[str, Any] | None = None


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


# --- Structured output for bullets/charts (bullets replace paragraph, bar/pie toggle) ---

class ChartEntry(BaseModel):
    label: str = Field(description="Class label, e.g. forest, urban, water or car count or delta")
    value: float = Field(ge=-100.0, le=1000.0, description="Percentage -100..100, delta, or count")


class StructuredOutput(BaseModel):
    bullets: list[str] = Field(default_factory=list, description="3-6 markdown bullet strings")
    chart: list[ChartEntry] = Field(default_factory=list, description="2-5 entries for bar/pie")
    chart_type: Literal["distribution", "count", "change", "none"] | None = Field(default=None, description="Question-aware chart type")
    summary: str | None = Field(default=None, description="Optional one-line summary")


# --- API payloads ---

class QueryResponse(BaseModel):
    answer: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="Model confidence if available, else null")
    execution_trace: ExecutionTrace
    evidence: list[EvidenceRef] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list, description="Structured key findings supporting answer")
    limitations: list[str] = Field(default_factory=list, description="Limitations when relevant")
    metrics: dict[str, Any] = Field(default_factory=dict, description="Actual numeric measurements")
    artifacts: list[dict[str, Any]] = Field(default_factory=list, description="Images, masks, overlays")
    structured: StructuredOutput | None = Field(default=None, description="Parsed bullets/chart")
    chart: list[ChartEntry] | None = Field(default=None, description="Alias for structured.chart for flat access")
    chart_type: Literal["distribution", "count", "change", "none"] | None = Field(default=None, description="Question-aware chart type")
    # Canonical visualization — always present for successful queries (fallback hierarchy)
    visualization: dict[str, Any] | None = Field(default=None, description="Canonical visualization {type, title, data} always present for success")
    # Active-scene context: set when the query was analyzed against a SELECTED satellite scene
    # (Selected Satellite Image Query Mode). Carries the scene id/collection/datetime/aoi that
    # was actually analyzed so the UI can render an "Active Scene" card + provenance.
    scene_context: dict[str, Any] | None = Field(
        default=None,
        description="Active satellite scene context the query was analyzed against (scene id, collection, datetime, platform, cloud, aoi, analysis_source).",
    )
    # Raster payload for map overlay (spectral index preview_b64/bounds/stats, or scene RGB
    # image info for VQA/count on the active scene). Kept separate from ExecutionTrace so the
    # frontend can render a GIS layer without re-deriving it from trace parameters.
    analysis: dict[str, Any] | None = Field(
        default=None,
        description="Raster analysis payload (type, preview_b64, bounds, stats, scene_id) for map overlay and evidence.",
    )


class HealthResponse(BaseModel):
    status: str
    specialists: dict[str, Any]
    base_model: str
    adapter_path: str
    cuda_available: bool
    force_cpu: bool = False
    compute: str = "cpu"
    device: str = "cpu"


__all__ = [
    "EvidenceRef",
    "ModelTraceEntry",
    "ExecutionTrace",
    "ChartEntry",
    "StructuredOutput",
    "QueryResponse",
    "HealthResponse",
]
