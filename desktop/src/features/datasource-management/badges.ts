import type { DataSource } from "../../lib/api";

export const healthType = (ds: DataSource) =>
  ds.last_test_status === "success" ? "success" : ds.last_test_status === "failed" ? "error" : "idle";

export const fmtDate = (value?: string) =>
  value
    ? new Date(value).toLocaleString("zh-CN", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "-";

export const dbBadge = (ds: DataSource) =>
  ds.db_type === "postgresql"
    ? { label: "PG", color: "var(--color-primary)", bg: "var(--color-primary-soft)" }
    : ds.db_type === "sqlite"
      ? { label: "Lite", color: "var(--color-text-muted)", bg: "var(--color-border)" }
      : { label: "MySQL", color: "var(--color-info)", bg: "var(--color-info-soft)" };

export const envBadge = (env?: string) =>
  env === "prod"
    ? { label: "生产", color: "var(--color-danger)", bg: "var(--color-danger-soft)" }
    : env === "test"
      ? { label: "测试", color: "var(--color-warning)", bg: "var(--color-warning-soft)" }
      : { label: "开发", color: "var(--color-text-secondary)", bg: "var(--color-border)" };
