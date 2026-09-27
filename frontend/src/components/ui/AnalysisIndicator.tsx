import { useId, type CSSProperties } from "react";
import usePrefersReducedMotion from "../../hooks/usePrefersReducedMotion";

interface AnalysisIndicatorProps {
  /** Rendered edge length in px. The viewBox is a fixed 100×100. */
  size?: number;
  className?: string;
}

/**
 * Mission-control satellite/radar motif: a fading sweep wedge, counter-rotating
 * dashed ring, an orbiting satellite glyph and a pulsing core.
 *
 * Motion is CSS `spin`/`ping` so index.css's reduced-motion reset applies, and
 * the inline transforms are dropped entirely when the user prefers reduced
 * motion (leaving a clean static emblem). Every part is `aria-hidden` — the
 * accompanying text carries the meaning.
 */
export default function AnalysisIndicator({ size = 96, className = "" }: AnalysisIndicatorProps) {
  const reduced = usePrefersReducedMotion();
  const uid = useId().replace(/:/g, "");
  const sweepId = `sq-sweep-${uid}`;
  const coreId = `sq-core-${uid}`;

  /** Spin about the centre of the viewBox. */
  const spin = (seconds: number): CSSProperties | undefined =>
    reduced
      ? undefined
      : {
          transformBox: "view-box",
          transformOrigin: "50% 50%",
          animation: `spin ${seconds}s linear infinite`,
        };

  /** Counter-rotate about the glyph's own centre so it keeps a fixed heading. */
  const counterSpin = (seconds: number): CSSProperties | undefined =>
    reduced
      ? undefined
      : {
          transformBox: "fill-box",
          transformOrigin: "center",
          animation: `spin ${seconds}s linear infinite reverse`,
        };

  return (
    <svg
      viewBox="0 0 100 100"
      width={size}
      height={size}
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <radialGradient id={sweepId} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#2dd4bf" stopOpacity="0" />
          <stop offset="55%" stopColor="#14b8a6" stopOpacity="0.12" />
          <stop offset="100%" stopColor="#5eead4" stopOpacity="0.42" />
        </radialGradient>
        <radialGradient id={coreId} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#5eead4" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#0f766e" stopOpacity="0.15" />
        </radialGradient>
      </defs>

      {/* static outer ring */}
      <circle cx="50" cy="50" r="46" fill="none" stroke="#1e293b" strokeWidth="1" />

      {/* radar sweep wedge */}
      {!reduced && (
        <g style={spin(2.6)}>
          <path d="M50 50 L50 4 A46 46 0 0 1 96 50 Z" fill={`url(#${sweepId})`} />
        </g>
      )}

      {/* counter-rotating dashed ring */}
      <g style={spin(28)}>
        <circle
          cx="50"
          cy="50"
          r="37"
          fill="none"
          stroke="#14b8a6"
          strokeOpacity="0.28"
          strokeWidth="1"
          strokeDasharray="2 7"
        />
      </g>

      {/* inner reference ring */}
      <circle cx="50" cy="50" r="26" fill="none" stroke="#14b8a6" strokeOpacity="0.12" strokeWidth="1" />

      {/* crosshair ticks */}
      <g stroke="#334155" strokeWidth="1" strokeLinecap="round">
        <path d="M50 1.5v4" />
        <path d="M50 94.5v4" />
        <path d="M1.5 50h4" />
        <path d="M94.5 50h4" />
      </g>

      {/* orbiting satellite: outer g travels the circle, inner g stays upright */}
      <g style={spin(7)}>
        <g transform="translate(50 11)">
          <g style={counterSpin(7)}>
            <rect x="-1.6" y="-1.6" width="3.2" height="3.2" rx="0.6" fill="#5eead4" />
            <rect x="-6.4" y="-0.9" width="4" height="1.8" rx="0.4" fill="#14b8a6" fillOpacity="0.75" />
            <rect x="2.4" y="-0.9" width="4" height="1.8" rx="0.4" fill="#14b8a6" fillOpacity="0.75" />
          </g>
        </g>
      </g>

      {/* pulsing core */}
      {!reduced && <circle cx="50" cy="50" r="7" fill="none" stroke="#2dd4bf" strokeWidth="1" className="origin-center animate-radar-ping" />}
      <circle cx="50" cy="50" r="4.5" fill={`url(#${coreId})`} />
      <circle cx="50" cy="50" r="1.6" fill="#5eead4" />
    </svg>
  );
}
