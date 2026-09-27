import { useCallback, useState } from "react";
import type { InputMode } from "../types/api";
import { formatCoords } from "../lib/imageMeta";

interface Props {
  inputMode: InputMode;
  locationQuery: string;
  setLocationQuery: (v: string) => void;
  locationQuery2: string;
  setLocationQuery2: (v: string) => void;
  inputSource: "upload" | "location";
  setInputSource: (v: "upload" | "location") => void;
}

const SOURCES: { key: "upload" | "location"; label: string; sub: string }[] = [
  { key: "upload", label: "Upload", sub: "Local file" },
  { key: "location", label: "Location", sub: "Resolve coordinates" },
];

function parseLatLon(s: string): { lat: number; lon: number } | null {
  const m = s.trim().match(/^\s*([+-]?\d+(?:\.\d+)?)\s*[, ]\s*([+-]?\d+(?:\.\d+)?)\s*$/);
  if (!m) return null;
  const lat = parseFloat(m[1]!);
  const lon = parseFloat(m[2]!);
  if (isNaN(lat) || isNaN(lon)) return null;
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null;
  return { lat, lon };
}

/**
 * Imagery source switch plus the location form.
 *
 * The form unfolds out of the tab bar when "Location" is selected. Coordinate
 * detection is real — it only reports a match when the field actually parses as
 * `lat, lon` — and the confirmation animates in once.
 *
 * There are deliberately no date-range, cloud-cover or source-filter controls
 * here: the query endpoint accepts a place, a coordinate pair and an optional
 * second location, and nothing else. Adding more would imply filtering the app
 * cannot actually perform.
 */
export default function LocationSearchInput({
  inputMode,
  locationQuery,
  setLocationQuery,
  locationQuery2,
  setLocationQuery2,
  inputSource,
  setInputSource,
}: Props) {
  const [showHelp, setShowHelp] = useState(false);
  const isLocation = inputSource === "location";
  const showSecond = inputMode === "bi-temporal";

  const handleClear = useCallback(() => {
    setLocationQuery("");
    setLocationQuery2("");
  }, [setLocationQuery, setLocationQuery2]);

  const parsed = parseLatLon(locationQuery);
  const parsed2 = parseLatLon(locationQuery2);

  return (
    <div className="space-y-3">
      <div
        role="tablist"
        aria-label="Imagery source"
        className="flex gap-1 rounded-lg border border-slate-800 bg-slate-950 p-1"
      >
        {SOURCES.map((source) => {
          const isActive = inputSource === source.key;
          return (
            <button
              key={source.key}
              type="button"
              role="tab"
              aria-selected={isActive}
              tabIndex={isActive ? 0 : -1}
              onClick={() => setInputSource(source.key)}
              className={[
                "group relative flex-1 overflow-hidden rounded-md border px-2 py-1.5 text-left",
                "transition-all duration-200 ease-out",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/50",
                isActive
                  ? "border-teal-500/50 bg-teal-500/10 shadow-glow"
                  : "border-transparent hover:border-slate-700 hover:bg-slate-900/70",
              ].join(" ")}
            >
              <span
                className={`absolute inset-x-2 bottom-0 h-px origin-center bg-teal-400 transition-transform duration-300 ease-out ${
                  isActive ? "scale-x-100 opacity-100" : "scale-x-0 opacity-0"
                }`}
                aria-hidden="true"
              />
              <span
                className={`block text-[11px] font-semibold uppercase tracking-wider transition-colors duration-200 ${
                  isActive ? "text-teal-300" : "text-slate-500 group-hover:text-slate-300"
                }`}
              >
                {source.label}
              </span>
              <span
                className={`block text-[9px] leading-tight transition-colors duration-200 ${
                  isActive ? "text-teal-400/70" : "text-slate-600 group-hover:text-slate-500"
                }`}
              >
                {source.sub}
              </span>
            </button>
          );
        })}
      </div>

      {!isLocation ? (
        <p className="text-[11px] leading-relaxed text-slate-500">
          Upload GeoTIFF/PNG below, or switch to{" "}
          <span className="text-slate-400">Location</span> to resolve a place into Sentinel-2
          scenes.
        </p>
      ) : (
        <div className="search-reveal space-y-3">
          <div>
            <label htmlFor="location-query" className="field-label">
              {showSecond ? "Location T1 (or single)" : "Place name or coordinates"}
            </label>
            <div className="relative">
              <input
                id="location-query"
                value={locationQuery}
                onChange={(e) => setLocationQuery(e.target.value)}
                placeholder="Bengaluru, India  or  12.97, 77.59"
                autoComplete="off"
                className="field pr-9"
              />
              {locationQuery && (
                <button
                  type="button"
                  onClick={handleClear}
                  aria-label="Clear location fields"
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded px-1 text-[11px]
                    text-slate-500 transition-colors hover:text-rose-400
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/50"
                >
                  ✕
                </button>
              )}
            </div>
            {/* Real feedback: only shown when the field genuinely parses as lat,lon. */}
            <CoordinateReadout parsed={parsed} query={locationQuery} id="coords-1" />
          </div>

          {showSecond && (
            <div className="search-reveal">
              <label htmlFor="location-query-2" className="field-label">
                Location T2 (bi-temporal second date)
              </label>
              <input
                id="location-query-2"
                value={locationQuery2}
                onChange={(e) => setLocationQuery2(e.target.value)}
                placeholder="Mumbai, India  or  leave empty to fetch 2 dates for T1"
                autoComplete="off"
                className="field"
              />
              <CoordinateReadout parsed={parsed2} query={locationQuery2} id="coords-2" />
            </div>
          )}

          <div className="rounded-lg border border-slate-800 bg-slate-950/60">
            <button
              type="button"
              onClick={() => setShowHelp((v) => !v)}
              aria-expanded={showHelp}
              className="flex w-full items-center gap-2 px-3 py-2 text-left
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-500/50"
            >
              <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                How it works
              </span>
              <svg
                width="10"
                height="10"
                viewBox="0 0 12 12"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                aria-hidden="true"
                className={`ml-auto text-slate-600 transition-transform duration-200 ${
                  showHelp ? "rotate-180" : ""
                }`}
              >
                <path d="M3 5l3 3 3-3" strokeLinecap="round" />
              </svg>
            </button>
            <div
              className={`grid transition-all duration-300 ease-out ${
                showHelp ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
              }`}
            >
              <div className="overflow-hidden">
                <p className="px-3 pb-3 text-[10px] leading-relaxed text-slate-500">
                  Place name → Nominatim (OpenStreetMap, no key) → lat/lon → Planetary Computer
                  STAC{" "}
                  <code className="text-teal-400/80">sentinel-2-l2a</code>, least-cloudy scene in a
                  2 km AOI over the last 90 days. For{" "}
                  <code className="text-teal-400/80">optical-sar</code> it also fetches{" "}
                  <code className="text-teal-400/80">sentinel-1-rtc</code>. No Google Earth Engine
                  needed.
                </p>
              </div>
            </div>
          </div>

          <p className="text-[11px] leading-relaxed text-slate-500">
            Fetched scenes appear in the viewer before analysis runs.
          </p>
        </div>
      )}
    </div>
  );
}

/** Coordinate confirmation that animates in, plus an honest hint otherwise. */
function CoordinateReadout({
  parsed,
  query,
  id,
}: {
  parsed: { lat: number; lon: number } | null;
  query: string;
  id: string;
}) {
  if (parsed) {
    return (
      <p
        id={id}
        className="coords-ok mt-1.5 flex items-center gap-1.5 text-[10px] text-emerald-400"
        role="status"
      >
        <svg width="10" height="10" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <path
            d="M3.5 8.5l3 3 6-6"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        {formatCoords(parsed.lat, parsed.lon)}
      </p>
    );
  }
  if (query.trim().length > 2) {
    return (
      <p id={id} className="mt-1.5 text-[10px] text-slate-500">
        Geocoding on submit via Nominatim
      </p>
    );
  }
  return null;
}
