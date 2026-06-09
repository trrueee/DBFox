import { useMemo } from "react";
import {
  Database,
  Shield,
  Table2,
  FileCode,
  MessageSquare,
  RefreshCw,
  Bug,
  X,
} from "lucide-react";
import type { AgentWorkspaceContext, DataSource, QueryResult } from "../../lib/api";

interface AgentHeaderProps {
  datasource: DataSource | null;
  workspaceContext?: AgentWorkspaceContext | null;
  lastQueryResult?: QueryResult | Record<string, unknown> | null;
  activeTableName?: string;
  activeSql?: string | null;
  hasMessages: boolean;
  onNewChat: () => void;
  onToggleDebug: () => void;
  onCollapse: () => void;
}

export function AgentHeader({
  datasource,
  workspaceContext,
  lastQueryResult,
  activeTableName,
  activeSql,
  hasMessages,
  onNewChat,
  onToggleDebug,
  onCollapse,
}: AgentHeaderProps) {
  const env = (datasource?.env || "").toUpperCase();
  const envLabel = env === "PROD" || env === "PRODUCTION" ? "PROD" : env || null;
  const isProd = envLabel === "PROD";

  const tableName = activeTableName || workspaceContext?.selected_table_names?.[0] || null;

  const sqlStatus = useMemo(() => {
    if (!activeSql?.trim()) return null;
    return "SQL 编辑中";
  }, [activeSql]);

  const resultStatus = useMemo(() => {
    if (!lastQueryResult) return null;
    const r = lastQueryResult as Record<string, unknown>;
    if (r.rowCount && Number(r.rowCount) > 0) {
      return `最近结果 ${r.rowCount} 行`;
    }
    return null;
  }, [lastQueryResult]);

  return (
    <div className="agent-header">
      <div className="agent-header-top">
        <span className="agent-header-title">
          <MessageSquare size={13} style={{ color: "var(--accent-primary)" }} />
          DataBox Copilot
        </span>
        <div className="agent-header-actions">
          {hasMessages && (
            <button
              className="btn-ghost"
              onClick={onNewChat}
              title="新建对话"
              style={{ fontSize: "0.62rem", padding: "2px 6px" }}
            >
              <RefreshCw size={11} />
              新对话
            </button>
          )}
          <button
            className="btn-ghost"
            onClick={onToggleDebug}
            title="调试面板"
            style={{ fontSize: "0.62rem", padding: "2px 6px" }}
          >
            <Bug size={11} />
          </button>
          <button
            className="btn-ghost"
            onClick={onCollapse}
            title="折叠面板"
            style={{ padding: 2 }}
          >
            <X size={12} />
          </button>
        </div>
      </div>

      {/* Context chips — only show what's available */}
      {(datasource || tableName || sqlStatus || resultStatus) && (
        <div className="agent-header-chips">
          {datasource && (
            <span className="context-chip" title={`${datasource.database_name || datasource.name}`}>
              <Database size={10} />
              <span className="context-chip-text">
                {datasource.database_name || datasource.name}
              </span>
            </span>
          )}
          {isProd && (
            <span className={`context-chip context-chip-env context-chip-env-prod`}>
              <Shield size={10} />
              PROD
            </span>
          )}
          {envLabel && !isProd && (
            <span className="context-chip context-chip-env">
              {envLabel}
            </span>
          )}
          {tableName && (
            <span className="context-chip" title={tableName}>
              <Table2 size={10} />
              <span className="context-chip-text">{truncate(tableName, 24)}</span>
            </span>
          )}
          {sqlStatus && (
            <span className="context-chip context-chip-sql">
              <FileCode size={10} />
              {sqlStatus}
            </span>
          )}
          {resultStatus && (
            <span className="context-chip context-chip-result">
              {resultStatus}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen - 1) + "…";
}
