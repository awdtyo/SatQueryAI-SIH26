import type { ExecutionTrace, HealthState, ModelTraceEntry } from "../types/api";
import CollapsiblePanel from "./ui/CollapsiblePanel";
import TraceNodeList from "./ui/ExecutionTimeline";
import ModelTraceRow from "./ModelTraceRow";
import { buildTraceView } from "../lib/analysisStages";

interface Props {
  trace: ExecutionTrace | null;
  /** Real pending state of the query request. */
  isRunning?: boolean;
  /** Health payload — decides READY vs. unreachable in the idle state. */
  health?: HealthState;
}

/**
 * Execution trace panel.
 *
 * The node chain is derived from real state by `buildTraceView`: idle reads
 * SYSTEM READY, an in-flight request marks nothing complete, and a landed
 * response reports exactly which of the five nodes ran.
 */
export default function ExecutionTracePanel({ trace, isRunning = false, health = null }: Props) {
  const view = buildTraceView(health, isRunning, trace);

  const badge = isRunning ? (
    <span className="tag border-teal-500/30 bg-teal-500/10 text-teal-300">
      <span className="h-1 w-1 animate-pulse rounded-full bg-teal-400" aria-hidden="true" />
      In flight
    </span>
  ) : trace ? (
    <span className="tag border-emerald-500/20 bg-emerald-500/10 text-emerald-400">Complete</span>
  ) : (
    <span className="tag border-teal-500/20 bg-teal-500/10 text-teal-300">System ready</span>
  );

  const body = (
    <div className="space-y-4">
      <p className="text-[11px] leading-relaxed text-slate-500" role="status" aria-live="polite">
        {view.summary}
      </p>

      <TraceNodeList nodes={view.nodes} inFlight={view.inFlight} />

      {trace && !isRunning && <TraceDetails trace={trace} />}
    </div>
  );

  if (isRunning || !trace) {
    return (
      <CollapsiblePanel label="Execution Trace" className="flex-1" action={badge}>
        {body}
      </CollapsiblePanel>
    );
  }

  return (
    <CollapsiblePanel
      label="Execution Trace"
      className="flex-1"
      action={
        <div className="flex items-center gap-2">
          {badge}
          <span className="text-[11px] tabular-nums text-slate-500">
            {trace.total_latency_ms}ms
          </span>
        </div>
      }
    >
      {body}
    </CollapsiblePanel>
  );
}

/** Response-derived detail: task, models, parameters, evidence. All real. */
function TraceDetails({ trace }: { trace: ExecutionTrace }) {
  // Gradio error paths may return partial traces — never crash on .length
  const modelsUsed: ModelTraceEntry[] = Array.isArray(trace.models_used) ? trace.models_used : [];
  const evidenceRefs = Array.isArray(trace.evidence_refs) ? trace.evidence_refs : [];
  const parameters =
    trace.parameters && typeof trace.parameters === "object" ? trace.parameters : {};
  const taskLabel =
    typeof trace.task === "string" && trace.task
      ? trace.task.replace(/_/g, " ").toUpperCase()
      : "UNNAMED";

  return (
    <div className="space-y-5">
      <div className="divider" />

      <section className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
            Task
          </span>
          <span className="text-[12px] font-medium text-teal-300">{taskLabel}</span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
            Model
          </span>
          <span className="truncate text-[12px] text-slate-400">{modelsUsed[0]?.name ?? "N/A"}</span>
        </div>
      </section>

      {modelsUsed.length > 0 && (
        <section className="space-y-2">
          <h3 className="field-label">Models invoked</h3>
          {modelsUsed.map((model, i) => (
            <ModelTraceRow key={`${model.name}-${i}`} model={model} />
          ))}
        </section>
      )}

      {Object.keys(parameters).length > 0 && (
        <section>
          <h3 className="field-label">Parameters</h3>
          <div className="space-y-1.5">
            {Object.entries(parameters)
              .filter(([key]) => !key.startsWith("_"))
              .map(([key, value]) => (
                <div key={key} className="flex items-center justify-between gap-2">
                  <span className="min-w-0 truncate text-[11px] text-slate-500">
                    {key.replace(/_/g, " ")}
                  </span>
                  <span className="min-w-[10px] flex-1 border-b border-dotted border-slate-800" />
                  <span className="whitespace-nowrap font-mono text-[11px] tabular-nums text-slate-400">
                    {String(value)}
                  </span>
                </div>
              ))}
          </div>
        </section>
      )}

      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
          Evidence
        </span>
        <span className="text-[11px] tabular-nums text-slate-400">
          {evidenceRefs.length} reference{evidenceRefs.length !== 1 ? "s" : ""}
        </span>
      </div>
    </div>
  );
}
