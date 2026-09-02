# AGENTS.md

Instructions for AI coding agents working in this repository.

## Project

**SatQuery AI** — an agentic vision-language assistant for querying single and paired
remote-sensing images (optical/multispectral, SAR) through natural language.
Built for Smart India Hackathon 2026.

**Current state: initial scaffold (single commit).** All backend modules are placeholder
stubs. No `.env.example`, no pre-commit config, no CI workflows. Do not attempt to run
the backend server, tests, linter, or type-checker until the respective files exist and
dependencies are installed.

Core idea: a controller interprets a query, validates the input images, routes to one or
more specialist models (VQA, captioning, grounding, change detection, optical-SAR fusion),
merges their outputs, and returns an evidence-grounded answer with a full execution trace.

Read `docs/problem_statement.md` (if present) before making architectural changes — the
mandatory functional scope defined there overrides convenience shortcuts.

## Tech stack

- **Backend**: Python 3.10+, FastAPI, PyTorch
- **Models**: HuggingFace `transformers` + `peft` (LoRA/QLoRA fine-tuning), CLIP-style
  vision encoder, LLaMA/Qwen-family decoder
- **Frontend**: React (or Streamlit/Gradio for early prototyping) — check `frontend/` for
  which one is actually in use before assuming
- **Data**: rasterio / GDAL for GeoTIFF handling, numpy, torchvision transforms
- **Orchestration**: custom lightweight controller (not LangChain) — see
  `backend/controller/`
- **Training environment**: Google Colab free tier (T4 GPU). All fine-tuning happens
  in notebooks, not local scripts — see `training/notebooks/`. Local/backend code never
  imports training-time-only deps (`bitsandbytes`, `peft` training utilities beyond
  inference-time adapter loading) into the API path.

## Setup

Not yet runnable — `requirements.txt` is empty and no `.env.example`, pre-commit config,
or CI workflow exists. These are aspirational and may not work on the scaffold:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pre-commit install
```

When a `.env.example` appears: copy it to `.env` and fill required keys (never commit `.env`).

## Commands

- Run backend dev server: `uvicorn backend.main:app --reload`
- Run frontend dev server: `cd frontend && npm run dev`
- Run tests: `pytest tests/ -v`
- Run a single test: `pytest tests/test_controller.py::test_task_routing -v`
- Lint: `ruff check .` / Format: `ruff format .`
- Type check: `mypy backend/`

Always run lint + tests before considering a change complete. Do not skip failing tests
by deleting or weakening assertions — fix the underlying issue or flag it explicitly.

## Repository structure

```
backend/
  controller/        # agentic controller: task classification, input validation, routing
  models/             # specialist model wrappers (vqa, grounding, change, fusion)
  registry.py         # model/tool registry the controller selects from
  api/                # FastAPI routes
  schemas/            # pydantic request/response + execution-trace schemas
frontend/              # upload UI, query box, results + evidence panel
training/
  notebooks/            # Colab .ipynb notebooks, one per fine-tuning stage
    satquery_ai_qlora_finetune.ipynb   # stage 1: BigEarthNet vision-language adaptation
    # stage 2 (vrsbench_rsvqa_sft.ipynb) and stage 3 (cdvqa_change_sft.ipynb)
    # follow the same structure once added
  configs/               # per-dataset training configs (bigearthnet, vrsbench, rsvqa, cdvqa)
  adapters/               # NOT committed — LoRA adapter weights live on Drive/HF Hub,
                           # referenced by path/URL in backend/config.py, never in git
data/
  loaders/             # dataset-specific loaders (do not hardcode paths, use config)
tests/
docs/
```

## Conventions

- **Input modality checks are mandatory**, not optional validation. Every entrypoint that
  accepts an image must check format (GeoTIFF/TIFF, or approved PNG/JPEG for benchmark
  datasets only), band count, and single/pair/bi-temporal configuration before calling a
  specialist model. Do not bypass this even for quick internal scripts.
- **Execution trace is a first-class output**, not a debug log. Any change to the
  controller must keep `ExecutionTrace` (task, selected model/tool names, parameters,
  confidence) populated and returned in the API response — this is what gets evaluated.
- Specialist models are called through the registry interface in `backend/registry.py`,
  never imported and invoked directly from route handlers. If a new specialist model is
  added, register it there with its supported input modality/configuration so the
  controller can select it correctly.
- Config over hardcoding: dataset paths, model checkpoint paths, and task→model mappings
  live in `training/configs/` or `backend/config.py`, not inline in code.
- Prefer LoRA/QLoRA fine-tuning over full fine-tuning given hackathon time/compute
  constraints, unless a task explicitly calls for full fine-tuning.
- New specialist models must declare which benchmark(s) they're evaluated against
  (RSVQA, VRSBench, CDVQA) in their module docstring.

## Training workflow (Colab free tier)

Fine-tuning happens in Colab notebooks under `training/notebooks/`, not as standalone
Python scripts run locally or in CI. This repo's backend code must stay independent of
that environment — it only ever loads a *finished* LoRA adapter for inference, never
trains one.

Constraints baked into every training notebook (do not "simplify" these away when
editing a notebook — they exist because free-tier Colab sessions can disconnect at any
time and have ~15GB VRAM):

- **QLoRA only** (4-bit base model + LoRA adapters), never full fine-tuning. Base model
  choice must fit a T4 (~15GB VRAM) — small VLMs (2–3B params, e.g. Qwen2-VL-2B-Instruct)
  only, not 7B+.
- **Checkpoint to Google Drive frequently** (`save_steps` on the order of tens of steps,
  not epochs) and **resume from the latest checkpoint automatically** at the top of
  training — every notebook must be safe to rerun top-to-bottom after a disconnect
  without losing progress or duplicating work.
- **Dataset subsets are cached to Drive once**, not re-downloaded/re-streamed each
  session. Full BigEarthNet.txt (or other full benchmark splits) should never be pulled
  into a single Colab session — subset first, cache the subset, iterate on that.
- **Small batch size + gradient accumulation** (e.g. batch size 1, accumulation 8) rather
  than large batches, to stay under the VRAM ceiling.
- Each fine-tuning stage (BigEarthNet adaptation → VRSBench/RSVQA SFT → CDVQA change SFT)
  gets its own notebook and its own checkpoint directory on Drive; a later stage loads
  the previous stage's adapter as its starting point rather than the base model.

When asked to add a new training stage, copy the structure of
`satquery_ai_qlora_finetune.ipynb` (mount Drive → install deps → load quantized base +
adapter-to-continue-from → dataset subset/cache → resume-aware `Trainer` → save adapter)
rather than writing a new pattern from scratch.

If free-tier T4 availability becomes unreliable, the fallback is Kaggle notebooks
(30 GPU-hrs/week free, T4×2) — same notebook structure, swap the Drive mount for
Kaggle's persistent `/kaggle/working` output directory.

## What not to do

- Do not add a generic/non-adapted LLM or VLM as a fallback path that bypasses
  remote-sensing adaptation — the problem statement explicitly disqualifies this.
- Do not commit model checkpoints, `.env`, or raw dataset files (BigEarthNet etc.) — use
  the paths defined in configs and keep large files out of git (see `.gitignore`).
- Do not remove or shortcut the input compatibility-checking step, even to make a demo
  path faster — judged criteria depend on it being real.
- Do not write training code that assumes an uninterrupted long-running session, a full
  dataset download, or full fine-tuning — it will not run on the free-tier hardware this
  project actually uses. Do not add adapter weights or dataset caches to git.

## PR / commit conventions

- Commit messages: short imperative summary line, e.g. `Add change-VQA specialist wrapper`
- Keep changes scoped — a controller change and a new specialist model belong in
  separate commits/PRs where practical
- Update `docs/execution_trace_schema.md` if you change the shape of `ExecutionTrace`
