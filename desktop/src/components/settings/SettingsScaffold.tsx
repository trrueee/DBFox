import { useId, type ComponentType, type HTMLAttributes, type ReactNode } from "react";
import { AlertCircle, CheckCircle2, Info, Loader2, TriangleAlert } from "lucide-react";

import { cn } from "../../lib/utils";
import "./settings-scaffold.css";

type SettingsIcon = ComponentType<{ size?: number; className?: string; "aria-hidden"?: boolean }>;
type SettingsStatusTone = "neutral" | "info" | "success" | "warning" | "danger" | "loading";

const STATUS_ICONS: Record<SettingsStatusTone, SettingsIcon> = {
  neutral: Info,
  info: Info,
  success: CheckCircle2,
  warning: TriangleAlert,
  danger: AlertCircle,
  loading: Loader2,
};

interface SettingsContentProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

export function SettingsContent({ className, children, ...props }: SettingsContentProps) {
  return (
    <div className={cn("settings-content", className)} {...props}>
      {children}
    </div>
  );
}

export function SettingsSection({
  icon: Icon,
  title,
  description,
  trailing,
  children,
  className,
}: {
  icon?: SettingsIcon;
  title: string;
  description?: string;
  trailing?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const titleId = useId();
  return (
    <section className={cn("settings-section", className)} aria-labelledby={titleId}>
      <header className="settings-section__header">
        <div className="settings-section__identity">
          {Icon ? (
            <span className="settings-section__icon" aria-hidden="true">
              <Icon size={16} />
            </span>
          ) : null}
          <div>
            <h3 id={titleId} className="settings-section__title">{title}</h3>
            {description ? <p className="settings-section__description">{description}</p> : null}
          </div>
        </div>
        {trailing ? <div className="settings-section__trailing">{trailing}</div> : null}
      </header>
      <div className="settings-section__body">{children}</div>
    </section>
  );
}

export function SettingsField({
  label,
  htmlFor,
  hint,
  error,
  children,
  className,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
  error?: string;
  children: ReactNode;
  className?: string;
}) {
  const descriptionId = useId();
  return (
    <div className={cn("settings-field", className)}>
      <label className="settings-field__label" htmlFor={htmlFor}>{label}</label>
      {children}
      {error ? (
        <p id={descriptionId} className="settings-field__message is-error" role="alert">{error}</p>
      ) : hint ? (
        <p id={descriptionId} className="settings-field__message">{hint}</p>
      ) : null}
    </div>
  );
}

export function SettingsToggle({
  checked,
  onCheckedChange,
  label,
  description,
  disabled = false,
  compact = false,
}: {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
  compact?: boolean;
}) {
  const labelId = useId();
  const descriptionId = useId();
  return (
    <div className={cn("settings-toggle", compact && "settings-toggle--compact", disabled && "is-disabled")}>
      <div className="settings-toggle__copy">
        <span id={labelId} className="settings-toggle__label">{label}</span>
        {description ? <span id={descriptionId} className="settings-toggle__description">{description}</span> : null}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={labelId}
        aria-describedby={description ? descriptionId : undefined}
        className="settings-switch"
        disabled={disabled}
        onClick={() => onCheckedChange(!checked)}
      >
        <span className="settings-switch__thumb" />
      </button>
    </div>
  );
}

export function SettingsStatus({
  tone = "neutral",
  label,
  description,
  meta,
  className,
}: {
  tone?: SettingsStatusTone;
  label: string;
  description?: string;
  meta?: ReactNode;
  className?: string;
}) {
  const Icon = STATUS_ICONS[tone];
  return (
    <div
      className={cn("settings-status", `settings-status--${tone}`, className)}
      role={tone === "danger" ? "alert" : "status"}
    >
      <Icon className={tone === "loading" ? "is-spinning" : undefined} size={16} aria-hidden={true} />
      <div className="settings-status__copy">
        <strong>{label}</strong>
        {description ? <span>{description}</span> : null}
      </div>
      {meta ? <div className="settings-status__meta">{meta}</div> : null}
    </div>
  );
}

export function SettingsActionBar({
  status,
  children,
  className,
}: {
  status?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <footer className={cn("settings-action-bar", className)}>
      <div className="settings-action-bar__status">{status}</div>
      <div className="settings-action-bar__actions">{children}</div>
    </footer>
  );
}
