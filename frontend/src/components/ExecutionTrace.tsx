import { useState } from "react";
import type { ExecutionTrace, ModelTraceEntry } from "../types/api";

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
  const isStub = model.is_stub ?? (model.is_real === false);
  const badge = isStub ? "STUB" : model.is_real ? "REAL" : null;
  return (
    <div className="ml-6 pl-3 border-l border-accent/20 py-2">
      <div className="flex items-center gap-2.5">
        <span className="text-[12px] font-medium text-accent truncate max-w-[150px]" title={model.name}>{model.name}</span>
        <span className="tag-muted">{model.role}</span>
        {badge && (
          <span className={`text-[9px] px-1.5 py-0.5 rounded font-medium tracking-wider ${isStub ? "bg-signal-amber/15 text-signal-amber border border-signal-amber/20" : "bg-signal-green/15 text-signal-green border border-signal-green/20"}`}>
            {badge}
          </span>
        )}
        <span className="ml-auto text-[11px] text-ink-muted tabular-nums">
          {model.latency_ms}ms
        </span>
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5">
        {Object.entries(model.parameters).map(([k, v]) => (
          <span key={k} className="text-[10px] font-mono text-ink-secondary">
            <span className="text-ink-muted">{k}:</span> {String(v)}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function ExecutionTracePanel({ trace }: Props) {
  const [expanded, setExpanded] = useState(true);

  if (!trace) {
    return (
      <section className="panel flex-1 min-h-0 flex flex-col">
        <div className="panel-header">
          <span className="panel-label">Execution Trace</span>
        </div>
        <div className="panel-body flex-1 flex items-center justify-center">
          <p className="text-[12px] text-ink-muted">Awaiting analysis</p>
        </div>
      </section>
    );
  }

  const modelSteps = getModelStepIndex(trace.models_used.length, PIPELINE_STEPS.length);

  return (
    <section className="panel flex-1 min-h-0 flex flex-col">
      <button
        onClick={() => setExpanded(!expanded)}
        className="panel-header hover:bg-surface-700/30 transition-colors cursor-pointer"
      >
        <span className="panel-label">Execution Trace</span>
        <div className="flex-1" />
        <span className="text-[11px] text-ink-muted tabular-nums">
          {trace.total_latency_ms}ms
        </span>
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          className={`text-ink-muted transition-transform duration-150 ${expanded ? "rotate-180" : ""}`}
        >
          <path d="M3 5l3 3 3-3" />
        </svg>
      </button>

      {expanded && (
        <div className="panel-body overflow-y-auto flex-1 min-h-0 space-y-4">
          {/* Pipeline steps */}
          <div>
            <span className="text-[10px] font-medium text-ink-muted uppercase tracking-[0.1em] block mb-2">
              Pipeline
            </span>
            <div className="space-y-0">
              {PIPELINE_STEPS.map((step, i) => {
                const isModelStep = modelSteps.includes(i);
                const isLastStep = i === PIPELINE_STEPS.length - 1;
                const isComplete = true;

                return (
                  <div key={i}>
                    <div className="flex items-center gap-3 py-1.5">
                      <span className="text-[10px] font-mono text-ink-muted w-6 text-right tabular-nums">
                        {i + 1}
                      </span>
                      {/* Status icon (check) */}
                      <span className="w-4 flex-shrink-0 flex justify-center">
                        <svg
                          width="13"
                          height="13"
                          viewBox="0 0 16 16"
                          fill="none"
                          className={isComplete ? "text-signal-green" : "text-surface-400"}
                        >
                          <path d="M3.5 8.5l3 3 6-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </span>
                      <span
                        className={`text-[12px] font-medium ${
                          isComplete ? "text-ink-secondary" : "text-ink-muted/50"
                        }`}
                      >
                        {step}
                      </span>
                    </div>

                    {isModelStep && trace.models_used[modelSteps.indexOf(i)] && (
                      <ModelRow model={trace.models_used[modelSteps.indexOf(i)]!} />
                    )}

                    {!isLastStep && <div className="ml-[30px] w-px h-1 bg-surface-400/20" />}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="divider" />

          {/* Task */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-medium text-ink-muted uppercase tracking-[0.1em]">
                Task
              </span>
              <span className="text-[12px] font-medium text-accent">
                {trace.task.replace("_", " ").toUpperCase()}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-[10px] font-medium text-ink-muted uppercase tracking-[0.1em]">
                Model
              </span>
              <span className="text-[12px] text-ink-secondary">
                {trace.models_used[0]?.name ?? "N/A"}
              </span>
            </div>
          </div>

          {/* Parameters */}
          <div>
            <span className="text-[10px] font-medium text-ink-muted uppercase tracking-[0.1em] block mb-2">
              Parameters
            </span>
            <div className="space-y-1.5">
              {Object.entries(trace.parameters).map(([k, v]) => (
                <div key={k} className="flex items-center justify-between gap-2">
                  <span className="text-[11px] text-ink-muted truncate min-w-0">{k}</span>
                  <span className="flex-1 border-b border-dotted border-surface-400/20 min-w-[10px]" />
                  <span className="text-[11px] font-mono text-ink-secondary tabular-nums whitespace-nowrap">
                    {String(v)}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Evidence */}
          <div className="flex items-center justify-between pt-1">
            <span className="text-[10px] font-medium text-ink-muted uppercase tracking-[0.1em]">
              Evidence
            </span>
            <span className="text-[11px] text-ink-secondary">
              {trace.evidence_refs.length} reference{trace.evidence_refs.length !== 1 ? "s" : ""}
            </span>
          </div>
        </div>
      )}
    </section>
  );
}
