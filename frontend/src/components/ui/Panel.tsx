import type { ReactNode } from "react";

interface PanelProps {
  /** Uppercase section caption rendered in the panel header. */
  label: string;
  /** Optional content pinned to the trailing edge of the header (counts, chips, controls). */
  action?: ReactNode;
  /** Extra classes for the panel shell — used for sizing and animation. */
  className?: string;
  /** Extra classes for the scrollable body. */
  bodyClassName?: string;
  children: ReactNode;
}

/**
 * Shared panel shell for every column of the dashboard: slate-900 surface,
 * slate-800 border, rounded-xl, and a fixed header with an independently
 * scrolling body.
 */
export default function Panel({
  label,
  action,
  className = "",
  bodyClassName = "",
  children,
}: PanelProps) {
  return (
    <section className={`panel ${className}`}>
      <header className="panel-header">
        <h2 className="panel-label">{label}</h2>
        {action ? <div className="ml-auto flex items-center gap-2">{action}</div> : null}
      </header>
      <div className={`panel-body overflow-y-auto ${bodyClassName}`}>{children}</div>
    </section>
  );
}
