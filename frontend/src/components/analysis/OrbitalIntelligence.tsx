import { CAPABILITY_CARDS, ORBITAL_INTELLIGENCE, capabilityInUse, imageryDescriptor } from "../../lib/capabilities";
import type { InputMode, QueryResponse } from "../../types/api";

/**
 * ORBITAL INTELLIGENCE — the rotating remote-sensing fact deck.
 *
 * The outgoing fact is held mounted and cross-fades with the incoming one, so
 * the panel is never blank between facts. A keyed remount here would flash the
 * card area for a frame on every rotation.
 */
export default function OrbitalIntelligenceCard({ index }: { index: number }) {
  const current = index % ORBITAL_INTELLIGENCE.length;
  const previous = (current - 1 + ORBITAL_INTELLIGENCE.length) % ORBITAL_INTELLIGENCE.length;
  const card = ORBITAL_INTELLIGENCE[current]!;
  const prior = ORBITAL_INTELLIGENCE[previous]!;

  // Both facts occupy the same box and cross-fade, so the panel is never blank
  // and nothing is remounted mid-rotation.
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="mb-2.5 flex items-center gap-2">
        <h4 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-teal-300">
          Orbital Intelligence
        </h4>
        <span className="h-px flex-1 bg-gradient-to-r from-teal-500/25 to-transparent" />
        <span className="font-mono text-[9.5px] tabular-nums text-slate-600">
          {String(current + 1).padStart(2, "0")}/{String(ORBITAL_INTELLIGENCE.length).padStart(2, "0")}
        </span>
      </div>

      <div className="relative min-h-[3.6rem]">
        <div className="analysis-fact analysis-fact-leaving" data-state="out" aria-hidden="true">
          <h5 className="text-[11.5px] font-semibold uppercase tracking-[0.1em] text-slate-500">
            {prior.title}
          </h5>
          <p className="mt-1.5 text-[11.5px] leading-relaxed text-slate-600">{prior.body}</p>
        </div>
        <div className="analysis-fact relative" data-state="in">
          <h5 className="text-[11.5px] font-semibold uppercase tracking-[0.1em] text-slate-200">
            {card.title}
          </h5>
          <p className="mt-1.5 text-[11.5px] leading-relaxed text-slate-400">{card.body}</p>
        </div>
      </div>
    </div>
  );
}

/**
 * SATQUERY CAPABILITIES — reference grid. Exactly one tile is promoted to
 * "CAPABILITY IN USE", derived from the real execution trace once a response
 * exists, or from the operator's actual input mode before that.
 */
export function CapabilityModule({
  inputMode,
  response,
  imageCount,
}: {
  inputMode: InputMode;
  response: QueryResponse | null;
  imageCount: number;
}) {
  const inUse = capabilityInUse(inputMode, response);
  const sensor = imageryDescriptor(inputMode, imageCount);
  const index = CAPABILITY_CARDS.findIndex((c) => c.title === inUse);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="mb-2.5 flex items-center gap-2">
        <h4 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-300">
          Satquery Capabilities
        </h4>
        <span className="h-px flex-1 bg-gradient-to-r from-slate-700/50 to-transparent" />
        {index >= 0 && (
          <span className="chip-accent animate-fade-in">
            <span className="h-1 w-1 animate-status-pulse rounded-full bg-current" />
            Capability in use
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-1.5">
        {CAPABILITY_CARDS.map((card, i) => {
          const isActive = i === index;
          return (
            <div key={card.id} className={`capability-tile ${isActive ? "capability-tile-active" : ""}`}>
              <div className="flex items-center gap-1.5">
                <span className={`h-1 w-1 rounded-full ${isActive ? "bg-teal-400" : "bg-slate-600"}`} />
                <span className="text-[9.5px] font-semibold uppercase tracking-[0.09em] text-slate-300">
                  {card.title}
                </span>
              </div>
              <p className="mt-1 text-[9.5px] leading-snug text-slate-600">{card.body}</p>
              {isActive && <span className="capability-tile-marker" aria-hidden="true" />}
            </div>
          );
        })}
      </div>

      <p className="mt-2 text-[10px] text-slate-500">
        <span className="text-slate-400">Sensor:</span> {sensor}
      </p>
    </div>
  );
}
