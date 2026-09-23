"""Counting specialist wrapper."""

from __future__ import annotations

from backend.agents.specialists.base import SpecialistBase, SpecialistResult
from backend.core.assets import SatelliteAsset


class CountingSpecialist(SpecialistBase):
    name = "counting"
    capabilities = ["counting", "count", "detection", "yolo"]
    supported_inputs = ["single"]

    def can_handle(self, query: str, assets: list[SatelliteAsset]) -> bool:
        return any(k in query.lower() for k in ["how many", "count", "number of"])

    def run(self, assets: list[SatelliteAsset], query: str, task: str | None = None, **kwargs) -> SpecialistResult:
        from backend import registry
        from PIL import Image
        import io

        pils = []
        for a in assets[:1]:
            if isinstance(a.image, Image.Image):
                pils.append(a.image)
            elif isinstance(a.image, (bytes, bytearray)):
                try:
                    pils.append(Image.open(io.BytesIO(a.image)).convert("RGB"))
                except Exception:
                    continue
        if not pils and assets and isinstance(assets[0].image, Image.Image):
            pils = [assets[0].image]
        try:
            res = registry.predict(pils if pils else [assets[0].image] if assets and isinstance(assets[0].image, Image.Image) else [], query, "count")
            return SpecialistResult(specialist=self.name, status="success", answer=str(res.get("answer", "")), evidence=res.get("evidence", []), confidence=res.get("confidence"), metrics={"latency_ms": res.get("_latency_ms", 0)}, artifacts=res.get("_detections", []))
        except Exception as e:
            return SpecialistResult(specialist=self.name, status="error", answer=f"Counting failed: {e}", limitations=[str(e)])
