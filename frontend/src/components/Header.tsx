import { useEffect, useState } from "react";
import type { HealthSnapshot } from "../types/api";
import StatusPill from "./ui/StatusPill";
import { SatelliteIcon } from "./ui/Icons";

function useUtcClock() {
  const [time, setTime] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return `${time.toISOString().slice(0, 19).replace("T", " ")} UTC`;
}

function TelemetryLabel({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex flex-col leading-tight">
      <span className="text-[9px] font-medium uppercase tracking-[0.15em] text-slate-500">
        {label}
      </span>
      <span
        className={`text-[11px] text-slate-300 ${mono ? "font-mono tabular-nums" : ""}`}
      >
        {value}
      </span>
    </div>
  );
}

export default function Header({ health }: { health?: HealthSnapshot | null }) {
  const utcTime = useUtcClock();
  const isOffline = health?.status === "offline";
  const isCpuOnly = health?.force_cpu ?? true; // default to CPU-only per backend config
  const computeLabel = isCpuOnly ? "CPU-ONLY" : (health?.compute?.toUpperCase() ?? "CPU");
  const deviceLabel = health?.device ?? "cpu";

  return (
    <header className="flex h-14 flex-shrink-0 items-center gap-6 border-b border-slate-800 bg-slate-950 px-4 sm:px-5">
      <div className="flex items-center gap-3">
        <SatelliteIcon className="h-7 w-7 flex-shrink-0 text-teal-400" />
        <div className="leading-tight">
          <div className="flex items-baseline gap-1.5">
            <span className="text-[17px] font-semibold tracking-wide text-slate-50">
              SAT<span className="text-teal-400">QUERY</span>
            </span>
            <span className="font-mono text-[11px] tracking-[0.15em] text-teal-400">AI</span>
          </div>
          <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-slate-500">
            Remote Sensing Intelligence
          </p>
        </div>
      </div>

      <div className="flex-1" />

      <div className="hidden items-center gap-5 text-[11px] md:flex">
        <TelemetryLabel value="SAT-QUERY-01" label="Mission" />
        <div className="h-4 w-px bg-slate-800" />
        <TelemetryLabel value="Analysis" label="Mode" />
        <div className="h-4 w-px bg-slate-800" />
        <div className="hidden lg:block">
          <TelemetryLabel value={utcTime} label="UTC" mono />
        </div>
      </div>

      <div className="flex items-center gap-3">
        <span className="hidden font-mono text-[10px] text-slate-500 sm:inline">{deviceLabel}</span>
        <StatusPill status={isOffline ? "offline" : "online"} label={isOffline ? "OFFLINE" : "ONLINE"} />
        <span className="chip-accent hidden sm:inline-flex" title="Active compute backend">
          {computeLabel}
        </span>
      </div>
    </header>
  );
}
