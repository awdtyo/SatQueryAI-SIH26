"""Provenance record — captures full execution graph."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from backend.core.assets import SatelliteAsset
from backend.agents.planner import Plan


class ProvenanceRecord(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    query: str
    input_type: str | None = None
    assets: list[dict[str, Any]] = Field(default_factory=list)
    plan: dict[str, Any] | None = None
    specialists_executed: list[str] = Field(default_factory=list)
    model_names: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    answer: str | None = None
    limitations: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    trace: dict[str, Any] | None = None
    duration_ms: int | None = None


def build_provenance(
    query: str,
    assets: list[SatelliteAsset],
    plan: Plan | dict[str, Any] | None,
    specialist_results: list[dict[str, Any]],
    fused: dict[str, Any] | None,
    answer: str | None,
    execution_trace: dict[str, Any] | Any | None = None,
    duration_ms: int | None = None,
) -> ProvenanceRecord:
    asset_dicts = [a.to_provenance_dict() for a in assets]
    plan_dict = plan.model_dump() if hasattr(plan, "model_dump") else (plan if isinstance(plan, dict) else None)
    # Extract specialists
    specs = []
    models = []
    evidence = []
    limitations = []
    errors = []
    for r in specialist_results or []:
        specs.append(r.get("specialist") or r.get("name") or "unknown")
        if r.get("model") or r.get("adapter"):
            models.append(str(r.get("model") or r.get("adapter")))
        if r.get("evidence"):
            evidence.extend(r.get("evidence", []))
        if r.get("limitations"):
            limitations.extend(r.get("limitations", []))
        if r.get("status") == "error" and r.get("answer"):
            errors.append(str(r.get("answer"))[:500])
    if fused:
        evidence = fused.get("fused_evidence", evidence)
    trace_dict = None
    if execution_trace:
        if hasattr(execution_trace, "model_dump"):
            trace_dict = execution_trace.model_dump()
        elif isinstance(execution_trace, dict):
            trace_dict = execution_trace
        else:
            try:
                trace_dict = dict(execution_trace)
            except Exception:
                trace_dict = {"trace": str(execution_trace)}

    input_type = "live" if any(a.source_type == "live" for a in assets) else ("upload" if assets else None)

    return ProvenanceRecord(
        query=query,
        input_type=input_type,
        assets=asset_dicts,
        plan=plan_dict,
        specialists_executed=specs,
        model_names=models,
        parameters={"query": query, "asset_count": len(assets)},
        evidence=evidence,
        answer=answer,
        limitations=limitations,
        errors=errors,
        trace=trace_dict,
        duration_ms=duration_ms,
    )


def build_execution_graph(provenance: ProvenanceRecord) -> list[dict[str, Any]]:
    """Return ordered execution graph for visualization: INPUT -> INGESTION -> PLANNER -> SPECIALISTS -> EVIDENCE -> FUSION -> ANSWER."""
    graph = [
        {"step": "INPUT", "status": "success", "assets": len(provenance.assets), "query": provenance.query[:80]},
        {"step": "INGESTION", "status": "success", "assets": provenance.assets},
        {"step": "PLANNER", "status": "success", "plan": provenance.plan.get("intent") if provenance.plan else None},
    ]
    for spec in provenance.specialists_executed:
        graph.append({"step": spec.upper(), "status": "success"})
    graph.append({"step": "EVIDENCE", "status": "success", "count": len(provenance.evidence)})
    graph.append({"step": "FUSION", "status": "success", "agreement": provenance.trace.get("agreement") if provenance.trace else None})
    graph.append({"step": "ANSWER", "status": "success" if not provenance.errors else "partial", "answer": (provenance.answer or "")[:120]})
    return graph
