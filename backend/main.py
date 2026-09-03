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
    description="Controller + registry + specialist models (VQA real, grounding/change/fusion stubbed in stage 1)",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for frontend dev (vite on :5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod
    allow_credentials=True,
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
