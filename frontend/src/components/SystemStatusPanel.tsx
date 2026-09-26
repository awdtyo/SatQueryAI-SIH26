import type { ModuleInfo, ModuleState } from "../lib/capabilities";
import { readSpecialists, resolveModule } from "../lib/capabilities";
import { useMissionStatus } from "../hooks/useMissionStatus";
import StatusPill from "./ui/StatusPill";
import type { StatusKind } from "./ui/StatusPill";
import { Panel, PanelHeader, PanelTitle } from "./ui/Panel";
import { SpinnerIcon } from "./ui/Icons";

/** ModuleState → pill. Anything unconfirmed is UNKNOWN, never READY. */
const PILL: Record<ModuleState, StatusKind> = {
  ready: "online",
  deferred: "standby",
  stub: "standby",
  error: "offline",
  unknown: "unknown",
};

const LABEL: Record<ModuleState, string> = {
  ready: "READY",
  deferred: "DEFERRED",
  stub: "STUB",
  error: "ERROR",
  unknown: "UNKNOWN",
};

interface Row {
  id: string;
  label: string;
  state: ModuleState;
  detail?: string;
  /** Module rows breathe; the controller row is the heartbeat. */
  live: boolean;
}

export default function SystemStatusPanel() {
  const { health, capabilities, probing } = useMissionStatus();
  const offline = health?.status === "offline";
  const specialists = readSpecialists(health);

  /** Resolves a module id, forcing every row to ERROR while the backend is down. */
  const resolve = (id: string): ModuleInfo =>
    offline ? { state: "error" } : resolveModule(specialists, capabilities, id);

  const vqa = resolve("vqa");
  const change = resolve("change_detection");
  const grounding = resolve("grounding");
  const fusion = resolve("fusion");

  const compute = health?.force_cpu ? "cpu-only" : (health?.compute?.toLowerCase() ?? "unknown");
  const device = health?.device ?? "unknown";
  const adapter = health?.adapter_path?.split(/[\\/]/).pop();

  const rows: Row[] = [
    {
      id: "__controller",
      label: "Controller",
      state: probing ? "unknown" : offline ? "error" : "ready",
      live: true,
    },
    { id: "vqa", label: "VQA Module", state: vqa.state, detail: vqa.detail ?? adapter, live: true },
    { id: "change", label: "Change Detection", state: change.state, detail: change.detail, live: false },
    { id: "grounding", label: "Grounding Engine", state: grounding.state, detail: grounding.detail, live: false },
    { id: "fusion", label: "SAR Fusion", state: fusion.state, detail: fusion.detail, live: false },
    {
      id: "__compute",
      label: "Compute",
      state: offline ? "error" : health ? "ready" : "unknown",
      detail: `${compute} · ${device}`,
      live: true,
    },
  ];

  return (
    <Panel className="flex-1">
      <PanelHeader>
        <PanelTitle>System Status</PanelTitle>
        <div className="flex-1" />
        {offline ? (
          <span className="chip border-rose-500/20 bg-rose-500/10 text-rose-400">
            <SpinnerIcon className="h-3 w-3" />
            Reconnecting
          </span>
        ) : (
          <span className="chip border-emerald-500/20 bg-emerald-500/10 text-emerald-400">
            <span className="h-1.5 w-1.5 animate-status-pulse rounded-full bg-emerald-400" />
            {health?.force_cpu ? "CPU-ONLY" : (health?.compute?.toUpperCase() ?? "PROBING")}
          </span>
        )}
      </PanelHeader>

      <ul className="scroll-y flex-1 space-y-2.5 p-4">
        {rows.map((row) => (
          <li
            key={row.id}
            className="flex items-center justify-between gap-2"
            title={row.detail}
          >
            <span className="flex min-w-0 items-center gap-2">
              <span
                aria-hidden="true"
                className={`h-1 w-1 flex-shrink-0 rounded-full ${
                  row.state === "ready"
                    ? "bg-teal-400"
                    : row.state === "error"
                      ? "bg-rose-400"
                      : row.state === "deferred" || row.state === "stub"
                        ? "bg-amber-400/80"
                        : "bg-slate-600"
                } ${row.live && row.state === "ready" ? "animate-status-pulse" : ""}`}
              />
              <span className="min-w-0 truncate text-[12px] text-slate-300">{row.label}</span>
            </span>
            <StatusPill status={PILL[row.state]} label={LABEL[row.state]} detail={row.detail} />
          </li>
        ))}
      </ul>
    </Panel>
  );
}
