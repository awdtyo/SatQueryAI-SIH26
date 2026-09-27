import type { InputMode } from "../types/api";

export interface InputModeOption {
  key: InputMode;
  label: string;
  /** Short secondary line shown under the label inside the active tab. */
  sublabel: string;
  slots: number;
  slotLabels: string[];
  description: string;
}

export const INPUT_MODES: InputModeOption[] = [
  {
    key: "single",
    label: "SINGLE",
    sublabel: "One scene",
    slots: 1,
    slotLabels: ["Image"],
    description: "Single optical or SAR image",
  },
  {
    key: "optical-sar",
    label: "OPTICAL+SAR",
    sublabel: "Fused pair",
    slots: 2,
    slotLabels: ["Optical", "SAR"],
    description: "Co-registered optical and SAR pair",
  },
  {
    key: "bi-temporal",
    label: "BI-TEMPORAL",
    sublabel: "Two dates",
    slots: 2,
    slotLabels: ["Date 1 (T1)", "Date 2 (T2)"],
    description: "Same location, two different dates",
  },
];

interface InputModeTabsProps {
  value: InputMode;
  onChange: (mode: InputMode) => void;
}

/**
 * Segmented tab bar for imagery input mode. The active tab gets a teal border
 * with a soft outer glow plus accent text.
 */
export default function InputModeTabs({ value, onChange }: InputModeTabsProps) {
  const active = INPUT_MODES.find((mode) => mode.key === value) ?? INPUT_MODES[0]!;

  return (
    <div>
      <div
        role="tablist"
        aria-label="Input mode"
        className="flex gap-1 rounded-lg border border-slate-800 bg-slate-950 p-1"
      >
        {INPUT_MODES.map((mode) => {
          const isActive = mode.key === value;
          return (
            <button
              key={mode.key}
              type="button"
              role="tab"
              aria-selected={isActive}
              tabIndex={isActive ? 0 : -1}
              title={mode.description}
              onClick={() => onChange(mode.key)}
              className={[
                "group relative flex-1 overflow-hidden rounded-md border px-2 py-1.5 text-left",
                "transition-all duration-200 ease-out",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/50",
                isActive
                  ? "border-teal-500/50 bg-teal-500/10 shadow-glow"
                  : "border-transparent hover:border-slate-700 hover:bg-slate-900/70",
              ].join(" ")}
            >
              {/* active indicator bar — grows from the centre on selection */}
              <span
                className={`absolute inset-x-2 bottom-0 h-px origin-center bg-teal-400 transition-transform duration-300 ease-out ${
                  isActive ? "scale-x-100 opacity-100" : "scale-x-0 opacity-0"
                }`}
                aria-hidden="true"
              />
              <span
                className={`block text-[11px] font-semibold uppercase tracking-wider transition-colors duration-200 ${
                  isActive ? "text-teal-300" : "text-slate-500 group-hover:text-slate-300"
                }`}
              >
                {mode.label}
              </span>
              <span
                className={`block text-[9px] leading-tight transition-colors duration-200 ${
                  isActive ? "text-teal-400/70" : "text-slate-600 group-hover:text-slate-500"
                }`}
              >
                {mode.sublabel}
              </span>
            </button>
          );
        })}
      </div>
      <p className="mt-2 text-[11px] text-slate-500">{active.description}</p>
    </div>
  );
}
