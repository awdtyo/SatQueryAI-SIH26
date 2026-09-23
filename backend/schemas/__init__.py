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


# --- Structured output for bullets/charts (bullets replace paragraph, bar/pie toggle) ---

class ChartEntry(BaseModel):
    label: str = Field(description="Class label, e.g. forest, urban, water or car count or delta")
    value: float = Field(ge=-100.0, le=1000.0, description="Percentage -100..100, delta, or count")


class StructuredOutput(BaseModel):
    bullets: list[str] = Field(default_factory=list, description="3-6 markdown bullet strings")
    chart: list[ChartEntry] = Field(default_factory=list, description="2-5 entries for bar/pie")
    chart_type: Literal["distribution", "count", "change", "none"] | None = Field(default=None, description="Question-aware chart type")
    summary: str | None = Field(default=None, description="Optional one-line summary")


# --- Location input (search by place name) ---

class Coordinates(BaseModel):
    lat: float = Field(ge=-90, le=90, description="Latitude")
    lon: float = Field(ge=-180, le=180, description="Longitude")


class QueryRequest(BaseModel):
    query: str = Field(description="Natural language question")
    input_mode: str = Field(default="single", description="single | optical-sar | bi-temporal")
    # Alternative to images — resolved via geocode + Planetary Computer STAC
    location_query: str | None = Field(default=None, description="Place name (Nominatim), e.g. 'Bengaluru, India'")
    coordinates: Coordinates | None = Field(default=None, description="Direct lat/lon alternative to place name")
    # For bi-temporal: optional second location/date
    location_query_2: str | None = Field(default=None, description="Second place for bi-temporal (e.g. T2 AOI)")
    coordinates_2: Coordinates | None = Field(default=None, description="Second lat/lon for bi-temporal")

    # Note: images are sent as multipart files, not JSON — see backend/api/__init__.py


# --- API payloads ---

class ResolvedImagePreview(BaseModel):
    display_name: str | None = None
    lat: float | None = None
    lon: float | None = None
    scene_id: str | None = None
    collection: str | None = None
    preview_b64: str | None = Field(default=None, description="data:image/png;base64,... preview for ImageryViewer")
    bbox: list[float] | None = None


class QueryResponse(BaseModel):
    answer: str
    confidence: float = Field(ge=0.0, le=1.0)
    execution_trace: ExecutionTrace
    evidence: list[EvidenceRef] = Field(default_factory=list)
    structured: StructuredOutput | None = Field(default=None, description="Parsed bullets/chart")
    chart: list[ChartEntry] | None = Field(default=None, description="Alias for structured.chart for flat access")
    chart_type: Literal["distribution", "count", "change", "none"] | None = Field(default=None, description="Question-aware chart type")
    resolved_images: list[ResolvedImagePreview] | None = Field(default=None, description="Previews for location-fetched imagery (to show in ImageryViewer)")


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
    "Coordinates",
    "QueryRequest",
    "ResolvedImagePreview",
    "QueryResponse",
    "HealthResponse",
]
