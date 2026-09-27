import { useState, useCallback, useRef, useEffect } from "react";

interface Props {
  onSubmit: (query: string) => void;
  disabled: boolean;
}

/**
 * Quick actions. They only ever *populate the existing query field* — they never
 * submit, never touch the imagery, and never change any other app state. The
 * user stays in control of when the request fires.
 */
const SUGGESTIONS = [
  "What changed between these two dates?",
  "Describe the land cover in this image",
  "Are there any buildings in the SAR image?",
  "Detect urban expansion in this region",
  "Is there cloud cover in the optical image?",
  "Compare vegetation indices between T1 and T2",
];

/** Full-width analysis query bar with Enter-to-execute and an in-flight state. */
export default function QueryBar({ onSubmit, disabled }: Props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const canSubmit = value.trim().length > 0 && !disabled;

  /** Insert a quick action into the field and hand focus back to the user. */
  const applySuggestion = useCallback((suggestion: string) => {
    setValue(suggestion);
    const el = textareaRef.current;
    if (el) {
      el.focus();
      el.setSelectionRange(suggestion.length, suggestion.length);
    }
  }, []);

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    setValue("");
  }, [value, disabled, onSubmit]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 56)}px`;
    }
  }, [value]);

  return (
    <div className="relative flex items-end gap-3">
      <div className="flex-1">
        {/* Quick actions — visible when idle, they collapse away while running. */}
        <div
          className={`mb-2 flex flex-wrap items-center gap-1.5 overflow-hidden transition-all duration-300 ${
            disabled ? "max-h-0 opacity-0" : "max-h-8 opacity-100"
          }`}
        >
          <span className="mr-0.5 text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-600">
            Quick actions
          </span>
          {SUGGESTIONS.map((suggestion, i) => (
            <button
              key={suggestion}
              type="button"
              disabled={disabled}
              onClick={() => applySuggestion(suggestion)}
              style={{ animationDelay: `${i * 35}ms` }}
              className="quick-chip rounded-lg border border-slate-800 bg-slate-900 px-2.5 py-1 text-[11px]
                text-slate-400 transition-all duration-150 hover:border-teal-500/40 hover:bg-teal-500/5
                hover:text-teal-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/50
                disabled:cursor-not-allowed disabled:opacity-50"
            >
              {suggestion}
            </button>
          ))}
        </div>

        <label htmlFor="analysis-query" className="field-label">
          Analysis Query
        </label>
        <div className="relative">
          <textarea
            id="analysis-query"
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder="Ask about the satellite imagery…"
            rows={1}
            aria-describedby="analysis-query-hint"
            className="field resize-none py-3 pr-3 text-[15px] leading-6"
          />
        </div>
      </div>

      <div className="flex flex-shrink-0 flex-col items-stretch gap-1.5 pb-0.5">
        <button
          type="button"
          onClick={handleSubmit}
          disabled={!canSubmit}
          aria-busy={disabled}
          className="btn-primary h-11 px-5"
        >
          {disabled ? (
            <>
              <Spinner />
              Analyzing
            </>
          ) : (
            "Execute Analysis"
          )}
        </button>
        <span
          id="analysis-query-hint"
          className="flex items-center justify-center gap-1.5 text-[10px] text-slate-500"
        >
          <kbd className="rounded border border-slate-800 bg-slate-900 px-1.5 py-px font-mono text-slate-400">
            Enter
          </kbd>
          <span>to execute</span>
        </span>
      </div>
    </div>
  );
}

function Spinner() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      className="animate-spin"
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" opacity="0.25" />
      <path d="M21 12a9 9 0 00-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
