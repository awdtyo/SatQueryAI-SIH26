import { forwardRef } from "react";

const PARTS: ReadonlyArray<{ text: string; className: string }> = [
  { text: "SAT", className: "text-slate-200" },
  { text: "QUERY", className: "text-teal-300" },
  { text: "AI", className: "text-cyan-300" },
];

/**
 * Character offsets are precomputed at module scope so rendering is a pure read.
 *
 * Each glyph is a separate node carrying `--glyph-at`, its normalised position in
 * the word. BootSequence's clock reads those once and writes a transform and an
 * opacity per glyph each frame, so the wordmark assembles as one continuous
 * motion rather than N independent keyframes. Nothing here animates by itself.
 */
const GLYPHS = PARTS.flatMap((part) =>
  part.text.split("").map((char, i) => ({ char, className: part.className, index: i })),
);

const TOTAL = Math.max(1, GLYPHS.length - 1);

export const GLYPH_SELECTOR = "[data-glyph-at]";

/**
 * TITLE LAYER — the wordmark.
 *
 * Rendered exactly once. Arrival is anticipation (glyphs sit slightly low and
 * spread), then movement, then a damped settle — all from one eased progress
 * value, so no letter arrives on its own schedule.
 */
const TitleLayer = forwardRef<HTMLDivElement>(function TitleLayer(_props, ref) {
  return (
    <div
      ref={ref}
      className="pointer-events-none absolute inset-0 flex items-center justify-center"
      style={{ visibility: "hidden" }}
    >
      <h1
        className="boot-wordmark flex items-center justify-center gap-3 text-[13vw] font-bold leading-none sm:text-[64px]"
        aria-label="SATQUERY AI"
      >
        {GLYPHS.map((glyph, i) => (
          <span
            key={`${glyph.char}-${i}`}
            data-glyph-at={i / TOTAL}
            className={`boot-glyph ${glyph.className}`}
            aria-hidden="true"
          >
            {glyph.char}
          </span>
        ))}
      </h1>
    </div>
  );
});

export default TitleLayer;
