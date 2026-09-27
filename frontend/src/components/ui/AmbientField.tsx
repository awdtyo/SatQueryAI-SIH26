/**
 * Ambient mission-control backdrop for the imagery viewport.
 *
 * Purely decorative and entirely `aria-hidden` + `pointer-events-none`, so it
 * never intercepts a click on the floating result overlay. Four layers:
 *
 *  1. a fine grid that drifts very slowly (parallax feel without a scroll lib),
 *  2. a radar sweep wedge rotating about the centre,
 *  3. lat/long reference lines with tick marks and node markers,
 *  4. orbital telemetry particles on offset drift paths.
 *
 * All motion is CSS keyframes, so the `prefers-reduced-motion` reset in
 * index.css collapses it to a static field.
 */
export default function AmbientField() {
  // Deterministic offsets so particles do not reshuffle on every render.
  const particles = [
    { x: 18, y: 26, d: 0, s: 3.5 },
    { x: 74, y: 18, d: 1.4, s: 2.5 },
    { x: 41, y: 62, d: 2.7, s: 3 },
    { x: 86, y: 71, d: 0.8, s: 2 },
    { x: 9, y: 78, d: 3.5, s: 2.5 },
    { x: 62, y: 34, d: 2.1, s: 3 },
    { x: 29, y: 88, d: 4.2, s: 2 },
    { x: 92, y: 42, d: 1.9, s: 2.5 },
  ];

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
      {/* 1. drifting grid */}
      <div className="ambient-grid absolute inset-0 opacity-70" />

      {/* 2. radar sweep — conic wedge faded out radially so it has no hard edge */}
      <div className="ambient-spin absolute left-1/2 top-1/2 h-[200%] w-[200%] -translate-x-1/2 -translate-y-1/2">
        <div
          className="absolute inset-0"
          style={{
            background: "conic-gradient(from 0deg, rgba(45,212,191,0.20) 0deg, transparent 40deg, transparent 360deg)",
            WebkitMaskImage: "radial-gradient(circle at 50% 50%, #000 12%, transparent 62%)",
            maskImage: "radial-gradient(circle at 50% 50%, #000 12%, transparent 62%)",
          }}
        />
      </div>

      {/* 3. coordinate reference lines + node markers */}
      <svg className="absolute inset-0 h-full w-full" preserveAspectRatio="none" viewBox="0 0 100 100">
        {[25, 50, 75].map((v) => (
          <g key={v} stroke="#14b8a6" strokeOpacity="0.13" strokeWidth="0.2">
            <line x1={v} y1="0" x2={v} y2="100" />
            <line x1="0" y1={v} x2="100" y2={v} />
          </g>
        ))}
        {[
          [25, 25],
          [75, 25],
          [25, 75],
          [75, 75],
          [50, 50],
        ].map(([x, y]) => (
          <g key={`${x}-${y}`}>
            <circle cx={x} cy={y} r="1.1" fill="none" stroke="#2dd4bf" strokeOpacity="0.22" strokeWidth="0.3" />
            <circle cx={x} cy={y} r="0.3" fill="#5eead4" fillOpacity="0.35" />
          </g>
        ))}
      </svg>

      {/* 4. orbital telemetry particles */}
      <svg className="absolute inset-0 h-full w-full" preserveAspectRatio="none" viewBox="0 0 100 100">
        {particles.map((p) => (
          <circle
            key={`${p.x}-${p.y}`}
            cx={p.x}
            cy={p.y}
            r={p.s / 12}
            fill="#5eead4"
            className="ambient-drift"
            style={{ animationDelay: `${p.d}s` }}
          />
        ))}
      </svg>

      {/* 5. corner vignette so the imagery reads as the focal plane */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(2,6,23,0) 45%, rgba(2,6,23,0.55) 82%, rgba(2,6,23,0.9) 100%)",
        }}
      />
    </div>
  );
}
