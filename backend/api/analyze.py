"""Unified analysis API — preserves existing /api/query, adds /api/analyze convenience endpoints."""

from __future__ import annotations

import time
import json
import hashlib
import uuid
from typing import Any

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from PIL import Image
import io

from backend.core.assets import SatelliteAsset
from backend.ingestion.image import ingest_uploaded_image, ingest_pil_image
from backend.ingestion.live import ingest_live_scene
from backend.agents.planner import plan_query
from backend.evidence.fusion import fuse_evidence, confidence_from_fusion
from backend.provenance.record import build_provenance, build_execution_graph
from backend.session.store import get_session, set_assets, append_history

router = APIRouter()

# In-memory run store for GET /analysis/{run_id}
_runs: dict[str, dict[str, Any]] = {}


def _pil_from_bytes(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGB")


def _ingest_uploads(files: list[UploadFile] | list[tuple[str, bytes]] | None) -> list[SatelliteAsset]:
    assets: list[SatelliteAsset] = []
    if not files:
        return assets
    for f in files:
        if isinstance(f, tuple):
            fname, data = f
            assets.append(ingest_uploaded_image(fname, data))
        else:
            # UploadFile
            data = f.file.read() if hasattr(f.file, "read") else b""
            # FastAPI UploadFile read is async; but in sync context we use file
            # Actually caller should have read bytes; fallback
            fname = getattr(f, "filename", "upload.png")
            # Try to read via sync if possible
            if not data:
                try:
                    import asyncio

                    data = asyncio.run(f.read()) if hasattr(f, "read") else b""
                except Exception:
                    data = b""
            assets.append(ingest_uploaded_image(fname, data))
    return assets


@router.post("/analyze", tags=["analyze"])
async def analyze(
    query: str = Form(..., description="NL query"),
    images: list[UploadFile] = File(default=None),
    session_id: str = Form(default=None),
    scene_json: str = Form(default=None),
    aoi_json: str = Form(default=None),
):
    """Unified analyze — supports uploaded images and/or live scene, returns answer+evidence+provenance+trace."""
    t0 = time.time()
    # Resolve session
    sess = get_session(session_id)
    sid = sess["session_id"]

    assets: list[SatelliteAsset] = []
    # Live scene path
    scene = None
    aoi = None
    if scene_json:
        try:
            scene = json.loads(scene_json)
            if aoi_json:
                aoi = json.loads(aoi_json)
            assets.append(ingest_live_scene(scene, aoi))
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Invalid scene/aoi JSON: {e}")
    # Upload path
    if images:
        for uf in images:
            data = await uf.read()
            if not data:
                raise HTTPException(status_code=422, detail=f"Empty file {uf.filename}")
            assets.append(ingest_uploaded_image(uf.filename, data))
    # Fallback to session assets if no new uploads/scene (conversational)
    if not assets:
        assets = sess.get("assets", [])
        if not assets:
            raise HTTPException(status_code=400, detail="No images or scene provided, and no session assets found")

    # Update session
    if assets:
        set_assets(sid, assets)

    # Planner
    plan = plan_query(query, assets)
    # Route via existing controller for actual model inference (preserve HF behavior)
    from backend.controller import handle as controller_handle

    # Convert assets to controller payload: list of (filename, bytes) or PIL
    # For live assets we pass scene/aoi through controller's scene path
    controller_scene = scene
    controller_aoi = aoi
    image_payloads: list[tuple[str, bytes]] = []
    has_live = any(a.source_type == "live" for a in assets)
    if not has_live:
        for a in assets:
            if isinstance(a.image, Image.Image):
                buf = io.BytesIO()
                a.image.save(buf, format="PNG")
                image_payloads.append((a.filename or "upload.png", buf.getvalue()))
            elif isinstance(a.image, (bytes, bytearray)):
                image_payloads.append((a.filename or "upload.png", bytes(a.image)))
            else:
                # fallback: re-encode PIL
                try:
                    buf = io.BytesIO()
                    a.image.save(buf, format="PNG")
                    image_payloads.append((a.filename or "upload.png", buf.getvalue()))
                except Exception:
                    pass

    # Determine input_mode from asset count
    input_mode = "single"
    if len(assets) >= 2 and plan.requires_pair:
        input_mode = "bi-temporal"

    try:
        # Use controller_handle directly (already handles scene vs upload)
        if has_live:
            resp = controller_handle(query=query, images=[], input_mode=input_mode, scene=controller_scene, aoi=controller_aoi)
        else:
            resp = controller_handle(query=query, images=image_payloads, input_mode=input_mode, scene=controller_scene, aoi=controller_aoi)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Controller error: {e}") from e

    # Evidence fusion
    evidence_lists = [[e.model_dump() if hasattr(e, "model_dump") else dict(e) for e in resp.evidence]] if resp.evidence else []
    fused = fuse_evidence(evidence_lists, specialist_results=[{"answer": resp.answer, "confidence": resp.confidence}])
    # Provenance
    prov = build_provenance(query=query, assets=assets, plan=plan, specialist_results=[{"specialist": resp.execution_trace.task, "answer": resp.answer, "confidence": resp.confidence, "evidence": evidence_lists[0] if evidence_lists else []}], fused=fused, answer=resp.answer, execution_trace=resp.execution_trace, duration_ms=int((time.time() - t0) * 1000))
    graph = build_execution_graph(prov)

    # Store run
    run_id = prov.run_id
    _runs[run_id] = {"provenance": prov.model_dump(), "response": resp.model_dump() if hasattr(resp, "model_dump") else {}, "plan": plan.model_dump(), "fused": fused, "graph": graph}

    # Append history
    append_history(sid, query, resp.answer)

    return {
        "run_id": run_id,
        "session_id": sid,
        "answer": resp.answer,
        "confidence": resp.confidence,
        "evidence": fused["fused_evidence"],
        "fusion": fused,
        "provenance": prov.model_dump(),
        "execution_trace": resp.execution_trace.model_dump() if hasattr(resp.execution_trace, "model_dump") else resp.execution_trace,
        "plan": plan.model_dump(),
        "graph": graph,
        "scene_context": getattr(resp, "scene_context", None),
        "analysis": getattr(resp, "analysis", None),
    }


@router.get("/analysis/{run_id}", tags=["analyze"])
def get_analysis(run_id: str):
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return _runs[run_id]


@router.get("/analysis/{run_id}/trace", tags=["analyze"])
def get_trace(run_id: str):
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return _runs[run_id].get("provenance", {}).get("trace") or _runs[run_id].get("response", {}).get("execution_trace")


@router.get("/analysis/{run_id}/provenance", tags=["analyze"])
def get_provenance(run_id: str):
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return _runs[run_id].get("provenance")
