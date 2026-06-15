import type { CSSProperties, KeyboardEvent, ReactNode } from "react";

interface LabCardProps {
  children: ReactNode;
  accent?: boolean;
  elevated?: boolean;
  hover?: boolean;
  className?: string;
  style?: CSSProperties;
  onClick?: () => void;
}

export function LabCard({ children, accent, elevated, hover, className, style, onClick }: LabCardProps) {
  const cls = [
    accent ? "lab-card-accent" : elevated ? "lab-card-elevated" : "lab-card",
    hover ? "hover-lift" : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (onClick && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      onClick();
    }
  };

  return (
    <div
      className={cls}
      style={{ cursor: onClick ? "pointer" : undefined, ...style }}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? handleKeyDown : undefined}
    >
      {children}
    </div>
  );
}
