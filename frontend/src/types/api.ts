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

/** Query request sent to the backend */
export interface QueryRequest {
  query: string;
  input_mode: InputMode;
  images: File[];
  /** Selected Satellite Image Query Mode: analyze this ACTIVE scene's real assets. */
  scene?: import("./satellite").SatelliteScene | Record<string, unknown>;
  /** Optional AOI GeoJSON polygon to clip analysis to (EPSG:4326). */
  aoi?: Record<string, unknown>;
}

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

/** Full query response from the backend */
export interface QueryResponse {
  answer: string;
  confidence: number;
  execution_trace: ExecutionTrace;
  evidence: EvidenceRef[];
  structured?: StructuredOutput | null;
  chart?: ChartEntry[] | null;
  chart_type?: ChartType | null;
  /** Active scene this query was analyzed against (id, collection, datetime, aoi…). */
  scene_context?: Record<string, unknown> | null;
  /** Raster payload for map overlay (spectral index preview_b64/bounds/stats, or scene image). */
  analysis?: Record<string, unknown> | null;
}

/** Application error shape */
export interface AppError {
  message: string;
  code?: string;
  details?: string;
}
