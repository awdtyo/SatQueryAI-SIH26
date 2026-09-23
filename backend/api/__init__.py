"""FastAPI routes — thin handlers that delegate to the controller.

Route handlers must NOT import backend.models directly; they go via
backend.controller.handle() which in turn uses backend.registry.
"""

from __future__ import annotations

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
    # Location-based alternative to upload (place name or lat,lon)
    location_query: Annotated[Optional[str], Form(description="Place name, e.g. 'Bengaluru, India' or 'lat,lon'")] = None,
    coordinates: Annotated[Optional[str], Form(description="JSON or 'lat,lon' string, e.g. '12.97,77.59'")] = None,
    lat: Annotated[Optional[float], Form(description="Latitude alternative")] = None,
    lon: Annotated[Optional[float], Form(description="Longitude alternative")] = None,
    location_query_2: Annotated[Optional[str], Form(description="Second place for bi-temporal")] = None,
    coordinates_2: Annotated[Optional[str], Form(description="Second coordinates JSON or lat,lon")] = None,
    lat2: Annotated[Optional[float], Form()] = None,
    lon2: Annotated[Optional[float], Form()] = None,
):
    """Agentic query endpoint — validates, routes to specialist, returns trace.

    Accepts either:
      - `images` as repeated file field (frontend default)
      - `image_0`, `image_1` as explicit slots (alternative clients)
      - `location_query` / `coordinates` / `lat`+`lon` as alternative to upload
        (fetches real Sentinel-2 via Planetary Computer STAC)

    The location path resolves to images via geocode + imagery_fetch,
    then proceeds through the existing validate_inputs -> classify_task -> registry pipeline.
    """
    if not query_text or not query_text.strip():
        raise HTTPException(status_code=400, detail="query must be non-empty")

    # Collect UploadFiles from either style
    upload_files: list[UploadFile] = []
    if images:
        upload_files.extend(images)
    if image_0 is not None:
        upload_files.append(image_0)
    if image_1 is not None:
        upload_files.append(image_1)

    # Parse coordinates helpers (accept "lat,lon" string or JSON {"lat":..,"lon":..})
    def _parse_coords_str(s: str | None, flat_lat: float | None, flat_lon: float | None) -> dict | None:
        if flat_lat is not None and flat_lon is not None:
            return {"lat": float(flat_lat), "lon": float(flat_lon)}
        if not s:
            return None
        s = s.strip()
        # Try JSON
        if s.startswith("{"):
            try:
                import json

                j = json.loads(s)
                if isinstance(j, dict) and "lat" in j and "lon" in j:
                    return {"lat": float(j["lat"]), "lon": float(j["lon"])}
            except Exception:
                pass
        # Try lat,lon
        try:
            from backend.services.geocode import parse_coordinates

            parsed = parse_coordinates(s)
            if parsed:
                return parsed
        except Exception:
            pass
        # Fallback comma split
        if "," in s:
            parts = s.split(",")
            if len(parts) == 2:
                try:
                    return {"lat": float(parts[0].strip()), "lon": float(parts[1].strip())}
                except Exception:
                    pass
        return None

    coords = _parse_coords_str(coordinates, lat, lon)
    coords2 = _parse_coords_str(coordinates_2, lat2, lon2)

    has_images = bool(upload_files)
    has_location = bool((location_query and location_query.strip()) or coords or (location_query_2 and location_query_2.strip()) or coords2)

    if not has_images and not has_location:
        raise HTTPException(
            status_code=400,
            detail="Provide either images (field 'images' or 'image_0') or a location (location_query or coordinates/lat+lon).",
        )

    # Read UploadFiles asynchronously into (filename, bytes) tuples for the controller.
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
    # If location path, controller will resolve to images before validate_inputs
    try:
        response = controller_handle(
            query=query_text,
            images=image_payloads,
            input_mode=input_mode,
            location_query=location_query,
            coordinates=coords,
            location_query_2=location_query_2,
            coordinates_2=coords2,
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
