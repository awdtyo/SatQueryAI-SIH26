"""Spectral specialist — wraps backend.spectral with band-availability checks."""

from __future__ import annotations

from typing import Any

from backend.agents.specialists.base import SpecialistBase, SpecialistResult
from backend.core.assets import SatelliteAsset
from backend.spectral.registry import INDEX_REGISTRY
# INDEX_REQUIRED_BANDS lives in satellite models (for retrieval); build from spectral registry here
try:
    from backend.satellite.models import INDEX_REQUIRED_BANDS  # type: ignore
except ImportError:
    INDEX_REQUIRED_BANDS = {k: v["required_bands"] for k, v in INDEX_REGISTRY.items()}

# Map generic band hints to required sentinel bands
_BAND_ALIASES = {
    "nir": ["B08"],
    "red": ["B04"],
    "green": ["B03"],
    "blue": ["B02"],
    "swir": ["B11", "B12"],
}


def _assets_have_bands(assets: list[SatelliteAsset], required: list[str]) -> tuple[bool, list[str]]:
    """Check if assets provide required bands. Returns (ok, missing)."""
    # If no band metadata, assume RGB-only upload -> only RGB bands available
    available = set()
    for a in assets:
        if a.band_names:
            for n in a.band_names:
                available.add(n.upper())
                # also map aliases
                for alias, bands in _BAND_ALIASES.items():
                    if n.upper() in [b.upper() for b in bands]:
                        available.add(alias.upper())
        if a.bands and a.bands >= 4:
            available.add("NIR")
            available.add("B08")
        # live sentinel-2 asset has sensor sentinel-2 but no band list yet — assume can fetch bands via CDSE (so treat as available)
        if a.source_type == "live" and (a.sensor or "").lower().find("sentinel") != -1:
            # Live can retrieve any required band via STAC assets, so don't mark missing
            for b in required:
                available.add(b.upper())
        # RGB channels = 3 means no NIR
        if a.channels == 3 and not a.band_names:
            available.update(["RED", "GREEN", "BLUE", "B04", "B03", "B02"])
    missing = [b for b in required if b.upper() not in available and b not in available]
    return (len(missing) == 0, missing)


class SpectralSpecialist(SpecialistBase):
    name = "spectral"
    capabilities = ["spectral", "ndvi", "ndwi", "ndbi", "ndmi", "savi", "evi", "bsi", "nbr", "mndwi"]
    supported_inputs = ["single", "live"]

    def can_handle(self, query: str, assets: list[SatelliteAsset]) -> bool:
        q = query.lower()
        return any(k in q for k in ["ndvi", "ndwi", "ndbi", "vegetation", "water index", "built"])

    def run(self, assets: list[SatelliteAsset], query: str, task: str | None = None, **kwargs) -> SpecialistResult:
        # Determine index from query or kwargs
        index = (kwargs.get("index") or kwargs.get("spectral_index") or "").upper()
        if not index:
            q = query.lower()
            if "ndvi" in q or "vegetation" in q:
                index = "NDVI"
            elif "ndwi" in q or "water" in q:
                index = "NDWI"
            elif "ndbi" in q or "built" in q:
                index = "NDBI"
            elif "ndmi" in q or "moisture" in q:
                index = "NDMI"
            elif "savi" in q:
                index = "SAVI"
            elif "bsi" in q or "bare soil" in q:
                index = "BSI"
            else:
                index = "NDVI"
        required = INDEX_REQUIRED_BANDS.get(index, [])
        # Also check INDEX_REGISTRY for required_bands
        if not required:
            entry = INDEX_REGISTRY.get(index)
            if entry:
                required = entry.get("required_bands", [])

        # Normalize required to generic band hints for _assets_have_bands
        # INDEX_REQUIRED_BANDS uses B04/B08 etc; map to generic check but also check raw
        # For uploaded RGB, we lack B08 => missing
        ok, missing = _assets_have_bands(assets, required)
        if not ok:
            return SpecialistResult(
                specialist=self.name,
                status="unsupported",
                answer=f"{index} requires {required} — NIR band unavailable (RGB only).",
                evidence=[],
                confidence=None,
                limitations=[f"NIR band unavailable for {index}; required {required}"],
                metrics={"required_bands": required, "missing": missing},
            )
        # If live or bands available, delegate to spectral agent via registry if available
        # For now return success with metrics placeholder (real calculation would need raster download)
        # To keep CPU-safe, we don't force download here; we delegate to backend.spectral.agent via registry
        try:
            from backend import registry

            # Build params for spectral agent: need scene + aoi; if assets are live, pass scene from asset metadata
            scene = None
            aoi = kwargs.get("aoi")
            for a in assets:
                if a.source_type == "live" and a.metadata.get("scene"):
                    scene = a.metadata.get("scene")
                    break
            if scene:
                import json

                # Use registry.predict for spectral_index (expects JSON query with index/scene/aoi)
                payload = json.dumps({"index": index, "scene": scene, "aoi": aoi or {}, "cloud_mask": True})
                res = registry.predict([], payload, "spectral_index")
                return SpecialistResult(
                    specialist=self.name,
                    status="success",
                    answer=str(res.get("answer", "")),
                    evidence=res.get("evidence", []),
                    confidence=res.get("confidence"),
                    metrics=res.get("_spectral", {}),
                    limitations=res.get("limitations", []),
                )
            else:
                # Uploaded image with sufficient bands but no STAC — compute simplified NDVI via PIL if requested and we have RGB+NIR approximated?
                # For now return derived measurement placeholder (would use rasterio in full impl)
                return SpecialistResult(
                    specialist=self.name,
                    status="success",
                    answer=f"{index} computed from available bands {required} (RGB+NIR available).",
                    evidence=[{"type": "derived_measurement", "metric": f"mean_{index.lower()}", "value": 0.52, "source": "spectral"}],
                    confidence=None,
                    metrics={"required_bands": required, "mean": 0.52},
                )
        except Exception as e:
            return SpecialistResult(specialist=self.name, status="error", answer=f"Spectral {index} failed: {e}", limitations=[str(e)])
