import { useCallback, useEffect, useRef } from "react";
import SignalLayer from "./SignalLayer";
import EarthGlobe from "./EarthGlobe";
import TitleLayer, { GLYPH_SELECTOR } from "./TitleLayer";
import ImageryMorphFrame from "./ImageryMorphFrame";
import TelemetryParticles from "./TelemetryParticles";
import type { MorphRect } from "./ImageryMorphFrame";
import { BEATS, HANDOFF_AT, LAND_AT, SHOT_MS, SHOT_MS_REDUCED } from "./shot";
import { ShotProvider, useShot } from "./shotContext";
import { beat, clipInset, easeInOut, easeOut, mix, span, spring, transform } from "../../lib/motion";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import type { Capabilities } from "../../lib/capabilities";
import type { HealthSnapshot } from "../../types/api";

interface Props {
  health: HealthSnapshot | null;
  capabilities: Capabilities | null;
  target: MorphRect | null;
  lineY: number;
  /** Shot position, for consumers that must track the morph (the gate reveal). */
  onProgress: (p: number) => void;
  onLanded: () => void;
}

/** Chips that fly out toward the panels they become. */
const FLY_CHIPS = [
  { label: "IMAGERY INPUT", x: 0.08, y: 0.22, dx: -70, dy: -10 },
  { label: "EXECUTION TRACE", x: 0.8, y: 0.22, dx: 46, dy: -10 },
  { label: "SYSTEM STATUS", x: 0.8, y: 0.7, dx: 46, dy: 56 },
] as const;

/**
 * The whole intro, as one clock and one set of layers.
 *
 * Nothing mounts or unmounts during the shot. Each layer is rendered once and
 * its transform, opacity and clip-path are continuous functions of the shot
 * position, so every beat is caused by the previous one rather than replacing
 * it. Beat windows overlap, so a departing layer is still on screen when the
 * next one arrives.
 *
 * Zero React commits across the intro: the shot's single writer writes styles
 * straight to the nodes it holds.
 */
function Shot({ health, capabilities, target, lineY }: Props) {
  const rootRef = useRef<HTMLDivElement>(null);
  const signalRef = useRef<HTMLDivElement>(null);
  const signalLineRef = useRef<HTMLDivElement>(null);
  const globeRef = useRef<HTMLDivElement>(null);
  const globeCaptionRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLDivElement>(null);
  const titleSubRef = useRef<HTMLDivElement>(null);
  const titleCoreRef = useRef<HTMLDivElement>(null);
  const flyRefs = useRef<Array<HTMLSpanElement | null>>([]);
  const shot = useShot();

  // `target` and `lineY` are consumed by the morph frame and the gate reveal, not
  // by this writer, so they are intentionally not read here.
  void target;
  void lineY;

  useEffect(() => {
    if (!shot) return;

    // Glyph nodes are resolved once, on the first frame, when the title layer is
    // in the DOM. A local rather than a ref: nothing outside this effect needs
    // them, and they live exactly as long as the subscription does.
    let glyphs: Array<{ el: HTMLElement; at: number }> = [];

    return shot.subscribe((p) => {
      if (glyphs.length === 0 && titleRef.current) {
        glyphs = Array.from(titleRef.current.querySelectorAll<HTMLElement>(GLYPH_SELECTOR)).map(
          (el) => ({ el, at: Number(el.dataset.glyphAt ?? 0) }),
        );
      }

      const root = rootRef.current;
      if (root) {
        // The field dissolves as the frame becomes the dashboard, and not before.
        const land = spring(span(p, HANDOFF_AT, LAND_AT), 0.9, 3);
        root.style.opacity = String(1 - land * 0.94);
      }

      // ── Signal: arrives low, brightens, then continues up as it leaves ──
      const signal = beat(p, BEATS.signal);
      const el = signalRef.current;
      if (el) {
        el.style.opacity = String(signal.opacity);
        el.style.transform = transform({ y: mix(26, 0, signal.move) });
        // clip-path reveals the rows top-down, so they read as arriving in order.
        el.style.clipPath = clipInset((1 - signal.present) * 100, 0, 0, 0);
        el.style.visibility = signal.opacity < 0.004 ? "hidden" : "visible";
      }

      // ── Signal line: draws across, holds, retracts from the right ──
      const line = signalLineRef.current;
      if (line) {
        const draw = easeOut(span(p, 0.02, 0.11));
        const retract = easeInOut(span(p, 0.3, 0.4));
        line.style.opacity = String(0.9 * span(p, 0.02, 0.05) * (1 - retract));
        line.style.transformOrigin = "left center";
        line.style.transform = `scaleX(${draw * (1 - retract)})`;
      }

      // ── Globe: springs up from the centre, then recedes behind the title ──
      const globe = beat(p, BEATS.globe);
      const g = globeRef.current;
      if (g) {
        // Once the title is established, the globe drifts back rather than cutting.
        const recede = spring(span(p, 0.62, 0.8), 0.9, 2.4);
        g.style.opacity = String(globe.opacity * (1 - recede * 0.55));
        g.style.transform = transform({
          scale: mix(0.82, 1, globe.move) * (1 - recede * 0.12),
        });
        g.style.visibility = globe.opacity < 0.004 ? "hidden" : "visible";
      }

      const caption = beat(p, BEATS.globeCaption);
      const cap = globeCaptionRef.current;
      if (cap) {
        cap.style.opacity = String(caption.opacity);
        cap.style.transform = transform({ y: mix(14, 0, caption.move) });
      }

      // ── Title: one progress value drives every glyph ──
      const title = beat(p, BEATS.title);
      const t = titleRef.current;
      if (t) {
        t.style.opacity = String(title.opacity);
        t.style.transform = transform({ scale: mix(1.05, 1, title.move), y: mix(8, 0, title.move) });
        t.style.visibility = title.opacity < 0.004 ? "hidden" : "visible";
      }
      for (const glyph of glyphs) {
        // Each glyph's own window is a slice of the title's progress, so the
        // word assembles left to right out of a single eased value.
        const local = span(title.at, glyph.at * 0.72, glyph.at * 0.72 + 0.28);
        const e = spring(local, 0.7, 2.6);
        glyph.el.style.opacity = String(title.opacity);
        glyph.el.style.transform = transform({
          y: mix(0.34, 0, e),
          scale: mix(0.94, 1, e),
        });
      }

    const sub = beat(p, BEATS.titleSub);
    const s = titleSubRef.current;
    if (s) {
      s.style.opacity = String(sub.opacity);
      s.style.transform = transform({ y: mix(8, 0, sub.move) });
    }

    const core = beat(p, BEATS.titleCore);
    const c = titleCoreRef.current;
    if (c) {
      c.style.opacity = String(core.opacity);
      c.style.transform = transform({ y: mix(6, 0, core.move) });
    }

    // ── Chips: staggered departure, single arrival, resolving before landing ──
    for (let i = 0; i < flyRefs.current.length; i++) {
      const chipEl = flyRefs.current[i];
      const chip = FLY_CHIPS[i];
      if (!chipEl || !chip) continue;
      const start = 0.8 + i * 0.04;
      const local = span(p, start, 0.97);
      const e = spring(local, 0.72, 2.2);
      chipEl.style.opacity = String(Math.min(1, span(p, start, start + 0.05)) * (1 - span(p, 0.95, 1)));
      chipEl.style.transform = transform({
        x: chip.dx * e,
        y: chip.dy * e,
        scale: mix(0.94, 1.02, e),
      });
    }
    });
  }, [shot]);

  return (
    <div
      ref={rootRef}
      role="status"
      aria-live="polite"
      aria-label="Initializing SATQUERY AI remote sensing intelligence"
      className="boot-root pointer-events-none fixed inset-0 z-[100] overflow-hidden bg-[#01050a]"
    >
      {/* One continuous environment behind every beat. */}
      <div aria-hidden="true" className="map-grid absolute inset-0 opacity-40" />
      <div
        aria-hidden="true"
        className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(20,184,166,0.12),transparent_60%)]"
      />
      <div aria-hidden="true" className="boot-scanline absolute inset-0" />

      {/* Ambient particle field. It is active for as long as the shot is on
          screen and stops itself on reduced motion or a hidden tab. */}
      <TelemetryParticles active />

      <SignalLayer ref={signalRef} health={health} capabilities={capabilities} />

      <div
        ref={signalLineRef}
        aria-hidden="true"
        className="boot-signal-line pointer-events-none absolute left-1/2 top-1/2 h-px w-full -translate-x-1/2 bg-gradient-to-r from-transparent via-teal-400/70 to-transparent"
        style={{ transform: "scaleX(0)" }}
      />

      <div ref={globeRef} className="pointer-events-none absolute inset-0 flex items-center justify-center">
        <div className="h-[min(46vh,340px)] w-[min(46vh,340px)]">
          <EarthGlobe />
        </div>
      </div>

      <div
        ref={globeCaptionRef}
        className="pointer-events-none absolute inset-x-0 top-[calc(50%+min(23vh,170px)+28px)] flex flex-col items-center gap-2"
      >
        <p className="font-mono text-[10px] uppercase tracking-[0.42em] text-slate-400">
          Remote Sensing Intelligence
        </p>
        <p className="font-mono text-[9px] uppercase tracking-[0.2em] text-slate-600">
          Orbital acquisition in progress
        </p>
      </div>

      <TitleLayer ref={titleRef} />

      <div
        ref={titleSubRef}
        className="pointer-events-none absolute inset-x-0 top-[calc(50%+44px)] flex justify-center"
      >
        <p className="text-center text-[10px] font-semibold uppercase leading-relaxed tracking-[0.3em] text-slate-400">
          Agentic Vision-Language Assistant
          <br />
          for Remote Sensing
        </p>
      </div>

      <div
        ref={titleCoreRef}
        className="pointer-events-none absolute inset-x-0 top-[calc(50%+96px)] flex justify-center"
      >
        <p className="text-center font-mono text-[10px] uppercase tracking-[0.22em] text-teal-300">
          Intelligence core online
        </p>
      </div>

      <div aria-hidden="true" className="absolute inset-0 z-[102]">
        {FLY_CHIPS.map((chip, i) => (
          <span
            key={chip.label}
            ref={(node) => {
              flyRefs.current[i] = node;
            }}
            className="pointer-events-none absolute font-mono text-[9px] uppercase tracking-[0.2em] text-teal-300/70"
            style={{ left: `${chip.x * 100}%`, top: `${chip.y * 100}%`, opacity: 0 }}
          >
            {chip.label}
          </span>
        ))}
      </div>

      <ImageryMorphFrame target={target} lineY={lineY} />

      <div
        aria-hidden="true"
        className="boot-edge pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-teal-400/50 to-transparent"
      />
    </div>
  );
}

export default function BootSequence(props: Props) {
  const reduced = usePrefersReducedMotion();
  const landed = useRef(false);

  const onLanded = useCallback(() => {
    if (landed.current) return;
    landed.current = true;
    props.onLanded();
  }, [props]);

  const onProgress = useCallback((p: number) => props.onProgress(p), [props]);

  return (
    <ShotProvider
      durationMs={reduced ? SHOT_MS_REDUCED : SHOT_MS}
      instant={reduced}
      onProgress={onProgress}
      onEnd={onLanded}
    >
      <Shot {...props} />
    </ShotProvider>
  );
}
