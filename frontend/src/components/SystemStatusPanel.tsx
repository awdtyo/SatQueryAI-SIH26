import type { ExecutionTrace, HealthState } from "../types/api";
import StatusPill from "./ui/StatusPill";
import {
  buildModuleStatuses,
  computeLabel,
  computeStatus,
  isServiceOnline,
  type ModuleStatus,
} from "../lib/systemStatus";

interface Props {
  health: HealthState;
  /** Real pending state of the outgoing request. */
  isRunning?: boolean;
  /** Trace from the last response — decides which module was routed. */
  trace?: ExecutionTrace | null;
}

/**
 * System status list — one row per subsystem.
 *
 * Nothing here is hardcoded to "online". Each specialist row reads
 * `/api/health` → `specialists.registry[*]`, so a stub model reports STUB, a
 * failed load reports OFFLINE, and a module the transport never reports says
 * NOT REPORTED. The routed module additionally reports ACTIVE / COMPLETE while
 * a request is in flight or after one has landed.
 */
export default function SystemStatusPanel({ health, isRunning = false, trace = null }: Props) {
  const online = isServiceOnline(health);
  const modules = buildModuleStatuses(health, { isRunning, trace });
  const compute = computeStatus(health, isRunning);
  const rows: ModuleStatus[] = [...modules, compute];
  const label = computeLabel(health);

  return (
    <section className="panel flex-1">
      <header className="panel-header">
        <h2 className="panel-label">System Status</h2>
        <span className="tag-muted ml-auto">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              !health ? "bg-slate-600" : online ? "bg-emerald-400" : "bg-rose-400"
            }`}
            aria-hidden="true"
          />
          {label ?? (health ? "REPORTED" : "NO DATA")}
        </span>
      </header>

      <div className="panel-body overflow-y-auto">
        <ul className="space-y-2.5">
          {rows.map((row) => (
            <li key={row.key} className="flex items-center justify-between gap-2">
              <span className="min-w-0 truncate text-[12px] text-slate-300">{row.label}</span>
              <span className="flex flex-shrink-0 items-center gap-2">
                {row.detail && (
                  <span
                    className="max-w-[110px] truncate font-mono text-[10px] text-slate-600"
                    title={row.detail}
                  >
                    {row.detail}
                  </span>
                )}
                <StatusPill status={row.state} />
              </span>
            </li>
          ))}
        </ul>

        <p className="mt-4 text-[10px] leading-relaxed text-slate-600">
          Specialist rows are read from the backend health registry. A specialist the
          backend reports as <span className="text-slate-500">STUB</span> is reachable but
          running a placeholder model, not a trained one.
        </p>
      </div>
    </section>
  );
}
