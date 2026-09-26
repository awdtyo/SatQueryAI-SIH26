import { useCallback, useEffect, useRef, useState } from "react";
import { ANALYSIS_STAGES, AWAITING_RESPONSE_STAGE } from "../lib/capabilities";

/** How long each client stage is displayed before advancing. */
const STAGE_MS = 1700;

/** Fraction of a stage spent arriving. Movement, not a hard switch. */
const RISE = 0.35;

const LAST = ANALYSIS_STAGES.length - 1;
const TOTAL = (LAST + 1) * STAGE_MS;

/** The ring never closes: a full ring would claim the result is ready. */
const CAP = 0.97;

export interface AnalysisFrame {
  /** Index of the current stage within ANALYSIS_STAGES. */
  index: number;
  /** Continuous arrival across the whole sequence, capped below 1. */
  progress: number;
  /** 0→1 arrival within the current stage; 1 once that stage has settled. */
  arrival: number;
  /** Milliseconds since the overlay opened. */
  elapsedMs: number;
  /** Index into the fact deck, so the deck rotates off the same clock. */
  fact: number;
}

/** Fact deck holds for this long before handing over to the next fact. */
const FACT_MS = 3200;

const INITIAL: AnalysisFrame = { index: 0, progress: 0, arrival: 0, elapsedMs: 0, fact: 0 };

function sample(elapsed: number): AnalysisFrame {
  const index = Math.min(LAST, Math.floor(elapsed / STAGE_MS));
  // Within a stage, rise and settle. Across stages it stays continuous because
  // the next stage begins exactly where this one stopped.
  const arrival = Math.min(1, (elapsed - index * STAGE_MS) / (STAGE_MS * RISE));
  return {
    index,
    progress: Math.min(CAP, (index + arrival) / ANALYSIS_STAGES.length),
    arrival,
    elapsedMs: elapsed,
    fact: Math.floor(elapsed / FACT_MS),
  };
}

export interface AnalysisStageState {
  /** Label to display — the current stage, or the open-ended hold stage. */
  label: string;
  index: number;
  /** True once every client stage has been shown and the request is still open. */
  awaiting: boolean;
  elapsedMs: number;
  /**
   * Register a per-frame writer. This is the same arrangement as the boot shot:
   * the hook owns the only clock, and subscribers write the DOM directly so that
   * continuous values do not need a React commit to look continuous.
   *
   * The writer is called immediately with the current frame, and again on
   * teardown so the resting state matches the final animated frame.
   */
  subscribe: (write: (frame: AnalysisFrame) => void) => () => void;
}

/**
 * Drives the pending-stage sequence for a genuinely in-flight request.
 *
 * A single rAF loop reads real elapsed time, so the stage index, the arrival
 * progress and the rotating fact deck are three views of one number and can never
 * disagree. No setInterval: motion is derived from the clock, so it pauses with
 * the tab and resumes exactly where it was.
 *
 * React only commits when the *stage index* changes, which is rare. Everything
 * that moves every frame is written straight to the DOM by subscribers.
 *
 * Never reports completion. The index saturates at the last stage, the label
 * switches to AWAITING_RESPONSE_STAGE, and progress caps at CAP — the client
 * cannot know when the model will answer.
 */
export function useAnalysisStage(active: boolean): AnalysisStageState {
  const [committed, setCommitted] = useState(INITIAL);
  const live = useRef<AnalysisFrame>(INITIAL);
  const writers = useRef(new Set<(frame: AnalysisFrame) => void>());

  const subscribe = useCallback((write: (frame: AnalysisFrame) => void) => {
    writers.current.add(write);
    write(live.current);
    return () => {
      writers.current.delete(write);
    };
  }, []);

  useEffect(() => {
    if (!active) return;

    // Captured so the cleanup closes over this run's subscriber set rather than
    // re-reading the ref later.
    const subscribers = writers.current;
    const start = performance.now();
    let raf = 0;
    let lastIndex = -1;

    // A new request always restarts from the first stage rather than inheriting
    // wherever the previous one happened to be.
    live.current = sample(0);

    const tick = (now: number) => {
      const frame = sample(now - start);
      live.current = frame;
      for (const write of subscribers) write(frame);

      // Text changes are the only thing worth a React commit.
      if (frame.index !== lastIndex) {
        lastIndex = frame.index;
        setCommitted(frame);
      }
      raf = requestAnimationFrame(tick);
    };

    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      // Paint the last real frame one final time, so whatever is left on screen
      // is where the motion actually stopped.
      for (const write of subscribers) write(live.current);
    };
  }, [active]);

  const awaiting = committed.index >= LAST;

  return {
    label: awaiting ? AWAITING_RESPONSE_STAGE : ANALYSIS_STAGES[committed.index]!,
    index: committed.index,
    awaiting,
    elapsedMs: committed.elapsedMs,
    subscribe,
  };
}

export { TOTAL as ANALYSIS_TOTAL_MS };
