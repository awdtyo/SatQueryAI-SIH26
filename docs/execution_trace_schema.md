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
};
```

## Invariants

- `execution_trace.confidence == confidence` (top-level mirrors trace).
- `models_used[].is_real == !is_stub` for non-degraded paths; degraded VQA returns `is_real=false is_stub=true` with `load_error` in `get_model_info()` `backend/models/vqa.py:375`.
- `evidence_refs` and `evidence` are mirrors — controller builds both from same `result["evidence"]` `backend/controller/__init__.py:247`.
- `task` is normalized via `registry._normalize_task()` `backend/registry.py:54` and `controller.classify_task()` `backend/controller/__init__.py:152` (`single`->`vqa`/`grounding`, `bi-temporal`->`change_detection`, `optical-sar`->`optical_sar_fusion`).
- `total_latency_ms` includes validation + classification + specialist `latency_ms` (specialist may supply `_latency_ms`).

## Health

`GET /health` and `GET /api/health` return `HealthResponse` `backend/api/__init__.py:23`. `specialists` is `registry.health()` `backend/registry.py:132` keyed by `"vqa (real)"`, `"grounding (stub)"`, etc.

## Frontend rendering

- `ExecutionTracePanel` `frontend/src/components/ExecutionTrace.tsx:25` renders `REAL`/`STUB` badge from `is_real/is_stub`.
- `ResultsPanel` `frontend/src/components/ResultsPanel.tsx:8` maps `EvidenceRef.type` to icon (includes `image_ref`).
- `Header`/`System Status` `frontend/src/App.tsx:185` polls `/api/health` for `compute`/`device` badge.
