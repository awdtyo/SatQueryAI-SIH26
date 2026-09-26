import { useState } from "react";
import type { ExecutionTrace, ModelTraceEntry } from "../types/api";
import { formatLatency } from "../lib/format";
import { INTELLIGENCE_PIPELINE } from "../lib/capabilities";
import ExecutionTimeline from "./ExecutionTimeline";
import type { TimelineStep } from "./ExecutionTimeline";
import { Panel, PanelHeader, PanelTitle } from "./ui/Panel";
import { ChevronIcon } from "./ui/Icons";

interface Props {
  trace: ExecutionTrace | null;
  /** True while a request is in flight and no trace has been returned yet. */
  analyzing?: boolean;
}

/**
 * Only these three nodes are client-observable facts: the query was accepted,
 * the payload was built, the request is still open. Everything after them is a
 * backend-reported stage whose outcome is unknown until the trace returns, so it
 * stays pending â€” never faked.
 */
const PENDING_STEPS: TimelineStep[] = [
  { id: "received", label: "Query received", status: "complete", progress: 1 },
  { id: "payload", label: "Input payload prepared", status: "complete", progress: 1 },
  { id: "flight", label: "Request in flight", status: "active", progress: 0 },
  { id: "understanding", label: "Query understanding", status: "pending", progress: 0 },
  { id: "interpretation", label: "Image interpretation", status: "pending", progress: 0 },
  { id: "router", label: "Model router", status: "pending", progress: 0 },
  { id: "extraction", label: "Evidence extraction", status: "pending", progress: 0 },
];

function ModelRow({ model }: { model: ModelTraceEntry }) {
  const isStub = model.is_stub ?? model.is_real === false;
  const badge = isStub ? "STUB" : model.is_real ? "REAL" : null;
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-2.5">
      <div className="flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate text-[11px] font-medium text-teal-300" title={model.name}>
          {model.name}
        </span>
        <span className="chip-muted flex-shrink-0">{model.role}</span>
        {badge && (
          <span
            className={`chip flex-shrink-0 ${
              isStub
                ? "border-amber-500/20 bg-amber-500/10 text-amber-400"
                : "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
            }`}
          >
            {badge}
          </span>
        )}
        <span className="flex-shrink-0 font-mono text-[10px] tabular-nums text-slate-500">
          {formatLatency(model.latency_ms)}
        </span>
      </div>
      {Object.keys(model.parameters).length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5">
          {Object.entries(model.parameters).map(([k, v]) => (
            <span key={k} className="font-mono text-[10px] text-slate-500">
              <span className="text-slate-600">{k}:</span> {String(v)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ExecutionTracePanel({ trace, analyzing = false }: Props) {
  const [expanded, setExpanded] = useState(true);

  if (!trace) {
    return (
      <Panel className="flex-1">
        <PanelHeader>
          <PanelTitle>Execution Trace</PanelTitle>
          <div className="flex-1" />
          {analyzing ? (
            <span className="chip-accent">
              <span className="h-1.5 w-1.5 animate-status-pulse rounded-full bg-current" />
              In flight
            </span>
          ) : (
            <span className="chip-muted">Idle</span>
          )}
        </PanelHeader>

        <div className="panel-body scroll-y flex-1">
          {analyzing ? (
            <div className="animate-fade-in">
              <p className="mb-3 text-[10.5px] leading-relaxed text-slate-500">
                Solid nodes are observed by the client. Everything below{" "}
                <span className="text-slate-400">Request in flight</span> is reported by the
                backend and populates when the response returns.
              </p>
              <ExecutionTimeline steps={PENDING_STEPS} />
            </div>
          ) : (
            <div className="flex h-full flex-col items-center justify-center py-6 text-center">
              <p className="text-[12px] text-slate-500">Awaiting analysis</p>
              <p className="mt-1.5 text-[10.5px] text-slate-600">
                The agentic pipeline activates on query execution
              </p>
            </div>
          )}
        </div>
      </Panel>
    );
  }

  const model = trace.models_used[0];
  const grounding = trace.models_used.find((m) => m.role.toLowerCase().includes("ground"));
  const stageCount = INTELLIGENCE_PIPELINE.length;

  /** Distributes real model invocations across the pipeline so each gets a node. */
  const modelSlotIndexes =
    trace.models_used.length === 0
      ? []
      : trace.models_used.map((_, i) =>
          Math.floor(((i + 1) / (trace.models_used.length + 1)) * stageCount),
        );

  const steps: TimelineStep[] = INTELLIGENCE_PIPELINE.map((label, i) => {
    const slot = modelSlotIndexes.indexOf(i);
    const entry = slot >= 0 ? trace.models_used[slot] : undefined;
    return {
      id: label,
      label,
      // The response exists, so the whole pipeline genuinely ran.
      status: "complete",
      timing: entry ? formatLatency(entry.latency_ms) : undefined,
      meta: entry ? <ModelRow model={entry} /> : undefined,
    };
  });

  const parameterEntries = Object.entries(trace.parameters);

  return (
    <Panel className="flex-1">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        aria-controls="execution-trace-body"
        className="panel-header w-full cursor-pointer text-left transition-colors duration-150 hover:bg-slate-800/50"
      >
        <PanelTitle>Execution Trace</PanelTitle>
        <div className="flex-1" />
        <span className="font-mono text-[10px] tabular-nums text-slate-500">
          {formatLatency(trace.total_latency_ms)}
        </span>
        <ChevronIcon
          className={`h-3.5 w-3.5 text-slate-500 transition-transform duration-200 ${
            expanded ? "rotate-180" : ""
          }`}
        />
      </button>

      {expanded && (
        <div id="execution-trace-body" className="scroll-y flex-1 space-y-4 p-4">
          <section>
            <h3 className="mb-2.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
              Agentic Pipeline
            </h3>
            <ExecutionTimeline steps={steps} />
          </section>

          <div className="divider" />

          <section className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                Task
              </span>
              <span className="chip-accent truncate">{trace.task.replace(/_/g, " ")}</span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="flex-shrink-0 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                Model
              </span>
              <span
                className="min-w-0 truncate text-[11px] text-slate-300"
                title={model?.name}
              >
                {model?.name ?? "N/A"}
              </span>
            </div>
            {grounding && (
              <div className="flex items-center justify-between gap-2">
                <span className="flex-shrink-0 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                  Grounding
                </span>
                <span
                  className={`chip flex-shrink-0 ${
                    grounding.is_stub ?? grounding.is_real === false
                      ? "border-amber-500/20 bg-amber-500/10 text-amber-400"
                      : "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
                  }`}
                >
                  {(grounding.is_stub ?? grounding.is_real === false) ? "STUB" : "REAL"}
                </span>
              </div>
            )}
          </section>

          {parameterEntries.length > 0 && (
            <section>
              <h3 className="mb-2.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                Parameters
              </h3>
              <dl className="space-y-1.5">
                {parameterEntries.map(([k, v]) => (
                  <div key={k} className="flex items-baseline justify-between gap-2">
                    <dt className="min-w-0 truncate text-[11px] text-slate-500">{k}</dt>
                    <span aria-hidden="true" className="mx-1 min-w-[8px] flex-1 border-b border-dotted border-slate-800" />
                    <dd className="flex-shrink-0 whitespace-nowrap font-mono text-[11px] tabular-nums text-slate-300">
                      {String(v)}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          )}

          <div className="flex items-center justify-between pt-1">
            <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
              Evidence
            </span>
            <span className="text-[11px] text-slate-300">
              {trace.evidence_refs.length} reference{trace.evidence_refs.length !== 1 ? "s" : ""}
            </span>
          </div>
        </div>
      )}
    </Panel>
  );
}
