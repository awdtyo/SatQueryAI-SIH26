import { useEffect, useState } from "react";

function useUtcClock() {
  const [time, setTime] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return time.toISOString().slice(0, 19).replace("T", " ") + " UTC";
}

type HealthProp = {
  status?: string;
  compute?: string;
  device?: string;
  force_cpu?: boolean;
} | null;

export default function Header({ health }: { health?: HealthProp }) {
  const utcTime = useUtcClock();
  const isCpuOnly = health?.force_cpu ?? true; // default to CPU-only per backend config
  const computeLabel = isCpuOnly ? "CPU-ONLY" : (health?.compute?.toUpperCase() ?? "CPU");
  const deviceLabel = health?.device ?? "cpu";

  return (
    <header className="h-[56px] flex-shrink-0 border-b border-surface-400/40 bg-surface-800/90 flex items-center px-5 gap-6">
      {/* Brand block */}
      <div className="flex items-center gap-3">
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" className="text-accent flex-shrink-0">
          <circle cx="12" cy="12" r="2.5" fill="currentColor" />
          <rect x="1" y="11" width="7" height="2" rx="0.5" fill="currentColor" opacity="0.35" />
          <rect x="16" y="11" width="7" height="2" rx="0.5" fill="currentColor" opacity="0.35" />
          <line x1="3.5" y1="9.5" x2="3.5" y2="14.5" stroke="currentColor" strokeWidth="0.6" opacity="0.25" />
          <line x1="20.5" y1="9.5" x2="20.5" y2="14.5" stroke="currentColor" strokeWidth="0.6" opacity="0.25" />
          <circle cx="12" cy="12" r="9.5" stroke="currentColor" strokeWidth="0.4" opacity="0.1" strokeDasharray="2 3" />
        </svg>
        <div className="leading-tight">
          <div className="flex items-baseline gap-1.5">
            <span className="text-[17px] font-semibold tracking-wide text-ink">
              SAT<span className="text-accent">QUERY</span>
            </span>
            <span className="text-[11px] font-mono text-accent tracking-[0.15em]">AI</span>
          </div>
          <p className="text-[10px] font-medium text-ink-muted tracking-[0.12em] uppercase">
            Remote Sensing Intelligence
          </p>
        </div>
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Right telemetry — light touch */}
      <div className="hidden md:flex items-center gap-5 text-[11px]">
        <TelemetryLabel value="SAT-QUERY-01" label="MISSION" />
        <div className="w-px h-4 bg-surface-400/30" />
        <TelemetryLabel value="ANALYSIS" label="MODE" />
        <div className="w-px h-4 bg-surface-400/30" />
        <div className="hidden lg:block">
          <TelemetryLabel value={utcTime} label="UTC" mono />
        </div>
      </div>

      {/* CPU-specific health badge + online status */}
      <div className="flex items-center gap-3">
        <span className="hidden sm:inline-flex items-center gap-1.5 px-2 py-1 rounded border border-accent/25 bg-accent/10 text-[10px] font-medium tracking-wider text-accent">
          <span className="w-1.5 h-1.5 rounded-full bg-accent" />
          {computeLabel}
          <span className="text-accent/60 font-mono">·</span>
          <span className="font-mono text-accent/80">{deviceLabel}</span>
        </span>
        <span className="w-2 h-2 rounded-full bg-signal-green" />
        <span className="text-[11px] font-medium text-ink-secondary">System Online</span>
      </div>
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
      <span className="text-[9px] font-medium text-ink-muted tracking-[0.15em]">{label}</span>
      <span className={`text-[11px] text-ink-secondary ${mono ? "font-mono tabular-nums" : ""}`}>
        {value}
      </span>
    </div>
  );
}
