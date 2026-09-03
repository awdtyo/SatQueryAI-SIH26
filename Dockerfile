# HF Spaces — Docker SDK (CPU-only, i5/16GB friendly)
# Multi-stage: 1) build frontend (node), 2) runtime (python + frontend dist + FastAPI)
# HF Spaces expects app_port 7860; locally you can still use 8000 via PORT env
# See docs/hf_spaces.md for push instructions

# ── Stage 1: Frontend build (Vite) ──
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Build outputs to /app/frontend/dist
RUN npm run build

# ── Stage 2: Python runtime (CPU) ──
FROM python:3.10-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/tmp/hf_cache \
    TRANSFORMERS_CACHE=/tmp/hf_cache \
    SATQUERY_FORCE_CPU=1 \
    PORT=7860

WORKDIR /app

# System deps: for pillow, curl healthcheck, and /tmp offload
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgl1 \
    libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# Python deps — CPU torch via extra index, plus inference deps
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir huggingface_hub  # for HF_TOKEN auth if gated

# Copy backend + configs + docs (no need for training notebooks at runtime)
COPY backend/ ./backend/
COPY training/configs/ ./training/configs/
COPY docs/ ./docs/
COPY README.md AGENTS.md ./

# Copy built frontend
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# HF Spaces runs as user 1000 by default, ensure cache/offload writable
RUN mkdir -p /tmp/hf_cache /tmp/satquery_offload && chmod -R 777 /tmp/hf_cache /tmp/satquery_offload \
 && useradd -m -u 1000 user \
 && chown -R user:user /app /tmp/hf_cache /tmp/satquery_offload
USER user

# Env overridable at Space runtime: set in Space Settings → Variables
# SATQUERY_BASE_MODEL=Qwen/Qwen2-VL-2B-Instruct (default in backend/config.py)
# SATQUERY_ADAPTER_PATH=imadityasarkar/satquery-qwen2vl-stage1-bigearthnet
# HF_TOKEN=hf_xxx (if gated)
# SATQUERY_MAX_NEW_TOKENS=256

EXPOSE 7860

# Healthcheck hits FastAPI /health (not /api/health) for Spaces load balancer
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -sf http://localhost:7860/health || exit 1

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
