import { useMemo, useState } from "react";
import { Sparkles } from "lucide-react";
import { AgentHeader } from "./AgentHeader";
import { MessageList } from "./MessageList";
import { AgentComposer } from "./AgentComposer";
import { DebugDrawer } from "./DebugDrawer";
import { useAgentChat } from "./useAgentChat";
import { Button } from "../../components/ui/button";
import type { ChatMessage } from "./useAgentChat";
import { buildAgentWorkspaceContext } from "./workspaceContext";
import { buildAgentFollowUpContext } from "./context";
import type {
  AgentRunConfig, AgentRunResponse, AgentRuntimeEvent,
  AgentWorkspaceContext, DataSource, FollowUpSuggestion, QueryResult, SchemaTable,
} from "../../lib/api";

interface AgentCopilotPanelProps {
  datasource: DataSource | null;
  activeTableName?: string;
  activeSql?: string | null;
  lastQueryResult?: QueryResult | Record<string, unknown> | null;
  lastError?: string | null;
  isCollapsed: boolean;
  onCollapse: () => void;
  onInsertSql?: (sql: string) => void;
  onRunSql?: (sql: string) => void;
  onOpenQueryTab?: (sql: string, title: string) => void;
  onRuntimeEvent?: (event: AgentRuntimeEvent) => void;
  onResumeComplete?: (response: AgentRunResponse) => void;
  onOpenApiConfig: () => void;
  apiConfigured: boolean;
}

export function AgentCopilotPanel({
  datasource, activeTableName, activeSql, lastQueryResult, lastError,
  isCollapsed, onCollapse, onInsertSql, onRunSql, onOpenQueryTab,
  onRuntimeEvent, onResumeComplete, onOpenApiConfig, apiConfigured,
}: AgentCopilotPanelProps) {
  const [debugOpen, setDebugOpen] = useState(false);

  const workspaceContext = useMemo(
    () => buildAgentWorkspaceContext({
      currentDatasource: datasource, activeSql, lastQueryResult, lastError,
      selectedTable: activeTableName || null,
    }),
    [datasource, activeSql, lastQueryResult, lastError, activeTableName],
  );

  const chat = useAgentChat({
    datasourceId: datasource?.id || "",
    workspaceContext,
    config: { optimizeRag: true, execute: true },
    onApplySql: onInsertSql,
    onOpenQueryTab,
  });

  const env = (datasource?.env || "").toUpperCase();
  const isProd = env === "PROD" || env === "PRODUCTION";

  if (isCollapsed) {
    return (
      <aside className="flex flex-col items-center pt-3 border-l border-[hsl(var(--border))] bg-[hsl(var(--card))]" style={{ width: 48 }}>
        <Button variant="ghost" size="icon" onClick={onCollapse} title="展开 Agent (Alt+A)">
          <Sparkles size={16} />
        </Button>
        {chat.isRunning && (
          <span className="animate-spin mt-2 text-[0.65rem] text-[hsl(var(--primary))]">↻</span>
        )}
      </aside>
    );
  }

  const emptySuggestions = useMemo(() => {
    const base: string[] = [];
    if (activeTableName) {
      base.push(`查询 ${activeTableName} 最近记录`, `${activeTableName} 这张表是做什么的？`, `统计 ${activeTableName} 记录数量`);
    }
    if (activeSql?.trim()) base.push("解释当前 SQL", "优化当前 SQL");
    if (base.length === 0) base.push("查看当前数据库的所有表", "帮我生成一条查询", "当前数据库有哪些核心表？");
    return base;
  }, [activeTableName, activeSql]);

  const debugSteps = chat.finalResponse?.steps || [];
  const debugTrace = chat.finalResponse?.trace_events || [];

  return (
    <aside className="flex flex-col h-full min-h-0 overflow-hidden w-full bg-[hsl(var(--card))]">
      <AgentHeader
        datasource={datasource} workspaceContext={workspaceContext}
        lastQueryResult={lastQueryResult} activeTableName={activeTableName}
        activeSql={activeSql} hasMessages={chat.messages.length > 0}
        onNewChat={chat.clear} onToggleDebug={() => setDebugOpen(!debugOpen)}
        onCollapse={onCollapse} onOpenApiConfig={onOpenApiConfig}
        apiConfigured={apiConfigured}
      />

      {/* Messages */}
      <div className="flex-1 min-h-0 overflow-y-auto flex flex-col">
        {chat.messages.length > 0 ? (
          <MessageList
            messages={chat.messages} isRunning={chat.isRunning}
            finalResponse={chat.finalResponse} approval={chat.finalResponse?.approval}
            suggestions={chat.finalResponse?.suggestions} isProd={isProd}
            onInsertSql={onInsertSql} onRunSql={onRunSql}
            onExplainSql={(sql) => chat.send(`解释以下 SQL：\n${sql}`)}
            onRetry={() => {
              const lastUser = [...chat.messages].reverse().find((m) => m.role === "user");
              if (lastUser) chat.send(lastUser.question);
            }}
            onFixSql={() => chat.send("帮我修复当前 SQL 的错误")}
            onOpenSettings={() => {}}
            onAsk={(q) => chat.send(q)}
            onResumeApproval={(runId, approvalId) => chat.resumeApproval(runId, approvalId)}
            onRejectApproval={(runId, approvalId) => chat.rejectApproval(runId, approvalId)}
          />
        ) : !chat.isRunning ? (
          <div className="flex flex-col items-center justify-center flex-1 px-4 py-8 text-center">
            <div className="mb-2.5">
              <Sparkles size={28} className="text-[hsl(var(--primary))] opacity-60" />
            </div>
            <div className="text-[0.9rem] font-semibold text-[hsl(var(--foreground))] mb-1.5">
              DataBox Copilot
            </div>
            <div className="text-[0.72rem] text-[hsl(var(--muted-foreground))] mb-4 max-w-[260px] leading-relaxed">
              {activeTableName ? `当前表：${activeTableName}` : "我可以帮你生成 SQL、解释结果、修复错误"}
            </div>
            <div className="flex flex-wrap gap-1.5 justify-center">
              {emptySuggestions.map((s) => (
                <Button key={s} variant="outline" size="sm"
                  onClick={() => chat.send(s)}
                  className="text-[0.68rem] h-7"
                >
                  {s}
                </Button>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      <AgentComposer
        disabled={chat.isRunning}
        placeholder={activeTableName ? `问 DataBox：${activeTableName} 相关的查询…` : "问 DataBox：生成 SQL、解释结果、修复错误…"}
        workspaceContext={workspaceContext}
        onSubmit={(question) => chat.send(question)}
      />

      <DebugDrawer open={debugOpen} onClose={() => setDebugOpen(false)}
        workspaceContext={workspaceContext} response={chat.finalResponse}
        steps={debugSteps} traceEvents={debugTrace}
        runtimeEvents={chat.finalResponse?.events || ([] as AgentRuntimeEvent[])} />
    </aside>
  );
}
