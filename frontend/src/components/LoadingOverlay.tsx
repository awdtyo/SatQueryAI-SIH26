import { useEffect, useState } from "react";
import AnalysisIndicator from "./ui/AnalysisIndicator";
import CapabilityCard from "./ui/CapabilityCard";
import SatelliteTipCard from "./ui/SatelliteTipCard";
import TraceNodeList from "./ui/ExecutionTimeline";
import { buildTraceView } from "../lib/analysisStages";
import type { HealthState } from "../types/api";

interface LoadingOverlayProps {
  /** Real pending state from the query request — nothing here fakes progress. */
  visible: boolean;
  /** Health payload, so the node chain reads READY vs. unreachable. */
  health?: HealthState;
}

/** Tip rotation period. */
const TIP_INTERVAL_MS = 3500;
/** Keep the first seconds clean; surface a capability card only on longer runs. */
const CAPABILITY_AFTER_MS = 4000;

/** Seconds the request has genuinely been in flight. */
function useElapsed(visible: boolean): number {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    if (!visible) {
      setSeconds(0);
      return;
    }
    const started = Date.now();
    const id = setInterval(() => {
      setSeconds(Math.floor((Date.now() - started) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, [visible]);

  return seconds;
}

/** True once a run has been pending long enough to warrant the capability card. */
function useShowCapability(visible: boolean, afterMs: number): boolean {
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (!visible) {
      setShow(false);
      return;
    }
    const id = setTimeout(() => setShow(true), afterMs);
    return () => {
      clearTimeout(id);
      setShow(false);
    };
  }, [visible, afterMs]);

  return show;
}

/**
 * Analysis overlay for an in-flight query.
 *
 * Gated entirely on the real pending flag. The node chain shows nothing
 * complete and no stage cursor walks through invented names — it reads
 * "REQUEST IN FLIGHT" with a travelling signal, which is the only thing the
 * app can honestly claim until the response arrives. The progress bar is
 * indeterminate; elapsed time is measured, not simulated.
 */
export default function LoadingOverlay({ visible, health = null }: LoadingOverlayProps) {
  const seconds = useElapsed(visible);
  const showCapability = useShowCapability(visible, CAPABILITY_AFTER_MS);
  const view = buildTraceView(health, visible, null);

  if (!visible) return null;

  const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");

  return (
    // Scrim is light enough that the right-hand Execution Trace panel keeps
    // animating behind it; the card itself is opaque `bg-slate-900`.
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/65 p-4">
      <section
        className="panel max-h-[90vh] w-full max-w-md overflow-y-auto border-teal-500/25 shadow-2xl"
        aria-label="Analysis in progress"
      >
        <header className="panel-header">
          <h2 className="panel-label">Analysis in Progress</h2>
          <span
            className="ml-auto font-mono text-[11px] tabular-nums text-slate-500"
            aria-hidden="true"
          >
            {mm}:{ss}
          </span>
          <span className="h-1.5 w-1.5 flex-shrink-0 animate-pulse rounded-full bg-teal-400" aria-hidden="true" />
        </header>

        <div className="panel-body space-y-4">
          <p className="sr-only" role="status" aria-live="polite">
            Request in flight. {view.summary}
          </p>

          <div className="flex flex-col items-center gap-3 py-1">
            <AnalysisIndicator size={84} />
            <p className="text-center font-mono text-[12px] font-semibold tracking-[0.16em] text-teal-300">
              Request in flight
            </p>
          </div>

          {/* indeterminate — a real percentage is not knowable until the response lands */}
          <div
            className="relative h-0.5 overflow-hidden rounded-full bg-slate-800"
            role="progressbar"
            aria-label="Analysis in progress"
            aria-busy="true"
          >
            <span className="animate-shimmer absolute inset-y-0 left-0 w-1/3 rounded-full bg-gradient-to-r from-transparent via-teal-400 to-transparent" />
          </div>

          <div className="divider" />

          <TraceNodeList nodes={view.nodes} inFlight={view.inFlight} />

          <div className="divider" />

          <SatelliteTipCard intervalMs={TIP_INTERVAL_MS} />
          {showCapability && <CapabilityCard />}
        </div>
      </section>
    </div>
  );
}
