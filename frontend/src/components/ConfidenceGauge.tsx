interface Props {
  confidence: number | null;
}

function getConfidenceBand(score: number): { label: string; className: string; barColor: string } {
  if (score >= 0.75) return { label: "HIGH", className: "confidence-high", barColor: "bg-signal-green" };
  if (score >= 0.45) return { label: "MEDIUM", className: "confidence-medium", barColor: "bg-signal-amber" };
  return { label: "LOW", className: "confidence-low", barColor: "bg-signal-red" };
}

export default function ConfidenceGauge({ confidence }: Props) {
  if (confidence === null) return null;

  const pct = Math.round(confidence * 100);
  const band = getConfidenceBand(confidence);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-medium text-ink-muted uppercase tracking-[0.1em]">
          Confidence
        </span>
        <span className={`text-[11px] font-semibold tracking-wide ${band.className}`}>
          {band.label}
        </span>
      </div>

      <div className="flex items-baseline gap-1.5">
        <span className={`text-4xl font-bold font-mono tabular-nums leading-none ${band.className}`}>
          {pct}
        </span>
        <span className="text-lg text-ink-muted">%</span>
      </div>

      <div className="flex gap-0.5">
        {Array.from({ length: 20 }, (_, i) => {
          const filled = i < Math.round(pct / 5);
          return (
            <div
              key={i}
              className={`h-2 flex-1 rounded-xs transition-colors duration-500 ${
                filled ? band.barColor : "bg-surface-400/40"
              }`}
            />
          );
        })}
      </div>

      <div className="flex justify-between text-[9px] text-ink-muted">
        <span>0</span>
        <span>25</span>
        <span>50</span>
        <span>75</span>
        <span>100</span>
      </div>
    </div>
  );
}
