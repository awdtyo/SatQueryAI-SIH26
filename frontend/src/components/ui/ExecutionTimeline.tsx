import type { NodeVisualState, TraceNodeView } from "../../lib/analysisStages";

interface TraceNodeListProps {
  nodes: TraceNodeView[];
  /** True while a request is genuinely in flight — draws the transit pulse. */
  inFlight?: boolean;
}

/** Visual treatment per real state. No state is ever implied. */
const NODE_STYLE: Record<NodeVisualState, { ring: string; dot: string; label: string }> = {
  complete: {
    ring: "border-emerald-500/40 bg-emerald-500/10",
    dot: "text-emerald-400",
    label: "text-slate-200",
  },
  ready: {
    ring: "border-teal-500/30 bg-teal-500/[0.07]",
    dot: "bg-teal-400/70",
    label: "text-slate-300",
  },
  pending: {
    ring: "border-slate-700 bg-slate-900",
    dot: "bg-slate-600",
    label: "text-slate-400",
  },
  waiting: {
    ring: "border-slate-800 bg-slate-900",
    dot: "bg-slate-700",
    label: "text-slate-500",
  },
  error: {
    ring: "border-rose-500/40 bg-rose-500/10",
    dot: "bg-rose-400",
    label: "text-rose-300",
  },
};

/**
 * Vertical node chain for the execution trace.
 *
 * Each row renders one real state supplied by `buildTraceView`. While a request
 * is in flight the connector carries a slow travelling pulse — that is the
 * "signal in transit" affordance, and it deliberately completes no node, since
 * the backend reports nothing until the response lands.
 */
export default function TraceNodeList({ nodes, inFlight = false }: TraceNodeListProps) {
  return (
    <ol className="relative" aria-label="Execution trace nodes">
      {/* connector */}
      <span className="absolute bottom-4 left-[11px] top-4 w-px bg-slate-800" aria-hidden="true" />
      {inFlight && (
        <span
          className="trace-transit absolute bottom-4 left-[11px] top-4 w-px"
          aria-hidden="true"
        />
      )}

      {nodes.map((entry, index) => {
        const style = NODE_STYLE[entry.state];
        return (
          <li key={entry.node} className="relative py-1.5">
            <div className="flex items-center gap-2.5">
              <span
                className={`relative z-10 flex h-[22px] w-[22px] flex-shrink-0 items-center justify-center
                  rounded-full border transition-colors duration-200 ${style.ring}`}
              >
                {entry.state === "complete" ? (
                  <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                    <path
                      d="M3.5 8.5l3 3 6-6"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className={style.dot}
                    />
                  </svg>
                ) : entry.state === "error" ? (
                  <span className="h-1.5 w-1.5 rounded-full bg-rose-400" />
                ) : (
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${style.dot} ${
                      inFlight && index === 0 ? "animate-pulse" : ""
                    }`}
                  />
                )}
              </span>

              <span className={`text-[12px] ${style.label}`}>{entry.node}</span>

              {entry.detail && (
                <span
                  className="ml-auto max-w-[45%] truncate font-mono text-[10px] text-slate-500"
                  title={entry.detail}
                >
                  {entry.detail}
                </span>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
