# ExecutionTrace Schema

**Shared contract** between `backend/schemas` (Pydantic) and `frontend/src/types/api.ts` (TypeScript). Mirrors `README.md:71` flow. Changes here affect grading — update both sides and bump `backend/schemas` version.

## Pydantic (backend) — `backend/schemas/__init__.py:19`

```python
class EvidenceRef(BaseModel):
    type: Literal["bounding_box", "overlay", "heatmap", "saliency", "image_ref"]
    description: str
    coordinates: list[list[float]] | None = None
    image_index: int | None = 0

class ModelTraceEntry(BaseModel):
    name: str              # e.g. imadityasarkar/satquery-qwen2vl-stage1-bigearthnet
    role: str              # task, e.g. vqa / change_detection
    parameters: dict[str, Any]  # {input_mode, image_count, adapter_path, base_model}
    latency_ms: int
    is_real: bool = True   # False if stubbed/degraded
    is_stub: bool = False

class ExecutionTrace(BaseModel):
    task: str
    models_used: list[ModelTraceEntry]  # one per specialist invoked
    parameters: dict[str, Any]          # {input_mode, image_count, band_subset, spatial_resolution_m}
    confidence: float                   # 0..1 (logprob-based when available, else heuristic)
    evidence_refs: list[EvidenceRef]
    total_latency_ms: int

class QueryResponse(BaseModel):
    answer: str
    confidence: float
    execution_trace: ExecutionTrace
    evidence: list[EvidenceRef]         # mirrors execution_trace.evidence_refs
    scene_context: dict[str, Any] | None = None  # selected-satellite-image mode
    analysis: dict[str, Any] | None = None       # structured payload (e.g. spectral stats) vs text answer

class HealthResponse(BaseModel):
    status: str
    specialists: dict[str, Any]  # registry.health()
    base_model: str
    adapter_path: str
    cuda_available: bool
    force_cpu: bool
    compute: str   # "cpu" | "cuda" | "cpu-only"
    device: str    # e.g. "cpu" | "cuda:0" | "unloaded"
```

## TypeScript (frontend) — `frontend/src/types/api.ts:23`

```ts
type EvidenceRef = {
  type: "bounding_box" | "overlay" | "heatmap" | "saliency" | "image_ref";
  description: string;
  coordinates?: number[][];
  image_index?: number;
};
type ModelTraceEntry = {
  name: string;
  role: string;
  parameters: Record<string, string | number | boolean>;
  latency_ms: number;
  is_real?: boolean;
  is_stub?: boolean;
};
type ExecutionTrace = {
  task: string;
  models_used: ModelTraceEntry[];
  parameters: Record<string, string | number | boolean>;
  confidence: number;
  evidence_refs: EvidenceRef[];
  total_latency_ms: number;
};
type QueryResponse = {
  answer: string;
  confidence: number;
  execution_trace: ExecutionTrace;
  evidence: EvidenceRef[];
  scene_context?: Record<string, unknown>;
  analysis?: Record<string, unknown>;
};
```

## Invariants

- `execution_trace.confidence == confidence` (top-level mirrors trace).
- `models_used[].is_real == !is_stub` for non-degraded paths; degraded VQA returns `is_real=false is_stub=true` with `load_error` in `get_model_info()` `backend/models/vqa.py:375`.
- `evidence_refs` and `evidence` are mirrors — controller builds both from same `result["evidence"]` `backend/controller/__init__.py:247`.
- `task` is normalized via `registry._normalize_task()` `backend/registry.py:59` and `controller.classify_task()` `backend/controller/__init__.py:182` (`single`->`vqa`/`grounding`/`count`, `bi-temporal`->`change_detection` via `imadityasarkar/cdvqa_change`, `optical-sar`->`optical_sar_fusion`).
- `total_latency_ms` includes validation + classification + specialist `latency_ms` (specialist may supply `_latency_ms`).

## Selected-satellite-image mode (`scene_context` / `analysis`)

- `POST /api/query` accepts optional multipart `scene_json` + `aoi_json` form fields
  (`backend/api/__init__.py`), used when the user activates a retrieved scene ("Query This
  Image"). When `scene_json` is present, `images` may be omitted.
- `scene_context` (`backend/controller/__init__.py` `_scene_ctx`) is populated on scene
  queries: `{scene_id, collection, datetime, sentinel_tile, provider, aoi}` plus the resolved
  image provenance (`{image_source, expression, bands, leaflet_bounds}`).
- Controller reroutes scene queries via `_classify_scene_query`: quantitative cover/water/built
  phrases without an explicit index map to `spectral_index`; `satellite_retrieval` is preserved;
  otherwise `vqa`/`count` resolve the scene's real RGB bands to a PIL image
  (`backend/scene/raster.py` `resolve_scene_rgb`, B04/B03/B02) and call
  `registry.predict([pil], query, task)`. AOI confines the clip via
  `Intersection(Scene, AOI)` inside `backend/spectral/processor.py`.
- `analysis` mirrors structured non-answer payloads at the top level — e.g. spectral success
  returns `{**spec_data, type: "spectral_index"}` (`preview_b64`, `bounds`, `stats`,
  `provenance`) so the frontend overlay/legend renders from the same payload as the direct
  `/api/analysis/spectral-index` endpoint. Scene resolutions carry
  `{type: "active_scene_image", scene_id, source, bands, leaflet_bounds}`.

## Health

`GET /health` and `GET /api/health` return `HealthResponse` `backend/api/__init__.py:23`. `specialists` is `registry.health()` `backend/registry.py:118` keyed by `"vqa (real)"`, `"yolo (real)"`, `"grounding (real)"`, `"change_detection (real)"` (`imadityasarkar/cdvqa_change`), `"optical_sar_fusion (stub)"`.

## Frontend rendering

- `ExecutionTracePanel` `frontend/src/components/ExecutionTrace.tsx:25` renders `REAL`/`STUB` badge from `is_real/is_stub`.
- `ResultsPanel` `frontend/src/components/ResultsPanel.tsx:8` maps `EvidenceRef.type` to icon (includes `image_ref`).
- `Header`/`System Status` `frontend/src/App.tsx:185` polls `/api/health` for `compute`/`device` badge.
