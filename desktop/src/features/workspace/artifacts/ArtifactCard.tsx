import type { ReactNode } from "react";
import "./ArtifactCard.css";

export type ArtifactTone = "default" | "sql" | "table" | "chart" | "insight" | "warning" | "danger";

interface ArtifactCardProps {
  className?: string;
  icon?: ReactNode;
  title: string;
  badge?: string;
  headerAccessory?: ReactNode;
  tone?: ArtifactTone;
  description?: string;
  meta?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  compact?: boolean;
}

export function ArtifactCard({
  className,
  icon,
  title,
  badge,
  headerAccessory,
  tone = "default",
  description,
  meta,
  actions,
  children,
  compact = false,
}: ArtifactCardProps) {
  const classNames = [
    "artifact-card",
    `artifact-card-${tone}`,
    className,
    compact ? "is-compact" : "",
  ].filter(Boolean).join(" ");

  return (
    <section className={classNames}>
      <header className="artifact-card-header">
        <div className="artifact-card-title">
          {icon}
          <span>{title}</span>
        </div>
        <div className="artifact-card-header-end">
          {badge && <span className="artifact-card-badge">{badge}</span>}
          {headerAccessory}
        </div>
      </header>
      {description && <p className="artifact-card-desc">{description}</p>}
      {meta && <div className="artifact-card-meta">{meta}</div>}
      {children ? <div className="artifact-card-body">{children}</div> : null}
      {actions && <footer className="artifact-card-actions">{actions}</footer>}
    </section>
  );
}
