export type SystemStatus = "online" | "standby" | "error" | "mock";

interface Props {
  status: SystemStatus;
  label?: string;
}

const STYLES: Record<SystemStatus, { pill: string; dot: string }> = {
  online: {
    pill: "border-emerald-500/20 bg-emerald-500/10 text-emerald-400",
    dot: "bg-emerald-400",
  },
  standby: {
    pill: "border-amber-500/20 bg-amber-500/10 text-amber-400",
    dot: "bg-amber-400 animate-pulse",
  },
  error: {
    pill: "border-rose-500/20 bg-rose-500/10 text-rose-400",
    dot: "bg-rose-400",
  },
  mock: {
    pill: "border-slate-600/30 bg-slate-500/10 text-slate-400",
    dot: "bg-slate-400",
  },
};

export default function StatusPill({ status, label }: Props) {
  const style = STYLES[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider ${style.pill}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} aria-hidden="true" />
      {label ?? status}
    </span>
  );
}