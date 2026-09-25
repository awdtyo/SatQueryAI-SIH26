"""Modal backend — a NEW deployment alongside the existing Hugging Face Spaces.

Architecture (addition only — `app.py` at the repo root, `frontend/` and
`vercel.json` are untouched and keep serving the HF Spaces exactly as before):

    Vercel React  ──future HTTPS JSON──▶  Modal FastAPI (modal_app/api.py)
                                              │
                                              ▼
                                    backend/controller.handle()   [REUSED, unchanged]
                                              │
                              ┌───────────────┼────────────────┬──────────────┐
                              ▼               ▼                ▼              ▼
                            VQA            YOLO count     change (CDVQA)   fusion/spectral

GPU lifecycle: one warm container = one Qwen2-VL-2B + LoRA adapter load,
performed in `@modal.enter()` (NOT per request). Weights are cached on a
Modal Volume at HF_CACHE_DIR so cold starts do not re-download them.

Deploy / test (NOT part of this change — run only when explicitly asked):
    pip install -U modal
    modal deploy modal_app/app.py          # deploy
    modal serve modal_app/app.py            # hot-reload dev
    curl https://<endpoint>/health

Secrets: none are required — Qwen/Qwen2-VL-2B-Instruct and
imadityasarkar/satquery-phase2-vrsbench are public. If you want an HF token
for higher rate limits:
    modal secret create satquery-hf HF_TOKEN=hf_xxx
then set USE_HF_TOKEN_SECRET = True below. Never commit tokens.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

# The repo root must be importable at DEPLOY time so Modal can resolve the
# local `backend` / `modal_app` packages for add_local_python_source(), and so
# `from modal_app...` works when this file is launched as a plain script.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import modal  # noqa: E402  (must follow the sys.path bootstrap)

from modal_app.api import build_web_app  # noqa: E402  (fastapi only — no torch)
from modal_app.image import HF_CACHE_DIR, build_image  # noqa: E402

logger = logging.getLogger("satquery.modal.app")

app = modal.App("satquery-modal-backend")

IMAGE = build_image()

# ~4GB Qwen2-VL base + adapter: keep between cold starts. Modal runs background
# commits and a final commit on container shutdown, so downloads persist.
HF_VOLUME = modal.Volume.from_name("satquery-hf-cache", create_if_missing=True)

# Optional HF_TOKEN secret — OFF by default (both model repos are public).
#   modal secret create satquery-hf HF_TOKEN=hf_xxx
USE_HF_TOKEN_SECRET = False
SECRETS: list[modal.Secret] = []
if USE_HF_TOKEN_SECRET:
    SECRETS.append(modal.Secret.from_name("satquery-hf"))

# GPU: A10G (24GB) mirrors the HF ZeroGPU a10g target and fits Qwen2-VL-2B in
# 4-bit with room for the processor KV cache. Override by editing here only.
_GPU = "A10G"


@app.cls(
    image=IMAGE,
    gpu=_GPU,
    cpu=4,
    memory=16384,  # MiB — headroom for 4-bit load + FastAPI
    timeout=600,  # seconds — cold model load + query
    scaledown_window=300,  # keep the container warm 5 min after last request
    secrets=SECRETS,
    volumes={HF_CACHE_DIR: HF_VOLUME},
)
@modal.concurrent(max_inputs=1)  # one GPU inference at a time (matches HF queue limit)
class SatQueryBackend:
    """Warm GPU container: model loaded once in @modal.enter, reused per request."""

    @modal.enter()
    def load_model(self) -> None:
        """Once-per-container warmup — never runs inside a request handler."""
        from backend import config as app_config
        from backend.models import vqa_specialist

        started = time.time()
        ok = vqa_specialist.preload()  # Qwen2-VL-2B + adapter; False => degraded, no raise
        info = vqa_specialist.get_model_info()
        logger.info(
            "Modal warmup: vqa_ready=%s adapter=%s device=%s cuda=%s load_ms=%d error=%s",
            ok,
            app_config.ADAPTER_PATH,
            info.get("device"),
            info.get("has_cuda"),
            int((time.time() - started) * 1000),
            info.get("load_error"),
        )

    @modal.asgi_app()
    def fastapi_app(self):  # noqa: ANN201 — modal expects a FastAPI instance
        """Serve the JSON API in this same container (imports only fastapi)."""
        return build_web_app()
