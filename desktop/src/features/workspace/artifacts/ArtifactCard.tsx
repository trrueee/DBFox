import type { ReactNode } from "react";

export type ArtifactTone = "default" | "sql" | "table" | "chart" | "insight" | "warning" | "danger";

interface ArtifactCardProps {
  icon?: ReactNode;
  title: string;
  badge: string;
  tone?: ArtifactTone;
  description?: string;
  meta?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  compact?: boolean;
}

export function ArtifactCard({
  icon,
  title,
  badge,
  tone = "default",
  description,
  meta,
  actions,
  children,
  compact = false,
}: ArtifactCardProps) {
  return (
    <section className={`artifact-card artifact-card-${tone} ${compact ? "is-compact" : ""}`}>
      <header className="artifact-card-header">
        <div className="artifact-card-title">
          {icon}
          <span>{title}</span>
        </div>
        <span className="artifact-card-badge">{badge}</span>
      </header>
      {description && <p className="artifact-card-desc">{description}</p>}
      {meta && <div className="artifact-card-meta">{meta}</div>}
      <div className="artifact-card-body">{children}</div>
      {actions && <footer className="artifact-card-actions">{actions}</footer>}
    </section>
  );
}
