import type { HTMLAttributes, ReactNode } from "react";

interface PanelProps extends HTMLAttributes<HTMLElement> {
  children: ReactNode;
}

/** Primary dark surface: `rounded-xl border border-slate-800 bg-slate-900`. */
export function Panel({ className = "", children, ...rest }: PanelProps) {
  return (
    <section className={`panel flex min-h-0 flex-col ${className}`} {...rest}>
      {children}
    </section>
  );
}

export function PanelHeader({
  className = "",
  children,
  ...rest
}: HTMLAttributes<HTMLElement> & { children: ReactNode }) {
  return (
    <header className={`panel-header ${className}`} {...rest}>
      {children}
    </header>
  );
}

export function PanelTitle({ className = "", children }: { className?: string; children: ReactNode }) {
  return <h2 className={`panel-label ${className}`}>{children}</h2>;
}

export function PanelBody({ className = "", children }: { className?: string; children: ReactNode }) {
  return <div className={`panel-body ${className}`}>{children}</div>;
}
