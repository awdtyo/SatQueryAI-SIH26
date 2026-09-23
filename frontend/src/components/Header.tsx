import { useEffect, useState } from "react";

function useUtcClock() {
  const [time, setTime] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return time.toISOString().slice(0, 19).replace("T", " ") + " UTC";
}

export default function Header() {
  const utcTime = useUtcClock();

  return (
    <header className="flex h-[56px] flex-shrink-0 items-center gap-6 border-b border-slate-800 bg-slate-950 px-5">
      <div className="flex items-center gap-3">
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" className="flex-shrink-0 text-teal-400">
          <circle cx="12" cy="12" r="2.5" fill="currentColor" />
          <rect x="1" y="11" width="7" height="2" rx="0.5" fill="currentColor" opacity="0.35" />
          <rect x="16" y="11" width="7" height="2" rx="0.5" fill="currentColor" opacity="0.35" />
          <line x1="3.5" y1="9.5" x2="3.5" y2="14.5" stroke="currentColor" strokeWidth="0.6" opacity="0.25" />
          <line x1="20.5" y1="9.5" x2="20.5" y2="14.5" stroke="currentColor" strokeWidth="0.6" opacity="0.25" />
          <circle cx="12" cy="12" r="9.5" stroke="currentColor" strokeWidth="0.4" opacity="0.1" strokeDasharray="2 3" />
        </svg>
        <div className="leading-tight">
          <div className="flex items-baseline gap-1.5">
            <span className="text-[17px] font-semibold tracking-wide text-slate-100">
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
        <TelemetryLabel value="SAT-QUERY-01" label="MISSION" />
        <div className="h-4 w-px bg-slate-800" />
        <TelemetryLabel value="ANALYSIS" label="MODE" />
        <div className="h-4 w-px bg-slate-800" />
        <div className="hidden lg:block">
          <TelemetryLabel value={utcTime} label="UTC" mono />
        </div>
      </div>

      <span className="inline-flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-emerald-400" aria-hidden="true" />
        <span className="text-[11px] font-medium text-slate-300">System Online</span>
      </span>
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
      <span className="text-[9px] font-medium tracking-[0.15em] text-slate-500">{label}</span>
      <span className={`text-[11px] text-slate-300 ${mono ? "font-mono tabular-nums" : ""}`}>
        {value}
      </span>
    </div>
  );
}