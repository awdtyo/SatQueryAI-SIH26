/** Image input configuration modes */
export type InputMode = "single" | "optical-sar" | "bi-temporal";

/** Supported upload file types */
export type ImageFormat = "geotiff" | "tiff" | "png" | "jpeg";

/** Provenance the backend reports for imagery it resolved from a location query. */
export interface ImageSourceMeta {
  collection?: string;
  scene_id?: string;
  display_name?: string;
  lat?: number;
  lon?: number;
  bbox?: number[];
}

/** An uploaded image file with metadata */
export interface UploadedImage {
  file: File;
  preview: string;
  label: string;
  role?: "optical" | "sar" | "t1" | "t2";
  /** Real STAC provenance — only set for location-resolved scenes, never synthesised. */
  meta?: ImageSourceMeta;
}

/** Query request sent to the backend — images OR location (Nominatim + Planetary Computer) */
export interface QueryRequest {
  query: string;
  input_mode: InputMode;
  images: File[];
  // Alternative to images — resolved server-side via geocode + STAC
  location_query?: string;
  location_query_2?: string;
  coordinates?: { lat: number; lon: number };
  coordinates_2?: { lat: number; lon: number };
}

/** Execution trace — graded deliverable per problem statement.
 *  `parameters` and `latency_ms` default server-side (`default_factory=dict`), so a
 *  partial trace from an error or Gradio path may omit them; the UI reads both
 *  defensively rather than assuming they are present. */
export interface ExecutionTrace {
  task: string;
  models_used: ModelTraceEntry[];
  parameters?: Record<string, string | number | boolean>;
  confidence: number;
  evidence_refs: EvidenceRef[];
  total_latency_ms: number;
}

/** A single model invocation in the trace */
export interface ModelTraceEntry {
  name: string;
  role: string;
  parameters?: Record<string, string | number | boolean>;
  latency_ms?: number;
  is_real?: boolean;
  is_stub?: boolean;
}

/** Reference to evidence (bbox, overlay, etc.) — mirrors backend/schemas EvidenceRef */
export interface EvidenceRef {
  type: "bounding_box" | "overlay" | "heatmap" | "saliency" | "image_ref";
  description: string;
  coordinates?: number[][];
  image_index?: number;
}

/** Structured bullets/chart from backend (bullets replace paragraph) */
export interface ChartEntry {
  label: string;
  value: number;
}
export type ChartType = "distribution" | "count" | "change" | "none";
export interface StructuredOutput {
  bullets: string[];
  chart: ChartEntry[];
  chart_type?: ChartType | null;
  summary?: string;
}

export interface ResolvedImagePreview {
  display_name?: string;
  lat?: number;
  lon?: number;
  scene_id?: string;
  collection?: string;
  preview_b64?: string;
  bbox?: number[];
}

/** Full query response from the backend */
export interface QueryResponse {
  answer: string;
  confidence: number;
  execution_trace: ExecutionTrace;
  evidence: EvidenceRef[];
  structured?: StructuredOutput | null;
  chart?: ChartEntry[] | null;
  chart_type?: ChartType | null;
  resolved_images?: ResolvedImagePreview[] | null;
}

/** Application error shape */
export interface AppError {
  message: string;
  code?: string;
  details?: string;
}

/** Per-specialist truth reported under `/api/health` → `specialists.registry`. */
export interface SpecialistHealth {
  /** False means the specialist is a stub, not that it is unreachable. */
  is_real?: boolean;
  load_error?: string | null;
  device?: string;
  compute?: string;
  gpu_name?: string | null;
  [key: string]: unknown;
}

/** Backend /api/health (or Gradio /info) payload polled for system status */
export type HealthState = {
  status: string;
  compute?: string;
  device?: string;
  force_cpu?: boolean;
  adapter_path?: string;
  base_model?: string;
  cuda_effective?: boolean;
  gpu_name?: string | null;
  /**
   * FastAPI returns `{ registry, task_map }`. The Gradio transport has no such
   * route and omits the key entirely, so every read must tolerate `undefined`.
   */
  specialists?: { registry?: Record<string, SpecialistHealth> };
} | null;
