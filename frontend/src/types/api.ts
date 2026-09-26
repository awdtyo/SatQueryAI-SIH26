/** Image input configuration modes */
export type InputMode = "single" | "optical-sar" | "bi-temporal";

/** Supported upload file types */
export type ImageFormat = "geotiff" | "tiff" | "png" | "jpeg";

/** An uploaded image file with metadata */
export interface UploadedImage {
  file: File;
  preview: string;
  label: string;
  role?: "optical" | "sar" | "t1" | "t2";
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

/**
 * Real transport-level progress signals observed by the client.
 * Emitted only when the transport can genuinely observe the state — Gradio SSE
 * frames for `queued`/`generating`/`responding`, request lifecycle for
 * `dispatching`. Never used to imply a backend stage completed.
 */
export type QueryActivity = "dispatching" | "queued" | "generating" | "responding";

/** Execution trace — graded deliverable per problem statement */
export interface ExecutionTrace {
  task: string;
  models_used: ModelTraceEntry[];
  parameters: Record<string, string | number | boolean>;
  confidence: number;
  evidence_refs: EvidenceRef[];
  total_latency_ms: number;
}

/** A single model invocation in the trace */
export interface ModelTraceEntry {
  name: string;
  role: string;
  parameters: Record<string, string | number | boolean>;
  latency_ms: number;
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

/** `GET /api/health` payload (or the Gradio `/info` equivalent) */
export interface HealthSnapshot {
  status?: string;
  compute?: string;
  device?: string;
  force_cpu?: boolean;
  adapter_path?: string;
  base_model?: string;
  specialists?: Record<string, unknown>;
}
