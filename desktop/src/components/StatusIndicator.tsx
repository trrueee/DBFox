type StatusType = "success" | "warning" | "error" | "idle" | "info";

interface StatusIndicatorProps {
  type: StatusType;
  label?: string;
  size?: "sm" | "md";
}

const dotClass: Record<StatusType, string> = {
  success: "status-dot-success",
  warning: "status-dot-warning",
  error: "status-dot-error",
  idle: "status-dot-idle",
  info: "status-dot-idle",
};

const badgeClass: Record<StatusType, string> = {
  success: "status-badge-success",
  warning: "status-badge-warning",
  error: "status-badge-error",
  idle: "status-badge-neutral",
  info: "status-badge-info",
};

const defaultLabel: Record<StatusType, string> = {
  success: "正常",
  warning: "注意",
  error: "异常",
  idle: "空闲",
  info: "信息",
};

export function StatusIndicator({ type, label, size = "md" }: StatusIndicatorProps) {
  const sizeClass = `status-dot--${size}`;

  if (!label) {
    return (
      <span
        className={`status-dot ${sizeClass} ${dotClass[type]}`}
        title={defaultLabel[type]}
      />
    );
  }

  return (
    <span className={`status-badge ${badgeClass[type]}`}>
      <span className={`status-dot ${sizeClass} ${dotClass[type]}`} />
      {label || defaultLabel[type]}
    </span>
  );
}
