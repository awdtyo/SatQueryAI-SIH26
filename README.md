# SatQuery AI

An agentic vision-language assistant for querying single and paired remote-sensing images (optical/multispectral, SAR) through natural language — built for Smart India Hackathon 2026. A lightweight controller interprets the query, validates input modality (GeoTIFF/TIFF or approved PNG/JPEG, band count, single/pair/bi-temporal), routes to one or more specialist models (VQA, captioning, grounding, change detection, optical-SAR fusion) via a central registry, merges their outputs, and returns an evidence-grounded answer with a full `ExecutionTrace` (task, selected model/tool names, parameters, confidence).

## Repository structure

```
backend/
  controller/        # agentic controller: task classification, input validation, routing
  models/            # specialist model wrappers (vqa, grounding, change, fusion)
  registry.py        # model/tool registry the controller selects from
  api/               # FastAPI routes
  schemas/           # pydantic request/response + execution-trace schemas
frontend/            # upload UI, query box, results + evidence panel (React; Streamlit/Gradio for early prototyping — check frontend/ before assuming)
training/
  notebooks/         # Colab QLoRA notebooks, one per stage (satquery_ai_qlora_finetune.ipynb = stage 1 BigEarthNet)
  configs/           # per-dataset training configs (bigearthnet, vrsbench, rsvqa, cdvqa)
  adapters/          # NOT committed — LoRA adapter weights live on Drive/HF Hub, referenced by path/URL in backend/config.py
data/
  loaders/           # dataset-specific loaders (do not hardcode paths, use config)
tests/
docs/
```

See `AGENTS.md` for full conventions, training workflow (QLoRA on Colab free-tier T4), and mandatory functional scope.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pre-commit install
```

Copy `.env.example` to `.env` and fill required keys (never commit `.env`).

### Commands

- Run backend dev server: `uvicorn backend.main:app --reload`
- Run frontend dev server: `cd frontend && npm run dev`
- Run tests: `pytest tests/ -v`
- Run a single test: `pytest tests/test_controller.py::test_task_routing -v`
- Lint: `ruff check .` / Format: `ruff format .`
- Type check: `mypy backend/`
```

## Notes

- This is an initial scaffold only — controller, registry, API routes, and model logic are placeholders for team branches to implement.
- `training/notebooks/` is intentionally left untouched (existing notebooks preserved).
- Input modality checks and `ExecutionTrace` are mandatory first-class outputs — see `AGENTS.md`.
