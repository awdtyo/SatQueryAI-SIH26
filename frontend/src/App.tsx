import { useState, useCallback, useEffect } from "react";
import type { InputMode, QueryResponse, UploadedImage, AppError } from "./types/api";
import type { SatelliteScene } from "./types/satellite";
import { submitQuery, checkHealth } from "./api/mockClient";
import { searchSatellite } from "./api/satelliteClient";
import Header from "./components/Header";
import ImageUploader from "./components/ImageUploader";
import ImageryViewer from "./components/ImageryViewer";
import QueryInput from "./components/QueryInput";
import ResultsPanel from "./components/ResultsPanel";
import ExecutionTracePanel from "./components/ExecutionTrace";
import ConfidenceGauge from "./components/ConfidenceGauge";
import LoadingOverlay from "./components/LoadingOverlay";
import SatelliteSearchPanel from "./components/SatelliteSearchPanel";
import MapView from "./components/MapView";
import LayerControl, { type LayerVisibility } from "./components/LayerControl";
import SceneCards from "./components/SceneCards";
import SceneMetadataPanel from "./components/SceneMetadataPanel";
import { isValidGeoJSON } from "./utils/geojson";
import SpectralPanel from "./components/SpectralPanel";
import SpectralLegend from "./components/SpectralLegend";
import ActiveSceneContext from "./components/ActiveSceneContext";
import { samplePixel } from "./api/spectralClient";

type HealthState = {
  status: string;
  compute?: string;
  device?: string;
  force_cpu?: boolean;
  adapter_path?: string;
  specialists?: Record<string, unknown>;
} | null;

const DEFAULT_AOI: Record<string, unknown> = {
  type: "Polygon",
  coordinates: [[[77.45, 12.85], [77.75, 12.85], [77.75, 13.05], [77.45, 13.05], [77.45, 12.85]]],
};

function isRetrievalQuery(q: string): boolean {
  const low = q.toLowerCase();
  const keywords = ["sentinel", "satellite imagery", "find imagery", "best satellite", "aoi"];
  const verbs = ["find", "search", "retrieve", "get", "best", "cloud", "from", "between"];
  if (keywords.some((k) => low.includes(k)) && verbs.some((v) => low.includes(v))) return true;
  if (low.includes("find") && low.includes("imagery")) return true;
  return false;
}

function isSpectralQuery(q: string): boolean {
  const low = q.toLowerCase();
  if (["ndvi", "ndwi", "ndbi", "ndmi", "savi", "bsi"].some((k) => low.includes(k))) return true;
  if (["vegetation health", "vegetation index", "water index", "built-up", "built up", "moisture", "bare soil"].some((k) => low.includes(k)) && ["calculate", "show", "find", "display", "compute", "index"].some((v) => low.includes(v))) return true;
  return false;
}

export default function App() {
  const [images, setImages] = useState<UploadedImage[]>([]);
  const [inputMode, setInputMode] = useState<InputMode>("single");
  const [isLoading, setIsLoading] = useState(false);
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [error, setError] = useState<AppError | null>(null);
  const [queryHistory, setQueryHistory] = useState<string[]>([]);
  const [health, setHealth] = useState<HealthState>(null);
  const [selectedScene, setSelectedScene] = useState<SatelliteScene | null>(null);
  const [activeScene, setActiveScene] = useState<SatelliteScene | null>(null);
  const [satelliteTrace, setSatelliteTrace] = useState<Record<string, unknown> | null>(null);
  const [showSatellite, setShowSatellite] = useState(true);

  // GIS state
  const [aoiGeometry, setAoiGeometry] = useState<Record<string, unknown> | null>(DEFAULT_AOI);
  const [gisScenes, setGisScenes] = useState<SatelliteScene[]>([]);
  const [gisTrace, setGisTrace] = useState<Record<string, unknown> | null>(null);
  const [gisLoading, setGisLoading] = useState(false);
  const [gisError, setGisError] = useState<string | null>(null);
  const [drawMode, setDrawMode] = useState<"rectangle" | "polygon" | null>(null);
  const [layerVisibility, setLayerVisibility] = useState<LayerVisibility>({
    aoi: true,
    footprints: true,
    selected: true,
    preview: true,
    analysis: false,
  });
  const [mapMode, setMapMode] = useState<"gis" | "analysis">("gis");

  // Spectral index state
  const [spectralResult, setSpectralResult] = useState<Record<string, unknown> | null>(null);
  const [spectralOpacity, setSpectralOpacity] = useState(0.75);
  const [spectralVisible, setSpectralVisible] = useState(true);
  const [pixelInspect, setPixelInspect] = useState<{ lat: number; lon: number; value: number | null; loading: boolean; error?: string } | null>(null);

  // Poll backend health
  useEffect(() => {
    let cancelled = false;
    const fetchHealth = async () => {
      try {
        const h = await checkHealth();
        if (!cancelled) setHealth(h as HealthState);
      } catch {
        if (!cancelled) setHealth({ status: "offline" });
      }
    };
    fetchHealth();
    const id = setInterval(fetchHealth, 15000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const runSceneQuery = useCallback(
    async (query: string, scene: SatelliteScene) => {
      setError(null);
      setGisError(null);
      setIsLoading(true);
      setResponse(null);
      try {
        const result = await submitQuery({
          query,
          input_mode: "single",
          images: [],
          scene: scene as unknown as Record<string, unknown>,
          aoi: aoiGeometry ?? undefined,
        });
        setResponse(result);
        setQueryHistory((prev) => [query, ...prev].slice(0, 20));
        // Spectral/NL-cover answers carry the raster payload in `analysis` -> map overlay
        const analysis = (result.analysis ?? {}) as Record<string, unknown>;
        if (analysis.preview_b64) {
          setSpectralResult({ ...analysis, scene_id: analysis.scene_id ?? scene.id });
          setSpectralVisible(true);
          setLayerVisibility((prev) => ({ ...prev, analysis: true }));
          setMapMode("analysis");
        } else {
          setMapMode("analysis");
        }
      } catch (err) {
        setError({
          message: "Scene query processing failed",
          details: err instanceof Error ? err.message : String(err),
        });
      } finally {
        setIsLoading(false);
      }
    },
    [aoiGeometry]
  );

  const handleSubmit = useCallback(
    async (query: string) => {
      // Spectral NL routing on a selected/active scene -> unified /api/query (trace + overlay)
      if (isSpectralQuery(query)) {
        const sceneCtx = activeScene ?? selectedScene;
        if (!sceneCtx) {
          setError({ message: "Please select a Sentinel-2 scene first (run a search, pick a footprint, click Query This Image), then ask to calculate an index." });
          setMapMode("gis");
          return;
        }
        if (!aoiGeometry || !isValidGeoJSON(aoiGeometry)) {
          setError({ message: "Please draw an AOI on the map before calculating a spectral index." });
          setMapMode("gis");
          return;
        }
        await runSceneQuery(query, sceneCtx);
        return;
      }
      // GIS retrieval via natural language + AOI
      if (isRetrievalQuery(query) && !images.length) {
        if (!aoiGeometry || !isValidGeoJSON(aoiGeometry)) {
          setError({ message: "Please draw a valid AOI on the map before searching satellite imagery." });
          setMapMode("gis");
          return;
        }
        setError(null);
        setGisLoading(true);
        setGisError(null);
        try {
          // Parse dates/cloud from query if present, else defaults
          const params: Record<string, unknown> = {
            geometry: aoiGeometry,
            start_date: "2026-06-01",
            end_date: "2026-06-30",
            max_cloud_cover: 20,
            sensor: "sentinel-2",
            product: "l2a",
            max_results: 10,
          };
          // Simple extraction for cloud
          const cloudMatch = query.match(/(?:less than|max)\s*(\d{1,3})\s*%?\s*cloud/i);
          if (cloudMatch?.[1]) params.max_cloud_cover = parseFloat(cloudMatch[1]);
          const res = await searchSatellite(params as unknown as Parameters<typeof searchSatellite>[0]);
          setGisScenes(res.scenes || []);
          setGisTrace(res.trace || res.execution_trace || null);
          setSatelliteTrace(res.trace || res.execution_trace || null);
          if (res.scenes?.length) {
            setSelectedScene(res.best_scene ?? res.scenes[0] ?? null);
            // Do not auto-activate; user explicitly picks "Query This Image" per scene.
          }
          setQueryHistory((prev) => [query, ...prev].slice(0, 20));
          setMapMode("gis");
          if (res.count === 0) setGisError("No satellite scenes found for this AOI and date range.");
        } catch (err) {
          setGisError(err instanceof Error ? err.message : String(err));
        } finally {
          setGisLoading(false);
        }
        return;
      }

      // Selected Satellite Image Query Mode — analyze the ACTIVE scene's real assets.
      if (activeScene && images.length === 0) {
        await runSceneQuery(query, activeScene);
        return;
      }

      if (images.length === 0) {
        setError({ message: "Upload at least one image before querying, or select an active satellite scene to query." });
        return;
      }
      setError(null);
      setIsLoading(true);
      setResponse(null);
      try {
        const result = await submitQuery({
          query,
          input_mode: inputMode,
          images: images.map((img) => img.file),
        });
        setResponse(result);
        setQueryHistory((prev) => [query, ...prev].slice(0, 20));
        setMapMode("analysis");
      } catch (err) {
        setError({
          message: "Query processing failed",
          details: err instanceof Error ? err.message : String(err),
        });
      } finally {
        setIsLoading(false);
      }
    },
    [activeScene, images, inputMode, aoiGeometry, runSceneQuery]
  );

  const handleAoiChange = useCallback((geom: Record<string, unknown> | null) => {
    if (!geom) {
      setAoiGeometry(null);
      return;
    }
    if (isValidGeoJSON(geom)) setAoiGeometry(geom);
    else setGisError("Invalid AOI geometry: must be a valid Polygon with [lon, lat] coordinates.");
  }, []);

  const handleSceneSelect = useCallback(
    (id: string) => {
      const all = gisScenes.length ? gisScenes : [];
      const found = all.find((s) => s.id === id) || null;
      if (found) {
        setSelectedScene(found);
        // Active scene switches immediately when another footprint is clicked
        if (activeScene) {
          setActiveScene(found);
          setResponse(null);
          setGisError(null);
        }
      } else {
        // Also check panel's scenes if GIS empty
        setSelectedScene((prev) => (prev?.id === id ? prev : prev));
      }
    },
    [gisScenes, activeScene]
  );

  // Selected Satellite Image Query Mode — explicitly activate a scene for NL analysis.
  const handleActivateScene = useCallback((scene: SatelliteScene) => {
    setSelectedScene(scene);
    setActiveScene(scene);
    setResponse(null);
    setError(null);
    setMapMode("gis");
  }, []);

  const handleClearScene = useCallback(() => {
    setActiveScene(null);
    setResponse(null);
    // Keep the currently selected footprint; user picks a new one to activate.
  }, []);

  // Sync gisScenes with panel's external scenes: panel will call onScenesChange
  const handlePanelScenesChange = useCallback((scenes: SatelliteScene[], trace: Record<string, unknown> | null) => {
    setGisScenes(scenes);
    setGisTrace(trace);
  }, []);

  const handleSpectralResult = useCallback((res: Record<string, unknown> | null) => {
    setSpectralResult(res);
    if (res) {
      setLayerVisibility((prev) => ({ ...prev, analysis: true }));
      setSpectralVisible(true);
      // Ensure map fits to spectral bounds
    } else {
      setPixelInspect(null);
    }
  }, []);

  const handleMapClick = useCallback(
    async (lat: number, lon: number) => {
      if (!spectralResult || !spectralVisible) {
        setPixelInspect({ lat, lon, value: null, loading: false, error: "No spectral layer active — calculate an index first." });
        return;
      }
      const rasterPath = (spectralResult as { raster_path: string })?.raster_path;
      if (!rasterPath) {
        setPixelInspect({ lat, lon, value: null, loading: false, error: "No raster path" });
        return;
      }
      setPixelInspect({ lat, lon, value: null, loading: true });
      try {
        const res = await samplePixel(rasterPath, lon, lat);
        setPixelInspect({ lat, lon, value: res.value, loading: false });
      } catch (e) {
        setPixelInspect({ lat, lon, value: null, loading: false, error: e instanceof Error ? e.message : String(e) });
      }
    },
    [spectralResult, spectralVisible]
  );

  return (
    <div className="h-screen flex flex-col bg-surface-900 overflow-hidden">
      <Header health={health} />

      {error && (
        <div className="flex-shrink-0 mx-4 mt-2 px-4 py-2.5 border border-signal-red/25 bg-signal-red/5 flex items-center gap-3 animate-fade-in rounded-lg">
          <span className="text-signal-red text-xs font-semibold">!</span>
          <span className="text-[13px] text-ink">{error.message}</span>
          {error.details && <span className="text-[11px] text-ink-muted ml-auto truncate max-w-xs">{error.details}</span>}
          <button onClick={() => setError(null)} className="text-[11px] text-ink-muted hover:text-ink transition-colors ml-2">
            Dismiss
          </button>
        </div>
      )}

      {/* Top bar: Search + Map mode toggle */}
      <div className="flex-shrink-0 px-3 pt-2 flex items-center gap-2">
        <div className="flex bg-surface-800 border border-surface-400/40 rounded-lg overflow-hidden">
          <button onClick={() => setMapMode("gis")} className={`px-3 py-1.5 text-[11px] font-medium ${mapMode === "gis" ? "bg-accent/15 text-accent" : "text-ink-muted hover:text-ink"}`}>
            🗺️ GIS Workspace
          </button>
          <button onClick={() => setMapMode("analysis")} className={`px-3 py-1.5 text-[11px] font-medium ${mapMode === "analysis" ? "bg-accent/15 text-accent" : "text-ink-muted hover:text-ink"}`}>
            🛰️ Analysis
          </button>
        </div>
        <span className="text-[11px] text-ink-muted hidden sm:inline">Map is primary visual workspace — AOI, footprints, selected scene, layers.</span>
        <div className="ml-auto flex items-center gap-2 text-[11px] text-ink-muted">
          <span className={`w-2 h-2 rounded-full ${aoiGeometry ? "bg-signal-green" : "bg-signal-red"}`} />
          {aoiGeometry ? "AOI ready" : "No AOI"}
          <span>· {gisScenes.length} scenes</span>
        </div>
      </div>

      <div className="flex-1 flex flex-col lg:flex-row min-h-0 p-3 gap-3 overflow-y-auto lg:overflow-hidden">
        {/* LEFT: Controls */}
        <div className="w-full lg:w-[300px] flex-shrink-0 flex flex-col gap-3 min-h-0 lg:overflow-y-auto">
          <section className="panel flex-shrink-0">
            <div className="panel-header">
              <span className="panel-label">Imagery Input</span>
            </div>
            <div className="panel-body">
              <ImageUploader images={images} setImages={setImages} inputMode={inputMode} setInputMode={setInputMode} />
            </div>
          </section>

          <LayerControl
            visibility={layerVisibility}
            onChange={setLayerVisibility}
            hasAnalysis={!!response || !!spectralResult}
            hasPreview={!!selectedScene?.thumbnail || !!spectralResult}
          />

          {/* Live Satellite Search - now linked to map via lifted state */}
          <div className="flex-shrink-0">
            <button onClick={() => setShowSatellite(!showSatellite)} className="w-full flex items-center justify-between px-3 py-1.5 bg-surface-800 border border-surface-400/40 rounded-lg text-[11px] font-medium text-ink-secondary hover:text-ink transition-colors">
              <span className="tracking-wide">Live Satellite Search</span>
              <span className="text-[10px] text-ink-muted">{showSatellite ? "Hide" : "Show"} • CDSE</span>
            </button>
            {showSatellite && (
              <div className="mt-2">
                <SatelliteSearchPanel
                  selectedScene={selectedScene}
                  setSelectedScene={setSelectedScene}
                  onTrace={setSatelliteTrace}
                  aoiGeometry={aoiGeometry}
                  onAoiChange={handleAoiChange}
                  scenes={gisScenes}
                  onScenesChange={handlePanelScenesChange}
                />
              </div>
            )}
          </div>

          {/* Spectral Index Agent */}
          <SpectralPanel selectedScene={selectedScene} aoiGeometry={aoiGeometry} onResult={handleSpectralResult} onError={setGisError} />

          {queryHistory.length > 0 && (
            <section className="panel flex-shrink-0 flex flex-col max-h-[20vh]">
              <div className="panel-header">
                <span className="panel-label">Query Log</span>
                <span className="tag-muted">{queryHistory.length}</span>
              </div>
              <div className="panel-body overflow-y-auto flex-1 min-h-0">
                <div className="space-y-1">
                  {queryHistory.map((q, i) => (
                    <button key={i} onClick={() => handleSubmit(q)} className="w-full text-left text-[11px] text-ink-secondary px-2 py-1.5 hover:text-ink hover:bg-surface-700/40 transition-colors truncate rounded">
                      <span className="text-accent/40 mr-1.5">{">"}</span>
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            </section>
          )}
        </div>

        {/* CENTER: Map + Results (responsive) */}
        <div className="flex-1 flex flex-col gap-3 min-h-0 min-w-0 w-full">
          {/* GIS Map - primary */}
          <section className={`panel flex-shrink-0 overflow-hidden flex flex-col ${mapMode === "gis" ? "h-[48vh] min-h-[380px]" : "h-[36vh] min-h-[300px]"}`}>
            <div className="panel-header py-2">
              <span className="panel-label">Interactive Map — AOI & Footprints</span>
              <span className="ml-auto text-[10px] text-ink-muted hidden md:inline">Pan / Zoom / Click footprint → select · Draw rectangle/polygon on map</span>
            </div>
            <div className="flex-1 min-h-0 p-2">
              <MapView
                aoiGeometry={aoiGeometry}
                scenes={gisScenes}
                selectedSceneId={selectedScene?.id || null}
                onAoiChange={handleAoiChange}
                onSceneSelect={handleSceneSelect}
                layerVisibility={layerVisibility}
                drawMode={drawMode}
                onDrawModeChange={setDrawMode}
                spectralLayer={
                  spectralResult
                    ? {
                        preview_b64: (spectralResult as { preview_b64?: string }).preview_b64 || null,
                        bounds: (spectralResult as { bounds?: [[number, number], [number, number]] }).bounds || null,
                        opacity: spectralOpacity,
                        visible: spectralVisible && layerVisibility.analysis,
                        index: (spectralResult as { index?: string }).index || "NDVI",
                      }
                    : null
                }
                onMapClick={handleMapClick}
              />
            </div>
            {/* Map status bar */}
            <div className="px-3 py-1.5 border-t border-surface-400/20 bg-surface-800/50 flex items-center gap-2 text-[11px]">
              {gisLoading ? (
                <span className="text-accent">Searching satellite data…</span>
              ) : gisError ? (
                <span className="text-signal-red">{gisError}</span>
              ) : gisScenes.length > 0 ? (
                <span className="text-signal-green">✓ {gisScenes.length} scenes · Click footprint or card to select</span>
              ) : aoiGeometry ? (
                <span className="text-ink-muted">AOI ready — run search to see footprints</span>
              ) : (
                <span className="text-ink-muted">Draw a rectangle or polygon AOI to start</span>
              )}
              <span className="ml-auto flex gap-1">
                <button onClick={() => setAoiGeometry(null)} className="px-2 py-1 rounded border border-surface-400/30 text-[11px] text-ink-muted hover:text-signal-red">Clear AOI</button>
                <button onClick={() => setDrawMode(drawMode ? null : "rectangle")} className={`px-2 py-1 rounded border text-[11px] ${drawMode ? "bg-accent text-surface-900 border-accent" : "border-surface-400/30 text-ink-muted hover:text-ink"}`}>
                  {drawMode ? "Cancel Draw" : "Draw AOI"}
                </button>
              </span>
            </div>
            {/* Spectral layer controls */}
            {spectralResult && (
              <div className="px-3 py-2 border-t border-surface-400/20 bg-surface-800/30 flex flex-col gap-2">
                <div className="flex items-center gap-2 text-[11px]">
                  <span className="font-semibold text-accent">{(spectralResult as { index: string }).index} Layer</span>
                  <span className="text-ink-muted">{(spectralResult as { stats: { mean: number } }).stats.mean.toFixed(3)} mean · {(spectralResult as { stats: { valid_pct: number } }).stats.valid_pct.toFixed(1)}% valid</span>
                  <span className="ml-auto flex items-center gap-2">
                    <label className="flex items-center gap-1 text-[11px] text-ink-muted">
                      <input type="checkbox" checked={spectralVisible} onChange={(e) => setSpectralVisible(e.target.checked)} className="accent-accent" />
                      Visible
                    </label>
                    <input type="range" min={0} max={100} value={spectralOpacity * 100} onChange={(e) => setSpectralOpacity(parseInt(e.target.value) / 100)} className="w-20" title="Opacity" />
                    <span className="text-[10px] text-ink-muted">{Math.round(spectralOpacity * 100)}%</span>
                    <button onClick={() => setSpectralResult(null)} className="px-2 py-1 rounded border border-surface-400/30 text-[11px] text-ink-muted hover:text-signal-red">Remove</button>
                  </span>
                </div>
                <div className="flex gap-2">
                  <SpectralLegend
                    index={(spectralResult as { index: string }).index}
                    visual={(spectralResult as { visual: Record<string, unknown> }).visual || {}}
                    interpretation={(spectralResult as { interpretation: Record<string, unknown> }).interpretation || {}}
                  />
                </div>
              </div>
            )}
            {/* Pixel inspect */}
            {pixelInspect && (
              <div className="px-3 py-1.5 border-t border-surface-400/20 bg-surface-800/50 text-[11px]">
                {pixelInspect.loading ? (
                  <span className="text-accent">Sampling pixel…</span>
                ) : pixelInspect.error ? (
                  <span className="text-signal-red">{pixelInspect.error}</span>
                ) : (
                  <span className="text-ink">
                    Pixel: <span className="font-mono">{pixelInspect.lat.toFixed(5)}, {pixelInspect.lon.toFixed(5)}</span> →{" "}
                    <span className="font-semibold text-accent">{pixelInspect.value != null ? (pixelInspect.value as number).toFixed(3) : "nodata/masked"}</span>
                    {spectralResult && <span className="text-ink-muted"> · {(spectralResult as { index: string }).index} · {(spectralResult as { scene_id: string }).scene_id.slice(0, 20)}</span>}
                  </span>
                )}
                <button onClick={() => setPixelInspect(null)} className="ml-2 text-[10px] text-ink-muted hover:text-ink">Dismiss</button>
              </div>
            )}
          </section>

          {/* Scene cards below map - synced */}
          {gisScenes.length > 0 && (
            <section className="panel flex-shrink-0 max-h-[26vh] overflow-y-auto">
              <div className="panel-body p-3">
                <SceneCards scenes={gisScenes} selectedId={selectedScene?.id || null} onSelect={handleSceneSelect} />
              </div>
            </section>
          )}

          {/* Existing Imagery Viewer - collapses on GIS mode but remains for analysis mode */}
          <div className={mapMode === "gis" ? "hidden lg:flex flex-col gap-3" : "flex flex-col gap-3"}>
            <ImageryViewer images={images} inputMode={inputMode} evidence={response?.evidence ?? []} />
            {response && (
              <section className="panel flex-shrink-0 max-h-[32vh] overflow-y-auto animate-slide-up">
                <div className="panel-header">
                  <span className="panel-label">Intelligence Result</span>
                  <div className="flex-1" />
                  <span className="text-[11px] font-medium text-signal-green/80">Received</span>
                </div>
                <div className="panel-body">
                  <ResultsPanel response={response} />
                </div>
              </section>
            )}
          </div>
        </div>

        {/* RIGHT: Telemetry */}
        <div className="w-full lg:w-[300px] flex-shrink-0 flex flex-col gap-3 min-h-0 lg:overflow-y-auto">
          {/* Scene metadata - primary in GIS */}
          <SceneMetadataPanel scene={selectedScene} onSelectForAnalysis={handleActivateScene} />

          {/* Selected scene banner legacy (keep for trace continuity, hidden if metadata shows) */}
          {selectedScene && (
            <section className="panel flex-shrink-0 border-accent/20 hidden">
              <div className="panel-header">
                <span className="panel-label">Selected Scene</span>
                <span className="tag-muted truncate max-w-[160px]">{selectedScene.id.slice(0, 22)}…</span>
              </div>
              <div className="panel-body space-y-1 text-[11px]">
                <div className="text-ink-secondary truncate">{selectedScene.datetime ? new Date(selectedScene.datetime).toLocaleString() : "—"}</div>
                <div className="text-[10px] text-ink-muted">cloud {selectedScene.cloud_cover?.toFixed(1) ?? "—"}% • coverage {selectedScene.coverage?.toFixed(1) ?? "—"}% • score {selectedScene.selection_score?.toFixed(3) ?? "—"}</div>
                <div className="text-[10px] text-ink-muted">→ Ready for VQA / Change / Counting (assets via scene.assets)</div>
                <button onClick={() => setSelectedScene(null)} className="text-[10px] text-signal-red/70 hover:text-signal-red">
                  Clear
                </button>
              </div>
            </section>
          )}
          {satelliteTrace && !response && (
            <section className="panel flex-shrink-0">
              <div className="panel-header">
                <span className="panel-label">Retrieval Trace</span>
              </div>
              <div className="panel-body text-[10px] font-mono text-ink-muted break-words">
                <div>provider: CDSE</div>
                <div>collection: {String((satelliteTrace as Record<string, unknown>)?.["collection"] ?? "sentinel-2-l2a")}</div>
                <div>results: {String((satelliteTrace as Record<string, unknown>)?.["results_found"] ?? "—")}</div>
                <div>best: {String((satelliteTrace as Record<string, unknown>)?.["selected_scene"] ?? "—")}</div>
                {(gisTrace || satelliteTrace) && <div className="mt-1 text-accent">Map: {gisScenes.length} footprints · AOI {aoiGeometry ? "✓" : "—"}</div>}
              </div>
            </section>
          )}
          <ExecutionTracePanel trace={response?.execution_trace ?? null} />
          {response && (
            <section className="panel flex-shrink-0 animate-slide-up">
              <div className="panel-header">
                <span className="panel-label">Confidence</span>
              </div>
              <div className="panel-body">
                <ConfidenceGauge confidence={response.confidence} />
              </div>
            </section>
          )}
          <section className="panel flex-1 min-h-0 flex flex-col">
            <div className="panel-header">
              <span className="panel-label">System Status</span>
              <span className="ml-auto tag-muted flex items-center gap-1.5">
                <span className={`w-1.5 h-1.5 rounded-full ${health?.status === "offline" ? "bg-signal-red" : "bg-signal-green"}`} />
                {health?.force_cpu ? "CPU-ONLY" : health?.compute?.toUpperCase() ?? "CPU"}
              </span>
            </div>
            <div className="panel-body flex-1 overflow-y-auto">
              <div className="space-y-2.5">
                <StatusRow label="Controller" status={health?.status === "offline" ? "error" : "online"} />
                <StatusRow label="VQA Module" status={health?.status === "offline" ? "error" : "online"} detail={health?.adapter_path ? health.adapter_path.split("/").pop() : undefined} />
                <StatusRow label="Change Detection" status="online" />
                <StatusRow label="Grounding Engine" status="online" />
                <StatusRow label="SAR Fusion" status="standby" />
                <StatusRow label={health?.force_cpu ? "Compute · CPU-ONLY" : "Compute"} status={health?.status === "offline" ? "error" : "online"} detail={health?.device ?? (health?.force_cpu ? "cpu" : "auto")} />
                <StatusRow label="GIS Map" status={aoiGeometry ? "online" : "standby"} detail={aoiGeometry ? "AOI set" : "draw AOI"} />
              </div>
            </div>
          </section>
        </div>
      </div>

      <div className="flex-shrink-0 border-t border-surface-400/40 bg-surface-800/90 px-5 py-3.5">
        <div className="max-w-[1400px] mx-auto">
          <div className="mb-2.5">
            <ActiveSceneContext scene={activeScene} onClear={handleClearScene} onActivate={handleActivateScene} />
          </div>
          <QueryInput onSubmit={handleSubmit} disabled={isLoading || gisLoading} activeScene={activeScene} />
        </div>
      </div>

      <LoadingOverlay visible={isLoading || gisLoading} />
    </div>
  );
}

function StatusRow({ label, status, detail }: { label: string; status: "online" | "standby" | "error" | "mock"; detail?: string }) {
  const colors = {
    online: "bg-signal-green",
    standby: "bg-signal-amber",
    error: "bg-signal-red",
    mock: "bg-ink-muted",
  };
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <span className={`w-1.5 h-1.5 rounded-full ${colors[status]}`} />
        <span className="text-[12px] text-ink-secondary">{label}</span>
      </div>
      <div className="flex items-center gap-1.5">
        {detail && <span className="text-[10px] text-ink-muted">{detail}</span>}
        <span className={`text-[10px] uppercase ${status === "error" ? "text-signal-red" : "text-ink-muted"}`}>{status}</span>
      </div>
    </div>
  );
}
