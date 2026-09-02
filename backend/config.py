"""Backend config — dataset/model paths and task→model mappings.

All values are load-bearing for the controller/registry. Any change here
affects which specialist is selected for a given query/mode, so flag
changes to the team before modifying.

Env overrides let stage 2/3 adapters be swapped without code changes:
  SATQUERY_BASE_MODEL   -> BASE_MODEL
  SATQUERY_ADAPTER_PATH -> ADAPTER_PATH

See training/configs/bigearthnet_stage1.json for training-time hyperparams.
"""

import os

# --- Model ---
# Base VLM — must be a Qwen2-VL 2-3B variant to fit T4 (see AGENTS.md).
BASE_MODEL: str = os.getenv("SATQUERY_BASE_MODEL", "Qwen/Qwen2-VL-2B-Instruct")

# LoRA adapter — Hub repo id or local path. This is the ONLY place the
# adapter path is hardcoded; everything else imports from here.
# Stage 1: BigEarthNet captioning/VQA. Stage 2/3 will swap this to
# their respective adapters via env var.
ADAPTER_PATH: str = os.getenv(
    "SATQUERY_ADAPTER_PATH",
    "imadityasarkar/satquery-qwen2vl-stage1-bigearthnet",
)

# Optional HF token for gated/private repos (empty = anonymous).
HF_TOKEN: str | None = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")

# --- Inference knobs (config over hardcoding) ---
# Processor dynamic resolution caps — same values as training notebook
# (512*28*28 max, 256*28*28 min) to keep VRAM flat on T4.
IMAGE_MAX_PIXELS: int = int(os.getenv("SATQUERY_MAX_PIXELS", str(512 * 28 * 28)))
IMAGE_MIN_PIXELS: int = int(os.getenv("SATQUERY_MIN_PIXELS", str(256 * 28 * 28)))

# Generation
MAX_NEW_TOKENS: int = int(os.getenv("SATQUERY_MAX_NEW_TOKENS", "256"))

# Task → model routing (registry consults this; controller sets task)
# Only VQA/captioning has a trained adapter in stage 1. Others remain stubbed.
TASK_MODEL_MAP: dict[str, str] = {
    "vqa": "vqa",
    "captioning": "vqa",
    "visual_question_answering": "vqa",
    # Stubbed specialists — no trained adapter yet
    "grounding": "grounding_stub",
    "change_detection": "change_stub",
    "optical_sar_fusion": "fusion_stub",
}

# Supported input modes (mirrors frontend InputMode)
SUPPORTED_INPUT_MODES: set[str] = {"single", "optical-sar", "bi-temporal"}

# Supported formats — GeoTIFF/TIFF preferred; PNG/JPEG allowed for benchmarks
SUPPORTED_FORMATS: set[str] = {".tif", ".tiff", ".png", ".jpg", ".jpeg"}

# For env-based override of the task map (comma-separated "task:model" pairs)
# e.g. TASK_OVERRIDES="vqa:custom_vqa,grounding:my_grounding"
_task_overrides_raw = os.getenv("SATQUERY_TASK_OVERRIDES", "")
if _task_overrides_raw:
    for pair in _task_overrides_raw.split(","):
        if ":" in pair:
            k, v = pair.strip().split(":", 1)
            TASK_MODEL_MAP[k.strip()] = v.strip()
