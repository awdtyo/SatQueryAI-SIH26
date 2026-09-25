"""Modal FastAPI layer — thin JSON API in front of the EXISTING SatQuery controller.

This module contains no SatQuery logic of its own. Every request delegates to
`backend.controller.handle()` — the same entrypoint `app.py` (HF Gradio) and
`backend/api` (FastAPI) already use — so validation, task classification,
registry routing, specialists, coverage percentages, the coarse 3x3 spatial
heuristic and the ExecutionTrace are all reused, never re-implemented.

Endpoints:
    GET  /health  — lightweight, NEVER triggers a model download/load
    POST /query   — JSON body -> controller.handle() -> QueryResponse payload

The app is constructed in-process inside a warm Modal GPU container
(modal_app/app.py), where `backend/` is importable (see modal_app/image.py).

Deliberately kept free of `backend.controller` / torch imports at module scope
so importing this file on the laptop (deploy-time) never touches a model.
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
import sys
import time
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend import config as app_config  # env-only module (imports `os` only)

logger = logging.getLogger("satquery.modal")

# --- Model readiness state, recorded by @modal.enter in modal_app/app.py ---
# Read through sys.modules only: never import a specialist from /health, so
# health can never trigger a cold model download (same rule as backend/main.py).
_MODEL_MODULE = "backend.models.vqa"


# ---------------------------------------------------------------------------
# Request schema — compatible with the existing SatQuery query flow
# (frontend QueryRequest / app.py predict(): query, input_mode, images,
#  location_query, location_query_2; images arrive base64 instead of multipart)
# ---------------------------------------------------------------------------


class CoordinatesModel(BaseModel):
    lat: float = Field(ge=-90, le=90, description="Latitude")
    lon: float = Field(ge=-180, le=180, description="Longitude")


class QueryBody(BaseModel):
    query: str = Field(description="Natural language question")
    input_mode: str = Field(default="single", description="single | optical-sar | bi-temporal")
    image_a: str | None = Field(
        default=None, description="base64 or data URL of image 1 (optical / T1 / single)"
    )
    image_b: str | None = Field(
        default=None, description="base64 or data URL of image 2 (SAR / T2)"
    )
    image_a_filename: str | None = Field(
        default=None, description="optional filename/extension hint for image_a (.tif/.tiff/.png/.jpg)"
    )
    image_b_filename: str | None = Field(default=None, description="filename hint for image_b")
    location_query: str | None = Field(
        default=None, description="Place name or 'lat,lon' — alternative to image_a"
    )
    location_query_2: str | None = Field(
        default=None, description="Second place for bi-temporal (empty = 2 dates at T1)"
    )
    coordinates: CoordinatesModel | None = None
    coordinates_2: CoordinatesModel | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MIME_TO_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/tiff": ".tiff",
    "image/tif": ".tif",
    "image/geotiff": ".tif",
    "application/geotiff": ".tif",
}


def _error(status: int, message: str, code: str | None = None) -> JSONResponse:
    """Structured error envelope — mirrors backend/main.py (frontend reads `detail`)."""
    return JSONResponse(
        status_code=status,
        content={
            "status": "error",
            "error": {"code": code or f"HTTP_{status}", "message": message},
            "detail": message,
        },
    )


def _decode_image(payload: str | None, filename: str | None, slot: str) -> tuple[str, bytes] | None:
    """base64 / data URL -> (filename, bytes) for controller.validate_inputs.

    Raises ValueError with a user-readable message on malformed input.
    """
    if payload is None or not str(payload).strip():
        return None

    raw = str(payload).strip()
    name = filename
    if raw.startswith("data:") and "," in raw:
        header, raw = raw.split(",", 1)
        mime = header[5:].split(";")[0].lower() if header.startswith("data:") else ""
        if not name:
            name = "image" + _MIME_TO_EXT.get(mime, ".png")
        raw = raw.strip()

    # Tolerate whitespace/newlines and urlsafe-alphabet base64
    compact = "".join(raw.split()).replace("-", "+").replace("_", "/").rstrip("=")
    compact += "=" * (-len(compact) % 4)
    try:
        data = base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ValueError(f"{slot} is not valid base64 image data: {e}") from e
    if not data:
        raise ValueError(f"{slot} decoded to zero bytes")

    if not name:
        name = f"{slot}.png"
    if not os.path.splitext(name)[1]:
        # validate_inputs keys off the extension — default to PNG if unknown
        name = f"{name}.png"
    return name, data


def _model_state() -> dict[str, Any]:
    """VQA load state WITHOUT importing the module (import = torch import)."""
    mod = sys.modules.get(_MODEL_MODULE)
    if mod is None:
        return {"attempted": False, "ready": False, "load_error": None}
    return {
        "attempted": bool(getattr(mod, "_load_attempted", False)),
        "ready": bool(getattr(mod, "_is_real", False)),
        "load_error": getattr(mod, "_load_error", None),
    }


def _cheap_specialist_flag(module_name: str, loaded_module_name: str | None = None) -> str:
    """'ready' / 'error' / 'deferred' — reports cached flags only, never loads."""
    mod = sys.modules.get(loaded_module_name or module_name)
    if mod is None:
        return "deferred"
    return "ready" if getattr(mod, "_is_real", False) else "error"


def _gpu_info() -> dict[str, Any]:
    """CUDA status from an ALREADY-imported torch — never forces a torch import."""
    torch = sys.modules.get("torch")
    if torch is None:
        return {
            "cuda_available": False,
            "gpu_name": None,
            "compute": "deferred",
            "device": "cpu",
        }
    try:
        available = bool(torch.cuda.is_available())
        name = torch.cuda.get_device_name(0) if available else None
    except Exception:
        available, name = False, None
    forced_cpu = bool(getattr(app_config, "FORCE_CPU", False))
    effective = available and not forced_cpu
    return {
        "cuda_available": available,
        "gpu_name": name,
        "compute": "cuda" if effective else ("cpu-only" if forced_cpu else "cpu"),
        "device": "cuda" if effective else "cpu",
    }


def _serialize_response(resp: Any, wall_ms: int) -> dict[str, Any]:
    """QueryResponse -> JSON dict, preserving every field.

    Also hoists the VQA grounding fields to the top level (they are already
    present, untouched, inside `execution_trace.parameters`):
        coverage_percentages, spatial_grid, spatial_method
    """
    try:
        payload = resp.model_dump()  # pydantic v2
    except Exception:
        payload = resp.dict()  # pydantic v1 fallback
    trace = payload.get("execution_trace") or {}
    params = trace.get("parameters") or {}
    payload["coverage_percentages"] = params.get("coverage_percentages")
    payload["spatial_grid"] = params.get("spatial_grid")
    payload["spatial_method"] = params.get("spatial_method")
    payload["latency_ms"] = wall_ms
    return payload


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

web_app = FastAPI(
    title="SatQuery AI — Modal backend",
    description=(
        "JSON API over backend/controller.handle() — same pipeline as the HF "
        "Gradio app.py and the FastAPI backend, deployed on Modal GPU. "
        "Model is loaded once per warm container (@modal.enter), never per request."
    ),
    version="0.1.0",
)

_origins = getattr(app_config, "CORS_ORIGINS", ["*"])
web_app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=(list(_origins) != ["*"]),
    allow_methods=["*"],
    allow_headers=["*"],
)


@web_app.get("/", tags=["health"])
def root() -> dict[str, Any]:
    return {
        "message": "SatQuery AI — Modal backend (see /health, /docs, POST /query)",
        "deployment": "modal",
    }


@web_app.get("/health", tags=["health"])
def health() -> dict[str, Any]:
    """Lightweight health — reports cached load flags, never loads a model."""
    gpu = _gpu_info()
    state = _model_state()
    return {
        "status": "ok",
        "deployment": "modal",
        "specialists": {
            "vqa": _cheap_specialist_flag("backend.models.vqa"),
            "change_detection": _cheap_specialist_flag("backend.models.change"),
            "optical_sar_fusion": _cheap_specialist_flag("backend.models.fusion"),
            "grounding": _cheap_specialist_flag("backend.models.grounding"),
            "yolo": _cheap_specialist_flag("backend.models.yolo"),
        },
        "base_model": app_config.BASE_MODEL,
        "adapter_path": app_config.ADAPTER_PATH,
        "change_adapter_path": getattr(app_config, "CHANGE_ADAPTER_PATH", None),
        "cuda_available": gpu["cuda_available"],
        "force_cpu": bool(getattr(app_config, "FORCE_CPU", False)),
        "compute": gpu["compute"],
        "device": gpu["device"],
        "gpu_name": gpu["gpu_name"],
        "model_attempted": state["attempted"],
        "model_ready": state["ready"],
        "model_load_error": state["load_error"],
        "note": (
            "VQA weights load once per warm container in @modal.enter; "
            "'deferred' means not yet loaded in this process, not broken."
        ),
    }


@web_app.post("/query", tags=["query"])
def query(body: QueryBody) -> Any:
    """Run one SatQuery through the existing controller (unchanged behaviour).

    Deliberately a sync `def` so FastAPI runs it in the threadpool — the
    controller blocks on GPU inference, and we must not stall the event loop
    that serves /health.
    """
    started = time.time()

    q = (body.query or "").strip()
    if not q:
        return _error(400, "query must be non-empty")

    mode = (body.input_mode or "single").strip().lower()
    if mode not in app_config.SUPPORTED_INPUT_MODES:
        return _error(
            400,
            f"Unsupported input_mode '{mode}'. Allowed: {sorted(app_config.SUPPORTED_INPUT_MODES)}",
        )

    try:
        images: list[tuple[str | None, bytes]] = []
        for slot, payload, filename in (
            ("image_a", body.image_a, body.image_a_filename),
            ("image_b", body.image_b, body.image_b_filename),
        ):
            decoded = _decode_image(payload, filename, slot)
            if decoded:
                images.append(decoded)
    except ValueError as e:
        return _error(400, str(e), code="INVALID_IMAGE")

    coords = body.coordinates.model_dump() if body.coordinates else None
    coords2 = body.coordinates_2.model_dump() if body.coordinates_2 else None

    loc_q = (body.location_query or "").strip() or None
    loc_q2 = (body.location_query_2 or "").strip() or None
    has_images = bool(images)
    has_location = bool(loc_q or coords or loc_q2 or coords2)
    if not has_images and not has_location:
        return _error(
            400,
            "Provide images (image_a / image_b) or a location "
            "(location_query / coordinates).",
        )

    # Imported lazily: importing the controller pulls torch + specialist modules
    # into THIS process — correct inside the Modal container, wrong at deploy time.
    from backend.controller import handle as controller_handle  # noqa: PLC0415

    try:
        resp = controller_handle(
            query=q,
            images=images,
            input_mode=mode,
            location_query=loc_q,
            coordinates=coords,
            location_query_2=loc_q2,
            coordinates_2=coords2,
        )
    except HTTPException as e:
        # Validation / location-resolution failures raised by the controller
        return _error(int(e.status_code), str(e.detail))
    except Exception as e:  # noqa: BLE001 — surface as traced 500, never crash the container
        logger.exception("Controller failed: %s", e)
        return _error(500, f"Controller error: {e}", code="CONTROLLER_ERROR")

    wall_ms = int((time.time() - started) * 1000)
    payload = _serialize_response(resp, wall_ms)
    logger.info(
        "Modal query: mode=%s task=%s conf=%.3f wall=%dms answer_len=%d",
        mode,
        (payload.get("execution_trace") or {}).get("task"),
        float(payload.get("confidence", 0.0)),
        wall_ms,
        len(str(payload.get("answer", ""))),
    )
    return JSONResponse(content=payload)


def build_web_app() -> FastAPI:
    """Returned by @modal.asgi_app() in modal_app/app.py (one app per container)."""
    return web_app
