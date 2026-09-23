import { useState, useCallback, useEffect } from "react";
import type { InputMode, QueryResponse, UploadedImage, AppError } from "./types/api";
import { submitQuery, checkHealth } from "./api/mockClient";
import Header from "./components/Header";
import ImageUploader from "./components/ImageUploader";
import LocationSearchInput from "./components/LocationSearchInput";
import ImageryViewer from "./components/ImageryViewer";
import QueryInput from "./components/QueryInput";
import ResultsPanel from "./components/ResultsPanel";
import ExecutionTracePanel from "./components/ExecutionTrace";
import ConfidenceGauge from "./components/ConfidenceGauge";
import LoadingOverlay from "./components/LoadingOverlay";

type HealthState = {
  status: string;
  compute?: string;
  device?: string;
  force_cpu?: boolean;
  adapter_path?: string;
  specialists?: Record<string, unknown>;
} | null;

function dataUrlToFile(dataUrl: string, filename: string): File {
  const [header, b64] = dataUrl.split(",");
  const mime = header?.match(/:(.*?);/)?.[1] || "image/png";
  const bin = atob(b64 || "");
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new File([bytes], filename, { type: mime });
}

function parseLatLonInput(s: string): { lat: number; lon: number } | null {
  const m = s.trim().match(/^\s*([+-]?\d+(?:\.\d+)?)\s*[, ]\s*([+-]?\d+(?:\.\d+)?)\s*$/);
  if (!m) return null;
  const lat = parseFloat(m[1]!);
  const lon = parseFloat(m[2]!);
  if (isNaN(lat) || isNaN(lon)) return null;
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null;
  return { lat, lon };
}

export default function App() {
  const [images, setImages] = useState<UploadedImage[]>([]);
  const [inputMode, setInputMode] = useState<InputMode>("single");
  const [inputSource, setInputSource] = useState<"upload" | "location">("upload");
  const [locationQuery, setLocationQuery] = useState("");
  const [locationQuery2, setLocationQuery2] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [error, setError] = useState<AppError | null>(null);
  const [queryHistory, setQueryHistory] = useState<string[]>([]);
  const [health, setHealth] = useState<HealthState>(null);

  // Poll backend health for CPU badge + system status
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

  const handleSubmit = useCallback(
    async (query: string) => {
      const isLocation = inputSource === "location";
      const hasUpload = images.length > 0;
      const hasLocation = locationQuery.trim().length > 0 || parseLatLonInput(locationQuery) !== null;

      if (isLocation) {
        if (!hasLocation) {
          setError({ message: "Enter a place name or lat,lon before querying (or switch to Upload)." });
          return;
        }
        // Bi-temporal needs only one location if second empty (server will fetch 2 dates)
      } else {
        if (!hasUpload) {
          setError({ message: "Upload at least one image before querying (or switch to Search by location)." });
          return;
        }
      }

      setError(null);
      setIsLoading(true);
      setResponse(null);

      try {
        // Build request — location path resolves server-side via Nominatim + Planetary Computer
        const req: Parameters<typeof submitQuery>[0] = {
          query,
          input_mode: inputMode,
          images: isLocation ? [] : images.map((img) => img.file),
        };
        if (isLocation) {
          const c1 = parseLatLonInput(locationQuery);
          if (c1) {
            req.coordinates = c1;
          } else {
            req.location_query = locationQuery.trim();
          }
          if (inputMode === "bi-temporal" && locationQuery2.trim()) {
            const c2 = parseLatLonInput(locationQuery2);
            if (c2) req.coordinates_2 = c2;
            else req.location_query_2 = locationQuery2.trim();
          }
        }

        const result = await submitQuery(req);

        // If location was used, show fetched imagery in viewer (same as uploaded)
        if (isLocation && result.resolved_images && result.resolved_images.length > 0) {
          const newImages: UploadedImage[] = result.resolved_images
            .filter((ri) => ri.preview_b64)
            .map((ri, idx) => {
              const label = ri.display_name || ri.scene_id || `Location ${idx + 1}`;
              const filename = `location_${(ri.lat ?? 0).toFixed(4)}_${(ri.lon ?? 0).toFixed(4)}.png`;
              let file: File;
              let preview: string;
              try {
                file = dataUrlToFile(ri.preview_b64!, filename);
                preview = ri.preview_b64!;
              } catch {
                // Fallback: create a 1x1 placeholder
                const blob = new Blob([], { type: "image/png" });
                file = new File([blob], filename, { type: "image/png" });
                preview = ri.preview_b64!;
              }
              const role =
                inputMode === "optical-sar"
                  ? idx === 0
                    ? "optical"
                    : "sar"
                  : inputMode === "bi-temporal"
                    ? idx === 0
                      ? "t1"
                      : "t2"
                    : undefined;
              return { file, preview, label, role };
            });
          if (newImages.length > 0) setImages(newImages);
        }

        setResponse(result);
        setQueryHistory((prev) => [query, ...prev].slice(0, 20));
      } catch (err) {
        setError({
          message: "Query processing failed",
          details: err instanceof Error ? err.message : String(err),
        });
      } finally {
        setIsLoading(false);
      }
    },
    [images, inputMode, inputSource, locationQuery, locationQuery2],
  );

  return (
    <div className="h-screen flex flex-col bg-surface-900 overflow-hidden">
      <Header health={health} />

      {/* Error banner — inline below header */}
      {error && (
        <div className="flex-shrink-0 mx-4 mt-2 px-4 py-2.5 border border-signal-red/25 bg-signal-red/5 flex items-center gap-3 animate-fade-in rounded-lg">
          <span className="text-signal-red text-xs font-semibold">!</span>
          <span className="text-[13px] text-ink">{error.message}</span>
          {error.details && (
            <span className="text-[11px] text-ink-muted ml-auto truncate max-w-xs">{error.details}</span>
          )}
          <button
            onClick={() => setError(null)}
            className="text-[11px] text-ink-muted hover:text-ink transition-colors ml-2"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Three-zone workspace */}
      <div className="flex-1 flex min-h-0 p-3 gap-3">
        {/* LEFT: Data Ingestion (~18-20%) */}
        <div className="w-[280px] flex-shrink-0 flex flex-col gap-3 min-h-0">
          <section className="panel flex-shrink-0">
            <div className="panel-header">
              <span className="panel-label">Imagery Input</span>
              <span className="ml-auto tag-muted text-[10px]">{inputSource === "location" ? "LOCATION" : "UPLOAD"}</span>
            </div>
            <div className="panel-body space-y-4">
              <LocationSearchInput
                inputMode={inputMode}
                locationQuery={locationQuery}
                setLocationQuery={setLocationQuery}
                locationQuery2={locationQuery2}
                setLocationQuery2={setLocationQuery2}
                inputSource={inputSource}
                setInputSource={setInputSource}
              />
              {/* Show uploader only when source is upload, or as secondary when location */}
              <div className={inputSource === "location" ? "opacity-60" : ""}>
                <ImageUploader
                  images={images}
                  setImages={setImages}
                  inputMode={inputMode}
                  setInputMode={setInputMode}
                />
              </div>
              {inputSource === "location" && images.length > 0 && (
                <p className="text-[11px] text-signal-green">Location preview: {images.length} fetched image(s) shown in viewer → will be used on next query if you stay in location mode.</p>
              )}
            </div>
          </section>

          {/* Query history — compact */}
          {queryHistory.length > 0 && (
            <section className="panel flex-1 min-h-0 flex flex-col">
              <div className="panel-header">
                <span className="panel-label">Query Log</span>
                <span className="tag-muted">{queryHistory.length}</span>
              </div>
              <div className="panel-body overflow-y-auto flex-1 min-h-0">
                <div className="space-y-1">
                  {queryHistory.map((q, i) => (
                    <button
                      key={i}
                      onClick={() => handleSubmit(q)}
                      className="w-full text-left text-[11px] text-ink-secondary px-2 py-1.5 hover:text-ink hover:bg-surface-700/40 transition-colors truncate rounded"
                    >
                      <span className="text-accent/40 mr-1.5">{">"}</span>
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            </section>
          )}
        </div>

        {/* CENTER: Imagery Viewer + Results (~55-60%) */}
        <div className="flex-1 flex flex-col gap-3 min-h-0 min-w-0">
          <ImageryViewer
            images={images}
            inputMode={inputMode}
            evidence={response?.evidence ?? []}
          />

          {/* Intelligence output below viewer — bullets+charts (62vh as selected) */}
          {response && (
            <section className="panel flex-shrink-0 max-h-[62vh] overflow-y-auto animate-slide-up">
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

        {/* RIGHT: Analysis / Telemetry (~22-25%) */}
        <div className="w-[300px] flex-shrink-0 flex flex-col gap-3 min-h-0">
          <ExecutionTracePanel trace={response?.execution_trace ?? null} />

          {/* Confidence — always visible when response exists */}
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

          {/* System status — CPU-only badge driven by backend health */}
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
                 <StatusRow
                   label="VQA Module"
                   status={health?.status === "offline" ? "error" : "online"}
                   detail={health?.adapter_path ? health.adapter_path.split("/").pop() : undefined}
                 />
                 <StatusRow label="Change Detection" status="online" />
                 <StatusRow label="Grounding Engine" status="online" />
                 <StatusRow label="SAR Fusion" status="standby" />
                 <StatusRow
                   label={health?.force_cpu ? "Compute · CPU-ONLY" : "Compute"}
                   status={health?.status === "offline" ? "error" : "online"}
                   detail={health?.device ?? (health?.force_cpu ? "cpu" : "auto")}
                 />
               </div>
             </div>
           </section>
        </div>
      </div>

      {/* Bottom: Analysis Query Terminal */}
      <div className="flex-shrink-0 border-t border-surface-400/40 bg-surface-800/90 px-5 py-3.5">
        <QueryInput onSubmit={handleSubmit} disabled={isLoading} />
      </div>

      <LoadingOverlay visible={isLoading} />
    </div>
  );
}

/* ─── Inlined sub-components ─── */

function StatusRow({
  label,
  status,
  detail,
}: {
  label: string;
  status: "online" | "standby" | "error" | "mock";
  detail?: string;
}) {
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
        <span className={`text-[10px] uppercase ${status === "error" ? "text-signal-red" : "text-ink-muted"}`}>
          {status}
        </span>
      </div>
    </div>
  );
}
