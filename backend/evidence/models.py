"""Evidence models — typed evidence items."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


EvidenceType = Literal[
    "image_region",
    "bounding_box",
    "segmentation_mask",
    "change_mask",
    "derived_measurement",
    "metadata",
    "model_output",
    "source_scene",
    "execution_step",
    "overlay",
    "heatmap",
    "saliency",
    "image_ref",
]


class Evidence(BaseModel):
    type: EvidenceType
    description: str
    source: str | None = None
    bbox: list[float] | None = None
    coordinates: list[list[float]] | None = None
    metric: str | None = None
    value: float | None = None
    image_index: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)
