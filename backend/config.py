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
# Stage 2: VRSBench/RSVQA SFT (imadityasarkar/satquery-phase2-vrsbench) continues from stage1 BigEarthNet.
# Stage 1 was imadityasarkar/satquery-qwen2vl-stage1-bigearthnet. Stage 3 will swap via env var.
ADAPTER_PATH: str = os.getenv(
    "SATQUERY_ADAPTER_PATH",
    "imadityasarkar/satquery-phase2-vrsbench",
)

# Optional HF token for gated/private repos (empty = anonymous).
HF_TOKEN: str | None = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")

# --- Device ---
# Auto GPU when available — VLM runs on CUDA + BitsAndBytes 4-bit if CUDA
# is present, otherwise falls back to CPU. Set SATQUERY_FORCE_CPU=1 to
# force CPU-only (e.g. HF Spaces CPU basic, i5/16GB without CUDA).
# Default is AUTO (0) — GPU is used whenever torch.cuda.is_available().
FORCE_CPU: bool = os.getenv("SATQUERY_FORCE_CPU", "0").lower() not in ("0", "false", "off", "no", "")


def is_gpu_available() -> bool:
    """True if a CUDA GPU is available and not force-disabled."""
    if FORCE_CPU:
        return False
    try:
        import torch  # type: ignore

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def get_device() -> str:
    """Return 'cuda' if GPU available else 'cpu'. Respects FORCE_CPU."""
    return "cuda" if is_gpu_available() else "cpu"


def get_device_count() -> int:
    try:
        import torch  # type: ignore

        if is_gpu_available():
            return int(torch.cuda.device_count())
    except Exception:
        pass
    return 0

# --- Inference knobs (config over hardcoding) ---
# Processor dynamic resolution caps — same values as training notebook
# (512*28*28 max, 256*28*28 min) to keep VRAM flat on T4.
IMAGE_MAX_PIXELS: int = int(os.getenv("SATQUERY_MAX_PIXELS", str(512 * 28 * 28)))
IMAGE_MIN_PIXELS: int = int(os.getenv("SATQUERY_MIN_PIXELS", str(256 * 28 * 28)))

# Generation — detailed outputs by default (384 tokens ≈ 250-300 words, warm ~1.5s on zero-a10g)
# Override via SATQUERY_MAX_NEW_TOKENS env (Space Variables → 128 for CPU basic, 384-512 for ZeroGPU)
MAX_NEW_TOKENS: int = int(os.getenv("SATQUERY_MAX_NEW_TOKENS", "384"))
# Minimum tokens to avoid premature EOS on generic queries
MIN_NEW_TOKENS: int = int(os.getenv("SATQUERY_MIN_NEW_TOKENS", "40"))
# Sampling — 0.0 deterministic (old), 0.2-0.3 gives richer detail while staying factual
TEMPERATURE: float = float(os.getenv("SATQUERY_TEMPERATURE", "0.2"))
TOP_P: float | None = float(os.getenv("SATQUERY_TOP_P", "0.9")) if os.getenv("SATQUERY_TOP_P", "0.9").lower() not in ("", "none", "null") else None
REPETITION_PENALTY: float = float(os.getenv("SATQUERY_REPETITION_PENALTY", "1.05"))
NO_REPEAT_NGRAM_SIZE: int = int(os.getenv("SATQUERY_NO_REPEAT_NGRAM_SIZE", "3"))
# System prompt — bullets replace paragraph + chart JSON (identical Gradio/React)
# Output is markdown bullets (3-6) + optional JSON chart; bullets are the answer, not a paragraph.
SYSTEM_PROMPT: str = os.getenv(
    "SATQUERY_SYSTEM_PROMPT",
    "You are SatQuery AI, an expert remote-sensing analyst. "
    "Respond ONLY in markdown bullets (3-6 bullets, each 1 sentence, 18-30 words). "
    "Bullets replace paragraphs — no prose block. "
    "Each bullet: bold class name, percentage if relevant, quadrant/location, 10m Sentinel-2 context. "
    "Cover BigEarthNet taxonomy and note uncertainty in last bullet. "
    "If yes/no or counting, first bullet is **Answer: Yes/No/Number**, then bullets for context. "
    "After bullets, on a new line append a JSON code fence with chart data for bars/pie: "
    "```json {\"chart\": [{\"label\": \"forest\", \"value\": 45}, {\"label\": \"arable\", \"value\": 30}]}``` "
    "Use 2-5 entries, values 5-90 sum ~100, labels lowercase. If no percentages apply, use chart with single label and 100.",
)
# For very short queries (e.g. 'Describe land cover'), append this to elicit bullets+chart
DETAIL_SUFFIX: str = os.getenv(
    "SATQUERY_DETAIL_SUFFIX",
    " Respond with bullet points and include the JSON chart as specified.",
)
# Output toggles — env overridable
CHART_ENABLED: bool = os.getenv("SATQUERY_CHART_ENABLED", "1").lower() not in ("0", "false", "off", "no", "")
OUTPUT_BULLETS: bool = os.getenv("SATQUERY_BULLETS", "1").lower() not in ("0", "false", "off", "no", "")

# Task → model routing (registry consults this; controller sets task)
# Stage 2 (phase2-vrsbench) provides VQA + grounding (VRSBench) via the same QLoRA adapter.
TASK_MODEL_MAP: dict[str, str] = {
    "vqa": "vqa",
    "captioning": "vqa",
    "visual_question_answering": "vqa",
    # Stage 2 grounding is now real (same adapter as VQA); change/fusion remain stubbed until stage 3
    "grounding": "vqa",
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
