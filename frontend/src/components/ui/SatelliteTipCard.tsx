import { SATELLITE_TIPS, pick } from "../../lib/analysisStages";
import useRotatingIndex from "../../hooks/useRotatingIndex";

interface SatelliteTipCardProps {
  intervalMs?: number;
}

/**
 * Rotating factual tip shown while a query is genuinely in flight.
 *
 * The body is keyed on the index so React remounts it each rotation and the
 * fade replays without any transition state. Not a live region — the tip is
 * supplementary, and announcing it every few seconds would drown out the
 * analysis status that screen readers should hear.
 */
export default function SatelliteTipCard({ intervalMs = 3500 }: SatelliteTipCardProps) {
  const index = useRotatingIndex(SATELLITE_TIPS.length, intervalMs, true);
  const tip = pick(SATELLITE_TIPS, index);
  const total = SATELLITE_TIPS.length;

  return (
    <aside className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
      <div className="mb-1.5 flex items-center gap-2">
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          className="flex-shrink-0 text-teal-400"
          aria-hidden="true"
        >
          <path d="M3 14c4-6 14-6 18 0" strokeLinecap="round" />
          <circle cx="12" cy="18" r="2" />
          <path d="M12 4v4" strokeLinecap="round" />
        </svg>
        <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-teal-400">
          Satellite Tip
        </span>
        <span className="ml-auto font-mono text-[10px] tabular-nums text-slate-500">
          {String(index + 1).padStart(2, "0")}/{String(total).padStart(2, "0")}
        </span>
      </div>
      <p key={index} className="animate-fade-in text-[12px] leading-relaxed text-slate-300">
        {tip}
      </p>
    </aside>
  );
}
