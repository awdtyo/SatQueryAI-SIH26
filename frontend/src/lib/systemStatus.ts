/**
 * Honest system-status derivation.
 *
 * Every value in this module is read from something the app actually knows:
 *
 * - `HealthState.status` — the transport-level health probe result.
 * - `HealthState.specialists.registry[*].is_real` / `.load_error` — what
 *   `backend/registry.py:list_specialists()` reports per specialist. `is_real:
 *   false` means the specialist is a *stub*, which is a different fact from
 *   "unreachable", so it gets its own state rather than a fake green pill.
 * - `ExecutionTrace.task` / `.models_used` / `.evidence_refs` — what the last
 *   response actually reported.
 * - `isRunning` — the real pending flag of the outgoing request.
 *
 * Nothing here invents a status. When the backend does not report a module at
 * all (the Gradio transport has no `/api/health`), the module resolves to
 * `unknown` and the UI says so instead of showing a healthy green dot.
 */

import type { ExecutionTrace, HealthState, SpecialistHealth } from "../types/api";

/** Semantic module state. `unknown` is a first-class, renderable answer. */
export type ModuleState =
  | "ready"
  | "active"
  | "processing"
  | "complete"
  | "waiting"
  | "stub"
  | "error"
  | "unknown";

export interface ModuleStatus {
  key: string;
  label: string;
  state: ModuleState;
  /** Short, real detail — adapter filename, device, scene id. Never invented. */
  detail?: string;
}

/** The five nodes the request actually travels through, front to back. */
export const TRACE_NODES = [
  "Controller",
  "Query Router",
  "Vision Model",
  "Grounding",
  "Evidence",
] as const;

export type TraceNode = (typeof TRACE_NODES)[number];

/**
 * Which specialist a routed task lands on, using the alias table in
 * `backend/registry.py:_REGISTRY`. Returns `null` for an unrecognised task
 * rather than guessing at the nearest module.
 */
export function routedModule(task: string | undefined | null): string | null {
  const t = (task ?? "").trim().toLowerCase();
  if (!t) return null;
  if (["vqa", "captioning", "visual_question_answering", "vqa_captioning", "describe"].includes(t)) {
    return "vqa";
  }
  if (["count", "counting", "yolo"].includes(t)) return "yolo";
  if (["grounding", "visual_grounding"].includes(t)) return "grounding";
  if (["change_detection", "change", "cdvqa"].includes(t)) return "change_detection";
  if (["optical_sar_fusion", "fusion", "sar"].includes(t)) return "optical_sar_fusion";
  return null;
}

/** Display rows, in pipeline order. `registryKey` is the real /api/health key. */
interface ModuleDef {
  key: string;
  label: string;
  registryKey?: string;
}

const MODULES: ModuleDef[] = [
  { key: "controller", label: "Controller" },
  { key: "vqa", label: "Vision Model", registryKey: "vqa (real)" },
  { key: "yolo", label: "Object Detection", registryKey: "yolo (real)" },
  { key: "grounding", label: "Grounding Engine", registryKey: "grounding (real)" },
  { key: "change_detection", label: "Change Detection", registryKey: "change_detection (real)" },
  { key: "optical_sar_fusion", label: "SAR Fusion", registryKey: "optical_sar_fusion (real)" },
];

/** `/api/health` may be absent entirely; treat that as "not reported". */
function registryOf(health: HealthState): Record<string, SpecialistHealth> | undefined {
  const registry = health?.specialists?.registry;
  return registry && typeof registry === "object" ? registry : undefined;
}

function shortFileName(path: string | undefined): string | undefined {
  if (!path) return undefined;
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1];
}

/** Human-readable compute label, derived only from reported values. */
export function computeLabel(health: HealthState): string | null {
  if (!health) return null;
  if (health.force_cpu === true) return "CPU-ONLY";
  const compute = health.compute?.trim();
  if (compute) return compute.toUpperCase();
  if (health.cuda_effective === true) return "CUDA";
  if (health.device) return health.device.toUpperCase();
  return null;
}

/** Device label, omitted rather than defaulted when the backend is silent. */
export function deviceLabel(health: HealthState): string | null {
  const device = health?.device?.trim();
  if (!device) return null;
  return health?.gpu_name ? health.gpu_name : device;
}

/** True only when the health probe actually reported a healthy service. */
export function isServiceOnline(health: HealthState): boolean {
  if (!health) return false;
  return health.status !== "offline" && health.status !== "error";
}

/**
 * Build the status rows.
 *
 * Precedence for a specialist: a load error is the strongest signal, then an
 * in-flight request routed at it, then whatever the last trace reported, then
 * the model's own loaded/stub state, then plain availability.
 */
export function buildModuleStatuses(
  health: HealthState,
  opts: { isRunning: boolean; trace: ExecutionTrace | null },
): ModuleStatus[] {
  const { isRunning, trace } = opts;
  const registry = registryOf(health);
  const online = isServiceOnline(health);
  const routed = routedModule(trace?.task);

  const modelsUsed = Array.isArray(trace?.models_used) ? trace.models_used : [];
  const evidenceCount = Array.isArray(trace?.evidence_refs) ? trace.evidence_refs.length : 0;
  const grounded = evidenceCount > 0 || modelsUsed.some((m) => m.name?.includes("grounding"));

  const rows: ModuleStatus[] = MODULES.map((mod) => {
    if (mod.key === "controller") {
      if (!health) return { key: mod.key, label: mod.label, state: "unknown" };
      if (!online) return { key: mod.key, label: mod.label, state: "error" };
      if (isRunning) return { key: mod.key, label: mod.label, state: "active" };
      if (trace) return { key: mod.key, label: mod.label, state: "complete" };
      return { key: mod.key, label: mod.label, state: "ready" };
    }

    const info = registry?.[mod.registryKey!];
    if (!info) {
      // Backend never told us about this module — say so rather than guess.
      return { key: mod.key, label: mod.label, state: online ? "unknown" : "error" };
    }
    if (info.load_error) {
      return { key: mod.key, label: mod.label, state: "error", detail: "load failed" };
    }
    if (!online) return { key: mod.key, label: mod.label, state: "error" };

    const detail = shortFileName(typeof info.adapter_path === "string" ? info.adapter_path : undefined);
    if (info.is_real !== true) {
      return { key: mod.key, label: mod.label, state: "stub", detail };
    }
    if (isRunning && routed === mod.key) {
      return { key: mod.key, label: mod.label, state: "processing", detail };
    }
    if (trace && routed === mod.key) {
      return { key: mod.key, label: mod.label, state: "complete", detail };
    }
    return { key: mod.key, label: mod.label, state: "ready", detail };
  });

  // Grounding reports on evidence, which the routed module alone cannot express.
  const groundingIndex = rows.findIndex((r) => r.key === "grounding");
  if (groundingIndex !== -1 && rows[groundingIndex]!.state === "ready" && trace) {
    rows[groundingIndex] = { ...rows[groundingIndex]!, state: grounded ? "complete" : "waiting" };
  }

  return rows;
}

/** Compute row, kept separate because it comes from health rather than the registry. */
export function computeStatus(health: HealthState, isRunning: boolean): ModuleStatus {
  const label = computeLabel(health);
  const device = deviceLabel(health);
  if (!health) return { key: "compute", label: "Compute", state: "unknown" };
  if (!isServiceOnline(health)) {
    return { key: "compute", label: "Compute", state: "error", detail: device ?? undefined };
  }
  if (label === null) return { key: "compute", label: "Compute", state: "unknown" };
  return {
    key: "compute",
    label: `Compute · ${label}`,
    state: isRunning ? "active" : "ready",
    detail: device ?? undefined,
  };
}
