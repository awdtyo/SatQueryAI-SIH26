import { useEffect, useState } from "react";

/**
 * Cycles `0 … length - 1` on a fixed interval and returns the current index.
 *
 * `active` gates the timer so a rotation only runs while the thing being
 * described is genuinely on screen — the caller passes the real pending flag.
 * The index is reset to 0 when it stops so a new run always starts at the top.
 */
export default function useRotatingIndex(length: number, intervalMs: number, active: boolean): number {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (!active || length <= 1) {
      setIndex(0);
      return;
    }
    const id = setInterval(() => {
      setIndex((prev) => (prev + 1) % length);
    }, intervalMs);
    return () => clearInterval(id);
  }, [length, intervalMs, active]);

  return index;
}
