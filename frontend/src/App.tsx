import { useState, useCallback, useEffect } from "react";
import type { InputMode, QueryResponse, UploadedImage, AppError, HealthState } from "./types/api";
import { submitQuery, checkHealth } from "./api/mockClient";
import Header from "./components/Header";
import ImageUploader from "./components/ImageUploader";
import LocationSearchInput from "./components/LocationSearchInput";
import ImageryViewer from "./components/ImageryViewer";
import QueryBar from "./components/QueryBar";
import ResultOverlay, { ShowResultButton } from "./components/ResultOverlay";
import QueryLogAccordion from "./components/QueryLogAccordion";
import ExecutionTracePanel from "./components/ExecutionTrace";
import SystemStatusPanel from "./components/SystemStatusPanel";
import ImagerySourceCard from "./components/ImagerySourceCard";
import Panel from "./components/ui/Panel";
import ConfidenceRing from "./components/ui/ConfidenceRing";
import LoadingOverlay from "./components/LoadingOverlay";
import IntroSequence from "./components/IntroSequence";

type DrawerSide = "left" | "right" | null;

/**
 * `inert` is a standard boolean attribute but is not in the React 18 type
 * definitions, so it is spread in untyped. When set, the subtree is neither
 * focusable nor clickable, which is what an inactive panel needs.
 */
function inertWhen(inactive: boolean): Record<string, unknown> {
  return inactive ? { inert: "" } : {};
}

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
  const [drawer, setDrawer] = useState<DrawerSide>(null);
  const [showResult, setShowResult] = useState(true);
  // Boot gate: the intro owns the screen until it hands over, then the
  // dashboard mounts fresh and plays its entry transition exactly once.
  const [booted, setBooted] = useState(false);
  const finishBoot = useCallback(() => setBooted(true), []);

  // Health polling starts only once the dashboard is on screen.
  useEffect(() => {
    if (!booted) return;
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
  }, [booted]);

  // Close the stacked sidebar when the viewport grows past the 3-column breakpoint.
  useEffect(() => {
    const query = window.matchMedia("(min-width: 1280px)");
    const handleChange = (event: MediaQueryListEvent | MediaQueryList) => {
      if (event.matches) setDrawer(null);
    };
    handleChange(query);
    query.addEventListener("change", handleChange);
    return () => query.removeEventListener("change", handleChange);
  }, []);

  // Escape closes the stacked sidebar.
  useEffect(() => {
    if (!drawer) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawer(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [drawer]);

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
      setShowResult(true);

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
              // Carry the backend's real STAC provenance forward so the HUD and
              // the data-source card can show collection / scene id / centroid.
              const meta = {
                collection: ri.collection,
                scene_id: ri.scene_id,
                display_name: ri.display_name,
                lat: ri.lat,
                lon: ri.lon,
                bbox: ri.bbox,
              };
              return { file, preview, label, role, meta };
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

  const leftColumn = (
    <>
      <Panel
        label="Imagery Input"
        className="flex-shrink-0"
        action={
          <span className="tag-muted">{inputSource === "location" ? "LOCATION" : "UPLOAD"}</span>
        }
      >
        <div className="space-y-4">
          <LocationSearchInput
            inputMode={inputMode}
            locationQuery={locationQuery}
            setLocationQuery={setLocationQuery}
            locationQuery2={locationQuery2}
            setLocationQuery2={setLocationQuery2}
            inputSource={inputSource}
            setInputSource={setInputSource}
          />
          {/* The uploader stays mounted for layout, but Location mode sends only a
              location, so it is inert — a file dropped here would be displayed
              without ever reaching the backend. */}
          <div
            className={inputSource === "location" ? "pointer-events-none select-none opacity-60" : ""}
            {...inertWhen(inputSource === "location")}
          >
            <ImageUploader
              images={images}
              setImages={setImages}
              inputMode={inputMode}
              setInputMode={setInputMode}
            />
          </div>
          {inputSource === "location" && images.length > 0 && (
            <p className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-2.5 text-[11px] leading-relaxed text-emerald-400">
              Location preview: {images.length} fetched image(s) shown in the viewer — they will be
              reused if you stay in location mode.
            </p>
          )}
        </div>
      </Panel>

      {/* Provenance for whatever is actually loaded — real values only. */}
      <ImagerySourceCard
        images={images}
        inputMode={inputMode}
        inputSource={inputSource}
        health={health}
      />

      {/* Query history */}
      {queryHistory.length > 0 && (
        <Panel
          label="Query Log"
          className="flex-1"
          action={<span className="tag-muted tabular-nums">{queryHistory.length}</span>}
        >
          <QueryLogAccordion
            queries={queryHistory}
            onReplay={handleSubmit}
            disabled={isLoading}
          />
        </Panel>
      )}
    </>
  );

  const rightColumn = (
    <>
      <ExecutionTracePanel
        trace={response?.execution_trace ?? null}
        isRunning={isLoading}
        health={health}
      />

      {/* Confidence — always visible when response exists */}
      {response && (
        <Panel label="Confidence" className="flex-shrink-0 animate-slide-up">
          <div className="flex justify-center py-2">
            <ConfidenceRing value={response.confidence} />
          </div>
        </Panel>
      )}

      <SystemStatusPanel health={health} isRunning={isLoading} trace={response?.execution_trace ?? null} />
    </>
  );

  if (!booted) {
    return <IntroSequence onDone={finishBoot} />;
  }

  return (
    <>
      <div className="flex h-screen flex-col overflow-hidden bg-slate-950">
        <div className="dash-in-header flex flex-shrink-0 flex-col">
          <Header health={health} isRunning={isLoading} onOpenPanel={setDrawer} />
        </div>

        {/* Error banner — inline below header */}
        {error && (
          <div
            role="alert"
            className="mx-4 mt-3 flex flex-shrink-0 animate-fade-in items-center gap-3 rounded-lg border border-rose-500/25 bg-rose-500/5 px-4 py-2.5"
          >
            <span className="text-xs font-semibold text-rose-400" aria-hidden="true">
              !
            </span>
            <span className="text-[13px] text-slate-200">{error.message}</span>
            {error.details && (
              <span className="ml-auto max-w-xs truncate text-[11px] text-slate-500">
                {error.details}
              </span>
            )}
            <button
              type="button"
              onClick={() => setError(null)}
              className="ml-2 rounded text-[11px] text-slate-500 transition-colors hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/50"
            >
              Dismiss
            </button>
          </div>
        )}

          {/* Three-column workspace — each column scrolls independently */}
          <div className="flex min-h-0 flex-1 gap-4 p-4">
            {/* LEFT: Imagery input + query log */}
            <div className="dash-in-l hidden w-[320px] flex-shrink-0 flex-col gap-4 overflow-y-auto xl:flex">
              {leftColumn}
            </div>

            {/* CENTER: Imagery viewport + floating result overlay */}
            <main className="dash-in-center flex min-h-0 min-w-0 flex-1 flex-col">
            <ImageryViewer
              images={images}
              inputMode={inputMode}
              evidence={response?.evidence ?? []}
              isRunning={isLoading}
              hasResponse={response !== null}
              overlay={
                !response ? null : showResult ? (
                  <ResultOverlay response={response} onClose={() => setShowResult(false)} />
                ) : (
                  <ShowResultButton onClick={() => setShowResult(true)} />
                )
              }
            />
          </main>

          {/* RIGHT: Execution trace + system status */}
          <div className="dash-in-r hidden w-[340px] flex-shrink-0 flex-col gap-4 xl:flex">
            {rightColumn}
          </div>
        </div>

        {/* Bottom: analysis query bar */}
        <div className="dash-in-bar flex-shrink-0 border-t border-slate-800 bg-slate-900 px-4 py-3 sm:px-5">
          <QueryBar onSubmit={handleSubmit} disabled={isLoading} />
        </div>

        {/* Stacked sidebars below the xl breakpoint */}
        {drawer && (
          <div className="fixed inset-0 z-40 xl:hidden">
            <button
              type="button"
              aria-label="Close panel"
              onClick={() => setDrawer(null)}
              className="absolute inset-0 h-full w-full cursor-default bg-slate-950/70 backdrop-blur-sm"
            />
            <div
              role="dialog"
              aria-modal="true"
              aria-label={drawer === "left" ? "Imagery input and query log" : "Execution trace and system status"}
              className={`absolute inset-y-0 flex w-[min(88vw,360px)] flex-col gap-4 overflow-y-auto bg-slate-950 px-4 pb-4 pt-14 ${
                drawer === "left"
                  ? "left-0 animate-slide-in-left border-r border-slate-800"
                  : "right-0 animate-slide-in-right border-l border-slate-800"
              }`}
            >
              <button
                type="button"
                onClick={() => setDrawer(null)}
                aria-label="Close panel"
                className="icon-btn absolute right-3 top-3 h-8 w-8 z-10"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                  <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
                </svg>
              </button>
              {drawer === "left" ? leftColumn : rightColumn}
            </div>
          </div>
        )}

          <LoadingOverlay visible={isLoading} health={health} />
        </div>
    </>
  );
}
