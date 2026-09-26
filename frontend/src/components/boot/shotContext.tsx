import { createContext, useContext, useEffect, useMemo, useRef } from "react";
import type { ReactNode } from "react";
import { runClock } from "../../lib/motion";

/**
 * One clock per shot.
 *
 * Every layer of the intro subscribes and is driven by the same
 * requestAnimationFrame tick, so nothing can drift out of step with anything
 * else. This is the mechanism that lets the boot read as one continuous move
 * rather than several animations that happen to run at once.
 *
 * A writer is called with the shot position in [0..1] and is expected to write
 * transforms, opacities and clip-paths directly to nodes it holds. It must not
 * set React state — the shot renders its DOM once and animates it in place.
 *
 * Subscribe from inside an effect, not during render, so the per-frame work is
 * unambiguously outside the render pass.
 */
export type ShotWriter = (p: number, elapsedMs: number) => void;

/**
 * Structural rather than `RefObject`, because that type widens to `T | null` on
 * React 18. The position is always a number, and writers rely on that.
 */
interface ShotPosition {
  readonly current: number;
}

interface Shot {
  /** Current position on the shot timeline, in [0..1]. */
  readonly position: ShotPosition;
  /** Registers a per-frame writer. Returns an unsubscribe. */
  subscribe: (writer: ShotWriter) => () => void;
}

const ShotContext = createContext<Shot | null>(null);

interface ProviderProps {
  durationMs: number;
  /** Reduced motion: jump to the end state immediately, skipping the movement. */
  instant?: boolean;
  onProgress?: (p: number) => void;
  onEnd?: () => void;
  children: ReactNode;
}

export function ShotProvider({
  durationMs,
  instant = false,
  onProgress,
  onEnd,
  children,
}: ProviderProps) {
  const position = useRef(0);
  const writers = useRef(new Set<ShotWriter>());

  // Latest-callback refs keep the clock's effect free of dependency churn, so a
  // caller passing an inline arrow does not restart the animation loop. They are
  // synced in an effect rather than during render, and declared before the clock
  // effect so the first frame already sees the current callbacks.
  const progressRef = useRef(onProgress);
  const endRef = useRef(onEnd);
  useEffect(() => {
    progressRef.current = onProgress;
    endRef.current = onEnd;
  });

  const shot = useMemo<Shot>(
    () => ({
      position,
      subscribe: (writer: ShotWriter) => {
        writers.current.add(writer);
        return () => {
          writers.current.delete(writer);
        };
      },
    }),
    [],
  );

  useEffect(() => {
    return runClock(durationMs, {
      instant,
      onFrame: (p, elapsed) => {
        position.current = p;
        for (const writer of writers.current) writer(p, elapsed);
        progressRef.current?.(p);
      },
      onEnd: () => endRef.current?.(),
    });
  }, [durationMs, instant]);

  return <ShotContext.Provider value={shot}>{children}</ShotContext.Provider>;
}

/** The enclosing shot, or null outside a `ShotProvider`. */
export function useShot(): Shot | null {
  return useContext(ShotContext);
}
