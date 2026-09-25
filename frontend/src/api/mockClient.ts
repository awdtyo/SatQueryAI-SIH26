import type {
  ChartEntry,
  ChartType,
  EvidenceRef,
  ExecutionTrace,
  QueryRequest,
  QueryResponse,
  ResolvedImagePreview,
} from "../types/api";

/**
 * API client with two transports:
 *
 * - fastapi (local dev): FormData POST to /api/query on backend/main.py —
 *   VITE_API_BASE_URL empty (Vite proxy /api) or http://localhost:8000.
 * - gradio (production): HF Gradio SDK Space (ZeroGPU). Images are uploaded via
 *   POST /gradio_api/upload (FileData), then a FRESH queue job per submission:
 *   POST /gradio_api/call/predict  →  GET /gradio_api/call/predict/{event_id}
 *   (SSE: heartbeat* → complete | error).
 *
 * Transport auto-detect: empty/localhost base → fastapi, any other host →
 * gradio; override with VITE_API_TRANSPORT=gradio|fastapi.
 *
 * Model/config resolution (SATQUERY_BASE_MODEL / SATQUERY_ADAPTER_PATH) stays
 * server-side — nothing model-related is hardcoded here.
 */

const API_BASE =
  (
    (import.meta.env.VITE_API_BASE_URL as string | undefined) ||
    (import.meta.env.VITE_API_BASE as string | undefined)
  )?.replace(/\/$/, "") || "";

function apiUrl(path: string): string {
  // Local dev: VITE_API_BASE_URL=http://localhost:8000 (or empty → Vite proxy /api → localhost:8000)
  // Vercel prod: VITE_API_BASE_URL=https://<user>-satquery-backend.hf.space (Gradio transport)
  // Backward compat: VITE_API_BASE (old Azure hybrid name) still works if VITE_API_BASE_URL not set
  return `${API_BASE}${path}`;
}

type Transport = "gradio" | "fastapi";

function resolveTransport(): Transport {
  const explicit = (import.meta.env.VITE_API_TRANSPORT as string | undefined)?.toLowerCase();
  if (explicit === "gradio" || explicit === "fastapi") return explicit;
  if (!API_BASE) return "fastapi";
  try {
    const host = new URL(API_BASE).hostname;
    if (host === "localhost" || host === "127.0.0.1" || host === "0.0.0.0") return "fastapi";
  } catch {
    return "fastapi";
  }
  return "gradio";
}

function gradioBase(): string {
  if (!API_BASE) {
    throw new Error(
      "Gradio transport requires VITE_API_BASE_URL pointing at the HF Space (set it in Vercel)",
    );
  }
  return `${API_BASE}/gradio_api`;
}

/**
 * Gradio event name for /gradio_api/call/<event>.
 * app.py registers `run_btn.click(fn=predict, ...)` as the FIRST fn whose
 * __name__ is "predict", so Gradio 5.16.1 auto-derives api_name "predict"
 * (gradio/blocks.py set_event_trigger → utils.append_unique_suffix). The three
 * Enter-key `.submit(fn=predict, ...)` duplicates become predict_1..3 and the
 * chart `.then(...)` handlers become _update_chart* — UI only, unused here.
 */
const PREDICT_EVENT = "predict";

// ZeroGPU cold start (~30-60s) + @spaces.GPU(duration=60) → generous ceiling.
const CALL_TIMEOUT_MS = 300_000;

type GradioFileData = {
  path: string;
  orig_name: string;
  meta: { _type: "gradio.FileData" };
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

async function httpErrorText(res: Response, context: string): Promise<string> {
  let detail: string | undefined;
  try {
    const body: unknown = await res.json();
    if (isRecord(body)) {
      const d = body["detail"] ?? body["message"];
      detail = typeof d === "string" ? d : JSON.stringify(d);
    } else {
      detail = JSON.stringify(body);
    }
  } catch {
    detail = await res.text().catch(() => String(res.status));
  }
  return detail ? `${context} failed (${res.status}): ${detail}` : `${context} failed: ${res.status}`;
}

async function uploadToGradio(file: File): Promise<GradioFileData> {
  const form = new FormData();
  form.append("files", file, file.name);
  const res = await fetch(`${gradioBase()}/upload`, { method: "POST", body: form });
  if (!res.ok) throw new Error(await httpErrorText(res, "Gradio upload"));
  const paths: unknown = await res.json();
  const path = Array.isArray(paths) ? paths[0] : undefined;
  if (typeof path !== "string" || !path) {
    throw new Error(`Gradio upload returned no path for ${file.name}`);
  }
  // Same FileData shape gradio_client sends (path from /upload, original name
  // for PIL format inference, explicit meta required by ImageData validation).
  return { path, orig_name: file.name, meta: { _type: "gradio.FileData" } };
}

function findFrameEnd(buffer: string): { index: number; length: number } | null {
  const m = /\r?\n\r?\n/.exec(buffer);
  return m ? { index: m.index, length: m[0].length } : null;
}

function parseSseFrame(frame: string): { event: string; data: string } | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0 && event === "message") return null;
  return { event, data: dataLines.join("\n") };
}

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function errorMessageFromSseData(data: string): string {
  const parsed: unknown = safeJsonParse(data);
  if (typeof parsed === "string" && parsed) return parsed;
  if (Array.isArray(parsed) && typeof parsed[0] === "string") return parsed[0];
  if (Array.isArray(parsed) && isRecord(parsed[0]) && typeof parsed[0]["error"] === "string") {
    return parsed[0]["error"];
  }
  return data && data !== "null" && data !== "[]"
    ? data
    : "Gradio reported an error with no detail";
}

async function streamCallOutputs(eventId: string): Promise<unknown[]> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), CALL_TIMEOUT_MS);
  try {
    const res = await fetch(`${gradioBase()}/call/${PREDICT_EVENT}/${eventId}`, {
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(await httpErrorText(res, "Gradio event stream"));
    const reader = res.body?.getReader();
    if (!reader) throw new Error("Gradio event stream has no readable body");
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let frameEnd = findFrameEnd(buffer);
      while (frameEnd) {
        const frame = buffer.slice(0, frameEnd.index);
        buffer = buffer.slice(frameEnd.index + frameEnd.length);
        const parsed = parseSseFrame(frame);
        if (parsed?.event === "complete") {
          const outputs = safeJsonParse(parsed.data);
          if (Array.isArray(outputs)) return outputs;
          throw new Error(
            `Unexpected Gradio completion payload: ${parsed.data.slice(0, 200)}`,
          );
        }
        if (parsed?.event === "error") {
          throw new Error(errorMessageFromSseData(parsed.data));
        }
        // heartbeat / generating frames — keep reading until complete
        frameEnd = findFrameEnd(buffer);
      }
    }
    // Stream ended — some proxies strip the final blank line; accept a trailing frame.
    const tail = parseSseFrame(buffer.trim());
    if (tail?.event === "complete") {
      const outputs = safeJsonParse(tail.data);
      if (Array.isArray(outputs)) return outputs;
    }
    if (tail?.event === "error") throw new Error(errorMessageFromSseData(tail.data));
    throw new Error("Gradio event stream closed before completion");
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new Error(`Gradio queue timed out after ${CALL_TIMEOUT_MS / 1000}s`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error ?? new Error("Failed to read image blob"));
    reader.readAsDataURL(blob);
  });
}

/**
 * Gallery output (app.py `fetched_gallery`) → ResolvedImagePreview[] for the
 * viewer. Each item is {image: {path, url: "/gradio_api/file=...", ...}, caption};
 * fetch bytes once so preview_b64 is a real data URL (App.tsx dataUrlToFile
 * reuses it as a File for multi-turn queries).
 */
async function galleryToResolvedImages(value: unknown): Promise<ResolvedImagePreview[] | null> {
  if (!Array.isArray(value) || value.length === 0) return null;
  const out: ResolvedImagePreview[] = [];
  for (const item of value) {
    if (!isRecord(item)) continue;
    const image = item["image"];
    const caption = typeof item["caption"] === "string" ? item["caption"] : undefined;
    const raw = isRecord(image)
      ? typeof image["url"] === "string"
        ? image["url"]
        : typeof image["path"] === "string"
          ? image["path"]
          : null
      : null;
    if (!raw) continue;
    let preview = raw.startsWith("/") ? `${API_BASE}${raw}` : raw;
    if (!raw.startsWith("data:")) {
      try {
        const res = await fetch(preview);
        if (res.ok) preview = await blobToDataUrl(await res.blob());
      } catch {
        // keep absolute URL as preview fallback (display-only, not re-uploadable)
      }
    }
    out.push({ display_name: caption, preview_b64: preview });
  }
  return out.length > 0 ? out : null;
}

/**
 * /call/predict output array layout (app.py `predict` returns 6 values):
 * [answer, confidence, execution_trace, evidence_md, chart_state, gallery].
 * gr.State outputs serialize as null outside a live session (gradio/blocks.py
 * postprocess_data), so slot 4 is null — the chart is echoed into the trace
 * as `_chart`/`_chart_type`, and `evidence_md` (slot 3) is the rendered form
 * of trace.evidence_refs, which is what QueryResponse.evidence needs.
 */
async function normalizeGradioOutputs(outputs: unknown[]): Promise<QueryResponse> {
  const answer = typeof outputs[0] === "string" ? outputs[0] : "";
  const confidence = typeof outputs[1] === "number" ? outputs[1] : 0;
  const rawTrace = isRecord(outputs[2]) ? outputs[2] : {};
  const evidenceRefs = rawTrace["evidence_refs"];
  const chart = rawTrace["_chart"];
  const chartType = rawTrace["_chart_type"];
  return {
    answer,
    confidence,
    execution_trace: rawTrace as unknown as ExecutionTrace,
    evidence: Array.isArray(evidenceRefs) ? (evidenceRefs as EvidenceRef[]) : [],
    structured: null,
    chart: Array.isArray(chart) ? (chart as ChartEntry[]) : null,
    chart_type: typeof chartType === "string" ? (chartType as ChartType) : null,
    resolved_images: await galleryToResolvedImages(outputs[5]),
  };
}

async function submitQueryViaGradio(request: QueryRequest): Promise<QueryResponse> {
  const files = request.images.slice(0, 2);
  const uploaded: GradioFileData[] = [];
  for (const file of files) {
    uploaded.push(await uploadToGradio(file));
  }

  // predict() has no separate coordinates params — the controller parses
  // "lat,lon" strings from location_query (backend/services/geocode.parse_coordinates)
  const loc1 =
    request.location_query ??
    (request.coordinates ? `${request.coordinates.lat},${request.coordinates.lon}` : null);
  const loc2 =
    request.location_query_2 ??
    (request.coordinates_2 ? `${request.coordinates_2.lat},${request.coordinates_2.lon}` : null);

  const body = {
    data: [
      request.query,
      request.input_mode,
      uploaded[0] ?? null,
      uploaded[1] ?? null,
      loc1,
      loc2,
    ],
  };

  const postRes = await fetch(`${gradioBase()}/call/${PREDICT_EVENT}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!postRes.ok) throw new Error(await httpErrorText(postRes, "Gradio call"));
  const queued: unknown = await postRes.json();
  const eventId = isRecord(queued) ? queued["event_id"] : undefined;
  if (typeof eventId !== "string" || !eventId) {
    throw new Error("Gradio queue did not return an event_id");
  }

  const outputs = await streamCallOutputs(eventId);
  return normalizeGradioOutputs(outputs);
}

async function submitQueryViaFastapi(request: QueryRequest): Promise<QueryResponse> {
  const formData = new FormData();
  formData.append("query", request.query);
  formData.append("input_mode", request.input_mode);
  // Backend expects `images` as repeated File field (also accepts image_0/image_1)
  request.images.forEach((file) => {
    formData.append("images", file, file.name);
  });
  // Location alternative — server resolves via Nominatim + Planetary Computer STAC
  if (request.location_query) formData.append("location_query", request.location_query);
  if (request.location_query_2) formData.append("location_query_2", request.location_query_2);
  if (request.coordinates) {
    formData.append("coordinates", `${request.coordinates.lat},${request.coordinates.lon}`);
    // also send as separate lat/lon for robustness
    formData.append("lat", String(request.coordinates.lat));
    formData.append("lon", String(request.coordinates.lon));
  }
  if (request.coordinates_2) {
    formData.append("coordinates_2", `${request.coordinates_2.lat},${request.coordinates_2.lon}`);
    formData.append("lat2", String(request.coordinates_2.lat));
    formData.append("lon2", String(request.coordinates_2.lon));
  }

  const res = await fetch(apiUrl("/api/query"), {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    throw new Error(await httpErrorText(res, "Query"));
  }

  return (await res.json()) as QueryResponse;
}

export async function submitQuery(request: QueryRequest): Promise<QueryResponse> {
  if (resolveTransport() === "gradio") {
    return submitQueryViaGradio(request);
  }
  return submitQueryViaFastapi(request);
}

export async function checkHealth(): Promise<{
  status: string;
  compute?: string;
  device?: string;
  force_cpu?: boolean;
  specialists?: unknown;
  adapter_path?: string;
  base_model?: string;
}> {
  if (resolveTransport() === "gradio") {
    // Reachable /gradio_api/info (endpoint signatures, no model load) = Space online.
    // compute/device reflect the documented Space hardware (zero-a10g, SATQUERY_FORCE_CPU=0).
    const res = await fetch(`${gradioBase()}/info`);
    if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
    await res.json().catch(() => null);
    return { status: "online", compute: "zero-gpu", device: "cuda", force_cpu: false };
  }
  const res = await fetch(apiUrl("/api/health"));
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}

export async function getCapabilities(): Promise<{
  vqa: boolean;
  object_detection: boolean;
  spectral_indices: boolean;
  change_detection: boolean;
  live_satellite: boolean;
  visualizations: boolean;
}> {
  // Gradio production transport has no FastAPI /api/capabilities route — return
  // the same static values backend/main.py serves (no network call, no model load).
  if (resolveTransport() === "gradio") {
    return {
      vqa: true,
      object_detection: true,
      spectral_indices: true,
      change_detection: true,
      live_satellite: true,
      visualizations: true,
    };
  }
  const res = await fetch(apiUrl("/api/capabilities"));
  if (!res.ok) throw new Error(`Capabilities check failed: ${res.status}`);
  return res.json();
}
