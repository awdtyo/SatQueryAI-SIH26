import type { ModelTraceEntry } from "../types/api";

function ModelRow({ model }: { model: ModelTraceEntry }) {
  const isStub = model.is_stub ?? model.is_real === false;
  const badge = isStub ? "STUB" : model.is_real ? "REAL" : null;
  // A partial trace (error paths, older or Gradio backends) may omit the
  // parameter map entirely, so it is read defensively rather than assumed.
  const parameters =
    model.parameters && typeof model.parameters === "object" ? model.parameters : {};
  const latency = typeof model.latency_ms === "number" ? model.latency_ms : null;

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2.5">
      <div className="flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate text-[12px] font-medium text-teal-300" title={model.name}>
          {model.name}
        </span>
        {badge && (
          <span
            className={`tag ${
              isStub
                ? "border-amber-500/20 bg-amber-500/10 text-amber-400"
                : "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
            }`}
          >
            {badge}
          </span>
        )}
        {latency !== null && (
          <span className="text-[11px] tabular-nums text-slate-500">{latency}ms</span>
        )}
      </div>
      {Object.keys(parameters).length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5">
          {Object.entries(parameters).map(([key, value]) => (
            <span key={key} className="font-mono text-[10px] text-slate-400">
              <span className="text-slate-600">{key}:</span> {String(value)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default ModelRow;
