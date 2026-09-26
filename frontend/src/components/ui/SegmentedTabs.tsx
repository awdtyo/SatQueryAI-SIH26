import { useRef } from "react";
import type { KeyboardEvent } from "react";

export interface SegmentedTab<T extends string> {
  value: T;
  label: string;
  /** Rendered under the label — used for the active input-mode description. */
  hint?: string;
}

interface Props<T extends string> {
  ariaLabel: string;
  tabs: SegmentedTab<T>[];
  value: T;
  onChange: (value: T) => void;
  /** Show the `hint` of the active tab underneath the control. */
  showHint?: boolean;
  className?: string;
}

/**
 * Segmented tab bar. Active segment gets the teal glow border + accent text,
 * inactive segments stay muted and lift on hover. Arrow keys move between
 * tabs (standard `role="tablist"` keyboard model).
 */
export default function SegmentedTabs<T extends string>({
  ariaLabel,
  tabs,
  value,
  onChange,
  showHint = false,
  className = "",
}: Props<T>) {
  const listRef = useRef<HTMLDivElement>(null);
  const active = tabs.find((t) => t.value === value) ?? tabs[0]!;

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const keys = ["ArrowRight", "ArrowLeft", "Home", "End"];
    if (!keys.includes(event.key)) return;
    event.preventDefault();
    const current = tabs.findIndex((t) => t.value === value);
    let next = current;
    if (event.key === "ArrowRight") next = (current + 1) % tabs.length;
    if (event.key === "ArrowLeft") next = (current - 1 + tabs.length) % tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length - 1;
    const target = tabs[next];
    if (!target) return;
    onChange(target.value);
    const buttons = listRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
    buttons?.[next]?.focus();
  };

  return (
    <div className={className}>
      <div
        ref={listRef}
        role="tablist"
        aria-label={ariaLabel}
        onKeyDown={handleKeyDown}
        className="flex gap-1 rounded-lg border border-slate-800 bg-slate-950 p-1"
      >
        {tabs.map((tab) => {
          const isActive = tab.value === value;
          return (
            <button
              key={tab.value}
              type="button"
              role="tab"
              aria-selected={isActive}
              tabIndex={isActive ? 0 : -1}
              onClick={() => onChange(tab.value)}
              title={tab.hint}
              className={`min-w-0 flex-1 truncate rounded-md border px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wide transition-all duration-150 ${
                isActive
                  ? "border-teal-500/50 bg-slate-900 text-teal-300 shadow-glow"
                  : "border-transparent text-slate-500 hover:bg-slate-900/60 hover:text-slate-200"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      {showHint && active.hint && (
        <p className="mt-2 text-[11px] leading-snug text-slate-500">{active.hint}</p>
      )}
    </div>
  );
}
