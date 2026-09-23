"""VQA specialist wrapper — delegates to existing backend.models.vqa without duplicating load."""

from __future__ import annotations

from typing import Any

from backend.agents.specialists.base import SpecialistBase, SpecialistResult
from backend.core.assets import SatelliteAsset


class VQASpecialist(SpecialistBase):
    name = "vqa"
    capabilities = ["vqa", "captioning", "visual_question_answering", "grounding_fallback"]
    supported_inputs = ["single", "live"]

    def can_handle(self, query: str, assets: list[SatelliteAsset]) -> bool:
        return True  # fallback

    def run(self, assets: list[SatelliteAsset], query: str, task: str | None = None, **kwargs) -> SpecialistResult:
        from backend import registry
        from PIL import Image

        # Convert assets to PIL list for registry.predict (which expects PIL/bytes)
        pil_images = []
        for a in assets:
            if isinstance(a.image, Image.Image):
                pil_images.append(a.image)
            elif isinstance(a.image, (bytes, bytearray)):
                from PIL import Image as PILI
                import io

                try:
                    pil_images.append(PILI.open(io.BytesIO(a.image)).convert("RGB"))
                except Exception:
                    continue
        # If no pil but asset has filename, try to use as path etc; for live scenes we may have no image bytes — use fallback
        if not pil_images and assets:
            # Try to use image field directly (could be PIL already handled) or create dummy
            pass
        try:
            # Use registry which will call backend.models.vqa_specialist.predict
            # For empty live assets without image, we still try; registry will error gracefully
            if pil_images:
                res = registry.predict(pil_images, query, task or "vqa")
            else:
                # Attempt with empty — will trigger specialist error handling, return structured error
                res = {"answer": "No image available for VQA", "evidence": [], "confidence": 0.0, "status": "error"}
            answer = str(res.get("answer", ""))
            evidence = res.get("evidence", [])
            conf = res.get("confidence")
            return SpecialistResult(
                specialist=self.name,
                status="success",
                answer=answer,
                evidence=evidence if isinstance(evidence, list) else [],
                confidence=conf if isinstance(conf, (int, float)) else None,
                metrics={"latency_ms": res.get("_latency_ms", 0)},
                artifacts=res.get("_structured", {}).get("chart", []) if isinstance(res.get("_structured"), dict) else [],
            )
        except Exception as e:
            return SpecialistResult(specialist=self.name, status="error", answer=f"VQA failed: {e}", evidence=[], confidence=None, limitations=[str(e)])
