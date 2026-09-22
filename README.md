---
title: SatQuery AI
emoji: 🛰️
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 5.16.1
app_file: app.py
pinned: false
python_version: "3.12"
hardware: zero-a10g
startup_duration_timeout: 30m
short_description: Agentic VLM for satellite VQA, grounding and change
license: mit
---

<div align="center">

<img src="assets/banner3.png" alt="SatQuery AI" width="1000" />

[![OpenEnv](https://img.shields.io/badge/SIH-2026-blue?style=flat-square)](https://www.sih.gov.in/)
[![HuggingFace](https://img.shields.io/badge/🤗-HuggingFace%20Spaces-yellow?style=flat-square)](https://huggingface.co/spaces/imadityasarkar/satquery-ai)
[![VLM](https://img.shields.io/badge/VLM-Qwen2--VL--2B-purple?style=flat-square)](#tech-stack)
[![Trace](https://img.shields.io/badge/ExecutionTrace-Graded-red?style=flat-square)](#how-it-works--pipeline-flowchart)

Smart India Hackathon 2026 — Agentic Vision-Language Intelligence for Earth Observation

[🚀 Live Space](https://huggingface.co/spaces/imadityasarkar/satquery-ai) · [📓 Training Notebook](https://colab.research.google.com/github/awdtyo/SatQueryAI-SIH26/blob/main/training/notebooks/satquery_ai_qlora_finetune.ipynb) · [📝 Execution Trace](docs/execution_trace_schema.md)

</div>

---

## The Problem

Every day, Sentinel-2, Landsat and SAR satellites capture terabytes of Earth observation imagery — but turning pixels into answers still requires a remote-sensing analyst, a GIS stack, and hours of manual inspection.

A disaster-response team wants to ask: *“Where was forest cleared between these two dates?”* A farmer asks: *“Is there water stress in this field?”* Today that means:

* Exporting GeoTIFFs, checking band counts, reprojecting, opening QGIS
* Writing bespoke classifiers for each task (land cover / change / SAR fusion)
* Waiting for an expert to interpret and write a report

We built an agentic assistant that answers these questions **in natural language, from the imagery itself — with evidence and a full execution trace**.

---

## What We Built

An **agentic vision-language system** where a controller validates the imagery, classifies the task, routes to the right specialist via a registry, and returns an evidence-grounded answer. No task-specific code per query — just `query + images → { answer, confidence, evidence, execution_trace, chart }`.

### The Agent's Task

At each turn the agent receives a query and 1–2 satellite images (single / optical-SAR / bi-temporal) and must return a grounded answer:

```
INTELLIGENCE QUERY — single / 10m Sentinel-2

Query: "Describe the land cover in this satellite image."
Input: s2_chip.png  (224×224, RGB, 10m)

SatQuery returns:
```

```json
{
  "answer": "- **Broad-leaved forest** dominates the northeast quadrant (~45%) with dense canopy.\n- **Arable land** forms geometric parcels in the southwest, consistent with 10m Sentinel-2.\n- **Urban fabric** appears as gray mosaic in the northwest quadrant.\n- **Water body** is visible in the south with low-uncertainty shoreline.",
  "confidence": 0.84,
  "evidence": [{ "type": "image_ref", "description": "Input image for task=vqa" }],
  "chart": [{ "label": "vegetation", "value": 45.2 }, { "label": "urban", "value": 28.1 }],
  "chart_type": "distribution",
  "execution_trace": {
    "task": "vqa",
    "models_used": [{ "name": "imadityasarkar/satquery-phase2-vrsbench", "role": "vqa", "is_real": true, "latency_ms": 842 }]
  }
}
```

---

## Problem Constraints

Three constraints force a real agentic design — not a single VQA call:

| Constraint | Description | Why It Matters |
|---|---|---|
| **Input Validation** | Every image is checked for `{.tif,.tiff,.png,.jpg,.jpeg}`, `single→1` / `optical-sar→2` / `bi-temporal→2`, and GeoTIFF band count via `rasterio` + PIL fallback (`backend/controller/__init__.py:49`) | `422` on mismatch — judged as mandatory, not optional |
| **Registry Routing** | Controller never imports `backend.models.*` — all specialists go via `backend/registry.py:91` `predict(images,query,task)` | New adapters plug in via env without code |
| **Graded Trace** | Every response carries `ExecutionTrace{task, models_used[{is_real,is_stub,latency_ms}], confidence, evidence_refs, total_latency_ms}` (`backend/schemas/__init__.py:39`) | Evaluated as first-class output, not a debug log |

A naive VLM that skips validation or trace **fails the SIH criteria. Our controller doesn't.**

---

## Vision-Language: Qwen2-VL + QLoRA

We use **Qwen2-VL-2B-Instruct** — the largest VLM to fine tune on **Colab T4 (15GB, sm_75, fp16)** — adapted with **QLoRA (4-bit NF4 + LoRA r=16 α=32, ~14M trainable 0.7%)**:

```
Qwen2-VL-2B (frozen, NF4) + LoRA adapters → PeftModel.from_pretrained(base, ADAPTER_PATH)
Processor: AutoProcessor(min 256*28*28 max 512*28*28) → apply_chat_template → prompt-masked labels (-100)
```

No full fine-tuning, no 7B+ model — same math as flown adapters on the Hub. `2B` is a feature, not a limit.

### Specialist Roster 

| Specialist | Module | Adapter / Weight | Status | Task keys |
|---|---|---|---|---|
| **VQA / Captioning** | `backend/models/vqa.py:82` | `imadityasarkar/satquery-phase2-vrsbench` (Qwen2-VL-2B + QLoRA, continues stage-1) | **REAL** | `vqa`, `captioning`, `visual_question_answering` |
| **Counting** | `backend/models/yolo.py:75` | `yolov8n.pt` (Ultralytics, 6 MB, COCO-80) | **REAL** | `count`, `counting` |
| **Change Detection** | `backend/models/change.py:82` | `imadityasarkar/cdvqa_change` (bi-temporal QLoRA, stage-3) | **REAL** | `change_detection`, `change`, `cdvqa` |
| **Optical-SAR Fusion** | `backend/models/fusion.py:80` | `imadityasarkar/satquery-phase2-vrsbench` (fusion-aware) | **REAL** | `optical_sar_fusion`, `fusion`, `sar` |
| **Grounding** | `backend/models/grounding.py:14` | — | **STUB** (planned stage 2/3) | `grounding`, `visual_grounding` |

All five are registered in `backend/registry.py:31` and health-reported at `GET /health`. `is_real` is derived lazily per module (`get_model_info()`).

---

## Confidence & Evidence

Question-aware output — **bullets replace paragraphs**, charts are **measured from pixels, not hallucinated**:

| Evidence | Type | When | Chart |
|---|---|---|---|
| **Image ref** | `image_ref` | Every VQA answer — `task=vqa` | `distribution` (vegetation/water/urban/bare/other %) |
| **Bounding box** | `bounding_box` | Counting — one per YOLO detection (`xyxy`) | `count` (per-class counts, Bar/Pie) |
| **Change overlay** | `overlay` | `bi-temporal` change — `T1→T2` delta | `change` (Δ % per label, negative = loss) |
| **Heatmap** | `heatmap` | Fusion — SAR backscatter complement | `distribution` from optical |
| **Saliency** | `saliency` | Future | — |

**Chart** is computed in `backend/utils/chart.py:21` `compute_chart()` via RGB thresholds on a 256×256 downsample (vegetation/water/urban/bare/other → 100%). For `bi-temporal`, two charts are differenced (`T2−T1`) and filtered to `|Δ|≥1%`. VQA/Fusion use the optical chart; YOLO uses per-class counts.

**Confidence:** `log_softmax` per generated token inside `model.generate(output_scores=True)` → `exp(mean logprob) → 0.35+0.6*prob` (apology-capped to `0.35`, `0.72→0.95` fallback for mocks). For YOLO, mean box confidence. `execution_trace.confidence` mirrors top-level `confidence` — both `0..1`.

**Bullets:** 3–6 markdown bullets (`- **Class** ...`), enforced by `SYSTEM_PROMPT` (`backend/config.py:85`) and post-parsed in each specialist. Charts are *not* emitted as JSON by the LLM.

---

## Tech Stack

| Layer | Technologies | Notes |
|-------|--------------|-------|
| **Backend** | Python 3.12, **FastAPI**, **Uvicorn**, **Pydantic v2**, `python-multipart` | `backend/main.py:28` lifespan, CORS, `/api` + root mounts, serves `frontend/dist` |
| **VLM** | **PyTorch ≥2.0**, **Transformers ≥4.46** (`Qwen2VLForConditionalGeneration`), **PEFT ≥0.14** (QLoRA), **BitsAndBytes ≥0.45.5** (NF4), **qwen-vl-utils**, **Accelerate** | QLoRA only; 2–3B VLM to fit T4 15GB |
| **Adapters** | `Qwen/Qwen2-VL-2B-Instruct` + LoRA `r=16 α=32` (stage-1 → stage-2 → stage-3 chain) | Via `backend/config.py:18` `BASE_MODEL` / `ADAPTER_PATH` / `CHANGE_ADAPTER_PATH` / `FUSION_ADAPTER_PATH` |
| **Counting** | **Ultralytics ≥8.2** (`yolov8n.pt`), **OpenCV ≥4.8** | `backend/models/yolo.py:1`, configurable via `SATQUERY_YOLO_*` |
| **Charts / Vision** | **Pillow ≥10**, `numpy<2`, `torchvision ≥0.18`, `matplotlib ≥3.5`, `rasterio` (optional) | `Pillow` for `RGB` conversion, `rasterio` for `.tif` bands, `matplotlib` for Gradio plots |
| **Frontend** | **React 18**, **Vite 6**, **Tailwind 3**, **TypeScript 5**, **Recharts 2**, `react-markdown` | 3-zone console, Vite proxy `/api → 8000`, poll `/api/health` every 15s |
| **Spaces** | **Gradio 5.16.1** + `spaces` ZeroGPU (`app.py`) | `@spaces.GPU(duration=60)` on `zero-a10g`, `SATQUERY_FORCE_CPU=0` |
| **Retrieval** | **pystac-client ≥0.8**, **shapely ≥2.0**, **requests ≥2.28**, `CDSE STAC v1` | `sentinel-2-l2a`, AOI coverage, heuristic ranking `backend/satellite/ranking.py:1` |
| **Training env** | **Google Colab T4** (15GB, sm_75, fp16), fallback Kaggle T4×2 | Free-tier safe: Drive checkpoints, subset caching |
| **Testing** | `pytest`, `httpx`, `ruff`, `mypy` | `tests/test_controller_api.py`, `tests/test_registry.py`, `tests/test_vqa_wrapper.py`, `tests/test_satellite_retrieval.py` |

---

## How It Works — Detailed Pipeline Flowchart

```mermaid
flowchart TD
    A[User Input<br/>NL Query + AOI Polygon or 1-2 Images<br/>Find Sentinel-2 2026-06-01 2026-06-30 &lt;20% cloud<br/>or Describe land cover] --> B[Frontend<br/>React 3-zone + Gradio Blocks<br/>ImageryViewer + SatelliteSearchPanel<br/>frontend/src/App.tsx / app.py]

    B --> C[Controller<br/>validate_inputs rasterio PIL<br/>classify_task + parse_retrieval_params<br/>backend/controller/__init__.py:282]
    C --> D{Task Routing}

    D -->|Find Sentinel-2 / imagery &lt;X% cloud / best image| R1[Satellite Retrieval Agent<br/>backend/satellite/agent.py<br/>RetrievalRequest validation<br/>sensor product geometry dates cloud]
    R1 --> R2{Cache TTL 300s<br/>backend/satellite/cache.py}
    R2 -->|hit| R4[Ranked Scenes]
    R2 -->|miss| R3[CDSE STAC Client<br/>pystac-client → HTTP fallback<br/>sentinel-2-l2a intersects AOI<br/>datetime interval eo:cloud_cover<br/>backend/satellite/client.py]
    R3 --> P[Parse STAC → SatelliteScene<br/>id datetime platform cloud geometry bbox<br/>assets B02 B03 B04 B08 B11 B12 + thumbnail]
    P --> C1[AOI Coverage shapely<br/>intersection/AOI*100<br/>backend/satellite/coverage.py:18]
    C1 --> Rk[Ranking heuristic<br/>0.45coverage 0.35cloud 0.15temporal 0.05sensor<br/>backend/satellite/ranking.py:1]
    Rk --> R4
    R4 --> Sel[Best Scene + Ranked List<br/>selection_score coverage cloud<br/>API POST /api/satellite/search<br/>backend/api/satellite.py]
    Sel --> Pic[Frontend Select for Analysis<br/>stores SatelliteScene<br/>assets hrefs for NDVI etc<br/>ready for VQA/change/count]

    D -->|single describe/caption| V1[VQA / Captioning<br/>Qwen2-VL-2B phase2-vrsbench]
    D -->|single how many count| V2[Counting YOLOv8n<br/>yolov8n.pt]
    D -->|single where locate| V3[Grounding<br/>maps to vqa]
    D -->|bi-temporal| CH[Change Detection<br/>Qwen2-VL-2B cdvqa_change<br/>T1 T2 pair]
    D -->|optical-sar| FU[Fusion<br/>phase2-vrsbench optical+SAR]

    Pic --> REG
    V1 --> REG
    V2 --> REG
    V3 --> REG
    CH --> REG
    FU --> REG

    REG[Registry<br/>backend/registry.py<br/>predict images query task<br/>only importer of backend.models.*] --> EV[Evidence + Structured<br/>bullets 3-6 + chart measured<br/>backend/utils/chart.py / yolo boxes<br/>type image_ref bounding_box overlay]
    EV --> TR[ExecutionTrace Graded<br/>task models_used is_real is_stub latency_ms<br/>confidence evidence_refs total_latency<br/>backend/schemas/__init__.py]
    TR --> UI[Display<br/>ResultsPanel bullets ChartPanel Bar Pie<br/>ImageryViewer + Confidence + Trace<br/>React + Gradio queue]

    style R1 fill:#0ea5e9,stroke:#0284c7,color:#fff
    style Rk fill:#22c55e,stroke:#16a34a,color:#fff
    style REG fill:#1e293b,stroke:#334155,color:#e2e8f0
    style TR fill:#f59e0b,stroke:#d97706,color:#fff
```

**ExecutionTrace is graded** — every response includes `task`, `models_used[{name, role, parameters, latency_ms, is_real, is_stub}]`, `evidence_refs`, `total_latency_ms` (`frontend/src/types/api.ts:23` ↔ `backend/schemas/__init__.py:39`). See `docs/execution_trace_schema.md`.

Task routing (`backend/controller/__init__.py:282`):

* `Find Sentinel-2 …` / `satellite imagery <X% cloud` / `best satellite image between …` → `satellite_retrieval` (structured params via `parse_retrieval_params`)
* `bi-temporal` → `change_detection` always
* `optical-sar` → `optical_sar_fusion` always
* `single` + `how many/count/number of` → `count` (YOLO)
* `single` + `where/locate/bounding/ground` → `grounding` (stub, maps to vqa)
* default → `vqa`

## Live Satellite Data Retrieval (CDSE STAC)

**Purpose:** Turn natural-language AOI + date queries into live Sentinel-2 L2A scenes via Copernicus Data Space Ecosystem `https://stac.dataspace.copernicus.eu/v1`, rank candidates, pipe best scene toward existing VQA/change/counting (no fake data).

### Flow
```
User: “Find Sentinel-2 imagery for this AOI from 2026-06-01 to 2026-06-30 with <20% cloud”
   ↓  planner parses structured params (never raw STAC URLs)
RetrievalRequest{sensor, product, geometry, start_date, end_date, max_cloud_cover, max_results, required_bands}
   ↓  Satellite Retrieval Agent (backend/satellite/agent.py)
CDSE STAC search (pystac-client → HTTP fallback) collections=["sentinel-2-l2a"] intersects=AOI datetime=interval query={"eo:cloud_cover":{"lte":20}}
   ↓  SatelliteScene (id, datetime, platform, cloud_cover, geometry, bbox, assets, thumbnail)
   ↓  AOI coverage = intersection(scene,AOI)/AOI*100 (shapely, backend/satellite/coverage.py:18)
   ↓  ranking → selection_score (heuristic, not scientific QA)
   ↓  best scene + ranked list → API + ExecutionTrace
   ↓  frontend “Select for Analysis” → existing agents (future: retrieve_scene_assets)
```

### Live Retrieval — Simplified Flowchart

```mermaid
flowchart TD
    A[AOI Polygon + Dates + Cloud<br/>Frontend + NL parse] --> B[Validate RetrievalRequest<br/>422 if bad]
    B --> C[Agent + Cache 300s]
    C --> D[CDSE STAC sentinel-2-l2a<br/>pystac → HTTP fallback]
    D --> E[Parse → SatelliteScene<br/>assets + thumbnail]
    E --> F[Coverage & Ranking<br/>shapely + heuristic score]
    F --> G[Best + Ranked List]
    G --> H[API + Trace]
    H --> I[Frontend Select for Analysis]
    I --> J[Existing VQA / Change / Count]

    style C fill:#0ea5e9,stroke:#0284c7,color:#fff
    style F fill:#22c55e,stroke:#16a34a,color:#fff
    style J fill:#a78bfa,stroke:#7c3aed,color:#fff
```

> **Simplified view** — collapses cache, STAC fallback, coverage/ranking and trace into single nodes for readability. Full technical path is detailed below.

<details>
<summary><b>Technical details (click to expand) — all steps preserved</b></summary>

| Step | Module | Details |
|---|---|---|
| **1. NL → structured params** | `backend/controller/__init__.py:282` `parse_retrieval_params` | Extracts `sensor/product` (sentinel-2 l2a/l1c), `start_date`/`end_date` (ISO or “June 2026” → 01-last), `max_cloud_cover` (`less than 10% cloud`), `required_bands` via `INDEX_REQUIRED_BANDS` (NDVI→B04,B08). LLM never builds STAC URLs. |
| **2. Validation** | `backend/satellite/models.py` `RetrievalRequest` | Checks `start<=end`, `0<=cloud<=100`, GeoJSON type (Polygon/MultiPolygon, unwraps Feature/Collection), `sensor/product → collection` via `COLLECTION_MAP` (`sentinel-2-l2a`), shapely `is_valid`/`is_empty`. 422 on fail, no traceback. |
| **3. Agent + Cache** | `backend/satellite/agent.py` `search_satellite_data` + `backend/satellite/cache.py` | In-memory TTL 300s (`SATQUERY_STAC_CACHE_TTL`), max 128 (`SATQUERY_STAC_CACHE_MAX`), SHA256 key of collection/geometry/datetime/cloud/limit. Errors not cached. |
| **4. CDSE STAC** | `backend/satellite/client.py` | Tries `pystac_client.Client.open(CDSE_STAC_URL).search(collections,intersects,datetime,query eo:cloud_cover lte, max_items)` → `items()` → `to_dict()`; on exception falls back to `requests.post(/v1/search, {collections,intersects,datetime,query,limit}, timeout 20)`. Collections `["sentinel-2-l2a"]`. |
| **5. Error handling** | `backend/api/satellite.py` | Network/5xx/timeout → `502 Satellite data provider temporarily unavailable` (logged server-side); 0 results → `200 count 0` with message *No Sentinel-2 scenes found…*; malformed items skipped, not crashed. |
| **6. Parse** | `backend/satellite/client.py:_parse_stac_item` | Maps STAC Item → `SatelliteScene` (`id`, `collection`, `datetime` RFC3339, `platform`, `processing_level`, `cloud_cover`, `geometry`, `bbox`, `assets` href map, `thumbnail` from `thumbnail/preview/visual`, `metadata`). |
| **7. Asset discovery** | same | Collects **all** `assets` dynamically (not assumed B02-B12), surfaces `B02,B03,B04,B08,B11,B12,visual` when present for future `retrieve_scene_assets(scene_id, requested_assets)`. |
| **8. Coverage** | `backend/satellite/coverage.py:18` | `coverage = intersection(scene, AOI)/AOI*100` via `shapely`, `make_valid` for self-intersections, unwraps FeatureCollection, planar EPSG:4326. Returns 0-100, fallback 0 if no geometry. |
| **9. Ranking** | `backend/satellite/ranking.py:1` | `coverage_norm=coverage/100`, `cloud_score=1-cloud/100`, `temporal_score=0.5+0.5*((dt-start)/(end-start))` (recent preferred, 0.5 if dt missing), `sensor_score=1.0 L2A /0.9 L1C /0.8 other` → `selection_score=0.45*cov+0.35*cloud+0.15*temp+0.05*sensor` (0..1, 4dp), sorted `score desc, coverage desc, cloud asc, datetime desc`. *Heuristic, not scientific QA.* |
| **10. Best + store** | `backend/satellite/agent.py` | `best = max(selection_score)`; ranked list cached (if not from cache). |
| **11. Trace** | `backend/satellite/models.py` `RetrievalTrace` + controller | `{agent:satellite_retrieval, operation:search, provider:CDSE, collection:sentinel-2-l2a, results_found, results_after_filtering, selected_scene, latency_ms, parameters}` → merged into `ExecutionTrace.models_used` (`backend/controller/__init__.py`). |
| **12. API** | `backend/api/satellite.py` `POST /api/satellite/search` | Returns `{count, scenes[], best_scene, provider, collection, query, trace, execution_trace}`; `GET /api/satellite/health` (`status, stac_url, supported_sensors`), `POST /api/satellite/assets` stub. |
| **13. Frontend** | `frontend/src/components/SatelliteSearchPanel.tsx` + `app.py` Gradio | AOI presets Bengaluru/Delhi/Small, GeoJSON textarea, dates, sliders cloud/results, NDVI/NDWI/NDBI selector → ranked cards (thumbnail, date, platform, cloud, coverage, score, assets) → **Select for Analysis** → banner `Selected Scene` ready for VQA/change/count. |
| **14. Graded trace UI** | `frontend/src/App.tsx` / `app.py` | Retrieval trace panel shows `results_found`, `selected_scene`, `latency_ms`; existing `ExecutionTrace` remains graded (`is_real`, `latency_ms`). |

</details>

### Supported filters (MVP: Sentinel-2 L2A)
* **Sensor/Product:** `sentinel-2` + `l2a` → `sentinel-2-l2a` (also `l1c`; S1/Landsat extensible via `COLLECTION_MAP` `backend/satellite/models.py:14`)
* **Spatial:** GeoJSON `Polygon`/`MultiPolygon` EPSG:4326 validated via shapely; Feature/FeatureCollection unwrapped
* **Temporal:** `start_date`/`end_date` YYYY-MM-DD (`start<=end`) → `datetime` interval
* **Cloud:** `max_cloud_cover` 0–100 → `eo:cloud_cover lte`
* **Limit:** `max_results` 1–100
* **Future band-aware:** `required_analysis=NDVI|NDWI|NDBI` auto-maps to `required_bands` (`NDVI→B04,B08` etc.)

### AOI coverage & ranking
`coverage = intersection(scene, AOI)/AOI*100` (planar EPSG:4326, `make_valid` for self-intersections, `backend/satellite/coverage.py:18`).
**Score (heuristic, backend/satellite/ranking.py:1):**
```
coverage_norm=coverage/100; cloud_score=1-cloud/100
temporal_score=0.5+0.5*((datetime-start)/(end-start))  # recent preferred, 0.5 fallback
sensor_score=1.0(l2a)/0.9(l1c)/0.8(other)
selection_score=0.45*coverage_norm+0.35*cloud_score+0.15*temporal_score+0.05*sensor_score  # 0..1
Sorted by score desc, coverage desc, cloud asc, datetime desc
```

### API
| Method | Path | Body | Response |
|---|---|---|---|
| `POST` | `/api/satellite/search` | `{geometry, start_date, end_date, max_cloud_cover?, sensor?, product?, max_results?, required_bands?, required_analysis?}` | `{count, scenes[{id,datetime,platform,collection,cloud_cover,coverage,selection_score,thumbnail,assets,bbox}], best_scene, provider="CDSE", collection, query, trace, execution_trace}` |
| `GET` | `/api/satellite/health` | — | `{status, provider, stac_url, collection, supported_sensors, agent}` |
| `POST` | `/api/satellite/assets` | `{scene_id, requested_assets:[B02,B03,B04,B08,…]}` | stub — returns hrefs note, no raster download in MVP |

Validation: 422 on bad dates/cloud/geometry/sensor; 502 on provider timeout; 200+count 0 on empty (“No Sentinel-2 scenes found…”); never traceback. Caching: in-memory TTL 300s (`SATQUERY_STAC_CACHE_TTL`, max 128 `backend/satellite/cache.py:4`), errors not cached.

### Natural-language examples
* `Find Sentinel-2 imagery for this region from June 2026.`
* `Find a Sentinel-2 image with less than 10% cloud cover.`
* `Get the best satellite image for this AOI between June 1 and June 30.`
* `Find satellite imagery of this area suitable for vegetation analysis.` → all route to `satellite_retrieval` and produce structured `{intent,sensor,product,start_date,end_date,max_cloud_cover}`

### Frontend
`SatelliteSearchPanel` (`frontend/src/components/SatelliteSearchPanel.tsx:1`): AOI presets (Bengaluru/Delhi), GeoJSON textarea, dates, cloud/results, NDVI/NDWI/NDBI selector, **Search Sentinel-2 L2A** → ranked cards (thumbnail, date, platform, cloud, coverage, score, assets), **Select for Analysis**. Selected scene banner in right `Selected Scene` panel → ready for VQA/change/count via `scene.assets` (future `retrieve_scene_assets`).

### Execution trace
```json
{"agent":"satellite_retrieval","operation":"search","provider":"CDSE","collection":"sentinel-2-l2a","results_found":12,"results_after_filtering":7,"selected_scene":"S2A_...","latency_ms":842}
```
Shown in `Retrieval Trace` panel and API `execution_trace`.

### Current limitations & next step
Only Sentinel-2 L2A live; S1/Landsat schema-ready but not wired; no raster download (hrefs only); coverage planar not geodesic; AOI must be EPSG:4326; cache per-process. **Next:** actual `retrieve_scene_assets` download + AOI chip preprocessing → feed cropped bands into VQA.

### Dependencies added
`pystac-client>=0.8`, `shapely>=2.0`, `requests>=2.28` (`requirements.txt:44`)

---

## Training

### Method: QLoRA via PEFT

For each stage, QLoRA adapts the frozen 2B base with 4-bit NF4 + LoRA `r16 α32 dropout 0.05 target q/k/v/o+gate/up/down` (~14M). No labelled pipelines — just `image + question → answer` with `vision-language` cross-attention. `batch 1 × accum 8` + `paged_adamw_8bit + grad_checkpointing` keeps T4 under 15GB.

### Curriculum: Three Stages, One Base

| Stage | Dataset | Adapter | Purpose | Config |
|---|---|---|---|---|
| **1** | BigEarthNet Sentinel-2 `800` (val 5%) | `imadityasarkar/satquery-qwen2vl-stage1-bigearthnet` | Vision-language adaptation — `Describe land cover` | `training/configs/bigearthnet_stage1.json` |
| **2** | VRSBench / RSVQA `1200` (val 5%) | `imadityasarkar/satquery-phase2-vrsbench` | VQA + grounding — `Where is…` / counting | `training/configs/vrsbench_rsvqa_stage2.json` |
| **3** | CDVQA `1000` bi-temporal (paired `T1,T2`) | `imadityasarkar/cdvqa_change` | Change — `What changed between dates?` | `training/configs/cdvqa_stage3.json` |

Each stage reuses the previous adapter (`adapter_to_continue`), its own `CHECKPOINT_DIR` on Drive, and `save_steps 25` auto-resume — safe to `Run all` again after Colab disconnect. Notebooks live in `training/notebooks/`:

* `satquery_ai_qlora_finetune.ipynb` — stage 1 (BigEarthNet)
* `vrsbench_rsvqa_sft.ipynb` — stage 2 (VRSBench/RSVQA SFT from stage-1)
* `cdvqa_change_sft.ipynb` — stage 3 (CDVQA paired loader from stage-2, `384*28*28` max pixels for 2 images)

---

## Results

### Stage-1 Adapter

- **Hub:** `imadityasarkar/satquery-qwen2vl-stage1-bigearthnet` (30–80 MB LoRA, base 2B frozen)
- **Data:** `image → "Describe the land cover"` → `answer="This Sentinel-2 image shows predominantly {forest|urban fabric|arable land|...}"`
- **Training:** 1 epoch, 800 train / 40 val, `save_steps 25` → `checkpoint-25,50,...` on Drive, resume-safe
- **Performance:** `~842ms` T4 fp16 (`~70s` on i5 CPU `FORCE_CPU=1`), `30–80MB` adapter, `is_real` via `GET /health`

### Stage-2 Adapter (Live, default)

- **Hub:** `imadityasarkar/satquery-phase2-vrsbench` — **current default** via `backend/config.py:24` `ADAPTER_PATH`
- **Data:** VRSBench/RSVQA `1200` (val 5%) `image + question → answer` + counting/grounding
- **Training:** 1 epoch, 1200 train / 60 val, `lr 1e-4` cosine, `save_steps 25` → Drive `stage2_vrsbench_sft/checkpoint-*`, resume-safe; continues from stage-1 (`vrsbench_rsvqa_stage2.json:3`)
- **Inference:** VQA + fusion real via same adapter; YOLO handles counting; `is_real true` for `single` VQA/fusion and `count`

### Stage-3 Adapter (Live, bi-temporal)

- **Hub:** `imadityasarkar/cdvqa_change` (public) — via `backend/config.py:114` `CHANGE_ADAPTER_PATH`, continues stage-2
- **Data:** CDVQA `1000` paired `T1+T2` (val 5%), change-specific system prompt, `image_max_pixels 301056` for two images
- **Training:** 1 epoch, paired tokenization `processor(images=[T1,T2])`, `save_steps 25` → `stage3_cdvqa_change/checkpoint-*`
- **Inference:** `bi-temporal` → `change_detection` is **real** (was stub until `b0d1b4a`); chart is `delta T2−T1`

### Counting (Live)

- **Weight:** `yolov8n.pt` (Ultralytics, auto-downloaded, 6 MB, COCO-80). Override via `SATQUERY_YOLO_WEIGHTS` for DOTA `yolov8n-obb.pt`
- **Evidence:** `bounding_box` per detection with `[[x1,y1],[x2,y2]]`, chart = per-class counts (not %)
- **Config:** `SATQUERY_YOLO_CONF=0.25` / `SATQUERY_YOLO_IOU=0.45` / `SATQUERY_YOLO_CLASSES` filter

### Answer: Before vs After

**Before (generic VLM, no RS adaptation):**
```json
{"answer": "This is a satellite image. There are some green areas.", "confidence": 0.31}
→ No land-cover taxonomy, no percentages, no grounding.
```

**After (SatQuery Stage-2, QLoRA on BigEarthNet+VRSBench):**
```json
{"answer": "- **Broad-leaved forest** dominates the northeast quadrant (~45%) with dense canopy.\n- **Arable land** forms geometric parcels in the southwest.\n- **Urban fabric** appears as gray mosaic in the northwest.\n- **Water body** visible in the south with low uncertainty.", "confidence": 0.84}
→ Taxonomy-aware, bulleted, measured chart, evidence_ref image_ref, ExecutionTrace is_real true.
```

The model didn't learn this from a larger LLM — it learned it from **BigEarthNet + VRSBench reward (vision-language) alone.**

---

## Real-World Grounding

| Our Stack | Real-World Counterpart |
|---|---|
| QLoRA on Qwen2-VL-2B (14 M tunable) | NRSC/Bhuvan analysts fine-tuning on Sentinel-2 |
| `validate_inputs` band count via `rasterio` | GDAL GeoTIFF QA in ISRO pipelines |
| `optical_sar_fusion` (phase2-vrsbench) | ISRO RISAT + Sentinel-2 flood mapping |
| `change_detection` (`cdvqa_change` bi-temporal) | Deforestation / urban expansion monitoring |
| YOLO counting | Object census (vehicles, ships, buildings) |
| `ExecutionTrace` graded | Audit trail for disaster-response decisions |

---

## Quickstart

### Run Locally (i5 / 16GB / No GPU)

```bash
git clone https://github.com/awdtyo/SatQueryAI-SIH26 && cd SatQueryAI-SIH26/mvp
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt --index-url https://download.pytorch.org/whl/cpu
cd frontend && npm install && npm run dev  # http://localhost:5173
# in another terminal:
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
# one-command (backend 8000 + frontend 5173 + health wait):
make pitch-demo
# without browser:
make pitch-demo-no-browser
```

Test:

```bash
curl -X POST http://localhost:8000/api/query \
  -F query="Describe the land cover in this satellite image." \
  -F input_mode=single -F images=@s2_chip.png | jq
curl http://localhost:8000/health | jq
# alternative file fields (also accepted):
curl -X POST http://localhost:8000/api/query \
  -F query="How many buildings?" -F input_mode=single -F images=@s2_chip.png | jq
```

### Run a Complete Episode (Python)

```python
import requests
BACKEND="http://localhost:8000"
with open("s2_chip.png","rb") as f:
    r=requests.post(f"{BACKEND}/api/query",
      data={"query":"Describe the land cover","input_mode":"single"},
      files=[("images",("s2_chip.png", f, "image/png"))])
print(r.json()["answer"])
print(r.json()["execution_trace"])
print(r.json()["chart"], r.json()["chart_type"])

# Bi-temporal change:
with open("t1.png","rb") as f1, open("t2.png","rb") as f2:
    r=requests.post(f"{BACKEND}/api/query",
      data={"query":"What changed between these two dates?","input_mode":"bi-temporal"},
      files=[("images",("t1.png",f1,"image/png")),("images",("t2.png",f2,"image/png"))])
print(r.json()["answer"])
```

### Run via HF Spaces (ZeroGPU)

Space: `https://huggingface.co/spaces/imadityasarkar/satquery-ai` — Gradio `zero-a10g` `app.py` with `@spaces.GPU(duration=60)` (`SATQUERY_FORCE_CPU=0` enables 4-bit on Blackwell, `~1s` vs `~70s` CPU). Frontend is `app.py` Blocks; local React console remains at `5173`.

### Run via Docker (CPU or auto-GPU)

```bash
docker build -t satquery-ai:local .
docker run -p 7860:7860 -e SATQUERY_FORCE_CPU=0 satquery-ai:local  # auto GPU if available
# CPU-only:
docker run -p 7860:7860 -e SATQUERY_FORCE_CPU=1 satquery-ai:local
open http://localhost:7860          # FastAPI serves frontend/dist at /
open http://localhost:7860/docs     # API docs
open http://localhost:7860/health   # health
```

`Dockerfile` is multi-stage: `node:20` builds `frontend/dist`, `python:3.12-slim` runs FastAPI (`PORT=7860`).

---

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` , `/api/health` | `HealthResponse` — `specialists` (`registry.health()`), `base_model`, `adapter_path`, `cuda_available`, `force_cpu`, `compute`, `device` |
| `POST` | `/query` , `/api/query` | Multipart: `query` (str), `input_mode` (`single`/`optical-sar`/`bi-temporal`), `images` (1–2 files, repeated field; also `image_0`/`image_1`) → `QueryResponse` |
| `POST` | `/api/satellite/search` | JSON: `geometry` (GeoJSON), `start_date`, `end_date`, `max_cloud_cover?`, `sensor?`, `product?`, `max_results?`, `required_bands?` → `SatelliteSearchResponse` ranked |
| `GET` | `/api/satellite/health` | — | CDSE provider health |
| `GET` | `/docs` | Swagger UI |
| `GET` | `/` | Serves `frontend/dist/index.html` when built (Docker/Spaces), else `{"message": ...}` |

`QueryResponse` shape (`backend/schemas/__init__.py:67` ↔ `frontend/src/types/api.ts:64`): `answer`, `confidence`, `execution_trace`, `evidence`, `structured{bullets,chart,chart_type}`, `chart`, `chart_type` (`distribution`/`count`/`change`).

---

## Training

### Colab Notebooks

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/awdtyo/SatQueryAI-SIH26/blob/main/training/notebooks/satquery_ai_qlora_finetune.ipynb)

Each notebook (stage-1 `satquery_ai_qlora_finetune.ipynb`, stage-2 `vrsbench_rsvqa_sft.ipynb`, stage-3 `cdvqa_change_sft.ipynb`) does:

1. Checks T4 `nvidia-smi` (sm_75, fp16)
2. Mounts Drive `SatQueryAI/checkpoints/{stage1_bigearthnet_qlora,stage2_vrsbench_sft,stage3_cdvqa_change}`
3. Installs `transformers peft accelerate bitsandbytes qwen-vl-utils` (no torch upgrade)
4. Loads `Qwen2-VL-2B` in 4-bit + `AutoProcessor(min 256*28*28 max 512*28*28)` (+ previous stage adapter via `PeftModel.from_pretrained` for stage 2/3)
5. Tokenizes `apply_chat_template` with `label -100` masking, runs `Trainer` `save_steps 25` (auto-resume latest `checkpoint-*`)
6. Pushes `final_adapter` to Hub (`imadityasarkar/satquery-qwen2vl-stage1-bigearthnet` / `imadityasarkar/satquery-phase2-vrsbench` / `imadityasarkar/cdvqa_change`)

Stage-3 is paired: `processor(text=[prompt], images=[T1,T2])` with change-specific system prompt.

```python
# Core QLoRA (simplified)
from transformers import Qwen2VLForConditionalGeneration, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, PeftModel
bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True)
base = Qwen2VLForConditionalGeneration.from_pretrained("Qwen/Qwen2-VL-2B-Instruct", quantization_config=bnb)
peft = get_peft_model(base, LoraConfig(r=16, lora_alpha=32, target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"]))
```

Per-dataset hyperparams live in `training/configs/*.json` (see table above).

---

## Demo

### Local React console (`http://localhost:5173`)

- **ImageryViewer** — `ImageryViewer` with `bbox` `overlay` `heatmap` + 3-zone layout (`frontend/src/App.tsx:103`)
- **Intelligence Result** — bullets (markdown) + `ChartPanel` Bar/Pie toggle (`frontend/src/components/ChartPanel.tsx:19`) — question-aware (`distribution`/`count`/`change`)
- **Execution Trace** — `REAL`/`STUB` badge, `is_real`/`is_stub`, `latency_ms`, `total_latency_ms` 6-step `Query Parsed → Result Compiled`
- **Confidence gauge** — `HIGH ≥0.75` green / `MEDIUM` amber / `LOW` red, 20-block bar
- **Evidence** — `image_ref` / `bounding_box [[x,y]...]` / `overlay` per task
- **Query Log** — last 20 queries, click to re-run

### HF Space (`https://huggingface.co/spaces/imadityasarkar/satquery-ai`)

Same `Blocks` in `app.py:367` with `Refresh health` (`@spaces.GPU` on demand, no quota at startup) and `chart_state` Bar/Pie toggle identical to React. First click cold-pulls ~4 GB (30–60 s), warm ~1.2 s.

---

## Project Structure

```
mvp/
├── app.py                          # Gradio + ZeroGPU (HF) — @spaces.GPU reuses backend/controller
├── backend/
│   ├── main.py                     # FastAPI, lifespan is_real health, serves frontend/dist
│   ├── config.py                   # BASE_MODEL / ADAPTER_PATH / CHANGE/FUSION/YOLO knobs from env
│   ├── registry.py                 # task → specialist (only importer of backend.models.*)
│   ├── controller/__init__.py      # validate_inputs, classify_task, handle → QueryResponse + ExecutionTrace
│   ├── models/
│   │   ├── vqa.py                  # REAL QLoRA (VQA/captioning)
│   │   ├── yolo.py                 # REAL YOLOv8 counting
│   │   ├── change.py               # REAL bi-temporal CDVQA
│   │   ├── fusion.py               # REAL optical-SAR fusion
│   │   └── grounding.py            # STUB (VRSBench grounding, stage 2/3)
│   ├── schemas/__init__.py         # ExecutionTrace graded contract (Pydantic)
│   ├── api/__init__.py             # /health + /query routes (thin, delegates to controller)
│   └── utils/chart.py              # heuristic chart (measured, not LLM)
├── frontend/
│   ├── src/
│   │   ├── App.tsx                 # 3-zone console + health poll + query log
│   │   ├── api/mockClient.ts       # real fetch client → /api/query + /api/health
│   │   ├── types/api.ts            # ExecutionTrace / QueryResponse (mirrors backend/schemas)
│   │   └── components/             # Header, ImageUploader, ImageryViewer, ResultsPanel, ChartPanel, ...
│   ├── vite.config.ts              # proxy /api → 8000
│   └── package.json                # React 18 + Vite 6
├── training/
│   ├── notebooks/                  # satquery_ai_qlora_finetune.ipynb + vrsbench_rsvqa_sft.ipynb + cdvqa_change_sft.ipynb
│   └── configs/                    # bigearthnet_stage1.json, vrsbench_rsvqa_stage2.json, cdvqa_stage3.json
├── data/loaders/                   # dataset-specific loaders (config-driven, never hardcoded paths)
├── tests/                          # test_controller_api.py, test_registry.py, test_vqa_wrapper.py
├── docs/
│   ├── execution_trace_schema.md   # graded contract (Pydantic ↔ TypeScript)
│   ├── hf_spaces.md                # Docker Spaces deploy
│   └── hf_spaces_gradio.md         # ZeroGPU Gradio deploy
├── scripts/pitch-demo.sh           # one-command demo (backend + frontend + health wait)
├── Dockerfile                      # HF Spaces Docker (multi-stage, PORT 7860)
├── Makefile                        # pitch-demo, backend, frontend, health, test, build
├── requirements.txt                # inference + gradio + torchvision + ultralytics
└── assets/banner3.png
```

---

## Setup & Running

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt  # torch CPU: add --index-url https://download.pytorch.org/whl/cpu
```

Environment — create `.env` (never commit, see `.gitignore:22`) — all keys read in `backend/config.py:18`:

```
# Model
SATQUERY_BASE_MODEL=Qwen/Qwen2-VL-2B-Instruct
SATQUERY_ADAPTER_PATH=imadityasarkar/satquery-phase2-vrsbench
SATQUERY_CHANGE_ADAPTER_PATH=imadityasarkar/cdvqa_change
SATQUERY_FUSION_ADAPTER_PATH=imadityasarkar/satquery-phase2-vrsbench
SATQUERY_CHANGE_BASE_MODEL=Qwen/Qwen2-VL-2B-Instruct
SATQUERY_FUSION_BASE_MODEL=Qwen/Qwen2-VL-2B-Instruct
HF_TOKEN=hf_...                          # if gated/private

# Device — auto GPU when available (default 0), 1 forces CPU-only (HF CPU basic, i5/16GB)
SATQUERY_FORCE_CPU=0

# Inference
SATQUERY_MAX_NEW_TOKENS=384              # 256 CPU, 384-512 ZeroGPU (detailed bullets)
SATQUERY_MIN_NEW_TOKENS=40
SATQUERY_TEMPERATURE=0.2
SATQUERY_TOP_P=0.9
SATQUERY_REPETITION_PENALTY=1.05
SATQUERY_NO_REPEAT_NGRAM_SIZE=3
SATQUERY_MAX_PIXELS=401408               # 512*28*28
SATQUERY_MIN_PIXELS=200704               # 256*28*28 (stage-3: 301056/150528 for paired)
SATQUERY_SYSTEM_PROMPT=...               # override bullets prompt
SATQUERY_CHART_SOURCE=heuristic          # heuristic | llm | auto
SATQUERY_CHART_ENABLED=1
SATQUERY_BULLETS=1

# YOLO counting
SATQUERY_YOLO_WEIGHTS=yolov8n.pt         # or yolov8n-obb.pt (DOTA), or custom RS weight
SATQUERY_YOLO_CONF=0.25
SATQUERY_YOLO_IOU=0.45
SATQUERY_YOLO_CLASSES=                  # comma filter e.g. "car,truck" (empty = all)

# Task routing override
SATQUERY_TASK_OVERRIDES=                # e.g. "vqa:custom_vqa,grounding:my_grounding"
```

**Backend:** `uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload` → `curl http://localhost:8000/health`
**Frontend:** `cd frontend && npm install && npm run dev` → `http://localhost:5173`
**Both:** `make pitch-demo` (`:8000` + `:5173` via `Vite proxy /api → 8000`)

Checks:

```bash
make test          # pytest tests/ -v
ruff check .       # lint
ruff format .      # format
mypy backend/      # type check
make health        # curl /health + /api/health
make build         # vite build → frontend/dist
```

---

## Research References
- **Qwen2-VL** — Wang et al., *Qwen2-VL: Enhancing Vision-Language Model's Perception of the World at Any Resolution*, 2024. Base `Qwen/Qwen2-VL-2B-Instruct` (`Qwen2VLForConditionalGeneration`) — dynamic resolution, `AutoProcessor` with `min/max_pixels`.
- **LoRA / QLoRA** — Hu et al., *LoRA: Low-Rank Adaptation of Large Language Models*, 2021; Dettmers et al., *QLoRA: Efficient Finetuning of Quantized LLMs*, 2023. `r=16 α=32` NF4 4-bit + double quant via `BitsAndBytesConfig` + `peft` on T4.
- **BigEarthNet** — Sumbul et al., *BigEarthNet: A Large-Scale Benchmark Archive for Remote Sensing Image Understanding*, 2019. Sentinel-2 `120×120` chips, 19 land-cover labels — source for Stage-1 `800` S2 subset.
- **RSVQA / VRSBench** — Lobry et al., *RSVQA: Visual Question Answering for Remote Sensing Data*, 2020; Li et al., *VRSBench: A Versatile Benchmark for Vision-Language Models in Remote Sensing*, 2023. Grounding `bbox` and VQA `yes/no, count, comparison` for Stage-2.
- **CDVQA** — Change Detection VQA, bi-temporal `T1→T2` question answering — Stage-3 `cdvqa_change_sft.ipynb` paired loader, `imadityasarkar/cdvqa_change`.
- **YOLOv8** — Jocher et al., *Ultralytics YOLOv8*, 2023. `yolov8n.pt` (COCO mAP 37.3, 6 MB) for counting; DOTA OBB weight for RS small objects.
- **ExecutionTrace** — Graded trace `docs/execution_trace_schema.md` (`backend/schemas` ↔ `frontend/src/types/api.ts`) — compliant traces for hackathon evaluation.

<div align="center">
<i>"From reward signal alone."</i>
</div>
