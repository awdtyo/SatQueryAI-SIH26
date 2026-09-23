interface Props {
  value: number;
}

const RADIUS = 34;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

function getBand(score: number): { stroke: string; text: string; pill: string; label: string } {
  if (score >= 0.75) {
    return {
      stroke: "#34d399",
      text: "text-emerald-400",
      pill: "border-emerald-500/20 bg-emerald-500/10 text-emerald-400",
      label: "HIGH",
    };
  }
  if (score >= 0.45) {
    return {
      stroke: "#fbbf24",
      text: "text-amber-400",
      pill: "border-amber-500/20 bg-amber-500/10 text-amber-400",
      label: "MEDIUM",
    };
  }
  return {
    stroke: "#fb7185",
    text: "text-rose-400",
    pill: "border-rose-500/20 bg-rose-500/10 text-rose-400",
    label: "LOW",
  };
}

export default function ConfidenceRing({ value }: Props) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  const band = getBand(value);
  const offset = CIRCUMFERENCE * (1 - pct / 100);

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative h-24 w-24" role="img" aria-label={`Confidence ${pct} percent`}>
        <svg viewBox="0 0 80 80" className="h-full w-full -rotate-90">
          <circle cx="40" cy="40" r={RADIUS} fill="none" strokeWidth="7" className="stroke-slate-800" />
          <circle
            cx="40"
            cy="40"
            r={RADIUS}
            fill="none"
            strokeWidth="7"
            strokeLinecap="round"
            stroke={band.stroke}
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={offset}
            style={{ transition: "stroke-dashoffset 0.6s ease" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={`text-[22px] font-bold leading-none tabular-nums ${band.text}`}>
            {pct}
            <span className="text-[13px] font-semibold">%</span>
          </span>
          <span className="mt-1 text-[9px] font-medium uppercase tracking-[0.14em] text-slate-500">
            Confidence
          </span>
        </div>
      </div>
      <span className={`tag px-2.5 uppercase ${band.pill}`}>{band.label}</span>
    </div>
  );
}