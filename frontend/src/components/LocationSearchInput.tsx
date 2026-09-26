import { useCallback, useState } from "react";
import type { InputMode } from "../types/api";
import { CloseIcon, PinIcon, SearchIcon } from "./ui/Icons";
import SegmentedTabs from "./ui/SegmentedTabs";

interface Props {
  inputMode: InputMode;
  locationQuery: string;
  setLocationQuery: (v: string) => void;
  locationQuery2: string;
  setLocationQuery2: (v: string) => void;
  inputSource: "upload" | "location";
  setInputSource: (v: "upload" | "location") => void;
}

type SourceTab = "upload" | "location";

const SOURCE_TABS = [
  { value: "upload" as const, label: "Upload" },
  { value: "location" as const, label: "Search by location" },
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

export default function LocationSearchInput({
  inputMode,
  locationQuery,
  setLocationQuery,
  locationQuery2,
  setLocationQuery2,
  inputSource,
  setInputSource,
}: Props) {
  const [focused, setFocused] = useState(false);
  const isLocation = inputSource === "location";
  const showSecond = inputMode === "bi-temporal";

  const handleClear = useCallback(() => {
    setLocationQuery("");
    setLocationQuery2("");
  }, [setLocationQuery, setLocationQuery2]);

  const parsed = parseLatLon(locationQuery);
  const parsed2 = parseLatLon(locationQuery2);

  return (
    <div className="space-y-3.5">
      <div>
        <span className="field-label">Imagery Source</span>
        <SegmentedTabs<SourceTab>
          ariaLabel="Imagery source"
          tabs={SOURCE_TABS}
          value={inputSource}
          onChange={setInputSource}
        />
      </div>

      {!isLocation ? (
        <p className="flex items-start gap-2 text-[11px] leading-relaxed text-slate-500">
          <SearchIcon className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-slate-600" />
          <span>
            Upload GeoTIFF/PNG below, or switch to{" "}
            <span className="text-slate-300">Search by location</span> to auto-fetch Sentinel-2.
          </span>
        </p>
      ) : (
        <div className="space-y-3">
          <div>
            <label
              htmlFor="location-query"
              className="field-label"
            >
              {showSecond ? "Location T1 (or single)" : "Place name or coordinates"}
            </label>
            <div className="relative">
              <input
                id="location-query"
                value={locationQuery}
                onChange={(e) => setLocationQuery(e.target.value)}
                onFocus={() => setFocused(true)}
                onBlur={() => setTimeout(() => setFocused(false), 200)}
                placeholder="Bengaluru, India  or  12.97, 77.59"
                className="field pr-9"
              />
              {locationQuery && (
                <button
                  type="button"
                  onClick={handleClear}
                  aria-label="Clear location query"
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-500 transition-colors duration-150 hover:text-rose-400"
                >
                  <CloseIcon className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
            {parsed ? (
              <p className="mt-1.5 flex items-center gap-1.5 text-[10px] text-emerald-400">
                <PinIcon className="h-3 w-3" />
                Detected coordinates: {parsed.lat.toFixed(4)}, {parsed.lon.toFixed(4)}
              </p>
            ) : (
              locationQuery.trim().length > 2 && (
                <p className="mt-1.5 text-[10px] text-slate-500">
                  Will geocode via Nominatim (OpenStreetMap) → Planetary Computer Sentinel-2
                </p>
              )
            )}
          </div>

          {showSecond && (
            <div>
              <label htmlFor="location-query-2" className="field-label">
                Location T2 (bi-temporal second date)
              </label>
              <input
                id="location-query-2"
                value={locationQuery2}
                onChange={(e) => setLocationQuery2(e.target.value)}
                placeholder="Mumbai, India  or  leave empty to fetch 2 dates for T1"
                className="field"
              />
              {parsed2 && (
                <p className="mt-1.5 flex items-center gap-1.5 text-[10px] text-emerald-400">
                  <PinIcon className="h-3 w-3" />
                  Detected coordinates: {parsed2.lat.toFixed(4)}, {parsed2.lon.toFixed(4)}
                </p>
              )}
              <p className="mt-1.5 text-[10px] text-slate-500">
                If empty, same location will be used for T1 and T2 (two most recent scenes).
              </p>
            </div>
          )}

          <div className="space-y-1.5 rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2.5">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">
              How it works
            </p>
            <p className="text-[10px] leading-relaxed text-slate-500">
              Place name → Nominatim (no key) → lat/lon → Planetary Computer STAC{" "}
              <code className="font-mono text-teal-400/80">sentinel-2-l2a</code> (2km AOI,
              least-cloudy recent). For <code className="font-mono text-teal-400/80">optical-sar</code>,
              also fetches <code className="font-mono text-teal-400/80">sentinel-1-rtc</code> SAR.
              No Google Earth Engine needed.
            </p>
            {focused && (
              <p className="text-[10px] text-slate-500">
                Tip: paste <code className="font-mono text-slate-300">lat,lon</code> to skip
                geocoding.
              </p>
            )}
          </div>

          <p className="text-[11px] text-slate-500">
            On submit, fetched Sentinel-2 imagery appears in the viewer before analysis runs.
          </p>
        </div>
      )}
    </div>
  );
}
