"""
Optical-SAR fusion specialist — STUB (no trained adapter yet).

Handles optical+SAR paired inputs. Will be replaced when a fusion
adapter is trained. Keeps registry stable.

Interface: predict(images, query, task) -> {answer, evidence, confidence}
Expects images as (optical, SAR) pair.
"""

from typing import Any


def predict(images: Any, query: str, task: str = "optical_sar_fusion") -> dict[str, Any]:
    return {
        "answer": "[STUB] Optical-SAR fusion not yet trained — no fine-tuned adapter. Query was: " + (query[:120] if query else ""),
        "evidence": [
            {
                "type": "overlay",
                "description": "[STUB] SAR-optical fusion overlay placeholder",
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
    return "Optical-SAR fusion specialist is stubbed — no trained adapter yet"


def get_model_info() -> dict[str, Any]:
    return {"is_real": False, "load_error": load_error(), "stub": True}


def preload() -> bool:
    return False
