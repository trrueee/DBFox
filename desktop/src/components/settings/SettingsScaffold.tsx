import {
  cloneElement,
  isValidElement,
  useId,
  type ComponentType,
  type HTMLAttributes,
  type ReactNode,
} from "react";
import { AlertCircle, CheckCircle2, Info, TriangleAlert } from "lucide-react";

import { cn } from "../../lib/utils";
import { Alert, AlertDescription, AlertTitle } from "../ui/alert";
import { ErrorDetails } from "../ui/error-details";
import { Field, FieldDescription, FieldError, FieldLabel } from "../ui/field";
import { Spinner } from "../ui/spinner";
import { Switch } from "../ui/switch";
import "./settings-scaffold.css";

type SettingsIcon = ComponentType<{ size?: number; className?: string; "aria-hidden"?: boolean }>;
type SettingsStatusTone = "neutral" | "info" | "success" | "warning" | "danger" | "loading";

const STATUS_ICONS: Record<SettingsStatusTone, SettingsIcon> = {
  neutral: Info,
  info: Info,
  success: CheckCircle2,
  warning: TriangleAlert,
  danger: AlertCircle,
  loading: Info,
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
    <section
      className={cn("settings-section", Icon && "settings-section--with-icon", className)}
      aria-labelledby={titleId}
    >
      <header className="settings-section__header">
        <div className="settings-section__identity">
          {Icon ? (
            <span className="settings-section__icon" aria-hidden="true">
              <Icon size={16} />
            </span>
          ) : null}
          <div>
            <h2 id={titleId} className="settings-section__title">{title}</h2>
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
  const labelId = useId();
  const descriptionId = `${htmlFor}-description`;
  const hasDescription = Boolean(error || hint);
  const isDirectControl = isValidElement(children)
    && typeof children.type === "string"
    && ["input", "select", "textarea"].includes(children.type);
  const control = isDirectControl && isValidElement<{
    "aria-describedby"?: string;
    "aria-invalid"?: boolean | "true" | "false";
  }>(children)
    ? cloneElement(children, {
        "aria-describedby": [
          children.props["aria-describedby"],
          hasDescription ? descriptionId : undefined,
        ].filter(Boolean).join(" ") || undefined,
        "aria-invalid": error ? true : children.props["aria-invalid"],
      })
    : children;
  return (
    <Field
      className={cn("settings-field !grid", className)}
      data-invalid={Boolean(error)}
      aria-labelledby={isDirectControl ? undefined : labelId}
      aria-describedby={hasDescription ? descriptionId : undefined}
    >
      <FieldLabel id={labelId} className="settings-field__label" htmlFor={htmlFor}>{label}</FieldLabel>
      <div className="settings-field__control">{control}</div>
      {error ? (
        <FieldError id={descriptionId} className="settings-field__message is-error">{error}</FieldError>
      ) : hint ? (
        <FieldDescription id={descriptionId} className="settings-field__message">{hint}</FieldDescription>
      ) : null}
    </Field>
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
      <Switch
        checked={checked}
        onCheckedChange={onCheckedChange}
        aria-labelledby={labelId}
        aria-describedby={description ? descriptionId : undefined}
        disabled={disabled}
        size={compact ? "sm" : "default"}
      />
    </div>
  );
}

export function SettingsStatus({
  tone = "neutral",
  label,
  description,
  error,
  meta,
  className,
}: {
  tone?: SettingsStatusTone;
  label: string;
  description?: string;
  error?: unknown;
  meta?: ReactNode;
  className?: string;
}) {
  const Icon = STATUS_ICONS[tone];
  return (
    <Alert
      variant={tone === "danger" ? "destructive" : "default"}
      className={cn("settings-status", `settings-status--${tone}`, className)}
      role={tone === "danger" ? "alert" : "status"}
    >
      {tone === "loading" ? (
        <Spinner role="presentation" aria-hidden="true" aria-label={undefined} />
      ) : (
        <Icon aria-hidden={true} />
      )}
      <AlertTitle className="settings-status__title">
        <span>{label}</span>
        {meta ? <span className="settings-status__meta">{meta}</span> : null}
      </AlertTitle>
      {description || error ? (
        <AlertDescription>
          {description ? <p>{description}</p> : null}
          {error ? <ErrorDetails error={error} /> : null}
        </AlertDescription>
      ) : null}
    </Alert>
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
