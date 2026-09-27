import { useState } from "react";

interface QueryLogAccordionProps {
  queries: string[];
  onReplay: (query: string) => void;
  disabled?: boolean;
}

/**
 * Historical queries as collapsible cards. Collapsed entries are clamped to two
 * lines; expanding reveals the full text in a scrollable block.
 */
export default function QueryLogAccordion({
  queries,
  onReplay,
  disabled = false,
}: QueryLogAccordionProps) {
  const [open, setOpen] = useState<Set<number>>(() => new Set());

  const toggle = (index: number) => {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  if (queries.length === 0) return null;

  return (
    <ul className="space-y-2">
      {queries.map((query, index) => {
        const expanded = open.has(index);
        return (
          <li
            key={`${index}-${query}`}
            className="rounded-lg border border-slate-800 bg-slate-950 transition-colors duration-150 hover:border-slate-700"
          >
            <div className="flex items-start gap-2 p-2.5">
              <span className="mt-px font-mono text-[11px] text-teal-500/60" aria-hidden="true">
                &gt;
              </span>

              <p
                className={`min-w-0 flex-1 text-[11px] leading-relaxed text-slate-300 transition-colors duration-150 ${
                  expanded ? "" : "line-clamp-2"
                }`}
              >
                {query}
              </p>

              <button
                type="button"
                onClick={() => onReplay(query)}
                disabled={disabled}
                aria-label={`Re-run query: ${query}`}
                title="Re-run this query"
                className="icon-btn hover:bg-teal-500/10 hover:text-teal-300 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                  <path d="M4 12a8 8 0 104.5-7.1M4 5v4h4" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>

              <button
                type="button"
                onClick={() => toggle(index)}
                aria-expanded={expanded}
                aria-label={expanded ? "Collapse query" : "Expand query"}
                className="icon-btn"
              >
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 12 12"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  aria-hidden="true"
                  className={`transition-transform duration-200 ${
                    expanded ? "rotate-180" : ""
                  }`}
                >
                  <path d="M3 5l3 3 3-3" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </div>

            {expanded && (
              <div className="animate-fade-in space-y-2 border-t border-slate-800 px-2.5 py-2.5">
                <p className="max-h-40 overflow-y-auto whitespace-pre-wrap break-words text-[11px] leading-relaxed text-slate-300">
                  {query}
                </p>
                <button
                  type="button"
                  onClick={() => onReplay(query)}
                  disabled={disabled}
                  className="btn-ghost h-7 w-full px-2 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Re-run query
                </button>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
