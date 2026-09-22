import { useState } from "react";
import { searchSatellite, type SatelliteSearchParams } from "../api/satelliteClient";
import type { SatelliteScene } from "../types/satellite";

const PRESET_AOIS: Record<string, Record<string, unknown>> = {
  Bengaluru: {
    type: "Polygon",
    coordinates: [[[77.45, 12.85], [77.75, 12.85], [77.75, 13.05], [77.45, 13.05], [77.45, 12.85]]],
  },
  Delhi: {
    type: "Polygon",
    coordinates: [[[76.9, 28.4], [77.35, 28.4], [77.35, 28.85], [76.9, 28.85], [76.9, 28.4]]],
  },
  "Small AOI (1km)": {
    type: "Polygon",
    coordinates: [[[77.59, 12.97], [77.6, 12.97], [77.6, 12.98], [77.59, 12.98], [77.59, 12.97]]],
  },
};

interface Props {
  selectedScene: SatelliteScene | null;
  setSelectedScene: (s: SatelliteScene | null) => void;
  onTrace?: (trace: Record<string, unknown> | null) => void;
}

export default function SatelliteSearchPanel({ selectedScene, setSelectedScene, onTrace }: Props) {
  const [aoiName, setAoiName] = useState("Bengaluru");
  const [geometryText, setGeometryText] = useState(JSON.stringify(PRESET_AOIS["Bengaluru"], null, 2));
  const [startDate, setStartDate] = useState("2026-06-01");
  const [endDate, setEndDate] = useState("2026-06-30");
  const [sensor] = useState("sentinel-2");
  const [product] = useState("l2a");
  const [maxCloud, setMaxCloud] = useState(20);
  const [maxResults, setMaxResults] = useState(10);
  const [requiredAnalysis, setRequiredAnalysis] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scenes, setScenes] = useState<SatelliteScene[]>([]);
  const [bestId, setBestId] = useState<string | null>(null);
  const [trace, setTrace] = useState<Record<string, unknown> | null>(null);

  const handlePreset = (name: string) => {
    setAoiName(name);
    const g = PRESET_AOIS[name];
    if (g) setGeometryText(JSON.stringify(g, null, 2));
  };

  const handleSearch = async () => {
    setError(null);
    let geom: Record<string, unknown>;
    try {
      geom = JSON.parse(geometryText);
    } catch (e) {
      setError(`Invalid GeoJSON: ${String(e)}`);
      return;
    }
    const params: SatelliteSearchParams = {
      geometry: geom,
      start_date: startDate,
      end_date: endDate,
      max_cloud_cover: maxCloud,
      sensor,
      product,
      max_results: maxResults,
      required_analysis: requiredAnalysis || undefined,
    };
    // Auto-fill bands for analysis
    if (requiredAnalysis) {
      const map: Record<string, string[]> = { NDVI: ["B04", "B08"], NDWI: ["B03", "B08"], NDBI: ["B08", "B11"] };
      params.required_bands = map[requiredAnalysis.toUpperCase()];
    }
    setLoading(true);
    try {
      const res = await searchSatellite(params);
      setScenes(res.scenes || []);
      setBestId(res.best_scene?.id || (res.scenes[0]?.id ?? null));
      setTrace(res.trace || res.execution_trace || null);
      if (onTrace) onTrace(res.execution_trace || res.trace || null);
      if (res.count === 0) setError("No Sentinel-2 scenes found for the requested AOI and date range.");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setScenes([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="panel flex flex-col min-h-0">
      <div className="panel-header">
        <span className="panel-label">Live Satellite Search</span>
        <span className="tag-muted">CDSE STAC</span>
      </div>
      <div className="panel-body space-y-3 overflow-y-auto max-h-[70vh]">
        {/* AOI */}
        <div>
          <label className="block text-[11px] font-medium text-ink-muted uppercase tracking-[0.1em] mb-1.5">AOI (GeoJSON Polygon)</label>
          <div className="flex gap-1 mb-1.5 flex-wrap">
            {Object.keys(PRESET_AOIS).map((n) => (
              <button
                key={n}
                onClick={() => handlePreset(n)}
                className={`px-2 py-1 text-[11px] rounded border transition-colors ${aoiName === n ? "bg-accent/15 text-accent border-accent/30" : "bg-surface-800 text-ink-muted border-surface-400/40 hover:text-ink"}`}
              >
                {n}
              </button>
            ))}
          </div>
          <textarea
            value={geometryText}
            onChange={(e) => setGeometryText(e.target.value)}
            rows={5}
            className="w-full bg-surface-900 border border-surface-400/40 rounded px-2 py-1.5 text-[11px] font-mono text-ink-secondary focus:outline-none focus:border-accent/50"
            placeholder='{"type":"Polygon","coordinates":[[[lon,lat],...]]}'
          />
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="block text-[11px] text-ink-muted mb-1">Start date</label>
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="w-full bg-surface-900 border border-surface-400/40 rounded px-2 py-1.5 text-[12px] text-ink" />
          </div>
          <div>
            <label className="block text-[11px] text-ink-muted mb-1">End date</label>
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="w-full bg-surface-900 border border-surface-400/40 rounded px-2 py-1.5 text-[12px] text-ink" />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="block text-[11px] text-ink-muted mb-1">Max cloud %</label>
            <input type="number" min={0} max={100} value={maxCloud} onChange={(e) => setMaxCloud(Number(e.target.value))} className="w-full bg-surface-900 border border-surface-400/40 rounded px-2 py-1.5 text-[12px] text-ink" />
          </div>
          <div>
            <label className="block text-[11px] text-ink-muted mb-1">Max results</label>
            <input type="number" min={1} max={100} value={maxResults} onChange={(e) => setMaxResults(Number(e.target.value))} className="w-full bg-surface-900 border border-surface-400/40 rounded px-2 py-1.5 text-[12px] text-ink" />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="block text-[11px] text-ink-muted mb-1">Sensor</label>
            <input value={sensor} disabled className="w-full bg-surface-800 border border-surface-400/30 rounded px-2 py-1.5 text-[12px] text-ink-muted" />
          </div>
          <div>
            <label className="block text-[11px] text-ink-muted mb-1">Product</label>
            <input value={product} disabled className="w-full bg-surface-800 border border-surface-400/30 rounded px-2 py-1.5 text-[12px] text-ink-muted" />
          </div>
        </div>

        <div>
          <label className="block text-[11px] text-ink-muted mb-1">Required analysis (future bands)</label>
          <select value={requiredAnalysis} onChange={(e) => setRequiredAnalysis(e.target.value)} className="w-full bg-surface-900 border border-surface-400/40 rounded px-2 py-1.5 text-[12px] text-ink">
            <option value="">— none —</option>
            <option value="NDVI">NDVI → B04,B08</option>
            <option value="NDWI">NDWI → B03,B08</option>
            <option value="NDBI">NDBI → B08,B11</option>
          </select>
        </div>

        <button
          onClick={handleSearch}
          disabled={loading}
          className="w-full py-2 rounded bg-accent text-surface-900 text-[12px] font-semibold tracking-wide hover:bg-accent/90 disabled:opacity-50 transition-colors"
        >
          {loading ? "Searching CDSE…" : "Search Sentinel-2 L2A"}
        </button>

        {error && <div className="text-[11px] text-signal-red bg-signal-red/10 border border-signal-red/20 rounded px-2 py-1.5">{error}</div>}

        {trace && (
          <div className="text-[10px] text-ink-muted bg-surface-800/60 border border-surface-400/20 rounded px-2 py-1.5 font-mono">
            <div>
              CDSE STAC • {String((trace as Record<string, unknown>)["collection"] ?? "sentinel-2-l2a")} • {String(trace["results_found"] ?? "")} found / {String(trace["results_after_filtering"] ?? "")} ranked • {String(trace["latency_ms"] ?? "")}ms
            </div>
            {trace["selected_scene"] ? <div className="text-accent">Best: {String(trace["selected_scene"])}</div> : null}
          </div>
        )}

        {/* Results */}
        {scenes.length > 0 && (
          <div className="space-y-2">
            <div className="text-[11px] font-medium text-ink-muted uppercase tracking-wide">Results ({scenes.length}) — ranked by selection_score</div>
            <div className="space-y-2 max-h-[28vh] overflow-y-auto pr-1">
              {scenes.map((s) => (
                <div
                  key={s.id}
                  className={`border rounded-lg overflow-hidden transition-colors ${bestId === s.id ? "border-accent/50 bg-accent/5" : "border-surface-400/30 bg-surface-800/40"} ${selectedScene?.id === s.id ? "ring-1 ring-accent" : ""}`}
                >
                  <div className="flex gap-2 p-2">
                    {s.thumbnail ? (
                      <img src={s.thumbnail} alt={s.id} className="w-20 h-20 object-cover rounded bg-surface-900 flex-shrink-0" onError={(e) => ((e.target as HTMLImageElement).style.display = "none")} />
                    ) : (
                      <div className="w-20 h-20 rounded bg-surface-900 flex items-center justify-center text-[10px] text-ink-muted flex-shrink-0">no preview</div>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="text-[11px] font-mono text-ink truncate" title={s.id}>
                        {s.id}
                      </div>
                      <div className="text-[11px] text-ink-secondary">{s.datetime ? new Date(s.datetime).toLocaleDateString() : "—"} • {s.platform || "sentinel-2"}</div>
                      <div className="flex gap-2 mt-1 text-[10px] flex-wrap">
                        <span className="px-1.5 py-0.5 rounded bg-surface-900 border border-surface-400/30 text-ink-muted">cloud {s.cloud_cover != null ? `${s.cloud_cover.toFixed(1)}%` : "—"}</span>
                        <span className="px-1.5 py-0.5 rounded bg-surface-900 border border-surface-400/30 text-ink-muted">coverage {s.coverage != null ? `${s.coverage.toFixed(1)}%` : "—"}</span>
                        <span className="px-1.5 py-0.5 rounded bg-accent/15 border border-accent/30 text-accent">score {s.selection_score != null ? s.selection_score.toFixed(3) : "—"}</span>
                      </div>
                      <div className="text-[10px] text-ink-muted mt-1 truncate">assets: {Object.keys(s.assets || {}).slice(0, 6).join(", ") || "—"}</div>
                      <button
                        onClick={() => setSelectedScene(s)}
                        className={`mt-1.5 px-2 py-1 rounded text-[11px] font-medium transition-colors ${selectedScene?.id === s.id ? "bg-signal-green text-white" : "bg-accent/20 text-accent hover:bg-accent/30 border border-accent/30"}`}
                      >
                        {selectedScene?.id === s.id ? "✓ Selected for Analysis" : "Select for Analysis"}
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {selectedScene && (
          <div className="border border-signal-green/30 bg-signal-green/10 rounded-lg p-2.5">
            <div className="text-[11px] font-semibold text-signal-green">Selected Scene → Ready for Analysis</div>
            <div className="text-[11px] font-mono text-ink truncate">{selectedScene.id}</div>
            <div className="text-[10px] text-ink-muted mt-1">Assets: {Object.keys(selectedScene.assets).length} available • Use existing SatQuery VQA/change/count on downloaded bands (future: retrieve_scene_assets)</div>
            <div className="text-[10px] text-ink-muted">Thumbnail: {selectedScene.thumbnail ? "available" : "—"} • Coverage {selectedScene.coverage?.toFixed(1)}% • Score {selectedScene.selection_score?.toFixed(3)}</div>
          </div>
        )}
      </div>
    </section>
  );
}
