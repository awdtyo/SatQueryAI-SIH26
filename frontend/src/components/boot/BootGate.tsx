import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import BootSequence from "./BootSequence";
import { HANDOFF_AT, LAND_AT, LINE_Y } from "./shot";
import { easeOut, span, spring } from "../../lib/motion";
import type { MorphRect } from "./ImageryMorphFrame";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import { useMissionStatus } from "../../hooks/useMissionStatus";

interface Props {
  children: ReactNode;
}

/**
 * Plays the intro once per page load, then hands the frame off to the dashboard.
 *
 * The reveal is not a separate animation that begins after the morph. The gate's
 * opacity and transform are written from the *same* shot clock as the morph, so
 * the dashboard is already resolving underneath the frame while that frame is
 * still expanding onto it. There is no instant where one animation has stopped
 * and the next has not started.
 *
 * Children stay mounted throughout (App is never remounted), so the health poll
 * and capability fetch begin on the first frame and the intro cannot disturb
 * dashboard state. Until the frame has landed the subtree is `inert`, so the
 * first click cannot land on a panel that is still visually covered.
 */
export default function BootGate({ children }: Props) {
  const reduced = usePrefersReducedMotion();
  const { health, capabilities } = useMissionStatus();

  const [done, setDone] = useState(false);
  const [target, setTarget] = useState<MorphRect | null>(null);
  const gateRef = useRef<HTMLDivElement>(null);
  const landingRef = useRef(-1);

  /**
   * Measure the live imagery panel. App is mounted from the first frame — it is
   * only visually held back by .boot-gate — and `visibility: hidden` preserves
   * layout, so the panel has real geometry long before the morph needs it.
   */
  useEffect(() => {
    const measure = () => {
      const node = document.querySelector('[data-morph="imagery"]');
      if (!(node instanceof HTMLElement)) return;
      const r = node.getBoundingClientRect();
      if (r.width < 40 || r.height < 40) return;
      setTarget({ x: r.left, y: r.top, w: r.width, h: r.height });
    };
    const raf = requestAnimationFrame(measure);
    window.addEventListener("resize", measure);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", measure);
    };
  }, []);

  useEffect(() => {
    const el = gateRef.current;
    if (!el) return;
    if (done) {
      el.removeAttribute("inert");
      el.style.opacity = "";
      el.style.transform = "";
      el.style.willChange = "auto";
      return;
    }
    el.setAttribute("inert", "");
    el.style.willChange = "opacity, transform";
    return () => {
      el.style.willChange = "auto";
    };
  }, [done]);

  /**
   * The gate's reveal, written from the shot position. It runs on the same curve
   * the frame uses for its final expansion, so the dashboard tracks the frame's
   * edge exactly instead of merely running alongside it.
   *
   * Writes go straight to the node — committing React state here would re-render
   * the whole dashboard sixty times a second for the length of the handoff.
   */
  const applyLanding = useCallback(
    (p: number) => {
      const el = gateRef.current;
      if (!el || done) return;
      if (p < HANDOFF_AT) return;

      const k = reduced ? 1 : spring(span(p, HANDOFF_AT, LAND_AT), 0.86, 2.4);
      const e = easeOut(k);
      el.style.opacity = String(e);
      el.style.transform = `scale(${1 - (1 - e) * 0.014}) translate3d(0, ${(1 - e) * 10}px, 0)`;

      if (landingRef.current < 0) {
        el.dataset.landing = "true";
        landingRef.current = 0;
      }
    },
    [done, reduced],
  );

  const handleLanded = useCallback(() => setDone(true), []);

  return (
    <>
      <div ref={gateRef} className="boot-gate h-full" data-revealed={done ? "true" : "false"}>
        {children}
      </div>

      {!done && (
        <BootSequence
          health={health}
          capabilities={capabilities}
          target={target}
          lineY={LINE_Y}
          onProgress={applyLanding}
          onLanded={handleLanded}
        />
      )}
    </>
  );
}
