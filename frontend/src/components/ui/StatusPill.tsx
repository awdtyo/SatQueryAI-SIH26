import type { ModuleState } from "../../lib/systemStatus";

export type StatusKind = ModuleState | "mock";

interface StatusPillProps {
  status: StatusKind;
  /** Optional override for the visible label; defaults to the uppercase status. */
  label?: string;
  className?: string;
}

/**
 * Semantic status palette.
 *
 * teal = interface/ready, emerald = complete, amber = in progress, slate =
 * waiting or unreported, rose = failed. The `unknown` kind is deliberately
 * visible: when the backend does not report a module we say so instead of
 * showing a healthy dot.
 */
const STYLES: Record<StatusKind, { pill: string; dot: string; text: string }> = {
  ready: {
    pill: "border-teal-500/25 bg-teal-500/10 text-teal-300",
    dot: "bg-teal-400",
    text: "READY",
  },
  active: {
    pill: "border-teal-500/30 bg-teal-500/10 text-teal-300",
    dot: "bg-teal-400 animate-pulse",
    text: "ACTIVE",
  },
  processing: {
    pill: "border-amber-500/25 bg-amber-500/10 text-amber-300",
    dot: "bg-amber-400 animate-pulse",
    text: "PROCESSING",
  },
  complete: {
    pill: "border-emerald-500/20 bg-emerald-500/10 text-emerald-400",
    dot: "bg-emerald-400",
    text: "COMPLETE",
  },
  waiting: {
    pill: "border-slate-800 bg-slate-800/60 text-slate-500",
    dot: "bg-slate-600",
    text: "WAITING",
  },
  stub: {
    pill: "border-slate-700 bg-slate-800/60 text-slate-400",
    dot: "bg-slate-500",
    text: "STUB",
  },
  error: {
    pill: "border-rose-500/20 bg-rose-500/10 text-rose-400",
    dot: "bg-rose-400",
    text: "OFFLINE",
  },
  unknown: {
    pill: "border-slate-800 bg-slate-900 text-slate-600",
    dot: "bg-slate-700",
    text: "NOT REPORTED",
  },
  mock: {
    pill: "border-slate-700 bg-slate-800/60 text-slate-400",
    dot: "bg-slate-500",
    text: "MOCK",
  },
};

/** Compact status badge driven by a real application state. */
export default function StatusPill({ status, label, className = "" }: StatusPillProps) {
  const style = STYLES[status];
  const text = label ?? style.text;

  return (
    <span className={`tag ${style.pill} ${className}`} title={text}>
      <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} aria-hidden="true" />
      {text}
    </span>
  );
}
