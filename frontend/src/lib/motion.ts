/**
 * Motion system — the single source of truth for timing, easing and continuity.
 *
 * Two rules govern everything here:
 *
 * 1. ONE CURVE SET. Every transition in the app, whether it is driven from a
 *    rAF loop or from a CSS transition, resolves through one of the EASE
 *    constants below. The cubic-bezier values are the exact control points of
 *    the JS curves, so a hand-off between the two worlds is seamless — a value
 *    interpolated on the main thread and a value interpolated by the compositor
 *    land on the same value at the same moment.
 *
 * 2. MOTION IS DERIVED, NOT SWITCHED. A state change never decides what is
 *    visible; it only moves a single normalized position along a timeline. What
 *    is visible is a continuous function of that position. This is what makes
 *    one beat cause the next instead of one animation stopping and another
 *    starting.
 */

/* ═══════════════════════════════════════════════════════════════════════════
   Easing
   ═══════════════════════════════════════════════════════════════════════════ */

const clamp01 = (n: number) => (n < 0 ? 0 : n > 1 ? 1 : n);

/** Remaps [a,b] → [0,1], clamped. Inverse of the segment windows below. */
export function span(t: number, a: number, b: number): number {
  if (b === a) return t >= b ? 1 : 0;
  return clamp01((t - a) / (b - a));
}

/**
 * Decelerating curve for anything entering or moving: fast departure, long
 * settle. `cubic-bezier(0.16, 1, 0.3, 1)`.
 */
export function easeOut(t: number): number {
  const x = clamp01(t);
  return 1 - Math.pow(1 - x, 4.2);
}

/**
 * Symmetric curve for elements that travel across the screen and arrive from
 * both ends. `cubic-bezier(0.65, 0, 0.35, 1)`.
 */
export function easeInOut(t: number): number {
  const x = clamp01(t);
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
}

/**
 * Anticipation. Pulls slightly *backwards* before committing, so an element
 * appears to gather itself before it moves. Only correct on the leading edge of
 * a transition — never on a dismissal.
 */
export function easeAnticipate(t: number): number {
  const x = clamp01(t);
  // Negative dip around 15% progress, then forward.
  return easeOut(x) - 0.14 * Math.sin(Math.PI * Math.pow(x, 0.55)) * (1 - x);
}

/**
 * Damped spring, closed form. Slight overshoot then settle — used for the final
 * few percent of a move so nothing arrives dead-stopped.
 *
 * ζ (dampingRatio) below 1 gives one small overshoot; at 1 it is critically
 * damped and never overshoots.
 */
export function spring(t: number, dampingRatio = 0.82, frequency = 2.4): number {
  const x = clamp01(t);
  if (x === 1) return 1;
  const w0 = frequency * Math.PI;
  const zeta = dampingRatio;
  const wd = w0 * Math.sqrt(1 - zeta * zeta);
  const decay = (Math.exp(-zeta * w0 * x) * (Math.cos(wd * x) + ((zeta * w0) / wd) * Math.sin(wd * x)));
  return 1 - decay;
}

/** Continuous loop with no directional easing — rotation, drift, scan. */
export const linear = (t: number) => clamp01(t);

export const EASE = { out: easeOut, inOut: easeInOut, anticipate: easeAnticipate, spring, linear } as const;
export type EaseName = keyof typeof EASE;

export function ease(name: EaseName, t: number): number {
  return EASE[name](t);
}

/**
 * The same curves as CSS custom properties. Referenced by index.css so a CSS
 * transition and a rAF interpolation of the same beat cannot disagree.
 */
export const CSS_EASE = {
  out: "cubic-bezier(0.16, 1, 0.3, 1)",
  inOut: "cubic-bezier(0.65, 0, 0.35, 1)",
  anticipate: "cubic-bezier(0.34, 1.4, 0.5, 1)",
  spring: "cubic-bezier(0.22, 1.35, 0.36, 1)",
  linear: "linear",
} as const;

/* ═══════════════════════════════════════════════════════════════════════════
   Beats
   A beat is one unit of choreography: anticipation → movement → settle. Beats
   are positioned on a shared normalized timeline and their windows are allowed
   to overlap, which is what produces cross-fades rather than cuts.
   ═══════════════════════════════════════════════════════════════════════════ */

export interface BeatSpec {
  /** Where the beat begins, in normalized shot position [0..1]. */
  at: number;
  /** How long the movement takes, in normalized position. */
  span: number;
  /** How long the element lingers after settling before it may leave. */
  hold?: number;
  /**
   * Opacity ramp duration as a fraction of `span`. Longer than the movement
   * means the element is still fading in while it is already moving, and still
   * at full opacity when it starts to move away.
   */
  feather?: number;
  /** Movement easing. */
  ease?: EaseName;
  /** Opacity easing — anticipation reads as a slow brighten, not a fade-in. */
  fadeEase?: EaseName;
}

export interface BeatState {
  /** 0→1 movement progress through the ease curve. */
  at: number;
  /** Raw 0→1 presence before the fade ease is applied. */
  present: number;
  /** Movement progress, for transforms. */
  move: number;
  /** 0→1 opacity. */
  opacity: number;
  /** True while the element is still arriving — for play/pause affordances. */
  arriving: boolean;
  /** True once movement has settled but the element has not left. */
  settled: boolean;
}

/**
 * Evaluates one beat at position `p` on the shot timeline.
 *
 * Presence is a trapezoid: it ramps over `feather`, holds, then ramps down over
 * `feather` once the beat's total occupancy has elapsed. Because occupancy is
 * `span + hold + feather`, adjacent beats naturally overlap — the outgoing beat
 * is still visible while the incoming one is arriving.
 */
export function beat(p: number, spec: BeatSpec): BeatState {
  const { at, span: s, hold = 0, feather = 0.6, ease: easeName = "out", fadeEase = "inOut" } = spec;
  const f = Math.max(0.001, feather * s);
  const exit = at + s + hold;
  const end = exit + f;

  const raw = span(p, at, at + s);
  const move = ease(easeName, raw);
  const present = span(p, at, at + f) * (1 - span(p, exit, end));

  return {
    at: raw,
    present,
    move,
    opacity: ease(fadeEase, present),
    arriving: p >= at && p < at + s,
    settled: p >= at + s && p < end,
  };
}

/**
 * A looping continuous motion whose phase is derived from the shot clock rather
 * than from CSS wall-clock animation. Deriving it means the loop never restarts
 * when a beat changes, and it freezes coherently with everything else when the
 * shot pauses.
 */
export function loop(p: number, turns: number, from = 0, to = 1): number {
  if (turns === 0) return from;
  return from + (to - from) * ((p * turns) % 1);
}

/* ═══════════════════════════════════════════════════════════════════════════
   Clock
   ═══════════════════════════════════════════════════════════════════════════ */

export interface ClockOptions {
  /**
   * When true the clock runs on a virtual timeline, advancing to its end
   * immediately. Reduced motion removes movement, never the state it conveys.
   */
  instant?: boolean;
  onFrame?: (position: number, elapsedMs: number) => void;
  onEnd?: () => void;
}

/**
 * A single requestAnimationFrame clock per shot.
 *
 * Deliberately not a React state hook: the whole point is that a 4-second shot
 * commits zero React renders. Callers write transforms straight to the nodes
 * they hold refs to, and only render when the *content* changes (a few times per
 * shot at most).
 *
 * Pauses while the tab is hidden so a backgrounded tab does no work, and
 * advances from the true elapsed time on resume so the shot does not stretch.
 */
export function runClock(durationMs: number, options: ClockOptions = {}): () => void {
  const { instant = false, onFrame, onEnd } = options;

  if (instant) {
    onFrame?.(1, durationMs);
    onEnd?.();
    return () => {};
  }

  const start = performance.now();
  let raf = 0;
  let stopped = false;
  let hiddenAt = 0;
  let carriedMs = 0;

  const frame = (now: number) => {
    if (stopped) return;
    const elapsed = now - start + carriedMs;
    const position = elapsed / durationMs;

    if (position >= 1) {
      onFrame?.(1, durationMs);
      onEnd?.();
      return;
    }
    onFrame?.(position, elapsed);
    raf = requestAnimationFrame(frame);
  };

  const onVisibility = () => {
    if (document.hidden) {
      hiddenAt = performance.now();
    } else if (hiddenAt > 0) {
      // Fold the hidden interval into `carriedMs` so the shot resumes in place.
      carriedMs += performance.now() - hiddenAt;
      hiddenAt = 0;
      raf = requestAnimationFrame(frame);
    }
  };

  document.addEventListener("visibilitychange", onVisibility);
  raf = requestAnimationFrame(frame);

  return () => {
    stopped = true;
    cancelAnimationFrame(raf);
    document.removeEventListener("visibilitychange", onVisibility);
  };
}

/* ═══════════════════════════════════════════════════════════════════════════
   Style writing
   Helpers that keep DOM writes uniform and cheap. Transform strings are built
   in the same order everywhere so the compositor sees a consistent pattern.
   ═══════════════════════════════════════════════════════════════════════════ */

export type TransformParts = {
  x?: number;
  y?: number;
  scale?: number;
  scaleX?: number;
  scaleY?: number;
  rotate?: number;
};

export function transform(p: TransformParts): string {
  let out = "";
  if (p.x !== undefined || p.y !== undefined) {
    out += `translate3d(${p.x ?? 0}px, ${p.y ?? 0}px, 0)`;
  }
  if (p.scale !== undefined) out += ` scale(${p.scale})`;
  if (p.scaleX !== undefined) out += ` scaleX(${p.scaleX})`;
  if (p.scaleY !== undefined) out += ` scaleY(${p.scaleY})`;
  if (p.rotate !== undefined) out += ` rotate(${p.rotate}deg)`;
  return out || "none";
}

/**
 * An `inset()` clip-path, expressed in percent of the element box. Preferred
 * over animating width/height: it is a paint-only property, so the element
 * keeps its layout box and nothing downstream reflows.
 */
export function clipInset(top: number, right: number, bottom: number, left: number): string {
  return `inset(${round(top)}% ${round(right)}% ${round(bottom)}% ${round(left)}%)`;
}

/**
 * `clip-path` revealing a band that travels down the element. Cheaper than a
 * height animation because the layout box never changes.
 */
export function clipBand(progress: number): string {
  return `inset(0% 0% ${round(clamp01(1 - progress) * 100)}% 0% round 0 0 2px 2px)`;
}

function round(n: number): number {
  return Math.round(n * 100) / 100;
}

export const clamp = clamp01;
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const mix = (a: number, b: number, t: number) => lerp(a, b, clamp01(t));
