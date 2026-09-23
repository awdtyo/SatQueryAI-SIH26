"""Change detection specialist wrapper."""

from __future__ import annotations

from backend.agents.specialists.base import SpecialistBase, SpecialistResult
from backend.core.assets import SatelliteAsset


class ChangeSpecialist(SpecialistBase):
    name = "change_detection"
    capabilities = ["change_detection", "change", "cdvqa"]
    supported_inputs = ["pair"]

    def can_handle(self, query: str, assets: list[SatelliteAsset]) -> bool:
        return len(assets) >= 2

    def run(self, assets: list[SatelliteAsset], query: str, task: str | None = None, **kwargs) -> SpecialistResult:
        if len(assets) < 2:
            return SpecialistResult(specialist=self.name, status="error", answer="Change detection requires 2 images.", limitations=["Requires image pair"])
        from backend import registry
        from PIL import Image
        import io

        pils = []
        for a in assets[:2]:
            if isinstance(a.image, Image.Image):
                pils.append(a.image)
            elif isinstance(a.image, (bytes, bytearray)):
                try:
                    pils.append(Image.open(io.BytesIO(a.image)).convert("RGB"))
                except Exception:
                    continue
        if len(pils) < 2:
            return SpecialistResult(specialist=self.name, status="error", answer="Could not load image pair for change detection.")
        try:
            res = registry.predict(pils, query, "change_detection")
            return SpecialistResult(specialist=self.name, status="success", answer=str(res.get("answer", "")), evidence=res.get("evidence", []), confidence=res.get("confidence"), metrics={"latency_ms": res.get("_latency_ms", 0)})
        except Exception as e:
            return SpecialistResult(specialist=self.name, status="error", answer=f"Change detection failed: {e}", limitations=[str(e)])
