import * as React from "react";
import { AlertTriangle, Inbox, Loader2 } from "lucide-react";
import { Button } from "./button";
import { cn } from "../../lib/utils";
import "./state.css";

interface StateBlockProps extends React.HTMLAttributes<HTMLDivElement> {
  title: string;
  description?: string;
  icon?: React.ReactNode;
}

interface EmptyStateProps extends StateBlockProps {
  action?: React.ReactNode;
}

function EmptyState({ title, description, action, icon, className, ...props }: EmptyStateProps) {
  return (
    <div
      className={cn("dbfox-empty-state", className)}
      {...props}
    >
      <div className="dbfox-empty-state__icon">
        {icon ?? <Inbox aria-hidden="true" />}
      </div>
      <h3 className="dbfox-empty-state__title">{title}</h3>
      {description ? <p className="dbfox-empty-state__description">{description}</p> : null}
      {action ? <div className="dbfox-empty-state__action">{action}</div> : null}
    </div>
  );
}

interface ErrorStateProps extends StateBlockProps {
  onRetry?: () => void;
  retryLabel?: string;
}

function ErrorState({ title, description, icon, onRetry, retryLabel = "重试", className, ...props }: ErrorStateProps) {
  return (
    <div
      role="alert"
      className={cn("dbfox-error-state", className)}
      {...props}
    >
      <div className="dbfox-error-state__icon">
        {icon ?? <AlertTriangle aria-hidden="true" />}
      </div>
      <div className="dbfox-error-state__content">
        <h3 className="dbfox-error-state__title">{title}</h3>
        {description ? <p className="dbfox-error-state__description">{description}</p> : null}
        {onRetry ? (
          <Button className="dbfox-error-state__retry" size="sm" variant="outline" onClick={onRetry}>
            {retryLabel}
          </Button>
        ) : null}
      </div>
    </div>
  );
}

interface LoadingStateProps extends React.HTMLAttributes<HTMLDivElement> {
  label?: string;
}

function LoadingState({ label = "加载中", className, ...props }: LoadingStateProps) {
  return (
    <div
      role="status"
      className={cn("dbfox-loading-state", className)}
      {...props}
    >
      <Loader2 className="dbfox-loading-state__icon" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export { EmptyState, ErrorState, LoadingState };
