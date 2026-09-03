# HF Spaces — Docker Deployment (SatQuery AI)

**Image:** CPU-only (`SATQUERY_FORCE_CPU=1`), `Qwen/Qwen2-VL-2B-Instruct` + `imadityasarkar/satquery-qwen2vl-stage1-bigearthnet` (~4GB cold pull, cached in `/tmp/hf_cache`). Frontend `frontend/dist` is baked into the image via multi-stage `Dockerfile:6` and served by `backend/main.py:96` at `/`.

## 1. Create the Space

1. Go to https://huggingface.co/new-space → **Owner:** your HF username → **Name:** `satquery-ai` → **SDK:** `Docker` → **Hardware:** `CPU basic` (16GB) → **Create**.
2. In **Settings → Variables** add (optional):
   ```
   SATQUERY_BASE_MODEL=Qwen/Qwen2-VL-2B-Instruct
   SATQUERY_ADAPTER_PATH=imadityasarkar/satquery-qwen2vl-stage1-bigearthnet
   HF_TOKEN=hf_xxx   # only if adapter/base is gated/private
   SATQUERY_MAX_NEW_TOKENS=256
   # SATQUERY_FORCE_CPU is already 1 in Dockerfile:15
   ```
   For Stage-2: `SATQUERY_ADAPTER_PATH=imadityasarkar/satquery-qwen2vl-stage2-vrsbench` (swap without code, `backend/config.py:24`).

## 2. Push this repo (Docker)

HF Spaces is a git repo. From your local `mvp/`:

```bash
# Add Spaces remote (first time only)
git remote add spaces https://huggingface.co/spaces/<YOUR_USERNAME>/satquery-ai
# Or if you already have origin, use: git remote add hf ...

# Ensure Dockerfile, backend, frontend, requirements.txt are committed
git status
# Push — HF will build the Docker image (watch logs in Spaces → Logs)
git push spaces main
```

The `Dockerfile:1` is multi-stage:
* `frontend-builder` (`node:20-slim`) → `npm ci && npm run build` → `/app/frontend/dist`
* `runtime` (`python:3.10-slim`) → `pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu` → copies `backend/`, `frontend/dist`, runs `uvicorn backend.main:app --host 0.0.0.0 --port 7860` (`PORT` env is honored, HF sets `7860`).

No separate `README` frontmatter needed for Docker SDK — the presence of `Dockerfile` is enough. If HF asks for `sdk: docker`, keep your GitHub `README.md` as-is and add frontmatter only in the Spaces repo's `README.md` (see below).

## 3. Spaces README (if you want GitHub + Spaces to share one file)

Spaces with `sdk: docker` does **not** require the `sdk:` frontmatter, but if you clone the Space back and want it explicit, add to the Space’s `README.md` top:

```yaml
---
title: SatQuery AI
emoji: 🛰️
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Agentic VLM for satellite imagery — VQA, grounding, change detection
---
```

Keep the rest of `README.md` below the frontmatter (GitHub ignores it).

## 4. Verify after build

* **Logs:** Spaces → Logs should show `backend/main.py:30` `SatQuery AI backend starting...` `COMPUTE = CPU-ONLY`, then `✓ vqa (real) — REAL` or `○ STUB / ✗ DEGRADED` with `load_error` (if `HF_TOKEN` missing).
* **Health:** `https://<YOUR_USERNAME>-satquery-ai.hf.space/health` and `…/api/health` → `HealthResponse{status, specialists, base_model, adapter_path, compute: cpu-only, device: cpu}` `backend/schemas/__init__.py:60`.
* **Frontend:** `https://<YOUR_USERNAME>-satquery-ai.hf.space/` serves `frontend/dist/index.html` (`backend/main.py:99` static mount). Query `single` + `Describe land cover` → `ExecutionTrace` `is_real true`.
* **Warmup:** First query after cold start pulls `~4GB` (30-90s on Spaces CPU). Keep `SATQUERY_FORCE_CPU=1` — Spaces CPU has no GPU.

## 5. Updating

```bash
git push spaces main  # rebuilds Docker (2-4 min)
# To swap Stage-2 without rebuild: Space Settings → Variables → SATQUERY_ADAPTER_PATH=...stage2-vrsbench → Restart Space
```

## 6. Local Docker test (before pushing to HF)

```bash
docker build -t satquery-ai:local .
docker run --rm -p 7860:7860 -e HF_TOKEN=hf_xxx -e SATQUERY_ADAPTER_PATH=imadityasarkar/satquery-qwen2vl-stage1-bigearthnet satquery-ai:local
curl http://localhost:7860/health | jq
curl -X POST http://localhost:7860/api/query -F query="Describe land cover" -F input_mode=single -F images=@tests/sample.png | jq
open http://localhost:7860/
```

## 7. Troubleshooting

* **`✗ DEGRADED: Adapter load failed (401)`** → set `HF_TOKEN` in Space Variables (or make adapter public).
* **`processor requires Torchvision`** warn → ignored, `backend/models/vqa.py:84` retries plain `AutoProcessor`.
* **`no space left`** → Spaces `CPU basic` is `16GB` (like your i5) — keep `SATQUERY_MAX_NEW_TOKENS=128` if OOM, ensure `/tmp/satquery_offload` writable (`Dockerfile:42` `chmod 777`).
* **Cold start timeout:** `HEALTHCHECK` `Dockerfile:48` `start-period 60s` gives the model time to load; if still `○ STUB`, refresh after 1 min.
