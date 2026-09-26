/**
 * Abstract Earth / orbital acquisition visual.
 *
 * Entirely procedural SVG: dark globe, cyan atmospheric rim, graticule,
 * abstract landmasses, illuminated surface points, orbital trajectory with a
 * satellite in transit, and a scanning arc. No stock imagery, no canvas, no
 * filters — so it stays cheap and scales to any viewport.
 *
 * Rotation is faked the way wireframes always have: the graticule + surface
 * spin about the centre while the latitude circles (true circles) stay put.
 */

/** Globe geometry in a 320-unit viewBox centred on (160, 160). */
const R = 108;
const CX = 160;
const ORBIT_RX = 152;
const ORBIT_RY = 54;
const ORBIT_TILT = -18;

/** Deterministic surface points — brightening points read as acquisition flashes. */
const SURFACE_POINTS: ReadonlyArray<readonly [number, number]> = [
  [-62, -38], [-30, -66], [8, -58], [44, -40], [70, -8], [58, 34],
  [18, 62], [-24, 54], [-64, 18], [-12, -16], [26, -24], [52, 6],
  [-44, 4], [-20, 26], [14, 40], [34, -52], [-52, -56], [78, 26],
];

/** Abstract landmasses — deliberately non-representational. */
const LANDMASSES: ReadonlyArray<{ d: string; delay: number }> = [
  { d: "M -78 -30 C -60 -58 -30 -66 -12 -52 C 4 -40 -6 -18 -24 -8 C -46 4 -70 2 -78 -30 Z", delay: 0 },
  { d: "M 22 -58 C 46 -62 70 -50 74 -28 C 78 -6 58 6 40 2 C 22 -2 10 -24 12 -42 C 13 -50 16 -55 22 -58 Z", delay: 0.4 },
  { d: "M -46 22 C -26 12 -2 16 6 32 C 14 48 2 66 -18 68 C -40 70 -58 54 -58 38 C -58 32 -54 26 -46 22 Z", delay: 0.8 },
  { d: "M 40 34 C 56 30 70 38 70 50 C 70 62 56 70 44 66 C 32 62 30 40 40 34 Z", delay: 1.2 },
];

/** Meridians as seen-on-disc ellipses (rx varies, ry is the full radius). */
const MERIDIANS = [R, R * 0.866, R * 0.5, R * 0.26];
/** Parallels as flat ellipses. */
const PARALLELS = [R, R * 0.866, R * 0.5];

function SatelliteGlyph() {
  return (
    <g fill="none" stroke="#a5f3fc" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="0" cy="0" r="2.2" fill="#a5f3fc" />
      <path d="M -4.2 -2 L -7.4 -3.4 L -5.6 -5.6 L -2.6 -4" />
      <path d="M 4.2 2 L 7.4 3.4 L 5.6 5.6 L 2.6 4" />
      <path d="M -2 -2 L -4 -6 L -1.4 -8 L 0.6 -4.4" />
      <path d="M 2 2 L 4 6 L 1.4 8 L -0.6 4.4" />
    </g>
  );
}

export default function EarthGlobe() {
  return (
    <svg viewBox="0 0 320 320" className="h-full w-full" aria-hidden="true">
      <defs>
        <radialGradient id="globe-body" cx="38%" cy="32%" r="78%">
          <stop offset="0%" stopColor="#0b2233" />
          <stop offset="55%" stopColor="#071827" />
          <stop offset="100%" stopColor="#020a12" />
        </radialGradient>
        <radialGradient id="globe-rim" cx="50%" cy="50%" r="50%">
          <stop offset="82%" stopColor="#22d3ee" stopOpacity="0" />
          <stop offset="93%" stopColor="#22d3ee" stopOpacity="0.28" />
          <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="globe-shade" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.1" />
          <stop offset="42%" stopColor="#020a12" stopOpacity="0" />
          <stop offset="100%" stopColor="#000205" stopOpacity="0.72" />
        </linearGradient>
        <linearGradient id="globe-sweep-fill" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
        </linearGradient>
        <clipPath id="globe-clip">
          <circle cx={CX} cy={CX} r={R} />
        </clipPath>
      </defs>

      {/* Atmospheric halo */}
      <circle cx={CX} cy={CX} r={R * 1.16} fill="url(#globe-rim)" className="boot-globe-halo" />

      {/* Globe body */}
      <circle cx={CX} cy={CX} r={R} fill="url(#globe-body)" />

      <g clipPath="url(#globe-clip)">
        {/* Parallels — static, they are true circles in projection */}
        <g className="boot-globe-lat">
          {PARALLELS.map((ry) => (
            <ellipse
              key={ry}
              cx={CX}
              cy={CX}
              rx={R}
              ry={ry}
              fill="none"
              stroke="#22d3ee"
              strokeOpacity="0.16"
              strokeWidth="0.8"
            />
          ))}
        </g>

        {/* Rotating group: meridians, landmasses, acquisition points */}
        <g className="boot-globe-spin">
          <g transform={`translate(${CX} ${CX})`}>
            {MERIDIANS.map((rx) => (
              <ellipse
                key={rx}
                cx={0}
                cy={0}
                rx={rx}
                ry={R}
                fill="none"
                stroke="#22d3ee"
                strokeOpacity="0.2"
                strokeWidth="0.8"
              />
            ))}

            {LANDMASSES.map((mass) => (
              <path
                key={mass.d}
                d={mass.d}
                fill="#2dd4bf"
                fillOpacity="0.09"
                stroke="#5eead4"
                strokeOpacity="0.22"
                strokeWidth="0.7"
                className="boot-globe-mass"
                style={{ animationDelay: `${mass.delay}s` }}
              />
            ))}

            {SURFACE_POINTS.map(([x, y], i) => (
              <circle
                key={`${x}:${y}`}
                cx={x}
                cy={y}
                r="1.5"
                fill="#a5f3fc"
                className="boot-globe-point"
                style={{ animationDelay: `${(i % 6) * 0.28}s` }}
              />
            ))}
          </g>

          {/* Acquisition wash — sweeps the disc as the satellite transits */}
          <g className="boot-globe-scan">
            <path
              d={`M ${CX} ${CX} L ${CX} ${CX - R} A ${R} ${R} 0 0 1 ${CX + R} ${CX} Z`}
              fill="url(#globe-sweep-fill)"
            />
            <line
              x1={CX}
              y1={CX}
              x2={CX}
              y2={CX - R}
              stroke="#67e8f9"
              strokeOpacity="0.5"
              strokeWidth="0.9"
            />
          </g>
        </g>

        {/* Terminator / limb shading */}
        <circle cx={CX} cy={CX} r={R} fill="url(#globe-shade)" />
      </g>

      {/* Atmospheric rim */}
      <circle
        cx={CX}
        cy={CX}
        r={R}
        fill="none"
        stroke="#22d3ee"
        strokeOpacity="0.45"
        strokeWidth="1.1"
      />

      {/* Orbital trajectory */}
      <g transform={`rotate(${ORBIT_TILT} ${CX} ${CX})`}>
        <ellipse
          cx={CX}
          cy={CX}
          rx={ORBIT_RX}
          ry={ORBIT_RY}
          fill="none"
          stroke="#22d3ee"
          strokeOpacity="0.28"
          strokeWidth="0.9"
          strokeDasharray="4 8"
        />
        {/* Satellite in transit — one pass across the boot window */}
        <g className="boot-sat-transit">
          <g transform={`translate(${CX + ORBIT_RX} ${CX})`}>
            <SatelliteGlyph />
          </g>
        </g>
      </g>
    </svg>
  );
}
