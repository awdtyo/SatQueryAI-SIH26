import type { QueryRequest, QueryResponse } from "../types/api";

/**
 * Real backend client — wired to backend/config.py
 * BASE_MODEL / ADAPTER_PATH are resolved server-side (SATQUERY_BASE_MODEL,
 * SATQUERY_ADAPTER_PATH env). Frontend just POSTs the query + images to
 * /api/query which the controller routes via registry to the specialist
 * loaded from that config. No model path is hardcoded here.
 */

export async function submitQuery(request: QueryRequest): Promise<QueryResponse> {
  const formData = new FormData();
  formData.append("query", request.query);
  formData.append("input_mode", request.input_mode);
  // Backend expects `images` as repeated File field (also accepts image_0/image_1)
  request.images.forEach((file) => {
    formData.append("images", file, file.name);
  });

  const res = await fetch("/api/query", {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    // Try to surface backend's detail (FastAPI HTTPException detail)
    let detail: string | undefined;
    try {
      const body = await res.json();
      detail = body?.detail ?? body?.message ?? JSON.stringify(body);
    } catch {
      detail = await res.text().catch(() => String(res.status));
    }
    throw new Error(detail ? `${res.status}: ${detail}` : `Query failed: ${res.status}`);
  }

  const data = (await res.json()) as QueryResponse;
  return data;
}

export async function checkHealth(): Promise<{ status: string; specialists?: unknown; adapter_path?: string; base_model?: string }> {
  const res = await fetch("/api/health");
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}
