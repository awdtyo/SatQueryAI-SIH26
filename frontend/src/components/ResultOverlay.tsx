import { useEffect, useState } from "react";
import type { QueryResponse } from "../types/api";
import ResultsPanel from "./ResultsPanel";

interface ResultOverlayProps {
  response: QueryResponse;
  /** Fully dismisses the overlay so the map is unobstructed. */
  onClose: () => void;
}

/**
 * Floating glassmorphism card pinned over the imagery viewport. It expands by
 * default whenever a new result arrives, scrolls internally, and can be
 * collapsed to a pill.
 */
export default function ResultOverlay({ response, onClose }: ResultOverlayProps) {
  const [expanded, setExpanded] = useState(true);

  // A new result always re-opens the panel.
  useEffect(() => setExpanded(true), [response]);

  return (
    <div className="absolute inset-0 flex flex-col justify-end p-4">
      {expanded ? (
        <div
          role="region"
          aria-label="Intelligence result"
          className="flex max-h-[62%] w-full max-w-2xl animate-slide-up flex-col overflow-hidden
            rounded-xl border border-slate-800 bg-slate-900/80 shadow-2xl backdrop-blur-md"
        >
          <header className="flex flex-shrink-0 items-center gap-2.5 border-b border-slate-800/80 px-4 py-3">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" aria-hidden="true" />
            <h2 className="panel-label">Intelligence Result</h2>
            <span className="tag-muted">Received</span>
            <div className="ml-auto flex items-center gap-1">
              <button
                type="button"
                onClick={() => setExpanded(false)}
                aria-label="Collapse intelligence result"
                aria-expanded={true}
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
                  className="rotate-180 transition-transform duration-200"
                >
                  <path d="M3 5l3 3 3-3" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
              <button
                type="button"
                onClick={onClose}
                aria-label="Dismiss intelligence result"
                className="icon-btn hover:bg-rose-500/10 hover:text-rose-400"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                  <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
                </svg>
              </button>
            </div>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            <ResultsPanel response={response} />
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          aria-expanded={false}
          aria-label="Expand intelligence result"
          className="flex w-full max-w-2xl items-center gap-2.5 rounded-xl border border-slate-800
            bg-slate-900/80 px-4 py-2.5 text-left shadow-xl backdrop-blur-md
            transition-colors duration-150 hover:border-slate-700
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/50"
        >
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" aria-hidden="true" />
          <span className="panel-label">Intelligence Result</span>
          <span className="tag-muted ml-auto">Expand</span>
          <svg
            width="12"
            height="12"
            viewBox="0 0 12 12"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            aria-hidden="true"
            className="text-slate-500 transition-transform duration-200"
          >
            <path d="M3 5l3 3 3-3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      )}
    </div>
  );
}

/** Restore affordance shown over the map after the result overlay is dismissed. */
export function ShowResultButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="btn-ghost absolute bottom-4 right-4 h-8 gap-2 border-teal-500/30
        bg-slate-900/80 px-3 backdrop-blur-md hover:border-teal-500/50 hover:text-teal-300"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" aria-hidden="true" />
      Show intelligence result
    </button>
  );
}
