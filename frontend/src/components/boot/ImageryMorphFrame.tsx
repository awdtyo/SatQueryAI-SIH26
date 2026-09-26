import { useEffect, useRef } from "react";
import { span, spring, transform } from "../../lib/motion";
import { useShot } from "./shotContext";
import { HANDOFF_AT, LAND_AT } from "./shot";

/** A viewport-space rectangle the morph interpolates between. */
export interface MorphRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface Props {
  /** Viewport rect of the live SATELLITE IMAGERY panel, measured by BootGate. */
  target: MorphRect | null;
  /** Y coordinate of the header's bottom edge — where the acquired line lands. */
  lineY: number;
}

const BASE_W = 460;
const BASE_H = 290;

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t;
}

function lerpRect(a: MorphRect, b: MorphRect, t: number): MorphRect {
  return { x: lerp(a.x, b.x, t), y: lerp(a.y, b.y, t), w: lerp(a.w, b.w, t), h: lerp(a.h, b.h, t) };
}

/**
 * The imagery frame, and the shot's ending.
 *
 * It opens from the centre of the viewport, holds the acquisition readout,
 * collapses to a hairline that becomes the application's top border, and then
 * expands outward until it is *exactly* the live imagery panel.
 *
 * The frame is never unmounted and never faded out by its parent. Its final
 * geometry coincides with the real panel, so when the boot field dissolves the
 * only thing that changes is which layer is on top — the rectangle the user is
 * looking at is literally the same rectangle. That is what makes the handoff
 * read as one continuous move rather than a transition ending and a page
 * beginning.
 */
export default function ImageryMorphFrame({ target, lineY }: Props) {
  const frameRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const shot = useShot();

  useEffect(() => {
    if (!shot) return;
    const el = frameRef.current;
    if (!el) return;

    // Geometry is read on the frame that needs it, so a resize mid-shot is picked
    // up without restarting anything.
    let vw = 0;
    let vh = 0;
    let panel: MorphRect | null = null;

    const measure = () => {
      vw = window.innerWidth;
      vh = window.innerHeight;
      panel = target;
    };
    measure();
    window.addEventListener("resize", measure);

    const unsubscribe = shot.subscribe((p) => {
      if (vw === 0 || vh === 0) return;

      const panelRect: MorphRect = panel ?? {
        x: vw * 0.22,
        y: vh * 0.14,
        w: vw * 0.56,
        h: vh * 0.68,
      };
      const acquired: MorphRect = {
        x: (vw - BASE_W) / 2,
        y: (vh - BASE_H) / 2 - 30,
        w: BASE_W,
        h: BASE_H,
      };
      const line: MorphRect = { x: 0, y: lineY, w: vw, h: 1 };

      // Open: springs up from nothing at the centre.
      const open = spring(span(p, 0.7, 0.86), 0.78, 2.1);
      const openRect: MorphRect = {
        x: lerp(vw / 2, acquired.x, open),
        y: lerp(vh / 2, acquired.y, open),
        w: lerp(0, acquired.w, open),
        h: lerp(0, acquired.h, open),
      };

      let rect: MorphRect;
      if (p < 0.86) {
        rect = openRect;
      } else if (p < HANDOFF_AT) {
        // Collapse toward the line with a smoothstep, so it arrives softly.
        const c = span(p, 0.86, HANDOFF_AT);
        rect = lerpRect(openRect, line, c * c * (3 - 2 * c));
      } else {
        rect = lerpRect(line, panelRect, spring(span(p, HANDOFF_AT, LAND_AT), 0.86, 2.4));
      }

      // Opacity and geometry advance together, so the frame never pops in.
      el.style.transform = transform({
        x: rect.x + rect.w / 2 - vw / 2,
        y: rect.y + rect.h / 2 - vh / 2,
        scaleX: Math.max(0, rect.w / BASE_W),
        scaleY: Math.max(0, rect.h / BASE_H),
      });
      el.style.opacity = String(span(p, 0.7, 0.74));

      // The readout dissolves as the frame starts to collapse, so the text is
      // never stretched as the rectangle narrows underneath it.
      if (overlayRef.current) {
        overlayRef.current.style.opacity = String(span(p, 0.74, 0.8) * (1 - span(p, 0.84, 0.88)));
      }
    });

    return () => {
      window.removeEventListener("resize", measure);
      unsubscribe();
    };
  }, [shot, target, lineY]);

  // Promoted to its own layer only while the shot is running, then released.
  useEffect(() => {
    const el = frameRef.current;
    if (!el) return;
    el.style.willChange = "transform, opacity";
    return () => {
      el.style.willChange = "auto";
    };
  }, []);

  return (
    <div
      ref={frameRef}
      aria-hidden="true"
      className="boot-morph-frame pointer-events-none fixed left-1/2 top-1/2 z-[101] overflow-hidden border border-teal-400/60"
      style={{ width: BASE_W, height: BASE_H, opacity: 0, transformOrigin: "50% 50%" }}
    >
      {/* Abstract remote-sensing texture — decorative only, never a real scene.
          Two grid layers drift at different rates, so it reads as a live
          downlink rather than a static plate. */}
      <div className="boot-imagery-drift absolute inset-[-6%]">
        <div className="boot-imagery-grid absolute inset-0 opacity-60" />
        <div className="boot-imagery-grid absolute inset-0 opacity-30 [animation-direction:reverse]" />
      </div>
      <div className="boot-morph-texture absolute inset-0" />
      <div className="boot-morph-scan absolute inset-0" />
      <div className="boot-morph-vignette absolute inset-0" />

      <div
        ref={overlayRef}
        className="absolute inset-0 flex flex-col items-center justify-center gap-3 opacity-0"
      >
        <p className="font-mono text-[12px] uppercase tracking-[0.34em] text-teal-200">
          Imagery Acquired
        </p>
        <div className="flex items-center gap-2">
          {["OPTICAL", "SAR", "MULTISPECTRAL"].map((band) => (
            <span key={band} className="boot-band-tag font-mono text-[9px] tracking-[0.16em] text-slate-300">
              {band}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

