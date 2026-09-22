import { useState } from "react";
import { calculateSpectralIndex } from "../api/spectralClient";
import type { SatelliteScene } from "../types/satellite";

interface Props {
  selectedScene: SatelliteScene | null;
  aoiGeometry: Record<string, unknown> | null;
  onResult: (res: Record<string, unknown> | null) => void;
  onError?: (msg: string | null) => void;
}

const INDICES = [
  { value: "NDVI", label: "NDVI — Vegetation", desc: "NIR B08 - RED B04" },
  { value: "NDWI", label: "NDWI — Water", desc: "GREEN B03 - NIR B08" },
  { value: "NDBI", label: "NDBI — Built-up", desc: "SWIR B11 - NIR B08" },
  { value: "NDMI", label: "NDMI — Moisture", desc: "NIR B08 - SWIR B11" },
  { value: "SAVI", label: "SAVI — Soil Vegetation", desc: "(NIR-RED)/(NIR+RED+0.5)*1.5" },
  { value: "BSI", label: "BSI — Bare Soil", desc: "((SWIR+RED)-(NIR+BLUE))/((SWIR+RED)+(NIR+BLUE))" },
];

export default function SpectralPanel({ selectedScene, aoiGeometry, onResult, onError }: Props) {
  const [index, setIndex] = useState("NDVI");
  const [cloudMask, setCloudMask] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [traceSteps, setTraceSteps] = useState<string[]>([]);

  // Auto-select index based on natural language? For now manual
  const handleCalculate = async () => {
    if (!selectedScene) {
      const msg = "Please select a Sentinel-2 scene first (via map footprint or search results).";
      setError(msg);
      if (onError) onError(msg);
      return;
    }
    if (!aoiGeometry) {
      const msg = "Please draw an AOI on the map first.";
      setError(msg);
      if (onError) onError(msg);
      return;
    }
    setError(null);
    if (onError) onError(null);
    setLoading(true);
    setStats(null);
    setTraceSteps([]);
    try {
      const res = await calculateSpectralIndex({
        index,
        scene: selectedScene as unknown as Record<string, unknown>,
        aoi: aoiGeometry,
        cloud_mask: cloudMask,
        target_resolution: 10,
      });
      setStats(res.stats as Record<string, unknown>);
      setTraceSteps(res.trace_steps || []);
      onResult(res as unknown as Record<string, unknown>);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      if (onError) onError(msg);
      onResult(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-label">Spectral Index Agent</span>
        <span className="tag-muted">real bands</span>
      </div>
      <div className="panel-body space-y-3">
        <div>
          <label className="block text-[11px] text-ink-muted mb-1">Index</label>
          <select value={index} onChange={(e) => setIndex(e.target.value)} className="w-full bg-surface-900 border border-surface-400/40 rounded px-2 py-1.5 text-[12px] text-ink">
            {INDICES.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <div className="text-[10px] text-ink-muted mt-1">{INDICES.find((o) => o.value === index)?.desc} — range -1..1, formula in registry</div>
        </div>

        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={cloudMask} onChange={(e) => setCloudMask(e.target.checked)} className="accent-accent" />
          <span className="text-[11px] text-ink">Cloud mask (SCL)</span>
          <span className="text-[10px] text-ink-muted">{cloudMask ? "SCL 0,1,3,8,9,10,11 masked" : "No masking (shows all pixels)"}</span>
        </label>

        <div className="text-[11px] text-ink-muted bg-surface-800/60 border border-surface-400/20 rounded px-2 py-1.5">
          <div>Scene: <span className="text-ink font-mono">{selectedScene ? selectedScene.id.slice(0, 28) : "— none selected —"}</span></div>
          <div>AOI: {aoiGeometry ? "✓ ready" : "— draw on map"}</div>
          <div>Bands: {INDICES.find((o) => o.value === index)?.desc}</div>
        </div>

        <button onClick={handleCalculate} disabled={loading || !selectedScene || !aoiGeometry} className="w-full py-2 rounded bg-accent text-surface-900 text-[12px] font-semibold hover:bg-accent-bright disabled:opacity-50 transition-colors">
          {loading ? "Calculating…" : `Calculate ${index} → Map Layer`}
        </button>

        {error && <div className="text-[11px] text-signal-red bg-signal-red/10 border border-signal-red/20 rounded px-2 py-1.5">{error}</div>}

        {stats && (
          <div className="space-y-2">
            <div className="text-[11px] font-medium text-ink-muted uppercase">Statistics (valid pixels only)</div>
            <div className="grid grid-cols-3 gap-2 text-[11px]">
              <div className="bg-surface-900 border border-surface-400/30 rounded p-2 text-center">
                <div className="text-[10px] text-ink-muted">Min</div>
                <div className="text-ink font-mono">{(stats as { min: number }).min?.toFixed(3)}</div>
              </div>
              <div className="bg-surface-900 border border-surface-400/30 rounded p-2 text-center">
                <div className="text-[10px] text-ink-muted">Mean</div>
                <div className="text-accent font-mono font-semibold">{(stats as { mean: number }).mean?.toFixed(3)}</div>
              </div>
              <div className="bg-surface-900 border border-surface-400/30 rounded p-2 text-center">
                <div className="text-[10px] text-ink-muted">Max</div>
                <div className="text-ink font-mono">{(stats as { max: number }).max?.toFixed(3)}</div>
              </div>
            </div>
            <div className="flex gap-2 text-[10px] flex-wrap">
              <span className="px-1.5 py-0.5 rounded bg-surface-900 border border-surface-400/30 text-ink-muted">valid {(stats as { valid_pct: number }).valid_pct?.toFixed(1)}% ({(stats as { valid_pixels: number }).valid_pixels})</span>
              <span className="px-1.5 py-0.5 rounded bg-surface-900 border border-surface-400/30 text-ink-muted">masked {(stats as { masked_pct: number }).masked_pct?.toFixed(1)}%</span>
              <span className="px-1.5 py-0.5 rounded bg-surface-900 border border-surface-400/30 text-ink-muted">median {(stats as { median: number }).median?.toFixed(3)}</span>
            </div>
          </div>
        )}

        {traceSteps.length > 0 && (
          <details className="text-[10px] text-ink-muted">
            <summary className="cursor-pointer text-accent">Execution trace ({traceSteps.length} steps)</summary>
            <ol className="list-decimal ml-4 mt-1 space-y-0.5">
              {traceSteps.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ol>
          </details>
        )}

        <div className="text-[10px] text-ink-muted leading-relaxed">
          Real STAC assets (only required bands) → clip AOI → 10m bilinear (SCL nearest) → nodata/cloud mask → safe divide → GeoTIFF + PNG overlay. Formula from centralized registry, easy to add new indices.
        </div>
      </div>
    </div>
  );
}
