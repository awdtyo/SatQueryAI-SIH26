"""FastAPI application entrypoint with startup health logging.

Usage:
    uvicorn backend.main:app --reload
    uvicorn backend.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend import config, registry
from backend.api import router as api_router

logger = logging.getLogger("satquery")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup check: which specialists are real vs stubbed ---
    logger.info("=" * 60)
    logger.info("SatQuery AI backend starting...")
    logger.info("  BASE_MODEL   = %s", config.BASE_MODEL)
    logger.info("  ADAPTER_PATH = %s", config.ADAPTER_PATH)
    logger.info("  (override via SATQUERY_BASE_MODEL / SATQUERY_ADAPTER_PATH)")
    if getattr(config, "FORCE_CPU", False):
        logger.info("  COMPUTE      = CPU-ONLY (SATQUERY_FORCE_CPU=1 — GPU/4-bit disabled)")
    else:
        # Auto GPU — report actual availability at startup
        try:
            import torch

            if torch.cuda.is_available():
                logger.info(
                    "  COMPUTE      = AUTO — GPU available (%s x%d) — VLM will run on GPU (4-bit if bitsandbytes present)",
                    torch.cuda.get_device_name(0),
                    torch.cuda.device_count(),
                )
            else:
                logger.info("  COMPUTE      = AUTO — no GPU detected, VLM will run on CPU")
        except Exception:
            logger.info("  COMPUTE      = auto (GPU if available, else CPU)")

    try:
        health = registry.health()
        specialists = health.get("registry", {})
        for name, info in specialists.items():
            is_real = info.get("is_real", False)
            stub = info.get("stub", False)
            err = info.get("load_error")
            if is_real and not stub:
                logger.info("  ✓ %s — REAL adapter loaded (is_real=True)", name)
            elif stub:
                logger.warning("  ○ %s — STUB mode (no adapter yet): %s", name, err or "stub")
            else:
                logger.warning("  ✗ %s — DEGRADED (load failed): %s", name, err or "unknown")

        # Explicit VQA status for demo clarity
        from backend.models import vqa_specialist

        vqa_info = vqa_specialist.get_model_info()
        if vqa_info.get("is_real"):
            logger.info("VQA specialist: REAL mode — queries will return model-generated answers")
        else:
            logger.warning(
                "VQA specialist: DEGRADED/STUB mode — queries will fail or return stub error text. "
                "Reason: %s | Check ADAPTER_PATH, HF_TOKEN, and GPU memory. "
                "Set SATQUERY_ADAPTER_PATH to a local path if Hub is unreachable.",
                vqa_info.get("load_error"),
            )
        logger.info("Backend ready — docs at /docs, health at /health")
    except Exception as e:
        logger.exception("Startup health check failed: %s", e)

    logger.info("=" * 60)
    yield
    logger.info("SatQuery AI backend shutting down")


app = FastAPI(
    title="SatQuery AI — Agentic Remote-Sensing VLM",
    description="Controller + registry + specialist models (VQA+grounding+fusion real via Stage-2 vrsbench, change real via Stage-3 cdvqa_change)",
    version="0.1.0",
    lifespan=lifespan,
)

# Structured error envelope — do not leak stack traces / paths / tokens to frontend
# Frontend expects {detail} for 4xx, but new API also returns {status:"error", error:{code,message}} for Vercel client
from fastapi import Request, HTTPException as FastAPIHTTPException
from fastapi.responses import JSONResponse


@app.exception_handler(FastAPIHTTPException)
async def _http_exception_handler(request: Request, exc: FastAPIHTTPException):
    # Log full detail server-side, return sanitized to client
    logger.warning(f"HTTP {exc.status_code} at {request.url.path}: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "error": {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail)},
            "detail": str(exc.detail),  # backward compat for existing frontend mockClient parsing detail
        },
    )


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error at {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "error": {"code": "INTERNAL_ERROR", "message": "Internal server error"},
        },
    )

# CORS for Vercel frontend → HF Space API
# Configured via CORS_ORIGINS env (comma-separated). Default ["*"] for backward compat.
# New deployment should set: CORS_ORIGINS=http://localhost:5173,https://satquery.vercel.app
_cors_origins = getattr(config, "CORS_ORIGINS", ["*"])
# Browsers reject allow_credentials=True with allow_origins=["*"]; only send
# credentials when explicit origins are configured.
_cors_allow_credentials = not (_cors_origins == ["*"])
# HF healthcheck and Gradio also need to allow all during local dev; tighten in prod via env
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Serve built frontend when present (Docker / HF Spaces) ---
# Frontend built to frontend/dist (vite build). In Docker multi-stage, copied to /app/frontend/dist.
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if not _FRONTEND_DIST.exists():
    _ALT = Path("/app/frontend/dist")
    if _ALT.exists():
        _FRONTEND_DIST = _ALT

_HAS_FRONTEND = _FRONTEND_DIST.exists() and (_FRONTEND_DIST / "index.html").exists()

# Lightweight health for HF Space healthcheck — does NOT trigger model loading (ZeroGPU)
# NOTE: this is intentionally lightweight/deferred. For loaded is_real status use
# GET /api/health (which may cold-pull ~4GB on first call). The "specialists" map
# below reports cached load flags WITHOUT forcing a load, so "deferred" means
# "not yet loaded in this process", not "stub".
def _cheap_specialist_flag(module_name: str) -> str:
    """Return 'ready' / 'deferred' / 'error' without triggering model download."""
    try:
        import importlib

        mod = importlib.import_module(module_name)
        if getattr(mod, "_load_attempted", False):
            return "ready" if getattr(mod, "_is_real", False) else "error"
        return "deferred"
    except Exception:
        return "deferred"


@app.get("/health", tags=["health"], include_in_schema=False)
def _lightweight_health():
    return {
        "status": "ok",
        "mode": "lightweight",
        "note": "Deferred flags only — use /api/health for loaded is_real status (may cold-pull model).",
        "specialists": {
            "vqa": _cheap_specialist_flag("backend.models.vqa"),
            "change_detection": _cheap_specialist_flag("backend.models.change"),
            "optical_sar_fusion": _cheap_specialist_flag("backend.models.fusion"),
            "yolo": _cheap_specialist_flag("backend.models.yolo"),
        },
        "base_model": config.BASE_MODEL,
        "adapter_path": config.ADAPTER_PATH,
        "cuda_available": False,
        "force_cpu": bool(getattr(config, "FORCE_CPU", False)),
        "compute": "cpu",
        "device": "cpu",
    }

# Capabilities endpoint for Vercel frontend — static registration map (no model load)
# Must NOT call registry.health()/get_model_info() here: those lazily _load_model()
# (cold-pull ~4GB) on first call. Use /api/health when loaded is_real is needed.
@app.get("/api/capabilities", tags=["capabilities"])
def capabilities() -> dict:
    # Registered (not loaded) capabilities — mirrors registry._REGISTRY keys + config.
    # "grounding" stays False (stub, no adapter yet). Spectral/live/viz need no weights.
    return {
        "vqa": True,  # registry: vqa/captioning → vqa_specialist (Qwen2-VL-2B + phase2-vrsbench)
        "object_detection": True,  # registry: count/counting → yolo_specialist (yolov8n.pt)
        "spectral_indices": True,  # spectral agent always available (no model weight)
        "change_detection": True,  # registry: change_detection/change/cdvqa → change_specialist
        "live_satellite": True,  # Planetary Computer + Nominatim
        "visualizations": True,  # chart + Gallery
        "grounding": False,  # stub (backend/models/grounding.py)
        "fusion": True,  # registry: optical_sar_fusion/fusion/sar → fusion_specialist
    }

# Mount order matters: frontend "/" must be registered before root api_router's "/" so "/" serves SPA when dist exists
app.include_router(api_router, prefix="/api")

if _HAS_FRONTEND:
    assets_dir = _FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    def _serve_index():
        return FileResponse(str(_FRONTEND_DIST / "index.html"))

    logger.info("Frontend static mounted from %s ( / serves SPA, /api/* and /health remain API )", _FRONTEND_DIST)
else:
    logger.debug("Frontend dist not found at %s — serving API only (dev mode)", _FRONTEND_DIST)

# Also mount at root for direct /health /query (frontend dev proxies /api, but direct calls and HF healthcheck use /health)
# Registered after frontend "/" so "/" remains SPA, while /health, /query, /docs still resolve to API
app.include_router(api_router)
