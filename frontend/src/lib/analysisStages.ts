/**
 * Front-end analysis sequence.
 *
 * The backend answers a single POST with one `QueryResponse` (answer +
 * `execution_trace` + evidence) — it exposes no streaming stage channel. This
 * module therefore never advances a cursor through a pretend pipeline.
 *
 * Instead it derives one state per node of `TRACE_NODES` from facts that
 * actually exist:
 *
 * - `isRunning` — the real pending flag. While it is set we know *only* that a
 *   request is in flight, so every node stays `pending` and the timeline draws
 *   a travelling "signal in transit" pulse. We do not guess which stage the
 *   server is on.
 * - a returned `ExecutionTrace` — after the response lands, `task`,
 *   `models_used` and `evidence_refs` say precisely which nodes ran.
 *
 * The rotating headline that previously walked through five invented stage
 * names is gone for that reason.
 */

import type { ExecutionTrace, HealthState } from "../types/api";
import { TRACE_NODES, isServiceOnline, routedModule, type TraceNode } from "./systemStatus";

export { TRACE_NODES };
export type { TraceNode };

/** How a single node should be drawn. */
export type NodeVisualState = "ready" | "pending" | "complete" | "waiting" | "error";

export interface TraceNodeView {
  node: TraceNode;
  state: NodeVisualState;
  /** Real annotation from the response — a task name or a model name. */
  detail?: string;
}

export interface TraceView {
  nodes: TraceNodeView[];
  /** True while a request is genuinely in flight; drives the transit pulse. */
  inFlight: boolean;
  /** One honest sentence describing what is known right now. */
  summary: string;
}

function firstModelName(trace: ExecutionTrace, matcher: (name: string) => boolean): string | undefined {
  const models = Array.isArray(trace.models_used) ? trace.models_used : [];
  const hit = models.find((m) => typeof m?.name === "string" && matcher(m.name));
  return hit?.name;
}

/**
 * Derive the node chain from real application state.
 *
 * Idle with no prior run → every node `ready` (the system is up and waiting).
 * Request in flight → every node `pending`, no completion claimed.
 * Response received → each node reports what the trace actually contains.
 */
export function buildTraceView(
  health: HealthState,
  isRunning: boolean,
  trace: ExecutionTrace | null,
): TraceView {
  const nodes: TraceNodeView[] = TRACE_NODES.map((node) => ({ node, state: "ready" }));
  const set = (node: TraceNode, patch: Partial<TraceNodeView>) => {
    const i = nodes.findIndex((n) => n.node === node);
    if (i !== -1) nodes[i] = { ...nodes[i]!, ...patch };
  };

  const online = isServiceOnline(health);

  if (isRunning) {
    // Nothing beyond "a request is open" is knowable here.
    return {
      nodes: nodes.map((n) => ({ ...n, state: online ? "pending" : "error" })),
      inFlight: true,
      summary: online
        ? "Request in flight — awaiting the response. Stage detail appears when it lands."
        : "Request in flight, but the backend health probe is failing.",
    };
  }

  if (!trace) {
    return {
      nodes: nodes.map((n) => ({ ...n, state: online ? "ready" : "error" })),
      inFlight: false,
      summary: online ? "System ready — no analysis has run yet." : "Backend unreachable.",
    };
  }

  const task = typeof trace.task === "string" ? trace.task : "";
  const routed = routedModule(task);
  const models = Array.isArray(trace.models_used) ? trace.models_used : [];
  const evidence = Array.isArray(trace.evidence_refs) ? trace.evidence_refs.length : 0;

  // Controller answered — that is a fact, we hold its response.
  set("Controller", { state: "complete" });

  // Router ran if it named a task we recognise.
  set("Query Router", routed ? { state: "complete", detail: task.replace(/_/g, " ") } : { state: "waiting" });

  // Vision model ran only if the route landed on a vision specialist.
  const visionKeys = ["vqa", "yolo", "change_detection", "optical_sar_fusion"];
  if (routed && visionKeys.includes(routed)) {
    const name =
      firstModelName(trace, (n) => n.includes(routed === "yolo" ? "yolo" : routed)) ??
      (models[0]?.name || undefined);
    set("Vision Model", { state: "complete", detail: name });
  } else {
    set("Vision Model", { state: "waiting" });
  }

  const groundingModel = firstModelName(trace, (n) => n.includes("grounding"));
  set("Grounding", {
    state: evidence > 0 || groundingModel ? "complete" : "waiting",
    detail: groundingModel,
  });

  set("Evidence", {
    state: evidence > 0 ? "complete" : "waiting",
    detail: evidence > 0 ? `${evidence} reference${evidence === 1 ? "" : "s"}` : undefined,
  });

  return {
    nodes,
    inFlight: false,
    summary: routed
      ? `Completed — routed to ${task.replace(/_/g, " ")}.`
      : "Completed — the response did not name a task.",
  };
}

/** Factual background on satellite imagery, shown while a run is pending. */
export const SATELLITE_TIPS = [
  "Sentinel-2 provides multispectral optical imagery useful for vegetation, water and land-cover analysis.",
  "SAR imagery can capture information even when optical imagery is affected by clouds or darkness.",
  "Bi-temporal imagery can be used to identify changes between two observations.",
  "Grounding connects generated answers to visual evidence in satellite imagery.",
  "Natural-language querying allows users to ask questions about satellite imagery without manually navigating complex analysis tools.",
] as const;

/** What the platform can do — surfaced occasionally during a pending run. */
export const CAPABILITIES = [
  {
    title: "VQA + GROUNDING",
    body: "Question answering over imagery, with answers linked to the regions that support them.",
  },
  {
    title: "OPTICAL + SAR ANALYSIS",
    body: "Pairing optical imagery with radar so analysis continues through cloud and darkness.",
  },
  {
    title: "BI-TEMPORAL CHANGE DETECTION",
    body: "Comparing two dated observations to isolate what changed, and where.",
  },
  {
    title: "SATELLITE SEARCH",
    body: "Resolving a place name or coordinate into dated scenes from public satellite archives.",
  },
  {
    title: "EVIDENCE-GROUNDED ANSWERS",
    body: "Each conclusion carries references back to the imagery it was drawn from.",
  },
  {
    title: "NATURAL LANGUAGE QUERIES",
    body: "Ask about a scene in plain language instead of driving complex analysis tools.",
  },
] as const;

/**
 * Index-safe pick from a readonly list. The rotating hooks only ever return an
 * in-range index, so this just states that invariant for the type checker
 * instead of scattering `!` or fallbacks at each call site.
 */
export function pick<T>(items: readonly T[], index: number): T {
  const length = items.length;
  return items[((index % length) + length) % length] as T;
}
