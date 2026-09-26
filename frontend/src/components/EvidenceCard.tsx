import { useEffect, useState } from "react";
import type { EvidenceRef } from "../types/api";
import { CheckIcon } from "./ui/Icons";

/** Evidence is stamped as verified, never as merely "loaded". */
const ACCENTS: Record<EvidenceRef["type"], string> = {
  bounding_box: "text-amber-400",
  overlay: "text-teal-400",
  heatmap: "text-rose-400",
  saliency: "text-violet-400",
  image_ref: "text-teal-400",
};

interface Props {
  evidence: EvidenceRef;
  /**
   * Position in the evidence list. Used only to offset when this card starts
   * moving, so a list of findings is verified in sequence on the one shared
   * curve rather than each card running its own animation.
   */
  index?: number;
}

export default function EvidenceCard({ evidence, index = 0 }: Props) {
  const [entering, setEntering] = useState(true);

  // Flip out of the arriving state on the frame after mount. The card is
  // painted at `data-entering` from its very first frame, so it is never shown
  // at its resting position and then snapped back.
  useEffect(() => {
    const raf = requestAnimationFrame(() => setEntering(false));
    return () => cancelAnimationFrame(raf);
  }, []);

  // The delay is set once and never changed. It is inert while the card sits at
  // `data-entering`, so it only takes effect on the flip to the resting state —
  // which is what staggers the list without any card ever being painted at its
  // final position first.
  const delay = `${index * 90}ms`;

  return (
    <li
      className="evidence-card relative flex items-start gap-2.5 rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2"
      data-entering={entering}
      style={{ transitionDelay: delay }}
    >
      <span
        aria-hidden="true"
        className="evidence-lock mt-0.5"
        data-entering={entering}
        // The lock settles just after its card body, so the mark reads as being
        // stamped on rather than arriving with the box.
        style={{ transitionDelay: `calc(${delay} + 60ms)` }}
      >
        <CheckIcon className="h-2.5 w-2.5" strokeWidth={2.6} />
      </span>
      <div className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className={`text-[10px] font-semibold uppercase tracking-wider ${ACCENTS[evidence.type]}`}>
            {evidence.type.replace("_", " ")}
          </span>
          <span className="text-[9px] uppercase tracking-[0.14em] text-emerald-400/70">
            Evidence verified
          </span>
        </span>
        <span className="mt-0.5 block text-[12px] leading-snug text-slate-300">
          {evidence.description}
        </span>
      </div>
    </li>
  );
}
