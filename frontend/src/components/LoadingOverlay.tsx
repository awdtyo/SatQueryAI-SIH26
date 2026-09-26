import { useEffect, useRef, useState } from "react";
import type { InputMode, QueryActivity, QueryResponse } from "../types/api";
import {
  ACTIVITY_RANK,
  ANALYSIS_STAGES,
  AWAITING_RESPONSE_STAGE,
  MISSION_STAGES,
  imageryDescriptor,
} from "../lib/capabilities";
import { useAnalysisStage } from "../hooks/useAnalysisStage";
import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion";
import { mix, span, spring, transform } from "../lib/motion";
import OrbitalIntelligenceCard, { CapabilityModule } from "./analysis/OrbitalIntelligence";
import { OrbitGlyph, ZoomInIcon, ZoomOutIcon } from "./ui/Icons";

interface Props {
  visible: boolean;
  message?: string;
  /** Live query text, shown as the mission query. */
  query?: string;
  /** Real transport phase, when the backend streams one. */
  activity?: QueryActivity | null;
  inputMode?: InputMode;
  imageCount?: number;
  response?: QueryResponse | null;
}

const R = 52;
const CIRCUMFERENCE = 2 * Math.PI * R;

/**
 * Only a real transport phase may override the client sequence. "responding"
 * merely means output is streaming, which tells us nothing about the stage, so
 * it resolves to the honest hold label.
 */
function headline(activity: QueryActivity | null, current: string): string {
  if (!activity) return current;
  return ACTIVITY_RANK[activity] !== undefined ? current : AWAITING_RESPONSE_STAGE;
}

/**
 * ANALYZING EARTH OBSERVATION.
 *
 * The overlay does not fade in over a still dashboard: it enters on the same
 * curve the query bar's submission uses, and everything that moves inside it â€”
 * stage rows, progress ring, percentage readout, background sweep, rotating
 * fact deck â€” is read from the single analysis clock in `useAnalysisStage`.
 *
 * There is no spinner anywhere. The ring and the rows are the same motion seen
 * from two distances, and neither restarts when the stage index changes, because
 * a stage change is a new position on a curve rather than a new animation.
 */
export default function LoadingOverlay({
  visible,
  message,
  query,
  activity,
  inputMode = "single",
  imageCount = 0,
  response = null,
}: Props) {
  const reduced = usePrefersReducedMotion();
  // Destructured so the per-frame effect depends only on the stable `subscribe`
  // identity, not on a fresh object from the hook.
  const { label, index, awaiting, subscribe } = useAnalysisStage(visible);

  const rootRef = useRef<HTMLDivElement>(null);
  const ringRef = useRef<SVGCircleElement>(null);
  const readoutRef = useRef<HTMLSpanElement>(null);
  const rowsRef = useRef<HTMLOListElement>(null);
  const missionRef = useRef<HTMLDivElement>(null);
  const sweepRef = useRef<HTMLDivElement>(null);

  // The fact deck rotates on the same clock as the ring, so its handover is
  // frame-accurate instead of riding on a coarse commit interval.
  const [fact, setFact] = useState(0);

  // One subscription, one clock. This effect depends only on `visible`, so the
  // loop is never torn down and rebuilt as the stage advances.
  useEffect(() => {
    if (!visible) return;
    return subscribe((frame) => {
      const rows = rowsRef.current?.children;
      if (rows) {
        for (let i = 0; i < rows.length; i++) {
          const row = rows[i] as HTMLElement;
          // Each row's window is a slice of the overall progress, so the list
          // fills top-down as one gesture.
          const at = (i / ANALYSIS_STAGES.length) * 0.94;
          const local = span(frame.progress, at, at + 0.16);
          const e = spring(local, 0.7, 2.4);
          row.style.opacity = String(mix(0, 1, e));
          row.style.transform = transform({ x: mix(-10, 0, e), scale: mix(0.985, 1, e) });
        }
      }

      if (ringRef.current) {
        ringRef.current.style.strokeDashoffset = String(CIRCUMFERENCE * (1 - frame.progress));
      }

      // Written directly so the number glides with the ring instead of being
      // quantised to however often React happens to commit.
      if (readoutRef.current) {
        readoutRef.current.textContent = String(Math.round(frame.progress * 100));
      }

      // The sweep is derived from the same clock, so it never restarts when the
      // stage index changes.
      if (sweepRef.current) {
        sweepRef.current.style.transform = `translate3d(0, ${(frame.elapsedMs % 5500) / 55.5}vh, 0)`;
      }

      // Only a genuine boundary change reaches React, and the fact deck
      // cross-fades from there. The functional form keeps `fact` out of this
      // effect's dependencies, so the subscription is never rebuilt.
      setFact((prev) => (prev === frame.fact ? prev : frame.fact));
    });
  }, [visible, subscribe]);

  // Entrance: the overlay arrives from the direction of the query bar, on the
  // project's standard curve. Reduced motion skips straight to the end state.
  useEffect(() => {
    if (!visible) return;
    const el = rootRef.current;
    const mission = missionRef.current;
    if (!el) return;

    if (reduced) {
      el.style.opacity = "1";
      el.style.transform = "none";
      if (mission) {
        mission.style.opacity = "1";
        mission.style.transform = "none";
      }
      return;
    }

    el.style.willChange = "opacity, transform";

    const frame = requestAnimationFrame(() => {
      el.style.transition = "opacity 260ms var(--ease-out), transform 320ms var(--ease-out)";
      el.style.opacity = "1";
      el.style.transform = "none";
    });

    if (mission) {
      // Slightly behind the root and offset along x, so the mission query reads
      // as arriving from the query bar rather than appearing with the panel.
      mission.style.transition = "opacity 340ms var(--ease-out) 60ms, transform 420ms var(--ease-out) 60ms";
      mission.style.opacity = "1";
      mission.style.transform = "none";
    }

    return () => {
      cancelAnimationFrame(frame);
      el.style.willChange = "auto";
      el.style.transition = "";
    };
  }, [visible, reduced]);

  if (!visible) return null;

  const current = label;
  const active = headline(activity ?? null, current);
  const waiting = awaiting;
  const missionQuery = query?.trim() || message || "";
  const sensor = imageryDescriptor(inputMode, imageCount);

  return (
    <div
      ref={rootRef}
      className="analysis-root fixed inset-0 z-40 flex flex-col"
      role="status"
      aria-live="polite"
      style={{ opacity: 0, transform: "translate3d(0, 18px, 0) scale(0.994)" }}
    >
      <div ref={sweepRef} aria-hidden="true" className="analysis-sweep" />
      <div aria-hidden="true" className="analysis-root-grid" />

      <header className="flex flex-shrink-0 items-center gap-3 px-6 py-4 sm:px-8">
        <OrbitGlyph className="h-4 w-4 text-teal-400" />
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-200">
          Analyzing Earth Observation
        </h2>
        <span className="h-px flex-1 bg-gradient-to-r from-teal-500/20 to-transparent" />
        <span className="chip-accent">
          <span className="h-1.5 w-1.5 animate-status-pulse rounded-full bg-current" />
          {sensor}
        </span>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-4 px-6 pb-6 sm:px-8 lg:flex-row lg:gap-6">
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="mx-auto flex w-full max-w-md flex-1 flex-col items-center justify-center">
            <div
              className="analysis-ring"
              role="img"
              aria-label={`Analyzing â€” ${active}`}
            >
              <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
                <circle cx="60" cy="60" r={R} fill="none" stroke="#0f2a33" strokeWidth="2" />
                <circle
                  ref={ringRef}
                  cx="60"
                  cy="60"
                  r={R}
                  fill="none"
                  stroke="url(#ring-grad)"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeDasharray={CIRCUMFERENCE}
                  strokeDashoffset={CIRCUMFERENCE}
                />
                <defs>
                  <linearGradient id="ring-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#2dd4bf" />
                    <stop offset="100%" stopColor="#67e8f9" />
                  </linearGradient>
                </defs>
              </svg>
              {/* The number is written per frame by the clock, so it is always in
                  step with the ring stroke rather than trailing it by a commit. */}
              <span className="ring-readout font-mono text-[19px] tabular-nums text-slate-100">
                <span ref={readoutRef}>0</span>
                <span className="text-[11px] text-slate-500">%</span>
              </span>
              <span className="absolute inset-x-0 -bottom-6 text-center font-mono text-[9.5px] uppercase tracking-[0.18em] text-slate-600">
                {active}
              </span>
            </div>

            <p className="mt-8 text-center font-mono text-[10px] tabular-nums text-slate-600">
              {String(index + 1).padStart(2, "0")} / {String(ANALYSIS_STAGES.length).padStart(2, "0")}
            </p>

            <ol ref={rowsRef} className="mt-5 w-full space-y-2">
              {ANALYSIS_STAGES.map((label, i) => (
                <li
                  key={label}
                  className={`analysis-stage analysis-stage-${index > i ? "complete" : index === i ? "active" : "pending"}`}
                >
                  <span className="analysis-stage-dot" aria-hidden="true" />
                  <span className="flex-1">{label}</span>
                  {index > i && <span className="analysis-stage-tick">OK</span>}
                  {index === i && <span className="analysis-stage-tick">Â·Â·Â·</span>}
                </li>
              ))}
            </ol>
          </div>
        </div>

        <aside className="flex w-full flex-shrink-0 flex-col gap-4 lg:w-[340px]">
          {missionQuery && (
            <div
              ref={missionRef}
              className="mission-query-block"
              style={{ opacity: 0, transform: "translate3d(14px, 0, 0)" }}
            >
              <div className="mb-2 flex items-center gap-2">
                <span className="text-[9.5px] font-semibold uppercase tracking-[0.18em] text-teal-300/90">
                  Mission Query
                </span>
                <span className="h-px flex-1 bg-teal-500/15" />
              </div>
              <p className="text-[12.5px] leading-relaxed text-slate-200">{missionQuery}</p>
              <div className="mt-3 space-y-1">
                {MISSION_STAGES.map((label, i) => {
                  const done = !waiting && i < 3;
                  const current2 = i === 3;
                  return (
                    <p
                      key={label}
                      className={`mission-query-stage ${done ? "mission-query-stage-done" : ""} ${
                        current2 ? "mission-query-stage-active" : ""
                      }`}
                    >
                      {label}
                    </p>
                  );
                })}
              </div>
            </div>
          )}

          <div className="rounded-lg border border-slate-800/80 bg-slate-950/40 p-3.5">
            <OrbitalIntelligenceCard index={fact} />
          </div>

          <div className="rounded-lg border border-slate-800/80 bg-slate-950/40 p-3.5">
            <CapabilityModule inputMode={inputMode} response={response} imageCount={imageCount} />
          </div>
        </aside>
      </div>

      <footer className="flex flex-shrink-0 items-center justify-between gap-4 px-6 pb-5 sm:px-8">
        <div className="flex items-center gap-1.5" aria-hidden="true">
          <ZoomOutIcon className="h-3 w-3 text-slate-700" />
          <div className="relative h-4 w-24 overflow-hidden rounded-sm border border-slate-800">
            <div className="analysis-zoom-sweep absolute inset-0" />
            <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-slate-600" />
          </div>
          <ZoomInIcon className="h-3 w-3 text-slate-700" />
        </div>
        <span className="font-mono text-[9.5px] uppercase tracking-[0.2em] text-slate-700">
          {reduced ? "Reduced motion" : "Processing"}
        </span>
      </footer>
    </div>
  );
}
