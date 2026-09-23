import { useState } from "react";
import { IconChevronDown } from "./icons";

interface Props {
  queries: string[];
  onSelect: (query: string) => void;
}

export default function QueryLogAccordion({ queries, onSelect }: Props) {
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  return (
    <div className="space-y-2">
      {queries.map((query, i) => {
        const isOpen = openIndex === i;
        const contentId = `query-log-${i}`;
        return (
          <div key={`${i}-${query}`} className="overflow-hidden rounded-lg border border-slate-800 bg-slate-900">
            <button
              type="button"
              aria-expanded={isOpen}
              aria-controls={contentId}
              onClick={() => setOpenIndex(isOpen ? null : i)}
              className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-slate-800/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-500/60"
            >
              <span className="text-[10px] font-semibold tabular-nums text-teal-500/70">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span className="min-w-0 flex-1 text-[12px] leading-snug text-slate-300 line-clamp-2">{query}</span>
              <IconChevronDown
                className={`flex-shrink-0 text-slate-500 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`}
              />
            </button>
            <div id={contentId} hidden={!isOpen}>
              <div className="animate-fade-in border-t border-slate-800/70 px-3 py-2.5">
                <p className="text-[12px] leading-relaxed text-slate-400">{query}</p>
                <button
                  type="button"
                  onClick={() => onSelect(query)}
                  className="mt-2 rounded text-[10px] font-semibold uppercase tracking-wider text-teal-400 transition-colors hover:text-teal-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/60"
                >
                  Run again
                </button>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}