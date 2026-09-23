import { useCallback, useState } from "react";
import type { InputMode } from "../types/api";

interface Props {
  inputMode: InputMode;
  locationQuery: string;
  setLocationQuery: (v: string) => void;
  locationQuery2: string;
  setLocationQuery2: (v: string) => void;
  inputSource: "upload" | "location";
  setInputSource: (v: "upload" | "location") => void;
}

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
    <div className="space-y-3">
      {/* Source toggle */}
      <div className="flex bg-surface-900 border border-surface-400/40 rounded-lg overflow-hidden">
        <button
          onClick={() => setInputSource("upload")}
          className={`flex-1 px-2 py-2 text-[11px] font-medium tracking-wide transition-colors ${
            inputSource === "upload" ? "bg-accent/10 text-accent" : "text-ink-muted hover:text-ink-secondary"
          }`}
        >
          Upload
        </button>
        <button
          onClick={() => setInputSource("location")}
          className={`flex-1 px-2 py-2 text-[11px] font-medium tracking-wide transition-colors ${
            isLocation ? "bg-accent/10 text-accent" : "text-ink-muted hover:text-ink-secondary"
          }`}
        >
          Search by location
        </button>
      </div>

      {!isLocation ? (
        <p className="text-[11px] text-ink-muted">
          Upload GeoTIFF/PNG or switch to <span className="text-ink-secondary">Search by location</span> to auto-fetch Sentinel-2.
        </p>
      ) : (
        <div className="space-y-2.5">
          <div>
            <label className="block text-[11px] font-medium text-ink-muted uppercase tracking-[0.1em] mb-1.5">
              {showSecond ? "Location T1 (or single)" : "Place name or coordinates"}
            </label>
            <div className="relative">
              <input
                value={locationQuery}
                onChange={(e) => setLocationQuery(e.target.value)}
                onFocus={() => setFocused(true)}
                onBlur={() => setTimeout(() => setFocused(false), 200)}
                placeholder="Bengaluru, India  or  12.97, 77.59"
                className="w-full bg-surface-900/60 border border-surface-400/40 text-ink placeholder-ink-muted/60 px-3 py-2.5 pr-8 text-[13px] rounded-lg focus:outline-none focus:border-accent/50 transition-colors"
              />
              {locationQuery && (
                <button
                  onClick={handleClear}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-muted hover:text-signal-red text-[10px] px-1"
                >
                  ✕
                </button>
              )}
            </div>
            {parsed && (
              <p className="text-[10px] text-signal-green mt-1">Detected coordinates: {parsed.lat.toFixed(4)}, {parsed.lon.toFixed(4)}</p>
            )}
            {!parsed && locationQuery.trim().length > 2 && (
              <p className="text-[10px] text-ink-muted mt-1">Will geocode via Nominatim (OpenStreetMap) → Planetary Computer Sentinel-2</p>
            )}
          </div>

          {showSecond && (
            <div>
              <label className="block text-[11px] font-medium text-ink-muted uppercase tracking-[0.1em] mb-1.5">
                Location T2 (bi-temporal second date)
              </label>
              <input
                value={locationQuery2}
                onChange={(e) => setLocationQuery2(e.target.value)}
                placeholder="Mumbai, India  or  leave empty to fetch 2 dates for T1"
                className="w-full bg-surface-900/60 border border-surface-400/40 text-ink placeholder-ink-muted/60 px-3 py-2.5 text-[13px] rounded-lg focus:outline-none focus:border-accent/50 transition-colors"
              />
              {parsed2 && (
                <p className="text-[10px] text-signal-green mt-1">Detected coordinates: {parsed2.lat.toFixed(4)}, {parsed2.lon.toFixed(4)}</p>
              )}
              <p className="text-[10px] text-ink-muted mt-1">
                If empty, same location will be used for T1 and T2 (two most recent scenes).
              </p>
            </div>
          )}

          <div className="bg-surface-800/50 border border-surface-400/20 rounded-lg px-3 py-2 space-y-1">
            <p className="text-[10px] font-medium text-ink-secondary">How it works</p>
            <p className="text-[10px] text-ink-muted leading-relaxed">
              Place name → Nominatim (no key) → lat/lon → Planetary Computer STAC <code className="text-accent/70">sentinel-2-l2a</code>{" "}
              (2km AOI, least-cloudy recent). For <code className="text-accent/70">optical-sar</code>, also fetches{" "}
              <code className="text-accent/70">sentinel-1-rtc</code> SAR. No Google Earth Engine needed.
            </p>
            {focused && (
              <p className="text-[10px] text-ink-muted">
                Tip: paste <code className="text-ink-secondary">lat,lon</code> to skip geocoding.
              </p>
            )}
          </div>

          <p className="text-[11px] text-ink-muted">
            On submit, fetched Sentinel-2 imagery will appear in the viewer before analysis runs.
          </p>
        </div>
      )}
    </div>
  );
}
