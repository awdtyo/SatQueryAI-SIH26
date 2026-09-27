import { useEffect, useState } from "react";
import StatusPill from "./ui/StatusPill";
import type { HealthState } from "../types/api";
import { computeLabel, deviceLabel, isServiceOnline } from "../lib/systemStatus";

function useUtcClock() {
  const [time, setTime] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return time.toISOString().slice(0, 19).replace("T", " ") + " UTC";
}

interface Props {
  health?: HealthState;
  /** Real pending state of the outgoing request. */
  isRunning?: boolean;
  /** Opens a stacked sidebar — only surfaced below the `xl` breakpoint. */
  onOpenPanel?: (side: "left" | "right") => void;
}

/**
 * Application header.
 *
 * The right-hand cluster shows only values the backend actually reported —
 * compute, device/GPU and the real UTC clock. When the Gradio transport is in
 * use there is no `/api/health`, so the compute and device readouts are simply
 * omitted rather than defaulted to a plausible-looking "CPU-ONLY".
 */
export default function Header({ health = null, isRunning = false, onOpenPanel }: Props) {
  const utcTime = useUtcClock();
  const online = isServiceOnline(health);
  const compute = computeLabel(health);
  const device = deviceLabel(health);

  return (
    <header className="flex h-14 flex-shrink-0 items-center gap-4 border-b border-slate-800 bg-slate-900 px-4 sm:px-5">
      {onOpenPanel && (
        <button
          type="button"
          onClick={() => onOpenPanel("left")}
          aria-label="Open imagery input and query log"
          className="icon-btn h-8 w-8 xl:hidden"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
            <path d="M3 6h18M3 12h18M3 18h18" strokeLinecap="round" />
          </svg>
        </button>
      )}

      {/* Brand block */}
      <div className="flex min-w-0 items-center gap-3">
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="flex-shrink-0 text-teal-400">
          <circle cx="12" cy="12" r="2.5" fill="currentColor" />
          <rect x="1" y="11" width="7" height="2" rx="0.5" fill="currentColor" opacity="0.35" />
          <rect x="16" y="11" width="7" height="2" rx="0.5" fill="currentColor" opacity="0.35" />
          <line x1="3.5" y1="9.5" x2="3.5" y2="14.5" stroke="currentColor" strokeWidth="0.6" opacity="0.25" />
          <line x1="20.5" y1="9.5" x2="20.5" y2="14.5" stroke="currentColor" strokeWidth="0.6" opacity="0.25" />
          <circle cx="12" cy="12" r="9.5" stroke="currentColor" strokeWidth="0.4" opacity="0.15" strokeDasharray="2 3" />
        </svg>
        <div className="min-w-0 leading-tight">
          <div className="flex items-baseline gap-1.5">
            <span className="text-[17px] font-semibold tracking-wide text-slate-100">
              SAT<span className="text-teal-400">QUERY</span>
            </span>
            <span className="font-mono text-[11px] tracking-[0.15em] text-teal-400/80">AI</span>
          </div>
          <p className="hidden truncate text-[10px] font-medium uppercase tracking-[0.12em] text-slate-500 sm:block">
            Remote Sensing Intelligence
          </p>
        </div>
      </div>

      <div className="flex-1" />

      {/* Right telemetry — reported values only, UTC clock is always real. */}
      <div className="hidden items-center gap-5 text-[11px] 2xl:flex">
        {compute && <TelemetryLabel value={compute} label="Compute" />}
        {device && (
          <>
            {compute && <div className="h-4 w-px bg-slate-800" />}
            <TelemetryLabel value={device} label="Device" mono />
          </>
        )}
        <div className="h-4 w-px bg-slate-800" />
        <TelemetryLabel value={utcTime} label="UTC" mono />
      </div>

      <div className="flex items-center gap-2">
        <span className="hidden items-center gap-1.5 font-mono text-[10px] text-slate-500 sm:flex">
          {compute ? <span className="text-slate-600">{compute}</span> : null}
          {compute && device ? <span className="text-slate-700">·</span> : null}
          {device ? <span className="truncate">{device}</span> : null}
        </span>
        <StatusPill
          status={!health ? "unknown" : isRunning ? "processing" : online ? "ready" : "error"}
          label={!health ? "NO DATA" : isRunning ? "Analyzing" : online ? "Ready" : "Offline"}
        />
      </div>

      {onOpenPanel && (
        <button
          type="button"
          onClick={() => onOpenPanel("right")}
          aria-label="Open execution trace and system status"
          className="icon-btn h-8 w-8 xl:hidden"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
            <path d="M4 6h16M4 12h10M4 18h16" strokeLinecap="round" />
            <circle cx="18" cy="12" r="2" />
          </svg>
        </button>
      )}
    </header>
  );
}

function TelemetryLabel({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex flex-col leading-tight">
      <span className="text-[9px] font-medium uppercase tracking-[0.15em] text-slate-600">{label}</span>
      <span className={`text-[11px] text-slate-400 ${mono ? "font-mono tabular-nums" : ""}`}>{value}</span>
    </div>
  );
}
