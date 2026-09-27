import { CAPABILITIES, pick } from "../../lib/analysisStages";
import useRotatingIndex from "../../hooks/useRotatingIndex";

interface CapabilityCardProps {
  intervalMs?: number;
}

/**
 * Compact "what this platform does" card, shown occasionally during a pending
 * run. Only one is ever on screen — the caller decides *when* to mount it.
 */
export default function CapabilityCard({ intervalMs = 4000 }: CapabilityCardProps) {
  const index = useRotatingIndex(CAPABILITIES.length, intervalMs, true);
  const capability = pick(CAPABILITIES, index);

  return (
    <aside className="rounded-lg border border-teal-500/20 bg-teal-500/[0.04] p-3">
      <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-teal-400/80">
        Capability
      </span>
      {/* keyed on index so the cross-fade replays on each rotation */}
      <div key={index} className="animate-fade-in mt-1">
        <p className="font-mono text-[12px] font-semibold tracking-[0.1em] text-teal-300">
          {capability.title}
        </p>
        <p className="mt-1 text-[12px] leading-relaxed text-slate-400">{capability.body}</p>
      </div>
    </aside>
  );
}
