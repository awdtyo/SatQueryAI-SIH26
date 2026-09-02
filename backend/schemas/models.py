"""Core Pydantic models for the SatQuery AI API contract.

See __init__.py for contract-freeze notes and task-type documentation.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TaskType(str, Enum):
    """Task types the controller can route to."""

    vqa = "vqa"
    captioning = "captioning"
    grounding = "grounding"
    change_detection = "change_detection"
    optical_sar_fusion = "optical_sar_fusion"


class InputModality(str, Enum):
    """Supported image modality configurations."""

    single = "single"  # one image (optical or SAR)
    optical_sar_pair = "optical_sar_pair"  # optical + SAR pair
    bi_temporal = "bi_temporal"  # same sensor, two dates


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class InputImage(BaseModel):
    """A single image reference.

    In the API the image is expected as a base64-encoded string or a file path
    (for development). The frontend will send base64; internal testing may use
    paths.
    """

    data: str = Field(
        ...,
        description=(
            "Image data — either a base64-encoded string (API) or a local file "
            "path (dev/testing). The controller normalises this before passing "
            "to specialist models."
        ),
    )
    format: str = Field(
        ...,
        description=(
            "Image file format. Allowed: 'geotiff', 'tiff', 'png', 'jpeg'. "
            "GeoTIFF/TIFF preferred; PNG/JPEG accepted for benchmarks only. "
            "The controller rejects unsupported formats."
        ),
    )
    bands: int = Field(
        default=3,
        ge=1,
        le=64,
        description="Number of spectral bands in the image.",
    )
    modality: Literal["optical", "sar", "multispectral"] = Field(
        default="optical",
        description="Sensor modality of this image.",
    )


class ModalityConfig(BaseModel):
    """Describes the input modality configuration for a query."""

    type: InputModality = Field(
        ...,
        description=(
            "Which configuration: single image, optical+SAR pair, or bi-temporal pair."
        ),
    )
    images: list[InputImage] = Field(
        ...,
        min_length=1,
        max_length=2,
        description=(
            "1 image for single, 2 for optical_sar_pair or bi_temporal. "
            "Ordering: for optical_sar_pair, [optical, SAR]; for bi_temporal, "
            "[earlier, later]."
        ),
    )

    @model_validator(mode="after")
    def _validate_image_count(self) -> ModalityConfig:
        """Cross-validate image count vs modality type.

        Note: semantic modality-combination checks (e.g. optical_sar_pair must
        contain one optical + one SAR) are performed by the controller's
        ``validate_input``, per AGENTS.md. The schema enforces structural shape.
        """
        expected = {
            InputModality.single: 1,
            InputModality.optical_sar_pair: 2,
            InputModality.bi_temporal: 2,
        }
        n = len(self.images)
        e = expected[self.type]
        if n != e:
            raise ValueError(
                f"Modality '{self.type.value}' requires exactly {e} image(s), got {n}"
            )
        return self


class QueryRequest(BaseModel):
    """Incoming query from the user.

    The frontend sends this shape. The controller validates, classifies the task,
    and routes to the appropriate specialist model.
    """

    query: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="Natural-language query about the satellite imagery.",
    )
    modality: ModalityConfig = Field(
        ...,
        description="Input image(s) and their modality configuration.",
    )

    @field_validator("query")
    @classmethod
    def _query_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must contain non-whitespace characters")
        return value


# ---------------------------------------------------------------------------
# Output / trace models
# ---------------------------------------------------------------------------


class BoundingBox(BaseModel):
    """Axis-aligned bounding box normalised to [0, 1].

    Used in grounding evidence to localise objects or regions.
    """

    x_min: float = Field(..., ge=0.0, le=1.0)
    y_min: float = Field(..., ge=0.0, le=1.0)
    x_max: float = Field(..., ge=0.0, le=1.0)
    y_max: float = Field(..., ge=0.0, le=1.0)

    def model_post_init(self, __context: Any, /) -> None:
        if self.x_min >= self.x_max or self.y_min >= self.y_max:
            raise ValueError(
                f"Invalid bbox: x_min ({self.x_min}) must be < x_max ({self.x_max}), "
                f"and y_min ({self.y_min}) must be < y_max ({self.y_max})"
            )


class EvidenceItem(BaseModel):
    """A single piece of evidence the specialist model returns.

    ``type`` determines which optional fields are populated:
      - "text":        ``text`` is set
      - "bbox":        ``bbox`` is set (and optionally ``text``)
      - "change_mask": ``change_mask_ref`` is set (reference to raster)
      - "caption":     ``text`` is set (free-form caption)
    """

    type: Literal["text", "bbox", "change_mask", "caption"] = Field(
        ...,
        description="Kind of evidence.",
    )
    text: str | None = Field(
        default=None,
        description="Textual evidence (description, VQA answer fragment, caption).",
    )
    bbox: BoundingBox | None = Field(
        default=None,
        description="Bounding-box evidence (for grounding tasks).",
    )
    change_mask_ref: str | None = Field(
        default=None,
        description=(
            "Reference to a change-mask raster (path or URL). The actual pixel "
            "data is returned out-of-band; this is a pointer."
        ),
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence for this individual evidence item.",
    )


class ExecutionTrace(BaseModel):
    """Mandatory graded output — full execution trace.

    Captures *how* the system arrived at its answer: which task was classified,
    which specialist model(s) were invoked, with what parameters, overall
    confidence, and the evidence produced.

    This is NOT a debug log. Treat it as a first-class API response field.
    """

    task: TaskType = Field(
        ...,
        description="The task the controller classified the query as.",
    )
    selected_models: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "Name(s) of specialist model(s) invoked, matching keys in the "
            "registry. E.g. ['vqa_stub'] or ['change_detection_stub']."
        ),
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Parameters passed to the specialist model(s). Schema varies by task type."
        ),
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall confidence score for the response.",
    )
    evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description=(
            "Structured evidence items produced by the specialist model(s). "
            "May include text, bounding boxes, change-mask references, captions."
        ),
    )


class QueryResponse(BaseModel):
    """Full response returned by the /query endpoint.

    Wraps the natural-language answer text plus the mandatory execution trace.
    """

    answer: str = Field(
        ...,
        min_length=1,
        description="Natural-language answer to the user's query.",
    )
    trace: ExecutionTrace = Field(
        ...,
        description="Full execution trace (mandatory graded output).",
    )
