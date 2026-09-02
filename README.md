# SatQuery AI

An agentic vision-language assistant for querying single and paired remote-sensing images (optical/multispectral, SAR) through natural language — built for Smart India Hackathon 2026.

A lightweight controller interprets the query, validates input modality (GeoTIFF/TIFF or approved PNG/JPEG, band count, single/pair/bi-temporal), routes to one or more specialist models (VQA, captioning, grounding, change detection, optical-SAR fusion) via a central registry, merges their outputs, and returns an evidence-grounded answer with a full `ExecutionTrace` (task, selected model/tool names, parameters, confidence).

## Architecture

```
User Query + Imagery (1-2 files)
        │
        ▼
┌─────────────────┐     ┌──────────────┐     ┌─────────────────────┐
│  Input Validation│────▶│  Controller  │────▶│  Registry (routing) │
│  format/bands/   │     │  task class. │     │  task → model map   │
│  single/pair     │     │              │     │                     │
└─────────────────┘     └──────────────┘     └─────────────────────┘
                                                       │
                              ┌────────────────────────┼────────────────────────┐
                              ▼                        ▼                        ▼
                       VQA / Captioning        Grounding / Detection    Change / SAR Fusion
                              │                        │                        │
                              └────────────────────────┼────────────────────────┘
                                                       ▼
                                              Merge + Evidence
                                                       │
                                                       ▼
                                            { answer, confidence,
                                              execution_trace, evidence }
```

**ExecutionTrace** is a graded first-class output — every response includes `task`, `models_used[]`, `parameters`, `confidence`, `evidence_refs`, `total_latency_ms`. See `frontend/src/types/api.ts` for the schema.

## Repository structure

```
backend/
  controller/        # agentic controller: task classification, input validation, routing (scaffold)
  models/            # specialist model wrappers (vqa, grounding, change, fusion) (scaffold)
  registry.py        # model/tool registry the controller selects from (scaffold)
  api/               # FastAPI routes (scaffold)
  schemas/           # pydantic request/response + execution-trace schemas (scaffold)
  config.py          # model/dataset paths, task→model mappings (scaffold)
frontend/            # React + Vite + Tailwind — upload UI, query box, results + evidence panel
  src/
    components/      # ImageUploader, ImageryViewer, QueryInput, ResultsPanel, ExecutionTrace, ConfidenceGauge
    api/mockClient.ts # mock backend (swap for real fetch when backend/api is ready)
    types/api.ts     # InputMode, QueryResponse, ExecutionTrace schemas
training/
  notebooks/
    satquery_ai_qlora_finetune.ipynb  # Stage 1: BigEarthNet VL adaptation (QLoRA, T4-ready)
  configs/
    bigearthnet_stage1.json           # Stage 1 hyperparams (source of truth for notebook)
    vrsbench_rsvqa_sft.json           # (planned) Stage 2
    cdvqa_change_sft.json             # (planned) Stage 3
  adapters/          # NOT committed — LoRA weights live on Drive/HF Hub, referenced by path in backend/config.py
data/
  loaders/           # dataset-specific loaders (use config, do not hardcode paths)
tests/               # pytest (placeholder)
docs/
```

See `AGENTS.md` for full conventions, training constraints, and mandatory functional scope.

## Tech stack

| Layer | Stack |
|-------|-------|
| Backend | Python 3.10+, FastAPI, PyTorch |
| Models | HuggingFace `transformers` + `peft` (QLoRA), `Qwen2-VL-2B-Instruct` (2B, T4-fit), `bitsandbytes` 4-bit NF4 |
| Frontend | React 18, Vite 6, Tailwind 3, TypeScript 5 |
| Data | `rasterio`/`GDAL` for GeoTIFF, `numpy`, `torchvision`, `datasets` |
| Orchestration | Custom lightweight controller (not LangChain) |
| Training env | Google Colab free-tier T4 (15GB VRAM), fallback Kaggle T4×2 |

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # backend deps (currently minimal — pin per branch)
pre-commit install
```

Copy `.env.example` to `.env` and fill required keys (never commit `.env`).

### Frontend

```bash
cd frontend && npm install && npm run dev   # http://localhost:5173 (proxies /api → :8000)
npm run build   # production
```

### Backend (scaffold — not yet runnable)

```bash
uvicorn backend.main:app --reload   # planned entrypoint (not yet implemented)
pytest tests/ -v
ruff check . && ruff format .
mypy backend/
```

## Training — Colab T4 QLoRA

All fine-tuning runs in Colab notebooks (`training/notebooks/`), not local scripts. Backend only loads finished adapters for inference — it never imports `bitsandbytes`/training-time `peft` utilities.

### Stage 1: BigEarthNet adaptation

**Notebook:** `training/notebooks/satquery_ai_qlora_finetune.ipynb` — open in Colab with **T4 GPU** runtime.

```text
Runtime → Change runtime type → T4 GPU → Run all
```

| Item | Value |
|------|-------|
| Base model | `Qwen/Qwen2-VL-2B-Instruct` (2B, fits T4) |
| Method | QLoRA — 4-bit NF4 + double-quant + LoRA r=16 α=32 (~14M trainable, 0.7%) |
| Targets | `q_proj k_proj v_proj o_proj gate_proj up_proj down_proj` |
| Batch | `1 × grad_accum 8` (effective 8), `fp16`, `paged_adamw_8bit`, `grad_checkpointing=True` |
| Checkpoints | `save_steps=25`, `save_total_limit=2`, auto-resume from latest `checkpoint-*` on Drive |
| Dataset cache | Subset `800` samples cached to Drive (`DATASET_CACHE_DIR`), `load_from_disk` on reruns — never re-downloads full 70GB BigEarthNet |
| Config | `training/configs/bigearthnet_stage1.json` (also mirrored to Drive `training_config_stage1.json`) |
| Paths (Drive) | `CHECKPOINT_DIR=/content/drive/MyDrive/SatQueryAI/checkpoints/stage1_bigearthnet_qlora` |
| | `DATASET_CACHE_DIR=/content/drive/MyDrive/SatQueryAI/datasets/bigearthnet_subset` |
| | `ADAPTER_OUTPUT_DIR=.../final_adapter` (~30-80MB) |
| Time | ~15-25 min for 800 samples, 1 epoch, on T4 |

**Dependency safety:** notebook keeps Colab's preinstalled `torch 2.10+cu128` and pins `transformers==4.46.3 peft==0.14.0 accelerate==1.4.0 bitsandbytes==0.45.5 datasets==3.1.0 qwen-vl-utils==0.0.10 trl==0.15.2` to avoid the classic `libnvJitLink.so.13` CUDA mismatch from upgrading to `cu130`. If imports fail, `§3b` in the notebook gives the exact fix (uninstall `nvidia-nvjitlink-cu*` or reinstall `cu128` wheels, then restart runtime).

**Flow (15 cells):** GPU check → Drive mount → pip install (no torch upgrade) → imports audit → `TrainConfig` → dataset subset/cache (synthetic fallback ensures end-to-end smoke test; swap with real BigEarthNet HF/parquet loader) → load 4-bit base + processor → LoRA → tokenize (prompt-masked labels, `max_seq_length=1024`, dynamic `min/max_pixels`) → `TrainingArguments` + `VisionDataCollator` → `Trainer` → resume-aware `train()` → save adapter to Drive (+ `DRIVE_PATH.txt` pointer) → inference sanity check → next-stage copy instructions.

**Next stages:** duplicate the notebook; change `CHECKPOINT_DIR`, `DATASET_CACHE_DIR`, and set `CFG.adapter_to_continue = .../stage1/final_adapter` to chain adapters. Update `training/configs/` for `vrsbench_rsvqa_sft` and `cdvqa_change_sft` (typically lower LR to `1e-4`).

> Full free-tier constraints (frequent Drive saves, resume safety, subset caching, small batch + accumulation) are defined in `AGENTS.md#Training workflow` — the notebook does not simplify them away.

## Frontend — current implementation

Fully built mock; backend is scaffold-only.

- **Three-zone layout** (`frontend/src/App.tsx`): left 280px ingestion (`ImageUploader` modes `single`/`optical-sar`/`bi-temporal`, `.tif,.tiff,.png,.jpg`), center imagery viewer (`ImageryViewer` with bbox overlay) + `ResultsPanel`, right 300px telemetry (`ExecutionTrace` 6-step pipeline, `ConfidenceGauge`, system status), bottom `QueryInput` terminal with suggestions.
- **Mock backend** (`frontend/src/api/mockClient.ts`): `submitQuery()` returns deterministic `MOCK_RESPONSE` (change_detection via `SatVQA-v1` + `ChangeFormer-B4`) after 1800ms. Replace with `fetch("/api/query", {method:"POST", body:FormData})` and `fetch("/api/health")` when `backend/api` is implemented (stubs already in file).
- **Types** (`frontend/src/types/api.ts`): `InputMode`, `UploadedImage`, `QueryRequest`, `QueryResponse`, `ExecutionTrace`, `ModelTraceEntry`, `EvidenceRef` — matches the graded backend schema.

## Commands

```bash
# Frontend
cd frontend && npm run dev          # dev (vite, proxy /api → :8000)
cd frontend && npm run build        # tsc + vite build

# Backend (when implemented)
uvicorn backend.main:app --reload
pytest tests/ -v
pytest tests/test_controller.py::test_task_routing -v
ruff check . && ruff format .
mypy backend/
```

## Implementation status

| Component | Status |
|-----------|--------|
| Frontend (React, mock client) | ✅ Implemented |
| Training notebook Stage 1 (QLoRA, T4) | ✅ Implemented |
| Training configs | ✅ `bigearthnet_stage1.json` (others planned) |
| Backend controller / registry / schemas / api / models | 🔲 Scaffold only — placeholders |
| Tests | 🔲 Scaffold only |
| BigEarthNet loader (real data) | 🔲 Synthetic fallback in notebook; swap in real HF/torchgeo loader when access granted |

## Conventions

- Input modality checks are mandatory (format, band count, single/pair/bi-temporal) — every image entrypoint validates before calling a specialist. See `AGENTS.md`.
- `ExecutionTrace` is a first-class output, not a debug log — controller must always populate and return it.
- Specialist models are called via `backend/registry.py`, never imported directly in route handlers.
- Config over hardcoding — paths and task→model maps live in `training/configs/` or `backend/config.py`.
- Prefer LoRA/QLoRA over full fine-tuning (hackathon time/compute constraints).
- Do not commit `.env`, checkpoints (`.bin/.safetensors`), adapters, or raw datasets — see `.gitignore`.

## Notes

- `training/adapters/` and `training/notebooks/*.ipynb_checkpoints` are gitignored — adapters live on Drive/HF Hub.
- `training/notebooks/` is no longer empty — `satquery_ai_qlora_finetune.ipynb` is the Stage 1 reference; later stages copy its structure (mount Drive → install deps → quantized base + adapter-to-continue → subset/cache → resume-aware `Trainer` → save adapter) per `AGENTS.md`.
- Input modality checks and `ExecutionTrace` are mandatory graded outputs — see `AGENTS.md`.
