import { useState, useCallback, useRef, useEffect } from "react";

interface Props {
  onSubmit: (query: string) => void;
  disabled: boolean;
}

const SUGGESTIONS = [
  "What changed between these two dates?",
  "Describe the land cover in this image",
  "Are there any buildings in the SAR image?",
  "Detect urban expansion in this region",
  "Is there cloud cover in the optical image?",
  "Compare vegetation indices between T1 and T2",
];

export default function QueryInput({ onSubmit, disabled }: Props) {
  const [value, setValue] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    setValue("");
    setShowSuggestions(false);
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
    <div className="relative flex items-end gap-4">
      {/* Prompt indicator + label */}
      <div className="flex flex-col items-end gap-0.5 flex-shrink-0 pb-1">
        <span className="text-[10px] font-medium text-ink-muted uppercase tracking-[0.1em] hidden sm:block">
          Analysis Query
        </span>
        <span className="text-accent/60 font-mono text-base leading-none">&gt;</span>
      </div>

      {/* Text input */}
      <div className="flex-1 relative">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            if (!showSuggestions && e.target.value.length === 0) {
              setShowSuggestions(true);
            }
          }}
          onFocus={() => {
            if (value.length === 0) setShowSuggestions(true);
          }}
          onBlur={() => {
            setTimeout(() => setShowSuggestions(false), 200);
          }}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder="Ask about the satellite imagery..."
          rows={1}
          className={`
            w-full bg-surface-900/60 border border-surface-400/40 text-ink
            placeholder-ink-muted/60 px-4 py-2.5 text-[15px] font-sans
            resize-none focus:outline-none rounded-lg
            focus:border-accent/50 transition-colors duration-150
            disabled:opacity-50 disabled:cursor-not-allowed
          `}
        />

        {/* Suggestions */}
        {showSuggestions && !disabled && (
          <div className="absolute bottom-full left-0 right-0 mb-2 flex flex-wrap gap-1.5">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onMouseDown={(e) => {
                  e.preventDefault();
                  setValue(s);
                  setShowSuggestions(false);
                }}
                className="
                  text-[11px] px-2.5 py-1.5 border border-surface-400/30
                  bg-surface-800 text-ink-secondary hover:border-accent/30 hover:text-ink
                  transition-colors rounded
                "
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Execute button */}
      <button
        onClick={handleSubmit}
        disabled={!value.trim() || disabled}
        className={`
          flex-shrink-0 px-5 py-2.5 text-[12px] font-semibold tracking-wide uppercase
          rounded-lg border transition-all duration-150
          ${
            value.trim() && !disabled
              ? "border-accent bg-accent text-surface-950 hover:bg-accent/90"
              : "border-surface-400/30 bg-surface-700/40 text-ink-muted/50 cursor-not-allowed"
          }
        `}
      >
        Execute Analysis
      </button>

      {/* Keyboard hint */}
      <div className="hidden xl:flex items-center gap-1.5 flex-shrink-0 pb-2">
        <span className="text-[10px] text-ink-muted">
          <kbd className="px-1.5 py-px border border-surface-400/30 bg-surface-700 text-ink-secondary rounded">
            Enter
          </kbd>{" "}
          execute
        </span>
      </div>
    </div>
  );
}
