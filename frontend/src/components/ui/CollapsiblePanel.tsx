import { useId, useState, type ReactNode } from "react";

interface CollapsiblePanelProps {
  label: string;
  action?: ReactNode;
  className?: string;
  bodyClassName?: string;
  defaultExpanded?: boolean;
  children: ReactNode;
}

/**
 * Panel whose header doubles as the expand/collapse trigger. The body is
 * unmounted while collapsed so scroll position resets on reopen.
 */
export default function CollapsiblePanel({
  label,
  action,
  className = "",
  bodyClassName = "",
  defaultExpanded = true,
  children,
}: CollapsiblePanelProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const bodyId = useId();

  return (
    <section className={`panel ${className}`}>
      <header className="panel-header">
        <h2 className="min-w-0 flex-1">
          <button
            type="button"
            onClick={() => setExpanded((prev) => !prev)}
            aria-expanded={expanded}
            aria-controls={bodyId}
            className="group -my-1 flex w-full items-center gap-2 rounded-md py-1 text-left
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/50"
          >
            <span className="panel-label truncate transition-colors group-hover:text-slate-100">
              {label}
            </span>
            <ChevronIcon expanded={expanded} />
          </button>
        </h2>
        {action ? <div className="flex flex-shrink-0 items-center gap-2">{action}</div> : null}
      </header>
      {expanded && (
        <div id={bodyId} className={`panel-body overflow-y-auto ${bodyClassName}`}>
          {children}
        </div>
      )}
    </section>
  );
}

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 12 12"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden="true"
      className={`flex-shrink-0 text-slate-500 transition-transform duration-200 group-hover:text-slate-300 ${
        expanded ? "rotate-180" : ""
      }`}
    >
      <path d="M3 5l3 3 3-3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
