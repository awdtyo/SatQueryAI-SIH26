"""
Change-detection specialist — STUB (no trained adapter yet).

Benchmarks: CDVQA (bi-temporal change). Will be replaced when CDVQA
adapter is trained in stage 3. Keeps the registry stable.

Interface: predict(images, query, task) -> {answer, evidence, confidence}
Expects images as pair (T1, T2) or list of 2.
"""

from typing import Any


def predict(images: Any, query: str, task: str = "change_detection") -> dict[str, Any]:
    return {
        "answer": "[STUB] Change detection not yet trained — no fine-tuned adapter. Query was: " + (query[:120] if query else ""),
        "evidence": [
            {
                "type": "overlay",
                "description": "[STUB] Change heatmap placeholder (T1 vs T2)",
                "image_index": 1,
            }
        ],
        "confidence": 0.0,
        "_latency_ms": 0,
        "_stub": True,
    }


def is_real() -> bool:
    return False


def load_error() -> str | None:
    return "Change detection specialist is stubbed — no trained adapter yet (stage 3 planned)"


def get_model_info() -> dict[str, Any]:
    return {"is_real": False, "load_error": load_error(), "stub": True}


def preload() -> bool:
    return False
