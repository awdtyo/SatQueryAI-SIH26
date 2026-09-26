import { forwardRef } from "react";
import { BOOT_TELEMETRY, readSpecialists, resolveModule } from "../../lib/capabilities";
import type { Capabilities } from "../../lib/capabilities";
import type { HealthSnapshot } from "../../types/api";
import { TELEMETRY_AT } from "./shot";

interface Props {
  health: HealthSnapshot | null;
  capabilities: Capabilities | null;
}

/**
 * Resolves a boot telemetry row to what the system can actually confirm.
 * Before the health probe lands, rows read CONNECTING — never READY.
 */
function useRowValue(health: HealthSnapshot | null, capabilities: Capabilities | null) {
  const specialists = readSpecialists(health);
  const online = health != null && health.status !== "offline";
  return (id: string): { text: string; tone: "pending" | "ok" | "warn" | "bad" } => {
    if (!online) return { text: "CONNECTING", tone: "pending" };
    if (id === "orbital") return { text: "LINKED", tone: "ok" };
    if (id === "imagery") return { text: "READY", tone: "ok" };
    const module = resolveModule(specialists, capabilities, id);
    switch (module.state) {
      case "ready":
        return { text: "READY", tone: "ok" };
      case "deferred":
        return { text: "DEFERRED", tone: "pending" };
      case "stub":
        return { text: "STUB", tone: "warn" };
      case "error":
        return { text: "ERROR", tone: "bad" };
      default:
        return { text: "UNKNOWN", tone: "pending" };
    }
  };
}

const TONE: Record<string, string> = {
  pending: "text-slate-500",
  ok: "text-teal-300",
  warn: "text-amber-300/90",
  bad: "text-rose-400",
};

/**
 * SIGNAL LAYER — telemetry readout.
 *
 * Rows are always mounted. Each row's arrival and the bar beneath it are driven
 * by the shot clock as custom properties, so a row never pops in: it brightens
 * into place and its underline grows from the left as the value resolves.
 *
 * The value column is fixed-width, so resolving CONNECTING → READY does not
 * shift anything to its right.
 */
const SignalLayer = forwardRef<HTMLDivElement, Props>(function SignalLayer(
  { health, capabilities },
  ref,
) {
  const rowValue = useRowValue(health, capabilities);

  return (
    <div
      ref={ref}
      className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center px-6"
      style={{ visibility: "hidden" }}
    >
      <p className="font-mono text-[10px] uppercase tracking-[0.42em] text-teal-300/80">Satellite Link</p>
      <p className="mt-2 font-mono text-[11px] uppercase tracking-[0.3em] text-slate-500">Establishing</p>

      <dl className="mt-8 w-full max-w-md space-y-2 font-mono text-[10.5px] uppercase tracking-[0.12em]">
        {BOOT_TELEMETRY.map((row, i) => {
          const value = rowValue(row.id);
          return (
            <div
              key={row.id}
              className="boot-telemetry-row flex items-baseline gap-2"
              style={{ ["--row-at" as string]: String(TELEMETRY_AT[i] ?? 0.1) }}
            >
              <dt className="w-[10.5rem] flex-shrink-0 truncate text-slate-500">{row.label}</dt>
              <span aria-hidden="true" className="boot-telemetry-rule mb-[3px] flex-1" />
              <dd
                className={`w-[6.5rem] flex-shrink-0 text-right tabular-nums ${TONE[value.tone]}`}
              >
                {value.text}
              </dd>
            </div>
          );
        })}
      </dl>
    </div>
  );
});

export default SignalLayer;
