"""Specialist base interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from backend.core.assets import SatelliteAsset


class SpecialistResult(BaseModel):
    specialist: str
    status: str = Field(description="success|unsupported|error")
    answer: str | None = None
    findings: list[dict[str, Any]] = Field(default_factory=list, description="Structured observations supporting answer")
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float | None = None
    limitations: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    visualization_data: dict[str, Any] | list[dict[str, Any]] | None = Field(default=None, description="Data intended for visualization")

    class Config:
        arbitrary_types_allowed = True


class SpecialistBase(ABC):
    name: str = "base"
    capabilities: list[str] = []
    supported_inputs: list[str] = ["single"]

    @abstractmethod
    def can_handle(self, query: str, assets: list[SatelliteAsset]) -> bool:
        raise NotImplementedError

    @abstractmethod
    def run(self, assets: list[SatelliteAsset], query: str, task: str | None = None, **kwargs) -> SpecialistResult:
        raise NotImplementedError

    def evidence_generation(self, result: SpecialistResult) -> list[dict[str, Any]]:
        return result.evidence
