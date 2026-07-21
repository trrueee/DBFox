export type PresentationTone = "success" | "warning" | "error" | "idle" | "info";

export interface StatusPresentation {
  label: string;
  tone: PresentationTone;
}

const datasourceStatuses: Record<string, StatusPresentation> = {
  active: { label: "已连接", tone: "success" },
  ready: { label: "已连接", tone: "success" },
  connecting: { label: "正在连接", tone: "info" },
  needs_credentials: { label: "需要重新填写密码", tone: "warning" },
  inactive: { label: "未启用", tone: "idle" },
  disabled: { label: "已停用", tone: "idle" },
  failed: { label: "连接异常", tone: "error" },
  error: { label: "连接异常", tone: "error" },
};

const runStatuses: Record<string, StatusPresentation> = {
  running: { label: "正在分析", tone: "info" },
  waiting_approval: { label: "等待你的确认", tone: "warning" },
  completed: { label: "已完成", tone: "success" },
  failed: { label: "未完成", tone: "error" },
  cancelled: { label: "已取消", tone: "idle" },
};

const approvalStatuses: Record<string, StatusPresentation> = {
  pending: { label: "待确认", tone: "warning" },
  approved: { label: "已确认", tone: "success" },
  rejected: { label: "已拒绝", tone: "error" },
  expired: { label: "已失效", tone: "idle" },
};

const errorMessagesByCode: Record<string, string> = {
  DBFOX_ERROR: "操作未完成，请重试。",
  INTERNAL_ERROR: "服务暂时不可用，请稍后重试。",
  CONNECTION_FAILED: "数据库连接失败，请检查连接信息和网络。",
  CREDENTIAL_VAULT_UNAVAILABLE: "无法读取已保存的密码，请重新输入。",
  CREDENTIAL_LEASE_INVALID: "连接信息已失效，请重新输入密码后再试。",
  INVALID_CREDENTIALS: "账号或密码不正确，请重新填写。",
  VALIDATION_ERROR: "填写的信息不完整，请检查标记项。",
  VALIDATION_FAILED: "填写的信息不完整，请检查标记项。",
  NOT_FOUND: "未找到相关内容，请刷新后重试。",
  SQL_EXECUTION_FAILED: "查询执行失败，请检查 SQL 后重试。",
  SQL_QUERY_TIMEOUT: "查询时间过长，请缩小查询范围后重试。",
  SQL_QUERY_CANCELLED: "查询已取消。",
  AI_TRANSLATION_FAILED: "智能分析暂时不可用，请稍后重试。",
  BACKUP_SOURCE_MISMATCH: "备份与当前数据源不匹配，无法恢复。",
  ENGINE_STARTUP_TIMEOUT: "DBFox 加载时间较长，请重试。",
  ENGINE_HEALTH_UNAVAILABLE: "DBFox 暂时无法启动，请重试。",
  ENGINE_STARTUP_FAILED: "DBFox 启动失败，请重试或查看诊断日志。",
  ENGINE_RESTART_FAILED: "DBFox 重新启动失败，请查看诊断日志。",
  ENGINE_STOPPED: "DBFox 已停止，请重新启动。",
  UNAUTHORIZED_ENGINE_ACCESS: "DBFox 访问凭据已失效，请重新启动应用。",
};

export function datasourceStatusPresentation(status?: string | null): StatusPresentation {
  const normalized = String(status || "").trim().toLowerCase();
  return datasourceStatuses[normalized] ?? { label: "状态待确认", tone: "idle" };
}

export function runStatusPresentation(status?: string | null): StatusPresentation {
  const normalized = String(status || "").trim().toLowerCase();
  return runStatuses[normalized] ?? { label: "状态待确认", tone: "idle" };
}

export function approvalStatusPresentation(status?: string | null): StatusPresentation {
  const normalized = String(status || "").trim().toLowerCase();
  return approvalStatuses[normalized] ?? { label: "状态待确认", tone: "idle" };
}

export function databaseTypeLabel(dbType?: string | null): string {
  switch (String(dbType || "").trim().toLowerCase()) {
    case "mysql": return "MySQL";
    case "postgres":
    case "postgresql": return "PostgreSQL";
    case "sqlite": return "SQLite";
    case "duckdb": return "DuckDB";
    default: return "数据库";
  }
}

export function safetyCheckLabel(result?: string | null): string {
  switch (String(result || "").trim().toLowerCase()) {
    case "pass":
    case "passed":
    case "allow":
    case "allowed": return "已通过";
    case "block":
    case "blocked":
    case "deny":
    case "denied": return "已拦截";
    case "warning":
    case "warn": return "需要留意";
    case "unknown":
    case "": return "等待检查";
    default: return "已完成检查";
  }
}

export function riskLevelLabel(level?: string | null): string {
  switch (String(level || "").trim().toLowerCase()) {
    case "critical":
    case "high": return "高风险";
    case "warning":
    case "medium": return "中风险";
    case "safe":
    case "low": return "低风险";
    default: return "风险待确认";
  }
}

const completionLimitationLabels: Record<string, string> = {
  TURN_BUDGET_REACHED: "已达到分析轮次上限",
  TOOL_BUDGET_REACHED: "已达到工具调用上限",
  TOKEN_BUDGET_REACHED: "已达到模型用量上限",
  COST_BUDGET_REACHED: "已达到本次费用上限",
  DEADLINE_REACHED: "已达到本次分析时限",
  INSUFFICIENT_EVIDENCE: "现有证据不足以完成全部判断",
  TOOL_REJECTED: "部分操作未获批准",
  PROVIDER_LIMIT: "模型服务限制了本次分析",
  NO_PROGRESS: "继续尝试未获得新的有效证据",
};

export function completionLimitationLabel(code: string): string {
  return completionLimitationLabels[code] ?? "本次回答存在已知限制";
}

function errorFields(error: unknown): { code?: string; message?: string; status?: number } {
  if (typeof error === "string") return { message: error };
  if (!error || typeof error !== "object") return {};
  const value = error as { code?: unknown; message?: unknown; status?: unknown };
  return {
    code: typeof value.code === "string" ? value.code : undefined,
    message: typeof value.message === "string" ? value.message : undefined,
    status: typeof value.status === "number" ? value.status : undefined,
  };
}

function containsChinese(value: string): boolean {
  return /[\u3400-\u9fff]/u.test(value);
}

export function userFacingErrorMessage(error: unknown, fallback = "操作失败，请重试"): string {
  const { code, message, status } = errorFields(error);
  if (code && errorMessagesByCode[code]) return errorMessagesByCode[code];

  const normalizedMessage = String(message || "").trim();
  if (normalizedMessage && containsChinese(normalizedMessage)) return normalizedMessage;

  const lowered = normalizedMessage.toLowerCase();
  if (lowered.includes("failed to fetch") || lowered.includes("networkerror") || lowered.includes("load failed")) {
    return "无法连接 DBFox 服务，请确认应用已正常启动。";
  }
  if (lowered.includes("agent event stream")) return "智能分析连接中断，请重试。";
  if (status === 401 || status === 403) return "当前访问已失效，请重新启动应用。";
  if (status === 404) return "未找到相关内容，请刷新后重试。";
  if (status === 409) return "当前内容已发生变化，请刷新后重试。";
  if (status && status >= 500) return "服务暂时不可用，请稍后重试。";
  return fallback;
}
