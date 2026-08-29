import type { ReactNode } from "react";

export function ComparisonCandidate({
  title,
  source,
  decision,
  children,
}: {
  title: string;
  source: string;
  decision: string;
  children: ReactNode;
}) {
  return (
    <article className="component-comparison__candidate">
      <header>
        <div>
          <strong>{title}</strong>
          <span title={source}>{source}</span>
        </div>
        <small>{decision}</small>
      </header>
      <div className="component-comparison__candidate-body">{children}</div>
    </article>
  );
}

export function ComparisonGrid({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`component-comparison__grid ${className}`.trim()}>{children}</div>;
}
