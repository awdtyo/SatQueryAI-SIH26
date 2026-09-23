import { useState } from "react";
import type { ExecutionTrace, ModelTraceEntry } from "../types/api";
import { IconCheck, IconChevronDown } from "./icons";

interface Props {
  trace: ExecutionTrace | null;
}

const PIPELINE_STEPS = [
  "Query Parsed",
  "Task Classified",
  "Model Selected",
  "Imagery Analyzed",
  "Evidence Generated",
  "Result Compiled",
];

function getModelStepIndex(modelCount: number, totalSteps: number): number[] {
  if (modelCount === 0) return [];
  const used = Math.min(modelCount, 2);
  return Array.from({ length: used }, (_, i) => {
    return Math.floor(((i + 1) / (used + 1)) * totalSteps);
  });
}

function ModelRow({ model }: { model: ModelTraceEntry }) {
  return (
    <div className="mb-2 ml-7 mt-1.5 border-l border-slate-700/70 py-1 pl-3">
      <div className="flex items-center gap-2">
        <span className="text-[12px] font-semibold text-teal-400">{model.name}</span>
        <span className="tag-muted">{model.role}</span>
        <span className="ml-auto text-[11px] tabular-nums text-slate-500">{model.latency_ms} ms</span>
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
        {Object.entries(model.parameters).map(([k, v]) => (
          <span key={k} className="font-mono text-[10px] text-slate-400">
            <span className="text-slate-600">{k}</span>={String(v)}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function ExecutionTimeline({ trace }: Props) {
  const [expanded, setExpanded] = useState(true);
  const modelSteps = trace ? getModelStepIndex(trace.models_used.length, PIPELINE_STEPS.length) : [];
  const bodyId = "execution-trace-body";

  return (
    <section className="flex min-h-0 flex-1 flex-col rounded-xl border border-slate-800 bg-slate-900">
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={bodyId}
        onClick={() => setExpanded(!expanded)}
        className="panel-header cursor-pointer rounded-t-xl transition-colors hover:bg-slate-800/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-500/60"
      >
        <span className="panel-label">Execution Trace</span>
        <span className="ml-auto text-[11px] tabular-nums text-slate-500">
          {trace ? `${trace.total_latency_ms} ms` : "pending"}
        </span>
        <IconChevronDown
          className={`text-slate-500 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`}
        />
      </button>

      {expanded && (
        <div id={bodyId} className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
          <div>
            <span className="mb-2 block text-[10px] font-medium uppercase tracking-[0.1em] text-slate-500">
              Pipeline
            </span>
            <ol className="mt-2">
              {PIPELINE_STEPS.map((step, i) => {
                const isModelStep = modelSteps.includes(i);
                const isLastStep = i === PIPELINE_STEPS.length - 1;
                const completed = trace !== null;
                const modelIndex = modelSteps.indexOf(i);

                return (
                  <li key={step}>
                    <div className="relative flex gap-3 pb-4">
                      {!isLastStep && (
                        <span
                          className="absolute bottom-0 left-[9px] top-5 w-px bg-slate-800"
                          aria-hidden="true"
                        />
                      )}
                      <span
                        className={`relative z-10 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full ${
                          completed
                            ? "border border-emerald-500/40 bg-emerald-500/15 text-emerald-400"
                            : "border border-slate-700"
                        }`}
                      >
                        {completed ? (
                          <IconCheck />
                        ) : (
                          <span className="h-1.5 w-1.5 rounded-full bg-slate-700" aria-hidden="true" />
                        )}
                      </span>
                      <div className="min-w-0 flex-1 pt-0.5">
                        <div className="flex items-baseline gap-2">
                          <span
                            className={`text-[12px] font-medium ${
                              completed ? "text-slate-200" : "text-slate-500"
                            }`}
                          >
                            {step}
                          </span>
                          {completed && isLastStep && trace && (
                            <span className="text-[10px] tabular-nums text-slate-500">
                              {trace.total_latency_ms} ms
                            </span>
                          )}
                        </div>
                        {completed && isModelStep && modelIndex >= 0 && trace && trace.models_used[modelIndex] && (
                          <ModelRow model={trace.models_used[modelIndex]!} />
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>

          {trace && (
            <>
              <div className="divider" />

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-medium uppercase tracking-[0.1em] text-slate-500">
                    Task
                  </span>
                  <span className="text-[12px] font-medium text-teal-400">
                    {trace.task.replace("_", " ").toUpperCase()}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-medium uppercase tracking-[0.1em] text-slate-500">
                    Model
                  </span>
                  <span className="text-[12px] text-slate-300">
                    {trace.models_used[0]?.name ?? "N/A"}
                  </span>
                </div>
              </div>

              <div>
                <span className="mb-2 block text-[10px] font-medium uppercase tracking-[0.1em] text-slate-500">
                  Parameters
                </span>
                <div className="space-y-1.5">
                  {Object.entries(trace.parameters).map(([k, v]) => (
                    <div key={k} className="flex items-center justify-between gap-2">
                      <span className="min-w-0 truncate text-[11px] text-slate-500">{k}</span>
                      <span className="min-w-[10px] flex-1 border-b border-dotted border-slate-800" />
                      <span className="whitespace-nowrap font-mono text-[11px] tabular-nums text-slate-300">
                        {String(v)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex items-center justify-between pt-1">
                <span className="text-[10px] font-medium uppercase tracking-[0.1em] text-slate-500">
                  Evidence
                </span>
                <span className="text-[11px] text-slate-300">
                  {trace.evidence_refs.length} reference
                  {trace.evidence_refs.length !== 1 ? "s" : ""}
                </span>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}