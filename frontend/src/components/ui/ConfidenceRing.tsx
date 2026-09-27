interface ConfidenceRingProps {
  /** Confidence as a 0–1 ratio, or null while no result is available. */
  value: number | null;
}

const SIZE = 132;
const STROKE = 9;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

type Band = { label: string; stroke: string; text: string; pill: string };

function getBand(score: number): Band {
  if (score >= 0.75) {
    return {
      label: "HIGH",
      stroke: "stroke-emerald-400",
      text: "text-emerald-300",
      pill: "border-emerald-500/20 bg-emerald-500/10 text-emerald-400",
    };
  }
  if (score >= 0.45) {
    return {
      label: "MEDIUM",
      stroke: "stroke-amber-400",
      text: "text-amber-300",
      pill: "border-amber-500/20 bg-amber-500/10 text-amber-400",
    };
  }
  return {
    label: "LOW",
    stroke: "stroke-rose-400",
    text: "text-rose-300",
    pill: "border-rose-500/20 bg-rose-500/10 text-rose-400",
  };
}

/** Circular radial gauge: animated SVG ring with the percentage at its centre. */
export default function ConfidenceRing({ value }: ConfidenceRingProps) {
  if (value === null || !Number.isFinite(value)) return null;

  const score = Math.min(1, Math.max(0, value));
  const pct = Math.round(score * 100);
  const band = getBand(score);
  const offset = CIRCUMFERENCE * (1 - score);

  return (
    <div className="flex flex-col items-center gap-3">
      <div
        className="relative"
        style={{ width: SIZE, height: SIZE }}
        role="img"
        aria-label={`Confidence ${pct} percent, rated ${band.label.toLowerCase()}`}
      >
        <svg
          width={SIZE}
          height={SIZE}
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          className="-rotate-90"
          aria-hidden="true"
        >
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            strokeWidth={STROKE}
            className="stroke-slate-800"
          />
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            strokeWidth={STROKE}
            strokeLinecap="round"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={offset}
            className={`${band.stroke} transition-[stroke-dashoffset] duration-700 ease-out`}
          />
        </svg>

        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={`font-mono text-3xl font-bold tabular-nums leading-none ${band.text}`}>
            {pct}
            <span className="text-lg">%</span>
          </span>
          <span className="mt-1 text-[10px] font-medium uppercase tracking-[0.12em] text-slate-500">
            Confidence
          </span>
        </div>
      </div>

      <span className={`tag ${band.pill}`}>{band.label}</span>
    </div>
  );
}
