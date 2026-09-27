import { useEffect, useRef, useState } from "react";
import AnalysisIndicator from "./ui/AnalysisIndicator";
import usePrefersReducedMotion from "../hooks/usePrefersReducedMotion";

interface IntroSequenceProps {
  /** Called once, after the outro completes (or immediately if skipped). */
  onDone: () => void;
}

/** Hold time before the outro starts — keeps the visible sequence near 1.5–2s. */
const HOLD_MS = 1250;
/** Outro duration. */
const OUTRO_MS = 400;
/** Reduced-motion hold: long enough to read the wordmark, no choreography. */
const REDUCED_HOLD_MS = 900;

/** When the status line flips from "initialising" to "online". */
const ONLINE_AT_MS = 850;

const OUTRO_EASE = [0.4, 0, 1, 1] as const;

/**
 * Full-screen boot animation shown once per application load.
 *
 * Runs on mount only — a rerender can never replay it. The dashboard is not
 * rendered behind it; `App` swaps it out when `onDone` fires.
 *
 * Each element's resting state is its *visible* state and the animation only
 * moves it from hidden, using `fill-mode: backwards` so the delay period shows
 * the first keyframe. That means index.css's reduced-motion reset (which
 * shortens animations) plus the zeroed delays below leave every word readable
 * even when no animation runs at all. Nothing here carries information that is
 * unavailable afterwards.
 */
export default function IntroSequence({ onDone }: IntroSequenceProps) {
  const reduced = usePrefersReducedMotion();
  const [leaving, setLeaving] = useState(false);
  const [online, setOnline] = useState(false);
  const finished = useRef(false);

  const hold = reduced ? REDUCED_HOLD_MS : HOLD_MS;
  // Zero the stagger under reduced motion so nothing sits invisible behind a delay.
  const at = (ms: number) => (reduced ? 0 : ms);

  useEffect(() => {
    let outroTimer: ReturnType<typeof setTimeout> | undefined;
    // Under reduced motion the line is already in its final state.
    const onlineTimer = setTimeout(() => setOnline(true), reduced ? 0 : ONLINE_AT_MS);

    const finish = () => {
      if (finished.current) return;
      finished.current = true;
      setLeaving(true);
      outroTimer = setTimeout(onDone, reduced ? 0 : OUTRO_MS);
    };

    const holdTimer = setTimeout(finish, hold);

    // Let an impatient user (or a keyboard user) skip straight through.
    const onSkip = () => finish();
    window.addEventListener("keydown", onSkip);
    window.addEventListener("pointerdown", onSkip);

    return () => {
      clearTimeout(holdTimer);
      clearTimeout(onlineTimer);
      clearTimeout(outroTimer);
      window.removeEventListener("keydown", onSkip);
      window.removeEventListener("pointerdown", onSkip);
    };
  }, [hold, reduced, onDone]);

  const outroStyle = leaving
    ? {
        opacity: 0,
        transition: `opacity ${reduced ? 0 : OUTRO_MS}ms cubic-bezier(${OUTRO_EASE.join(",")})`,
      }
    : undefined;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center overflow-hidden bg-slate-950"
      style={outroStyle}
      role="status"
      aria-label="SatQuery AI — system online"
    >
      {/* backdrop: fine grid + corner vignette */}
      <div className="boot-grid pointer-events-none absolute inset-0" aria-hidden="true" />
      <div
        className="pointer-events-none absolute inset-0"
        aria-hidden="true"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(2,6,23,0) 0%, rgba(2,6,23,0.55) 55%, rgba(2,6,23,0.95) 100%)",
        }}
      />

      <div className="relative flex w-full max-w-lg flex-col items-center px-6 text-center">
        {/* radar + satellite emblem, behind the wordmark */}
        <div
          className="boot-in pointer-events-none absolute inset-0 grid place-items-center"
          style={{ animationDelay: `${at(0)}ms` }}
          aria-hidden="true"
        >
          <AnalysisIndicator size={264} className="opacity-60" />
        </div>

        {/* 1. SATQUERY  2. AI (cyan glow) */}
        <h1
          className="boot-in-blur relative select-none text-[34px] font-semibold leading-none tracking-[0.22em] text-slate-100 sm:text-[42px]"
          style={{ animationDelay: `${at(200)}ms` }}
        >
          SATQUERY
          <span className="ml-3 text-teal-300 drop-shadow-[0_0_10px_rgba(45,212,191,0.55)]">AI</span>
        </h1>

        {/* 3. subtitle */}
        <p
          className="boot-in relative mt-4 font-mono text-[10px] uppercase tracking-[0.42em] text-teal-400/85 sm:text-[11px]"
          style={{ animationDelay: `${at(400)}ms` }}
        >
          Remote Sensing Intelligence
        </p>

        <span
          className="boot-in relative mt-5 h-px w-40 bg-gradient-to-r from-transparent via-teal-500/50 to-transparent"
          style={{ animationDelay: `${at(500)}ms` }}
          aria-hidden="true"
        />

        {/* 4. status line — resolves to SYSTEM ONLINE before the handover */}
        <p
          className={`boot-in relative mt-5 font-mono text-[10px] uppercase tracking-[0.3em] transition-colors duration-300 ${
            online ? "text-teal-300" : "text-slate-500"
          }`}
          style={{ animationDelay: `${at(880)}ms` }}
        >
          {online ? "System online" : "Initialising"}
          {!online && <span className="animate-blink text-teal-500">_</span>}
        </p>
      </div>
    </div>
  );
}
