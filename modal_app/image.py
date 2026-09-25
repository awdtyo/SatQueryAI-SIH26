"""Modal Image for the SatQuery Modal backend.

Contains ONLY the dependencies `backend/` actually needs at runtime — this is
deliberately NOT a copy of `requirements.txt`:

    excluded (HF/Gradio-only or dev-only):
        gradio, gradio_client, spaces, matplotlib, pytest, httpx, ruff, mypy,
        python-multipart (backend/api is Form/File based; this API is JSON),
        rasterio (optional GeoTIFF band check — backend falls back to PIL)

Import inspection used to derive this list:
    module-level: fastapi, pydantic, PIL, numpy, requests, backend.config (os only)
    lazy in-function: torch, transformers, peft, bitsandbytes, accelerate,
                      ultralytics (cv2), pystac_client, planetary_computer
    never imported by backend/: gradio, matplotlib

The Modal runtime serves @modal.asgi_app itself (uvicorn included), so uvicorn
is not installed here either.
"""

from __future__ import annotations

import modal

PYTHON_VERSION = "3.12"

# Hugging Face cache path — mounted on a Modal Volume in app.py so warm/cold
# containers reuse the ~4GB base model + adapter instead of re-downloading.
HF_CACHE_DIR = "/root/.cache/huggingface"

# Runtime libs for opencv-python (ultralytics/YOLO) on debian-slim — same two
# packages the existing Dockerfile installs (libgl1, libglib2.0-0).
_APT_PACKAGES = [
    "libgl1",
    "libglib2.0-0",
]

_PIP_PACKAGES = [
    # --- HTTP API (FastAPI JSON; Modal serves the ASGI app itself) ---
    "fastapi>=0.110",
    "pydantic>=2.0",
    # --- numerics + images (backend/utils/chart.py: coverage + 3x3 grid) ---
    "pillow>=10.0",
    "numpy<2.0",
    # --- VQA path: Qwen2-VL-2B-Instruct + LoRA adapter (backend/models/vqa.py) ---
    "torch>=2.0",
    "torchvision>=0.18",  # Qwen2VL processor video fallback (see requirements.txt)
    "transformers>=4.46",
    "peft>=0.14.0",
    "accelerate>=1.4.0",  # transformers/peft device_map
    "bitsandbytes>=0.45.5",  # 4-bit NF4 load on GPU
    "qwen-vl-utils>=0.0.10",  # Qwen2-VL companion (tiny, listed with the VLM stack)
    # --- count specialist: backend/models/yolo.py (ultralytics pulls opencv) ---
    "ultralytics>=8.2",
    "opencv-python>=4.8",
    # --- location mode: backend/services (Nominatim + Planetary Computer STAC) ---
    "requests>=2.28",
    "pystac-client>=0.8.0",
    "planetary-computer>=1.0",
]


def build_image() -> modal.Image:
    """Reproducible Modal Image for backend/ + modal_app/.

    Order matters: `add_local_python_source(...)` adds a lazy (non-copy) source
    layer, so it must come AFTER all build steps (pip_install / env / apt).
    """
    return (
        modal.Image.debian_slim(python_version=PYTHON_VERSION)
        .apt_install(*_APT_PACKAGES)
        .pip_install(*_PIP_PACKAGES)
        .env(
            {
                "PYTHONUNBUFFERED": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                # Modal gives the container a real GPU — never force CPU here
                # (the Docker/HF-CPU path sets SATQUERY_FORCE_CPU=1 itself).
                "SATQUERY_FORCE_CPU": "0",
                # Single shared HF cache, persisted on a Modal Volume (app.py)
                "HF_HOME": HF_CACHE_DIR,
            }
        )
        # Pure-python project source: backend/ is the single implementation of
        # controller + registry + specialists; modal_app/ holds only this layer.
        .add_local_python_source("backend", "modal_app")
    )
