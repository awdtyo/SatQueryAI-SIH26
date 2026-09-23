import type { ModelTraceEntry } from "../types/api";

interface Props {
  models: ModelTraceEntry[];
}

export default function ModelLatencyChart({ models }: Props) {
  if (models.length === 0) return null;

  const maxLatency = Math.max(...models.map((m) => m.latency_ms), 1);

  return (
    <div className="flex h-28 items-end gap-3">
      {models.map((m) => {
        const pct = Math.max(8, Math.round((m.latency_ms / maxLatency) * 100));
        return (
          <div key={m.name} className="group relative flex h-full min-w-0 flex-1 flex-col justify-end">
            <div className="pointer-events-none absolute -top-1 left-1/2 z-10 -translate-x-1/2 whitespace-nowrap rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-[10px] font-medium text-slate-100 opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100">
              {m.name} · {m.latency_ms} ms
            </div>
            <div
              className="w-full rounded-t-md bg-gradient-to-t from-teal-600 to-teal-400 transition-all duration-300 group-hover:from-teal-500 group-hover:to-teal-300"
              style={{ height: `${pct}%` }}
            />
            <span className="mt-1.5 truncate text-center text-[10px] text-slate-500">
              {m.name.split("-")[0]}
            </span>
          </div>
        );
      })}
    </div>
  );
}