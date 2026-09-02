"""
Grounding specialist — STUB (no trained adapter yet).

Benchmarks: VRSBench (grounding). Will be replaced in stage 2/3
when a grounding adapter is trained. Kept as stub so the registry
interface remains stable and the controller can already route to it.

Interface is identical to VQA: predict(images, query, task) -> {answer, evidence, confidence}
"""

from typing import Any


def predict(images: Any, query: str, task: str = "grounding") -> dict[str, Any]:
    # Stub response — clearly flagged so demo knows it's not real
    return {
        "answer": "[STUB] Grounding not yet trained — no fine-tuned adapter. Query was: " + (query[:120] if query else ""),
        "evidence": [
            {
                "type": "bounding_box",
                "description": "[STUB] Grounding evidence placeholder",
                "coordinates": [[10, 10], [100, 10], [100, 100], [10, 100]],
                "image_index": 0,
            }
        ],
        "confidence": 0.0,
        "_latency_ms": 0,
        "_stub": True,
    }


def is_real() -> bool:
    return False


def load_error() -> str | None:
    return "Grounding specialist is stubbed — no trained adapter yet (stage 2 planned)"


def get_model_info() -> dict[str, Any]:
    return {"is_real": False, "load_error": load_error(), "stub": True}


def preload() -> bool:
    return False
