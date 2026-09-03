# HF Spaces — Gradio + ZeroGPU (SatQuery AI)

**Image:** `app.py` Gradio `Blocks` on Blackwell `zero-a10g` (`large` = half RTX Pro 6000 `48GB` / `xlarge = 96GB`). `Space Variables: SATQUERY_FORCE_CPU=0` enables real CUDA via `@spaces.GPU(duration=30)` (vs Docker `CPU basic 16GB` `SATQUERY_FORCE_CPU=1`).

Hybrid repo: **Docker stays for local CPU** (`make pitch-demo`, `Dockerfile` `python:3.10-slim` `PORT 7860`), **Spaces runs `app.py`** (`sdk: gradio`, `hardware: zero-a10g`). Same `backend/controller` + `registry` + `Qwen2-VL-2B` `+ PEFT` stack, no HTTP in Space.

## 1. Create the Space (Gradio + ZeroGPU)

1. Go to https://huggingface.co/new-space → Owner `YOUR_USERNAME` → Name `satquery-ai` → **SDK `Gradio`** → **Hardware `ZeroGPU`** (`zero-a10g`) → Create.
2. Settings → Variables add:
   ```
   SATQUERY_BASE_MODEL=Qwen/Qwen2-VL-2B-Instruct
   SATQUERY_ADAPTER_PATH=imadityasarkar/satquery-qwen2vl-stage1-bigearthnet
   HF_TOKEN=hf_xxx   # only if gated/private
   SATQUERY_FORCE_CPU=0         # critical — enables CUDA on ZeroGPU (Docker local keeps 1)
   SATQUERY_MAX_NEW_TOKENS=128  # 128 cuts 30-90s → ~15s on ZeroGPU large, avoids OOM
   ```
   Stage-2: `SATQUERY_ADAPTER_PATH=imadityasarkar/satquery-qwen2vl-stage2-vrsbench` (swap without rebuild, `backend/config.py:24`).

HF injects `GRADIO_SERVER_NAME=0.0.0.0` `GRADIO_SERVER_PORT=7860`; `app.py: demo.launch(server_name, server_port)` honors it. Do **not** set `PORT` (Docker only).

## 2. Push (Gradio SDK)

From `mvp/`:

```bash
# Add Spaces remote (first time)
git remote add spaces https://huggingface.co/spaces/<YOUR_USERNAME>/satquery-ai
# Ensure app.py, backend/, requirements.txt (with gradio) are committed
git status  # should show app.py, requirements.txt, docs/hf_spaces_gradio.md — keep Dockerfile for local
git push spaces main  # HF builds Gradio image (~2 min, pip install gradio + torch CUDA), watch Logs
# ZeroGPU check: Spaces → Settings → Hardware must show zero-a10g, not CPU basic
```

**Do not** push `Dockerfile` as Space entry — with `sdk: gradio` the presence of `Dockerfile` is ignored (HF prioritizes `sdk` field). Keep `Dockerfile` in repo for local `docker build -t satquery-ai:local .`.

**README frontmatter for Gradio Space** (if Space clones back, add to Space’s `README.md` top; keep GitHub `README.md` as-is or add same block — GitHub ignores YAML):

```yaml
---
title: SatQuery AI
emoji: 🛰️
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 5.16.1  # or latest 6.x — Spaces pins, check HF new-space default
app_file: app.py
python_version: "3.12"
hardware: zero-a10g
startup_duration_timeout: 30m
short_description: Agentic VLM for satellite VQA, grounding and change
license: mit
pinned: false
---
```

`hardware: zero-a10g` in frontmatter is optional if you set via UI, but ensures correct flavor on clone.

## 3. How it works

* `app.py` at module scope can `import spaces` (provided by Gradio base image on `zero-a10g`/`CPU`, no-op locally). Real CUDA only inside `@spaces.GPU(duration=30)` handler (`spaces` emulates CUDA outside, forks worker after).
* `predict(query, input_mode, image_a, image_b)` `app.py: @spaces.GPU(duration=30)` coerces `gr.Image(type="pil")` → `(filename, bytes)` or `PIL.Image` and calls `backend.controller.handle(query, images, input_mode)` directly (no HTTP, reuses `validate_inputs` + `classify_task` + `registry.predict` + `ExecutionTrace`). Returns `(answer, confidence, trace_json, evidence_md)` to `gr.Textbox/Number/JSON/Markdown`.
* Model: `AutoProcessor` + `Qwen2VLForConditionalGeneration` + `PeftModel.from_pretrained(base, ADAPTER_PATH)` loaded lazily on first `@spaces.GPU` call (ZeroGPU emulation), cached per container. `SATQUERY_FORCE_CPU=0` keeps `device_map="auto"` + `BitsAndBytesConfig NF4 4-bit` `backend/models/vqa.py:121` for ~1.1GB VRAM on `large`.

## 4. Verify

* **Logs:** `Spaces → Logs` → `Max retries exceeded` gone, `Running on: http://0.0.0.0:7860` + `Gradio startup health: {"vqa (real)": true}`. `@spaces.GPU` scan must find handler or `RuntimeError: No @spaces.GPU function detected`.
* **UI:** `https://<you>-satquery-ai.hf.space/` → 3 columns (Imagery Input `single/optical-sar/bi-temporal` `Radio` → second `Image` visibility `app.py: _toggle_second`, query `Textbox` + `Examples`, `Execute Analysis` → `Answer`/`Confidence`/`Evidence` + `ExecutionTrace JSON` (`is_real true`) + `Health JSON`). Second image required for `optical-sar`/`bi-temporal` (`controller.validate_inputs:67` `2` else `422`).
* **Health:** `Refresh health` button → `registry.health()` `vqa (real) is_real true`.
* **Cold pull:** `~4GB` base + `30-80MB` adapter to `/tmp/hf_cache` on first `@spaces.GPU` call, `30-90s` on `large` (faster than CPU basic due to Blackwell). Warm `~1-2s` vs `CPU 30-90s`.

## 5. Local Graduo test (no ZeroGPU hardware, decorator is no-op)

```bash
pip install -r requirements.txt  # includes gradio>=4.0, torchvision>=0.18
python app.py  # → http://localhost:7860 (uses PORT or 7860)
# In another terminal:
curl http://localhost:7860/health  # not needed — Gradio has no /health, check UI
```

`spaces` stub `app.py: @spaces.GPU` falls back to plain function locally (`_SpacesStub`).

## 6. Local Docker still works (CPU-only, i5/16GB)

```bash
docker build -t satquery-ai:local .
docker run --rm -p 7860:7860 -e SATQUERY_FORCE_CPU=1 satquery-ai:local
curl http://localhost:7860/health | jq  # Docker path, not Gradio
make pitch-demo  # bare uvicorn + vite dev, also CPU-only
```

`Dockerfile` untouched; `SATQUERY_FORCE_CPU=1` hard `Dockerfile:22` vs `0` on Space.

## 7. Troubleshooting

* **`✗ DEGRADED: Adapter load failed (401)`** → set `HF_TOKEN` in Space Variables.
* **`RuntimeError: No @spaces.GPU function detected`** → `spaces.GPU` must decorate the `btn.click(fn=predict)` handler itself, not a helper.
* **`ZeroGPU quota exceeded (60s requested vs 30s left)`** → lower `duration` to `30` (already `app.py: @spaces.GPU(duration=30)`) — visitor quota `5 min/day free, 2 min anon` (`docs/hf_spaces.md` ZeroGPU docs).
* **`CUDA error: no kernel image is a suitable replacement`** → you added `flash-attn3` (needs `sm_90a/sm_100a`, Blackwell `sm_120` lacks `TMEM`) — don’t add.
* **`Qwen2VLVideoProcessor requires Torchvision`** → now in `requirements.txt: torchvision>=0.18`, Docker `pip install` includes it.
* **`ModuleNotFoundError: spaces`** locally → stub handles it; on Space, `spaces` is provided — **do not** `pip install spaces` mismatch (don’t pin `spaces`).
