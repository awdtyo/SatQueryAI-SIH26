export type StatusKind = "online" | "standby" | "offline" | "unknown";

const STYLES: Record<StatusKind, { pill: string; dot: string; text: string }> = {
  online: {
    pill: "border-emerald-500/20 bg-emerald-500/10 text-emerald-400",
    dot: "bg-emerald-400",
    text: "text-emerald-400",
  },
  standby: {
    pill: "border-amber-500/20 bg-amber-500/10 text-amber-400",
    dot: "bg-amber-400",
    text: "text-amber-400",
  },
  offline: {
    pill: "border-rose-500/20 bg-rose-500/10 text-rose-400",
    dot: "bg-rose-400",
    text: "text-rose-400",
  },
  unknown: {
    pill: "border-slate-700 bg-slate-800/80 text-slate-400",
    dot: "bg-slate-500",
    text: "text-slate-400",
  },
};

const DEFAULT_LABEL: Record<StatusKind, string> = {
  online: "ONLINE",
  standby: "STANDBY",
  offline: "OFFLINE",
  unknown: "UNKNOWN",
};

interface Props {
  status: StatusKind;
  /** Overrides the default uppercase status text. */
  label?: string;
  /** Optional secondary line rendered before the pill. */
  detail?: string;
  className?: string;
}

/** Single reusable status badge for every ONLINE / STANDBY / OFFLINE surface. */
export default function StatusPill({ status, label, detail, className = "" }: Props) {
  const style = STYLES[status];
  return (
    <div className={`flex min-w-0 items-center gap-2 ${className}`}>
      {detail && <span className="truncate text-[10px] text-slate-500">{detail}</span>}
      <span
        className={`chip shrink-0 ${style.pill}`}
        title={label ?? DEFAULT_LABEL[status]}
      >
        <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
        {label ?? DEFAULT_LABEL[status]}
      </span>
    </div>
  );
}
