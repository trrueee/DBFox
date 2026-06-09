import { AlertCircle, RefreshCw, Key, Shield } from "lucide-react";

interface ErrorMessageProps {
  code?: string;
  detail?: string;
  onRetry?: () => void;
  onFixSql?: () => void;
  onOpenSettings?: () => void;
}

interface ErrorTemplate {
  title: string;
  message: string;
  actions: Array<{
    label: string;
    icon: "retry" | "fix" | "settings" | "none";
    onClick?: () => void;
  }>;
}

const ERROR_TEMPLATES: Record<string, (detail: string) => ErrorTemplate> = {
  NO_LLM_KEY: () => ({
    title: "未配置模型服务",
    message:
      "还没有配置可用的模型服务，所以我暂时不能生成 SQL。\n请在设置里配置模型 API Key，或切换到本地 / 演示模型。",
    actions: [
      { label: "打开设置", icon: "settings" },
      { label: "重试", icon: "retry" },
    ],
  }),

  AGENT_RUNTIME_ERROR: () => ({
    title: "Agent 运行出错",
    message: "Agent 运行时遇到了问题，请稍后重试。",
    actions: [{ label: "重试", icon: "retry" }],
  }),

  POLICY_BLOCKED: (detail) => ({
    title: "操作被安全策略阻止",
    message:
      detail ||
      "这条 SQL 可能包含修改数据或结构的操作，已被安全策略阻止。\n你可以让我改写成只读查询。",
    actions: [
      { label: "修复 SQL", icon: "fix" },
      { label: "重试", icon: "retry" },
    ],
  }),

  EXECUTION_FAILED: (detail) => ({
    title: "查询执行失败",
    message: detail
      ? `查询执行失败：${detail}\n\n我可以帮你根据当前表结构修复这条 SQL。`
      : "查询执行失败，请检查 SQL 语法和字段名。",
    actions: [
      { label: "修复 SQL", icon: "fix" },
      { label: "重试", icon: "retry" },
    ],
  }),

  SCHEMA_MISSING: () => ({
    title: "表结构未加载",
    message:
      "我还没有读取到这个数据源的表结构。\n请先同步 Schema，或重新连接数据源。",
    actions: [{ label: "重试", icon: "retry" }],
  }),

  APPROVAL_REJECTED: () => ({
    title: "操作已取消",
    message: "你取消了这次操作。可以继续提问或修改查询。",
    actions: [],
  }),

  UNKNOWN: (detail) => ({
    title: "出错了",
    message: detail || "发生了一个未知错误，请稍后重试。",
    actions: [{ label: "重试", icon: "retry" }],
  }),
};

export function ErrorMessage({
  code = "UNKNOWN",
  detail = "",
  onRetry,
  onFixSql,
  onOpenSettings,
}: ErrorMessageProps) {
  const template = ERROR_TEMPLATES[code] || ERROR_TEMPLATES.UNKNOWN;
  const { title, message, actions } = template(detail);

  const actionHandlers: Record<string, (() => void) | undefined> = {
    retry: onRetry,
    fix: onFixSql,
    settings: onOpenSettings,
    none: undefined,
  };

  const iconFor = (icon: string) => {
    switch (icon) {
      case "retry":
        return <RefreshCw size={12} />;
      case "fix":
        return <Shield size={12} />;
      case "settings":
        return <Key size={12} />;
      default:
        return null;
    }
  };

  return (
    <div className="error-card">
      <div className="error-card-header">
        <AlertCircle size={14} className="error-card-icon" />
        <span className="error-card-title">{title}</span>
      </div>
      <div className="error-card-body">{message}</div>
      {actions.length > 0 && (
        <div className="error-card-actions">
          {actions.map((action) => (
            <button
              key={action.label}
              className="btn-secondary"
              onClick={actionHandlers[action.icon]}
              style={{ fontSize: "0.68rem", padding: "3px 10px" }}
            >
              {iconFor(action.icon)}
              {action.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
