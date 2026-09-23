import { useState } from "react";
import type { LandCoverSlice } from "../types/api";

interface Props {
  slices: LandCoverSlice[];
}

const PALETTE = ["#2dd4bf", "#38bdf8", "#a78bfa", "#fbbf24", "#fb7185", "#34d399", "#a3e635", "#94a3b8"];

const RADIUS = 54;
const STROKE = 16;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export default function LandCoverChart({ slices }: Props) {
  const [hovered, setHovered] = useState<number | null>(null);

  const total = slices.reduce((sum, s) => sum + s.value, 0);

  const segments = slices.map((s, i) => {
    const frac = total > 0 ? s.value / total : 0;
    const start = slices.slice(0, i).reduce((sum, prev) => sum + prev.value, 0) / total;
    return { slice: s, start, frac };
  });

  const largest = slices.length > 0
    ? slices.reduce((a, b) => (b.value > a.value ? b : a))
    : null;

  return (
    <div>
      <div className="relative">
        <svg
          viewBox="0 0 140 140"
          className="mx-auto block w-36"
          role="img"
          aria-label="Land cover distribution donut chart"
        >
          <circle cx="70" cy="70" r={RADIUS} fill="none" stroke="#1e293b" strokeWidth={STROKE} />
          {segments.map(({ slice, start }, i) => {
            const len = Math.max(0.5, (slice.value / total) * CIRCUMFERENCE - 1.5);
            const dash = CIRCUMFERENCE - len;
            const color = PALETTE[i % PALETTE.length]!;
            return (
              <circle
                key={slice.label}
                cx="70"
                cy="70"
                r={RADIUS}
                fill="none"
                stroke={color}
                strokeWidth={STROKE}
                strokeDasharray={`${len} ${dash}`}
                strokeDashoffset={-start * CIRCUMFERENCE}
                transform="rotate(-90 70 70)"
                className="cursor-pointer transition-opacity duration-150"
                opacity={hovered === null || hovered === i ? 1 : 0.35}
                onMouseEnter={() => setHovered(i)}
                onMouseLeave={() => setHovered(null)}
              />
            );
          })}
        </svg>

        {hovered !== null && segments[hovered] && (
          <div className="pointer-events-none absolute inset-x-0 top-0 mx-auto w-fit rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-[10px] font-medium text-slate-100 shadow-lg">
            {segments[hovered]!.slice.label} · {((segments[hovered]!.slice.value / total) * 100).toFixed(1)}%
          </div>
        )}

        {largest && total > 0 && (
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-[16px] font-bold leading-none text-slate-100">
              {((largest.value / total) * 100).toFixed(1)}%
            </span>
            <span className="mt-1 text-[9px] font-medium uppercase tracking-wider text-slate-500">
              {largest.label}
            </span>
          </div>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-center gap-x-4 gap-y-1.5">
        {segments.map(({ slice }, i) => (
          <span key={slice.label} className="flex items-center gap-1.5 text-[11px] text-slate-300">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: PALETTE[i % PALETTE.length]! }}
            />
            {slice.label} <span className="tabular-nums text-slate-500">
              {((slice.value / total) * 100).toFixed(1)}%
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}