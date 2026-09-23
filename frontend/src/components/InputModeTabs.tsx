import type { InputMode } from "../types/api";
import { INPUT_MODES } from "../lib/modes";

interface Props {
  value: InputMode;
  onChange: (mode: InputMode) => void;
}

export default function InputModeTabs({ value, onChange }: Props) {
  return (
    <div role="tablist" aria-label="Input mode" className="flex gap-1 rounded-lg border border-slate-800 bg-slate-950 p-1">
      {INPUT_MODES.map((mode) => {
        const active = mode.key === value;
        return (
          <button
            key={mode.key}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(mode.key)}
            className={`flex-1 rounded-md border px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wider transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/60 ${
              active
                ? "border-teal-500/50 bg-slate-900 text-teal-400 shadow-[0_0_12px_rgba(20,184,166,0.25)]"
                : "border-transparent text-slate-500 hover:text-slate-300"
            }`}
          >
            {mode.label}
          </button>
        );
      })}
    </div>
  );
}