"""Deterministic agentic planner — rule-based, no LLM required, extensible to LLM later."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

from backend.core.assets import SatelliteAsset


class PlanStep(BaseModel):
    task_id: str
    specialist: str
    action: str
    inputs: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    query: str
    intent: str
    requires_pair: bool = False
    requires_bands: list[str] | None = None
    requires_live: bool = False
    evidence_required: bool = True
    steps: list[PlanStep] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


def _has_band(assets: list[SatelliteAsset], band_hint: str) -> bool:
    """Check if any asset has band info indicating band availability."""
    band_hint = band_hint.lower()
    for a in assets:
        if a.band_names and any(band_hint in b.lower() for b in a.band_names):
            return True
        # RGB upload has no band_names but we can infer: RGB = B04,B03,B02 approx but not NIR
        # For NIR/SWIR we check metadata or band count >3 and sensor sentinel-2
        if band_hint in ("nir", "b08") and a.bands and a.bands >= 4 and (a.sensor or "").lower().find("sentinel") != -1:
            return True
        if band_hint == "nir" and a.channels and a.channels >= 4:
            return True
    return False


def _infer_assets_have_nir(assets: list[SatelliteAsset]) -> bool:
    for a in assets:
        if a.bands and a.bands >= 4:
            return True
        if a.band_names and any("nir" in n.lower() or "b08" in n.lower() for n in a.band_names):
            return True
    return False


def plan_query(query: str, assets: list[SatelliteAsset] | None = None, context: dict[str, Any] | None = None) -> Plan:
    """Deterministic planner.

    Inputs:
      query: user NL
      assets: current SatelliteAsset(s)
      context: session/context with available specialists etc

    Determines intent, required specialists, pair/band/live needs, and ordered steps.
    """
    q = (query or "").lower()
    assets = assets or []
    num_images = len(assets)

    # --- intent detection (rule-based) ---
    intent = "vqa"
    requires_pair = False
    requires_bands: list[str] | None = None
    requires_live = False
    limitations: list[str] = []

    # Spectral intents
    spectral_map = {
        "ndvi": ["nir", "red"],
        "ndwi": ["green", "nir"],
        "mndwi": ["green", "swir"],
        "ndbi": ["swir", "nir"],
        "nbr": ["nir", "swir"],
        "ndmi": ["nir", "swir"],
        "savi": ["nir", "red"],
        "evi": ["nir", "red", "blue"],
    }
    # Check for explicit spectral keywords
    spectral_intent = None
    for idx, bands in spectral_map.items():
        if idx in q:
            spectral_intent = idx
            requires_bands = bands
            intent = f"spectral_{idx}"
            break
    if not spectral_intent:
        if any(k in q for k in ["vegetation", "ndvi", "how much vegetation", "vegetation present"]):
            # generic vegetation -> ndvi
            spectral_intent = "ndvi"
            requires_bands = ["nir", "red"]
            # only set intent spectral if query is quantitative about vegetation
            if any(w in q for w in ["how much", "percent", "amount", "calculate", "ndvi", "index"]):
                intent = "spectral_ndvi"
        elif "water" in q and any(w in q for w in ["index", "ndwi", "mndwi"]):
            spectral_intent = "ndwi"
            requires_bands = ["green", "nir"]
            intent = "spectral_ndwi"

    # Change detection
    if any(k in q for k in ["what changed", "change between", "difference between", "before and after", "temporal"]):
        intent = "change_detection"
        requires_pair = True

    # Counting
    if any(k in q for k in ["how many", "count", "number of"]):
        if intent.startswith("spectral"):
            # keep spectral, counting spectral+count may need fusion later
            pass
        elif "change" not in intent:
            intent = "counting"

    # Live retrieval
    if any(k in q for k in ["find sentinel", "sentinel-2", "live satellite", "retrieve", "search scene"]):
        intent = "live_retrieval"
        requires_live = True

    # Urbanization + vegetation compound
    if "urban" in q and "vegetation" in q:
        intent = "compound_urban_vegetation"
        requires_bands = ["nir", "red", "swir"]

    # Pair detection heuristic: if query says two images / between / pair
    if any(k in q for k in ["between these two", "two images", "pair", "before after"]):
        requires_pair = True

    # Validate pair availability
    if requires_pair and num_images < 2:
        limitations.append("Change detection requires 2 images; only 1 available — will request pair.")

    # Validate bands
    if requires_bands:
        has_nir = _infer_assets_have_nir(assets)
        if not has_nir:
            # For RGB uploads, NIR unavailable
            if spectral_intent and not has_nir:
                limitations.append(f"{spectral_intent.upper()} requires {requires_bands} — NIR band unavailable (RGB only). Fallback to VQA.")
                # planner will keep spectral step but mark unsupported; caller should fallback
                pass

    # Build plan steps deterministic
    steps: list[PlanStep] = []
    step_id = 0

    def add_step(specialist: str, action: str, deps: list[str] | None = None, params: dict[str, Any] | None = None):
        nonlocal step_id
        step_id += 1
        tid = f"task_{step_id:02d}_{specialist}"
        steps.append(PlanStep(task_id=tid, specialist=specialist, action=action, dependencies=deps or [], parameters=params or {}))

    # Live retrieval first if needed
    if requires_live:
        add_step("satellite_retrieval", "search_satellite_data", params={"query": query})

    # Ingestion already assumed; next steps per intent
    if intent == "change_detection" or requires_pair:
        add_step("ingestion", "validate_pair", params={"count": num_images})
        add_step("change_detection", "detect_change", deps=[steps[0].task_id] if steps else [], params={"pair": True})
        add_step("vqa", "verify_semantic", deps=[steps[-1].task_id], params={"query": query})
        add_step("evidence_extraction", "extract_evidence", deps=[steps[-2].task_id, steps[-1].task_id])
        add_step("evidence_fusion", "fuse", deps=[steps[-1].task_id])
    elif intent.startswith("spectral"):
        idx = spectral_intent or "ndvi"
        add_step("spectral", f"compute_{idx}", params={"index": idx.upper(), "required_bands": requires_bands})
        # fallback VQA if bands missing
        if limitations:
            add_step("vqa", "describe_fallback", params={"reason": limitations[0]})
        add_step("evidence_extraction", "extract_evidence", deps=[steps[-1].task_id])
        add_step("evidence_fusion", "fuse", deps=[steps[-1].task_id])
    elif intent == "counting":
        add_step("counting", "count_objects", params={"query": query})
        add_step("evidence_extraction", "extract_evidence", deps=[steps[-1].task_id])
        add_step("evidence_fusion", "fuse", deps=[steps[-1].task_id])
    elif intent == "compound_urban_vegetation":
        add_step("spectral", "compute_ndvi", params={"index": "NDVI", "required_bands": ["nir", "red"]})
        add_step("spectral", "compute_ndbi", params={"index": "NDBI", "required_bands": ["swir", "nir"]}, deps=[steps[-1].task_id] if steps else [])
        add_step("change_detection", "detect_change", deps=[steps[-1].task_id] if steps else [], params={"pair": requires_pair})
        add_step("evidence_fusion", "fuse", deps=[s.task_id for s in steps])
    elif intent == "live_retrieval":
        # already added retrieval; next just validate
        add_step("evidence_extraction", "extract_evidence", deps=[steps[-1].task_id] if steps else [])
    else:
        # Default VQA
        add_step("vqa", "answer_query", params={"query": query})
        add_step("evidence_extraction", "extract_evidence", deps=[steps[-1].task_id])
        add_step("evidence_fusion", "fuse", deps=[steps[-1].task_id])

    # Always end with provenance
    add_step("provenance", "record_provenance", deps=[s.task_id for s in steps])

    evidence_required = True
    if any("unsupported" in l.lower() for l in limitations):
        evidence_required = True

    return Plan(
        query=query,
        intent=intent,
        requires_pair=requires_pair,
        requires_bands=requires_bands,
        requires_live=requires_live,
        evidence_required=evidence_required,
        steps=steps,
        limitations=limitations,
    )


# Backward compat for tests: alias
def classify_and_plan(query: str, assets: list[SatelliteAsset] | None = None) -> Plan:
    return plan_query(query, assets)
