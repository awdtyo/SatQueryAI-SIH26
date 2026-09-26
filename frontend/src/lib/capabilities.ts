import type { EvidenceRef, HealthSnapshot, InputMode, QueryResponse } from "../types/api";

/* ═══════════════════════════════════════════════════════════════════════════
   Real module state
   The backend exposes three shapes and we must never invent a fourth:
     /api/health      → specialists: { registry: {...}, task_map: {...} }
                         where each registry value is a model-info object
                         carrying is_real / is_stub / load_error / compute
     /health          → specialists: { vqa: "ready" | "deferred" | "error", ... }
     Gradio transport → no specialists at all (hardcoded health snapshot)
   Anything we cannot positively confirm resolves to "unknown", which the UI
   renders as UNKNOWN rather than READY.
   ═══════════════════════════════════════════════════════════════════════════ */

export type ModuleState = "ready" | "deferred" | "stub" | "error" | "unknown";

export interface ModuleInfo {
  state: ModuleState;
  detail?: string;
}

function fromModelInfo(info: unknown): ModuleInfo {
  if (typeof info !== "object" || info === null) return { state: "unknown" };
  const rec = info as Record<string, unknown>;
  const detail =
    typeof rec["adapter_path"] === "string"
      ? rec["adapter_path"].split(/[\\/]/).pop()
      : typeof rec["compute"] === "string"
        ? rec["compute"]
        : undefined;
  if (typeof rec["load_error"] === "string" && rec["load_error"]) {
    return { state: "error", detail: rec["load_error"] };
  }
  if (rec["is_stub"] === true) return { state: "stub", detail };
  if (rec["is_real"] === true) return { state: "ready", detail };
  // Present but neither real nor stubbed → loaded without weights loaded yet.
  return { state: "deferred", detail };
}

function fromFlag(flag: unknown): ModuleInfo {
  if (flag === "ready") return { state: "ready" };
  if (flag === "deferred") return { state: "deferred" };
  if (flag === "error") return { state: "error" };
  return { state: "unknown" };
}

/** Normalises every specialist payload shape into one record. */
export function readSpecialists(health: HealthSnapshot | null | undefined): Record<string, ModuleInfo> {
  const out: Record<string, ModuleInfo> = {};
  const raw = health?.specialists;
  if (!raw || typeof raw !== "object") return out;

  // Shape A — /api/health nests everything under `registry`
  const registry = (raw as Record<string, unknown>)["registry"];
  if (registry && typeof registry === "object") {
    for (const [key, value] of Object.entries(registry as Record<string, unknown>)) {
      // Keys look like "vqa (real)", "change_detection (real)"
      const name = key.replace(/\s*\(real\)\s*$/, "");
      out[name] = fromModelInfo(value);
    }
    return out;
  }

  // Shape B — /health returns plain "ready" | "deferred" | "error" strings
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof value === "string") out[key] = fromFlag(value);
  }
  return out;
}

export interface Capabilities {
  vqa: boolean;
  object_detection: boolean;
  spectral_indices: boolean;
  change_detection: boolean;
  live_satellite: boolean;
  visualizations: boolean;
  /** Backend stub — backend/models/grounding.py has no adapter. */
  grounding: boolean;
  fusion: boolean;
}

/**
 * UI rows use short ids; the backend registry uses canonical names.
 * Resolving through this map keeps callers free to use either.
 */
const MODULE_ALIASES: Record<string, string> = {
  change: "change_detection",
  objects: "object_detection",
  indices: "spectral_indices",
  search: "live_satellite",
  viz: "visualizations",
};

/** Resolves one module row, preferring live specialist info over the static map. */
export function resolveModule(
  specialists: Record<string, ModuleInfo>,
  capabilities: Capabilities | null,
  key: string,
): ModuleInfo {
  const canonical = MODULE_ALIASES[key] ?? key;
  const live = specialists[canonical] ?? specialists[key];
  if (live && live.state !== "unknown") return live;
  if (capabilities) {
    const flag = capabilities[canonical as keyof Capabilities];
    if (typeof flag === "boolean") {
      return flag ? { state: "ready" } : { state: "stub" };
    }
  }
  return live ?? { state: "unknown" };
}

/* ═══════════════════════════════════════════════════════════════════════════
   Capability-in-use — derived from real application state only.
   Priority: the backend's own task classification (authoritative) → the
   operator's selected input mode. Never guessed from query text.
   ═══════════════════════════════════════════════════════════════════════════ */

const TASK_CAPABILITY: Array<[RegExp, string]> = [
  [/change|cdvqa|diff/i, "CHANGE DETECTION"],
  [/fusion|sar/i, "OPTICAL + SAR"],
  [/count|yolo|detect/i, "OBJECT DETECTION"],
  [/ground/i, "VISUAL GROUNDING"],
  [/search|geocode|fetch/i, "SATELLITE SEARCH"],
  [/caption/i, "IMAGE CAPTIONING"],
  [/vqa/i, "VISION-LANGUAGE QA"],
];

function fromInputMode(mode: InputMode): string {
  if (mode === "bi-temporal") return "BI-TEMPORAL ANALYSIS";
  if (mode === "optical-sar") return "OPTICAL + SAR";
  return "VISION-LANGUAGE QA";
}

function hasBoundingEvidence(evidence: EvidenceRef[]): boolean {
  return evidence.some((e) => e.type === "bounding_box" || e.type === "overlay");
}

/**
 * What the system is actually doing, right now.
 * `task` comes from the real execution trace once a response exists;
 * before that we fall back to the input mode the operator actually selected.
 */
export function capabilityInUse(
  inputMode: InputMode,
  response: QueryResponse | null,
): string {
  const task = response?.execution_trace?.task;
  if (typeof task === "string" && task) {
    for (const [pattern, label] of TASK_CAPABILITY) {
      if (pattern.test(task)) return label;
    }
  }
  if (hasBoundingEvidence(response?.evidence ?? [])) return "VISUAL GROUNDING";
  return fromInputMode(inputMode);
}

/** Short sensor descriptor for the telemetry strip — reflects the real imagery. */
export function imageryDescriptor(inputMode: InputMode, imageCount: number): string {
  if (imageCount === 0) return "NO DATA";
  if (inputMode === "optical-sar") return "OPTICAL / SAR";
  if (inputMode === "bi-temporal") return "BI-TEMPORAL";
  return "OPTICAL";
}

/* ═══════════════════════════════════════════════════════════════════════════
   Cinematic copy
   ═══════════════════════════════════════════════════════════════════════════ */

/** Section 11 — client-side sequence. Never asserts a completed backend stage. */
export const ANALYSIS_STAGES = [
  "INTERPRETING QUERY",
  "ANALYZING PIXELS",
  "COMPARING FEATURES",
  "SEARCHING VISUAL EVIDENCE",
  "GROUNDING RESPONSE",
  "GENERATING ANSWER",
] as const;

export const AWAITING_RESPONSE_STAGE = "AWAITING MODEL RESPONSE";

/**
 * Maps the transport's real stage tokens onto our six client stages.
 * Gradio emits "queued" and "generating", which are genuine request phases, so
 * they advance the same sequence the timer drives. Anything else — including
 * "responding", which merely means output is streaming — returns undefined and
 * the UI holds at AWAITING_RESPONSE_STAGE.
 */
export const ACTIVITY_RANK: Record<string, number> = {
  queued: 0,
  analyzing: 1,
  generating: 2,
};

/** Section 8 — mission command cascade shown under the submitted query. */
export const MISSION_STAGES = [
  "QUERY UNDERSTANDING",
  "IMAGE ANALYSIS",
  "MODEL ROUTING",
  "VISUAL GROUNDING",
  "EVIDENCE GENERATION",
] as const;

/** Section 10 — the agentic pipeline rendered in the Execution Trace panel. */
export const INTELLIGENCE_PIPELINE = [
  "QUERY",
  "QUERY UNDERSTANDING",
  "IMAGE INTERPRETATION",
  "MODEL ROUTER",
  "VISUAL GROUNDING",
  "EVIDENCE EXTRACTION",
  "RESPONSE",
] as const;

export interface KnowledgeCard {
  id: string;
  title: string;
  body: string;
}

/** Section 12 — rotating remote-sensing facts. */
export const ORBITAL_INTELLIGENCE: KnowledgeCard[] = [
  {
    id: "sentinel-2",
    title: "SENTINEL-2",
    body: "Multispectral optical imagery enables analysis across multiple wavelength bands.",
  },
  {
    id: "sar",
    title: "SAR",
    body: "Radar-based observation provides complementary information to optical imagery.",
  },
  {
    id: "change",
    title: "CHANGE DETECTION",
    body: "Bi-temporal observations can reveal land-cover and structural changes.",
  },
  {
    id: "grounding",
    title: "GROUNDING",
    body: "Visual grounding connects generated answers with image evidence.",
  },
  {
    id: "nlq",
    title: "NATURAL LANGUAGE",
    body: "Users can interact with satellite imagery using natural-language queries.",
  },
];

/** Section 13 — rotating capability module. */
export const CAPABILITY_CARDS: KnowledgeCard[] = [
  { id: "vqa", title: "VISION-LANGUAGE QA", body: "Ask questions directly about satellite imagery." },
  { id: "change", title: "CHANGE DETECTION", body: "Compare observations across time." },
  { id: "fusion", title: "OPTICAL + SAR", body: "Combine complementary remote-sensing modalities." },
  { id: "grounding", title: "VISUAL GROUNDING", body: "Connect responses to image evidence." },
  { id: "search", title: "SATELLITE SEARCH", body: "Locate imagery based on geographic requirements." },
];

/** Section 1 — boot telemetry rows, resolved against real health when known. */
export const BOOT_TELEMETRY = [
  { id: "orbital", label: "ORBITAL LINK" },
  { id: "imagery", label: "IMAGERY CHANNEL" },
  { id: "vqa", label: "VISION MODEL" },
  { id: "grounding", label: "GROUNDING ENGINE" },
  { id: "change", label: "CHANGE DETECTION" },
] as const;
