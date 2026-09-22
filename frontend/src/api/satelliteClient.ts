import type { SatelliteScene } from "../types/satellite";

export interface SatelliteSearchParams {
  geometry: Record<string, unknown>;
  start_date: string;
  end_date: string;
  max_cloud_cover?: number;
  sensor?: string;
  product?: string;
  max_results?: number;
  required_bands?: string[];
  required_analysis?: string;
}

export interface SatelliteSearchResult {
  count: number;
  scenes: SatelliteScene[];
  best_scene: SatelliteScene | null;
  provider: string;
  collection: string;
  query?: Record<string, unknown>;
  trace?: Record<string, unknown>;
  execution_trace?: Record<string, unknown>;
}

export async function searchSatellite(params: SatelliteSearchParams): Promise<SatelliteSearchResult> {
  const res = await fetch("/api/satellite/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    let detail: string | undefined;
    try {
      const body = await res.json();
      detail = body?.detail ?? JSON.stringify(body);
    } catch {
      detail = await res.text().catch(() => String(res.status));
    }
    throw new Error(detail ? `${res.status}: ${detail}` : `Search failed: ${res.status}`);
  }
  return (await res.json()) as SatelliteSearchResult;
}

export async function checkSatelliteHealth(): Promise<Record<string, unknown>> {
  const res = await fetch("/api/satellite/health");
  if (!res.ok) throw new Error(`Satellite health failed: ${res.status}`);
  return res.json();
}
