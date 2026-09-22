export interface SpectralRequest {
  index: string;
  scene: Record<string, unknown>;
  aoi?: Record<string, unknown> | null;
  cloud_mask?: boolean;
  target_resolution?: number;
}

export interface SpectralResponse {
  index: string;
  scene_id: string;
  scene_datetime: string | null;
  aoi: Record<string, unknown> | null;
  required_bands: string[];
  raster_path: string;
  preview_b64: string | null;
  preview_path: string | null;
  bounds: [[number, number], [number, number]] | null;
  bounds_4326: [number, number, number, number] | null;
  profile: Record<string, unknown> | null;
  stats: {
    min: number;
    max: number;
    mean: number;
    median: number;
    std: number;
    valid_pixels: number;
    masked_pixels: number;
    valid_pct: number;
    masked_pct: number;
  };
  cloud_applied: boolean;
  latency_ms: number;
  trace_steps: string[];
  provenance: Record<string, unknown>;
  evidence: Array<Record<string, unknown>>;
  visual: Record<string, unknown>;
  interpretation: Record<string, unknown>;
}

export async function calculateSpectralIndex(req: SpectralRequest): Promise<SpectralResponse> {
  const res = await fetch("/api/analysis/spectral-index", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    let detail: string | undefined;
    try {
      const body = await res.json();
      detail = body?.detail ?? JSON.stringify(body);
    } catch {
      detail = await res.text().catch(() => String(res.status));
    }
    throw new Error(detail ? `${res.status}: ${detail}` : `Spectral failed: ${res.status}`);
  }
  return (await res.json()) as SpectralResponse;
}

export async function listSpectralIndices(): Promise<{ indices: string[]; registry: Record<string, unknown> }> {
  const res = await fetch("/api/analysis/spectral-index/indices");
  if (!res.ok) throw new Error(`List indices failed: ${res.status}`);
  return res.json();
}

export async function spectralHealth(): Promise<Record<string, unknown>> {
  const res = await fetch("/api/analysis/spectral-index/health");
  if (!res.ok) throw new Error(`Health failed: ${res.status}`);
  return res.json();
}

export async function samplePixel(rasterPath: string, lon: number, lat: number): Promise<{ value: number | null; lon: number; lat: number }> {
  const res = await fetch("/api/analysis/spectral-index/pixel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ raster_path: rasterPath, lon, lat }),
  });
  if (!res.ok) {
    const t = await res.text().catch(() => "");
    throw new Error(t || `Pixel sample failed: ${res.status}`);
  }
  return res.json();
}
