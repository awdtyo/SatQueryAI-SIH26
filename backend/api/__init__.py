"""FastAPI routes — thin handlers that delegate to the controller.

Route handlers must NOT import backend.models directly; they go via
backend.controller.handle() which in turn uses backend.registry.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend import config, registry
from backend.controller import handle as controller_handle
from backend.schemas import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> dict:
    # Auto GPU — report effective compute (cuda whenever available unless FORCE_CPU)
    from backend.models import vqa_specialist

    vqa_info = vqa_specialist.get_model_info() if hasattr(vqa_specialist, "get_model_info") else {}
    try:
        import torch  # type: ignore

        cuda_raw = bool(torch.cuda.is_available())
        cuda_effective = cuda_raw and not bool(getattr(config, "FORCE_CPU", False))
    except Exception:
        cuda_raw = False
        cuda_effective = False
    return {
        "status": "ok",
        "specialists": registry.health(),
        "base_model": config.BASE_MODEL,
        "adapter_path": config.ADAPTER_PATH,
        "cuda_available": cuda_raw,
        "cuda_effective": cuda_effective,
        "force_cpu": bool(getattr(config, "FORCE_CPU", False)),
        "compute": vqa_info.get("compute", "cpu-only" if getattr(config, "FORCE_CPU", False) else ("cuda" if cuda_effective else "cpu")),
        "device": vqa_info.get("device", "cuda" if cuda_effective else "cpu"),
        "gpu_name": vqa_info.get("gpu_name"),
        "gpu_count": vqa_info.get("gpu_count", 0),
    }


def _has_torch() -> bool:
    try:
        import torch  # type: ignore

        return True
    except Exception:
        return False


@router.post("/query", tags=["query"])
async def query(
    query_text: Annotated[str, Form(..., alias="query", description="Natural language question")],
    input_mode: Annotated[str, Form(..., description="single | optical-sar | bi-temporal")] = "single",
    images: Annotated[Optional[List[UploadFile]], File(description="One or two images (GeoTIFF/TIFF/PNG/JPEG)")] = None,
    # Allow alternative form field names for compatibility
    image_0: UploadFile | None = None,
    image_1: UploadFile | None = None,
    # Selected Satellite Image Query Mode: the active scene instead of uploaded images
    scene_json: Annotated[str, Form(description="Active Sentinel-2 scene as JSON (SatelliteScene)")] = None,
    aoi_json: Annotated[str, Form(description="Optional AOI GeoJSON polygon to clip analysis to")] = None,
):
    """Agentic query endpoint — validates, routes to specialist, returns trace.

    Accepts both:
      - `images` as repeated file field (frontend default)
      - `image_0`, `image_1` as explicit slots (alternative clients)
      - `scene_json` + optional `aoi_json`: analyze a SELECTED satellite scene's
        real assets instead of uploaded demo images (Selected Satellite Image
        Query Mode). No image files required in this mode.
    """
    logger.info("[USER QUERY] %r", query_text)
    if not query_text or not query_text.strip():
        raise HTTPException(status_code=400, detail="query must be non-empty")

    # Parse optional active-scene context
    scene: dict | None = None
    if scene_json:
        try:
            scene = json.loads(scene_json)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"scene_json is not valid JSON: {e}") from e
        if not isinstance(scene, dict):
            raise HTTPException(status_code=422, detail="scene_json must be a JSON object (SatelliteScene)")
    aoi: dict | None = None
    if aoi_json:
        try:
            aoi = json.loads(aoi_json)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"aoi_json is not valid JSON: {e}") from e
        if not isinstance(aoi, dict):
            raise HTTPException(status_code=422, detail="aoi_json must be a JSON object (GeoJSON)")

    # Collect UploadFiles from either style
    upload_files: list[UploadFile] = []
    if images:
        upload_files.extend(images)
    if image_0 is not None:
        upload_files.append(image_0)
    if image_1 is not None:
        upload_files.append(image_1)

    if not upload_files and not scene:
        raise HTTPException(status_code=400, detail="At least one image file is required (field 'images' or 'image_0'), or a selected scene via 'scene_json'")

    # Read UploadFiles asynchronously into (filename, bytes) tuples for the controller.
    # Controller is sync and handles (filename, bytes) or PIL — keep I/O at the edge.
    image_payloads: list[tuple[str | None, bytes]] = []
    for f in upload_files:
        try:
            data = await f.read()
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Failed to read image {f.filename}: {e}") from e
        if not data:
            raise HTTPException(status_code=422, detail=f"Image {f.filename} is empty")
        image_payloads.append((f.filename, data))

    # Delegate to controller — it validates modality and builds ExecutionTrace
    try:
        response = controller_handle(
            query=query_text,
            images=image_payloads,
            input_mode=input_mode,
            scene=scene,
            aoi=aoi,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected controller error: %s", e)
        raise HTTPException(status_code=500, detail=f"Controller error: {e}") from e

    # FastAPI will serialize the Pydantic model
    return response


@router.get("/", tags=["health"])
def root() -> dict:
    return {"message": "SatQuery AI backend — see /docs and /health"}
