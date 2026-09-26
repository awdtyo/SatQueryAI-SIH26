import { useState, useCallback } from "react";
import type {
  AppError,
  InputMode,
  QueryActivity,
  QueryResponse,
  UploadedImage,
} from "./types/api";
import { submitQuery } from "./api/mockClient";
import { useMissionStatus } from "./hooks/useMissionStatus";
import Header from "./components/Header";
import ImageUploader from "./components/ImageUploader";
import LocationSearchInput from "./components/LocationSearchInput";
import ImageryViewer from "./components/ImageryViewer";
import QueryBar from "./components/QueryBar";
import QueryLogAccordion from "./components/QueryLogAccordion";
import ResultOverlay from "./components/ResultOverlay";
import ExecutionTracePanel from "./components/ExecutionTrace";
import ConfidenceRing from "./components/ConfidenceRing";
import SystemStatusPanel from "./components/SystemStatusPanel";
import LoadingOverlay from "./components/LoadingOverlay";
import { Panel, PanelHeader, PanelTitle } from "./components/ui/Panel";
import { AlertIcon, CloseIcon, LayersIcon, SearchIcon } from "./components/ui/Icons";

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

function ErrorBanner({ error, onDismiss }: { error: AppError; onDismiss: () => void }) {
  return (
    <div
      role="alert"
      className="mx-4 mt-4 flex flex-shrink-0 animate-fade-in items-center gap-3 rounded-lg border border-rose-500/25 bg-rose-500/5 px-4 py-2.5"
    >
      <AlertIcon className="h-4 w-4 flex-shrink-0 text-rose-400" />
      <span className="text-[13px] text-slate-200">{error.message}</span>
      {error.details && (
        <span className="ml-auto max-w-xs truncate text-[11px] text-slate-500">
          {error.details}
        </span>
      )}
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss error"
        className="flex-shrink-0 rounded p-1 text-slate-500 transition-colors duration-150 hover:text-slate-200"
      >
        <CloseIcon className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

export default function App() {
  const { health } = useMissionStatus();
  const [images, setImages] = useState<UploadedImage[]>([]);
  const [inputMode, setInputMode] = useState<InputMode>("single");
  const [inputSource, setInputSource] = useState<"upload" | "location">("upload");
  const [locationQuery, setLocationQuery] = useState("");
  const [locationQuery2, setLocationQuery2] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [activity, setActivity] = useState<QueryActivity | null>(null);
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [error, setError] = useState<AppError | null>(null);
  const [queryHistory, setQueryHistory] = useState<string[]>([]);
  const [pendingQuery, setPendingQuery] = useState("");
  const [isResultOpen, setIsResultOpen] = useState(true);

  const handleSubmit = useCallback(
    async (query: string) => {
      setPendingQuery(query);
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
      setActivity(null);
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

        // onActivity reports only real transport signals (SSE frames / request lifecycle)
        const result = await submitQuery(req, (next) => setActivity(next));

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
        setIsResultOpen(true);
        setQueryHistory((prev) => [query, ...prev].slice(0, 20));
      } catch (err) {
        setError({
          message: "Query processing failed",
          details: err instanceof Error ? err.message : String(err),
        });
      } finally {
        setIsLoading(false);
        setActivity(null);
      }
    },
    [images, inputMode, inputSource, locationQuery, locationQuery2],
  );

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-slate-950 text-slate-200">
      <Header health={health} />

      {error && <ErrorBanner error={error} onDismiss={() => setError(null)} />}

      {/* Three-column workspace — stacks below the lg breakpoint */}
      <main className="scroll-y flex min-h-0 flex-1 flex-col gap-4 p-4 lg:flex-row lg:overflow-hidden">
        {/* LEFT: Imagery input + query log */}
        <div className="flex flex-col gap-4 lg:h-full lg:min-h-0 lg:w-[320px] lg:flex-shrink-0 lg:overflow-y-auto" data-morph="imagery-input">
          <Panel>
            <PanelHeader>
              <PanelTitle>Imagery Input</PanelTitle>
              <div className="flex-1" />
              <span className="chip-muted">
                {inputSource === "location" ? "Location" : "Upload"}
              </span>
            </PanelHeader>
            <div className="space-y-5 p-4">
              <LocationSearchInput
                inputMode={inputMode}
                locationQuery={locationQuery}
                setLocationQuery={setLocationQuery}
                locationQuery2={locationQuery2}
                setLocationQuery2={setLocationQuery2}
                inputSource={inputSource}
                setInputSource={setInputSource}
              />

              <div className="divider" />

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
                <p className="flex items-start gap-1.5 text-[11px] leading-relaxed text-emerald-400/90">
                  <SearchIcon className="mt-0.5 h-3 w-3 flex-shrink-0" />
                  Location preview: {images.length} fetched image(s) in the viewer → used on the
                  next query while location mode stays active.
                </p>
              )}
            </div>
          </Panel>

          {queryHistory.length > 0 && (
            <Panel className="flex-shrink-0">
              <PanelHeader>
                <PanelTitle>Query Log</PanelTitle>
                <div className="flex-1" />
                <span className="chip-muted">{queryHistory.length}</span>
              </PanelHeader>
              <div className="scroll-y max-h-80 p-3">
                <QueryLogAccordion
                  queries={queryHistory}
                  onRun={handleSubmit}
                  disabled={isLoading}
                />
              </div>
            </Panel>
          )}
        </div>

        {/* CENTER: Satellite viewport with the floating result overlay */}
        <div
          data-morph="imagery"
          className="relative flex min-h-[26rem] min-w-0 flex-1 flex-col lg:min-h-0"
        >
          <ImageryViewer
            images={images}
            inputMode={inputMode}
            evidence={response?.evidence ?? []}
            analyzing={isLoading}
          />

          {response && isResultOpen && (
            <ResultOverlay response={response} onClose={() => setIsResultOpen(false)} />
          )}

          {response && !isResultOpen && (
            <button
              type="button"
              onClick={() => setIsResultOpen(true)}
              className="btn absolute right-4 top-14 z-20 gap-1.5 border border-slate-800 bg-slate-900/80 px-3 py-2 text-teal-300 shadow-lg backdrop-blur-md hover:border-teal-500/40"
            >
              <LayersIcon className="h-3.5 w-3.5" />
              Intelligence Result
            </button>
          )}
        </div>

        {/* RIGHT: Execution trace, confidence, system status */}
        <div className="flex flex-col gap-4 lg:h-full lg:min-h-0 lg:w-[320px] lg:flex-shrink-0 lg:overflow-hidden">
          <div data-morph="trace" className="flex min-h-0 flex-1 flex-col">
            <ExecutionTracePanel
              trace={response?.execution_trace ?? null}
              analyzing={isLoading}
            />
          </div>

          {response && (
            <Panel className="flex-shrink-0 animate-slide-up">
              <PanelHeader>
                <PanelTitle>Confidence</PanelTitle>
              </PanelHeader>
              <div className="panel-body flex justify-center">
                <ConfidenceRing value={response.confidence} />
              </div>
            </Panel>
          )}

          <div data-morph="status" className="flex min-h-0 flex-1 flex-col">
            <SystemStatusPanel />
          </div>
        </div>
      </main>

      {/* Bottom: analysis query terminal */}
      <QueryBar onSubmit={handleSubmit} disabled={isLoading} />

      {/* Mounted only while a request is in flight so the stage sequence restarts cleanly. */}
      {isLoading && (
        <LoadingOverlay
          visible={isLoading}
          query={pendingQuery}
          activity={activity}
          inputMode={inputMode}
          imageCount={images.length}
          response={response}
        />
      )}
    </div>
  );
}
