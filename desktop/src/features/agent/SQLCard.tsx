import { Copy, Play, FileCode, MessageSquare } from "lucide-react";

interface SQLCardProps {
  sql: string;
  title?: string;
  isProd?: boolean;
  onCopy?: () => void;
  onInsert?: () => void;
  onRun?: () => void;
  onExplain?: () => void;
}

export function SQLCard({
  sql,
  title = "SQL 查询建议",
  isProd = false,
  onCopy,
  onInsert,
  onRun,
  onExplain,
}: SQLCardProps) {
  const handleCopy = () => {
    navigator.clipboard.writeText(sql).catch(() => {});
    onCopy?.();
  };

  return (
    <div className="sql-card">
      <div className="sql-card-header">
        <span className="sql-card-title">
          <FileCode size={13} />
          {title}
        </span>
        {isProd && (
          <span className="sql-card-env-badge" title="生产环境 — 执行前请确认">
            PROD
          </span>
        )}
      </div>

      <pre className="sql-card-body">
        <code>{sql}</code>
      </pre>

      <div className="sql-card-actions">
        <button
          className="sql-card-btn"
          onClick={handleCopy}
          title="复制 SQL"
        >
          <Copy size={12} />
          复制
        </button>
        {onInsert && (
          <button
            className="sql-card-btn sql-card-btn-primary"
            onClick={onInsert}
            title="插入到编辑器"
          >
            <FileCode size={12} />
            插入编辑器
          </button>
        )}
        {onRun && (
          <button
            className="sql-card-btn sql-card-btn-accent"
            onClick={onRun}
            title={isProd ? "在生产环境执行 — 请确认 SQL 安全" : "运行查询"}
          >
            <Play size={12} />
            运行
          </button>
        )}
        {onExplain && (
          <button
            className="sql-card-btn"
            onClick={onExplain}
            title="解释这条 SQL"
          >
            <MessageSquare size={12} />
            解释
          </button>
        )}
      </div>

      {isProd && onRun && (
        <div className="sql-card-prod-note">
          生产环境 · 用户手动执行 SELECT 语句无需额外审批
        </div>
      )}
    </div>
  );
}
