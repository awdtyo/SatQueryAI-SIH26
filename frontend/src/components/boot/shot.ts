import type { BeatSpec } from "../../lib/motion";

/**
 * Boot shot score.
 *
 * The intro is a single normalized timeline driven by one rAF clock. There are
 * no phase switches and nothing unmounts: every layer is rendered for the whole
 * shot and its transform, opacity and clip-path are continuous functions of
 * `p`.
 *
 * Beat windows deliberately overlap. The globe is still fully opaque when the
 * title starts arriving, and the title is still legible while the frame closes
 * over it — so no beat ever hands off to an empty stage.
 *
 *   p=0.00  SIGNAL      telemetry resolves, particles drifting
 *   p=0.24  GLOBE       globe sweeps in; signal line retracts
 *   p=0.50  TITLE       wordmark assembles out of the globe's centre
 *   p=0.72  IMAGERY     frame opens on the acquisition readout
 *   p=0.86  MORPH       frame collapses to a line, then lands on the panel
 *   p=1.00  LANDED      frame and dashboard are the same rectangle
 */

export const SHOT_MS = 4200;
export const SHOT_MS_REDUCED = 1500;

/** Header height — the acquired line lands on the app's top border. */
export const LINE_Y = 56;

/**
 * Layer beats. `at` and `span` are positions on the shot, not milliseconds, so
 * the score stays readable and every window is expressed relative to the others.
 */
export const BEATS = {
  /** Telemetry readout: rises with anticipation, then yields to the globe. */
  signal: {
    at: 0.0,
    span: 0.2,
    hold: 0.1,
    feather: 1.1,
    ease: "anticipate",
    fadeEase: "inOut",
  } satisfies BeatSpec,

  /** Globe: enters by scaling up from centre while fading in. */
  globe: {
    at: 0.22,
    span: 0.3,
    hold: 0.4,
    feather: 1.2,
    ease: "spring",
    fadeEase: "inOut",
  } satisfies BeatSpec,

  globeCaption: { at: 0.34, span: 0.14, hold: 0.24, feather: 1.3, ease: "out" } satisfies BeatSpec,

  /** Wordmark assembles as the globe is still present behind it. */
  title: {
    at: 0.5,
    span: 0.16,
    hold: 0.22,
    feather: 1.2,
    ease: "spring",
    fadeEase: "inOut",
  } satisfies BeatSpec,

  /** Subtitle trails the wordmark, then the core status line. */
  titleSub: { at: 0.56, span: 0.12, hold: 0.18, feather: 1.3, ease: "out" } satisfies BeatSpec,
  titleCore: { at: 0.62, span: 0.12, hold: 0.16, feather: 1.3, ease: "out" } satisfies BeatSpec,
} as const;

/**
 * Deliberately not in `BEATS`: the signal line, the acquisition frame and the
 * telemetry chips interpolate *geometry* — a width, a rectangle, a flight path —
 * rather than a single presence value, so they are computed directly in their
 * writers. Giving them beat specs would imply a second source of truth for the
 * same motion.
 */

/**
 * The morph is the shot's ending, and the dashboard reveal is part of it rather
 * than a fade that happens afterwards. `handoff` is where the frame has fully
 * become the top border; `land` is where it has arrived on the imagery panel.
 */
export const HANDOFF_AT = 0.88;
export const LAND_AT = 0.99;

/** Telemetry rows resolve on this schedule, in shot positions. */
export const TELEMETRY_AT = [0.02, 0.05, 0.08, 0.11, 0.14] as const;

export const SIGNAL_ROWS = [
  "ORBITAL LINK",
  "IMAGERY CHANNEL",
  "VISION MODEL",
  "GROUNDING ENGINE",
  "CHANGE DETECTION",
] as const;
