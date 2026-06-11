import { useMemo } from "react";
import {
  Database, Shield, Table2, FileCode, MessageSquare,
  RefreshCw, Bug, X,
} from "lucide-react";
import type { AgentWorkspaceContext, DataSource, QueryResult } from "../../lib/api";
import { SettingsButton } from "../../components/SettingsDialog";
import { ThemeToggle } from "../../components/ThemeToggle";
import { Button } from "../../components/ui/button";

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
  onOpenApiConfig: () => void;
  apiConfigured: boolean;
}

export function AgentHeader({
  datasource, workspaceContext, lastQueryResult, activeTableName, activeSql,
  hasMessages, onNewChat, onToggleDebug, onCollapse,
  onOpenApiConfig, apiConfigured,
}: AgentHeaderProps) {
  const env = (datasource?.env || "").toUpperCase();
  const envLabel = env === "PROD" || env === "PRODUCTION" ? "PROD" : env || null;
  const isProd = envLabel === "PROD";
  const tableName = activeTableName || workspaceContext?.selected_table_names?.[0] || null;
  const sqlStatus = useMemo(() => activeSql?.trim() ? "SQL 编辑中" : null, [activeSql]);
  const resultStatus = useMemo(() => {
    if (!lastQueryResult) return null;
    const r = lastQueryResult as Record<string, unknown>;
    if (r.rowCount && Number(r.rowCount) > 0) return `最近结果 ${r.rowCount} 行`;
    return null;
  }, [lastQueryResult]);

  return (
    <div className="px-2.5 py-1.5 border-b border-[hsl(var(--border))] bg-[hsl(var(--card))] shrink-0 select-none">
      {/* Top row */}
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-[0.8rem] font-bold text-[hsl(var(--foreground))]">
          <MessageSquare size={13} className="text-[hsl(var(--primary))]" />
          DataBox Copilot
        </span>
        <div className="flex items-center gap-1">
          <ThemeToggle />
          <SettingsButton onClick={onOpenApiConfig} isConfigured={apiConfigured} />
          {hasMessages && (
            <Button variant="ghost" size="sm" onClick={onNewChat} title="新建对话"
              className="h-7 text-[0.64rem] gap-1 px-2">
              <RefreshCw size={11} /> 新对话
            </Button>
          )}
          <Button variant="ghost" size="icon-sm" onClick={onToggleDebug} title="调试面板">
            <Bug size={12} />
          </Button>
          <Button variant="ghost" size="icon-sm" onClick={onCollapse} title="折叠面板">
            <X size={12} />
          </Button>
        </div>
      </div>

      {/* Context chips */}
      {(datasource || tableName || sqlStatus || resultStatus) && (
        <div className="flex flex-wrap gap-1 mt-1.5">
          {datasource && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm text-[0.64rem] font-medium text-[hsl(var(--muted-foreground))] bg-[hsl(var(--secondary))] border border-[hsl(var(--border))] max-w-[160px] overflow-hidden">
              <Database size={10} />
              <span className="truncate">{datasource.database_name || datasource.name}</span>
            </span>
          )}
          {isProd && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm text-[0.64rem] font-semibold text-[hsl(var(--destructive))] bg-[hsl(var(--destructive)/0.12)]">
              <Shield size={10} /> PROD
            </span>
          )}
          {envLabel && !isProd && (
            <span className="inline-flex items-center px-1.5 py-0.5 rounded-sm text-[0.64rem] font-medium text-[hsl(var(--foreground))] bg-[hsl(var(--secondary))] border border-[hsl(var(--border))]">
              {envLabel}
            </span>
          )}
          {tableName && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm text-[0.64rem] font-medium text-[hsl(var(--muted-foreground))] bg-[hsl(var(--secondary))] border border-[hsl(var(--border))] max-w-[160px] overflow-hidden">
              <Table2 size={10} />
              <span className="truncate">{truncate(tableName, 24)}</span>
            </span>
          )}
          {sqlStatus && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm text-[0.64rem] font-medium text-[hsl(var(--primary))] bg-[hsl(var(--primary)/0.1)]">
              <FileCode size={10} /> {sqlStatus}
            </span>
          )}
          {resultStatus && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm text-[0.64rem] font-medium text-[hsl(var(--success))] bg-[hsl(var(--success)/0.1)]">
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
