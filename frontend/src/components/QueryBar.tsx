import { useState, useCallback, useRef, useEffect } from "react";

interface Props {
  onRun?: (query: string) => void;
  onSubmit?: (query: string) => void;
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

export default function QueryBar({ onRun, onSubmit, disabled }: Props) {
  const [value, setValue] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);
 const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    (onRun ?? onSubmit)?.(trimmed);
    setValue("");
    setShowSuggestions(false);
 }, [value, disabled, onRun, onSubmit]);

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

  const canExecute = value.trim().length > 0 && !disabled;

  return (
    <div className="relative flex items-center gap-3">
      <div className="relative flex-1">
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
          className="w-full resize-none rounded-lg border border-slate-800 bg-slate-950 px-4 py-2.5 text-[14px] text-slate-200 placeholder:text-slate-500 transition-colors focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/30 disabled:cursor-not-allowed disabled:opacity-50"
        />

        {showSuggestions && !disabled && (
          <div className="absolute bottom-full left-0 right-0 mb-2 flex flex-wrap gap-1.5">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault();
                  setValue(s);
                  setShowSuggestions(false);
                }}
                className="rounded border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-[11px] text-slate-300 transition-colors hover:border-teal-500/40 hover:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/60"
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </div>

      <button
        type="button"
        onClick={handleSubmit}
        disabled={!canExecute}
        aria-label={disabled ? "Analysis in progress" : "Execute analysis"}
        className={`flex flex-shrink-0 items-center gap-2 rounded-lg px-5 py-2.5 text-[11px] font-semibold uppercase tracking-wider transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/60 ${
          canExecute
            ? "bg-teal-500 text-slate-950 hover:bg-teal-400"
            : "cursor-not-allowed bg-slate-800 text-slate-500"
        }`}
      >
        {disabled && (
          <span
            className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-950/30 border-t-slate-950"
            aria-hidden="true"
          />
        )}
        {disabled ? "Analyzing" : "Execute Analysis"}
      </button>

      <div className="hidden flex-shrink-0 items-center gap-1.5 xl:flex">
        <kbd className="rounded border border-slate-700 bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
          Enter
        </kbd>
        <span className="text-[10px] text-slate-500">to execute</span>
      </div>
    </div>
  );
}