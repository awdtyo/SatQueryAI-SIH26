"""Specialist registry — wraps existing backend.registry with agentic interface."""

from __future__ import annotations

from typing import Any

from backend.agents.specialists.base import SpecialistBase
from backend.agents.specialists.vqa_spec import VQASpecialist
from backend.agents.specialists.spectral_spec import SpectralSpecialist
from backend.agents.specialists.change_spec import ChangeSpecialist
from backend.agents.specialists.counting_spec import CountingSpecialist

_REGISTRY: dict[str, SpecialistBase] = {
    "vqa": VQASpecialist(),
    "spectral": SpectralSpecialist(),
    "change_detection": ChangeSpecialist(),
    "counting": CountingSpecialist(),
}

# Aliases
ALIASES = {
    "captioning": "vqa",
    "visual_question_answering": "vqa",
    "ndvi": "spectral",
    "ndwi": "spectral",
    "ndbi": "spectral",
    "ndmi": "spectral",
    "savi": "spectral",
    "change": "change_detection",
    "cdvqa": "change_detection",
    "count": "counting",
    "yolo": "counting",
    "optical_sar_fusion": "vqa",  # fusion maps to VQA via existing adapter
    "fusion": "vqa",
}


def get_specialist(name: str) -> SpecialistBase:
    key = ALIASES.get(name.lower(), name.lower())
    if key in _REGISTRY:
        return _REGISTRY[key]
    raise KeyError(f"Unknown specialist {name}")

def list_specialists() -> dict[str, SpecialistBase]:
    return dict(_REGISTRY)

def can_handle(query: str, assets: list[Any], specialist: str | None = None) -> bool:
    if specialist:
        return get_specialist(specialist).can_handle(query, assets)
    return any(s.can_handle(query, assets) for s in _REGISTRY.values())
