import { useMemo, useState } from "react";
import { Sparkles } from "lucide-react";
import { AgentHeader } from "./AgentHeader";
import { MessageList } from "./MessageList";
import { AgentComposer } from "./AgentComposer";
import { DebugDrawer } from "./DebugDrawer";
import { useAgentChat } from "./useAgentChat";
import type { ChatMessage } from "./useAgentChat";
import { buildAgentWorkspaceContext } from "./workspaceContext";
import { buildAgentFollowUpContext } from "./context";
import type {
  AgentRunConfig,
  AgentRunResponse,
  AgentRuntimeEvent,
  AgentWorkspaceContext,
  DataSource,
  FollowUpSuggestion,
  QueryResult,
  SchemaTable,
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
}

export function AgentCopilotPanel({
  datasource,
  activeTableName,
  activeSql,
  lastQueryResult,
  lastError,
  isCollapsed,
  onCollapse,
  onInsertSql,
  onRunSql,
  onOpenQueryTab,
  onRuntimeEvent,
  onResumeComplete,
}: AgentCopilotPanelProps) {
  const [debugOpen, setDebugOpen] = useState(false);

  const workspaceContext = useMemo(
    () =>
      buildAgentWorkspaceContext({
        currentDatasource: datasource,
        activeSql,
        lastQueryResult,
        lastError,
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

  // ── Collapsed state ──
  if (isCollapsed) {
    return (
      <aside
        className="agent-panel agent-panel-collapsed"
        style={{
          width: 48,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          paddingTop: 10,
          borderLeft: "1px solid var(--border-light)",
          background: "var(--bg-surface)",
        }}
      >
        <button
          className="btn-ghost"
          onClick={onCollapse}
          style={{ padding: 4 }}
          title="展开 Agent Copilot (Alt+A)"
        >
          <Sparkles size={16} />
        </button>
        {chat.isRunning && (
          <span
            className="animate-spin"
            style={{ marginTop: 8, fontSize: 10, color: "var(--accent-primary)" }}
          >
            ↻
          </span>
        )}
      </aside>
    );
  }

  // ── Empty state suggestions ──
  const emptySuggestions = useMemo(() => {
    const base: string[] = [];
    if (activeTableName) {
      base.push(
        `查询 ${activeTableName} 最近记录`,
        `${activeTableName} 这张表是做什么的？`,
        `统计 ${activeTableName} 记录数量`,
      );
    }
    if (activeSql?.trim()) {
      base.push("解释当前 SQL", "优化当前 SQL");
    }
    if (base.length === 0) {
      base.push(
        "查看当前数据库的所有表",
        "帮我生成一条查询",
        "当前数据库有哪些核心表？",
      );
    }
    return base;
  }, [activeTableName, activeSql]);

  // ── Build steps/trace for debug drawer ──
  const debugSteps = chat.finalResponse?.steps || [];
  const debugTrace = chat.finalResponse?.trace_events || [];

  return (
    <aside className="agent-panel agent-panel-expanded">
      <AgentHeader
        datasource={datasource}
        workspaceContext={workspaceContext}
        lastQueryResult={lastQueryResult}
        activeTableName={activeTableName}
        activeSql={activeSql}
        hasMessages={chat.messages.length > 0}
        onNewChat={chat.clear}
        onToggleDebug={() => setDebugOpen(!debugOpen)}
        onCollapse={onCollapse}
      />

      {/* Message area */}
      <div className="agent-panel-messages">
        {chat.messages.length > 0 ? (
          <MessageList
            messages={chat.messages}
            isRunning={chat.isRunning}
            finalResponse={chat.finalResponse}
            approval={chat.finalResponse?.approval}
            suggestions={chat.finalResponse?.suggestions}
            isProd={isProd}
            onInsertSql={onInsertSql}
            onRunSql={onRunSql}
            onExplainSql={(sql) => chat.send(`解释以下 SQL：\n${sql}`)}
            onRetry={() => {
              const lastUser = [...chat.messages]
                .reverse()
                .find((m) => m.role === "user");
              if (lastUser) chat.send(lastUser.question);
            }}
            onFixSql={() => chat.send("帮我修复当前 SQL 的错误")}
            onOpenSettings={() => {}}
            onAsk={(q) => chat.send(q)}
            onResumeApproval={(runId, approvalId) =>
              chat.resumeApproval(runId, approvalId)
            }
            onRejectApproval={(runId, approvalId) =>
              chat.rejectApproval(runId, approvalId)
            }
          />
        ) : !chat.isRunning ? (
          <div className="agent-empty-state">
            <div className="agent-empty-state-icon">
              <Sparkles size={28} style={{ color: "var(--accent-primary)", opacity: 0.6 }} />
            </div>
            <div className="agent-empty-state-title">DataBox Copilot</div>
            <div className="agent-empty-state-desc">
              {activeTableName
                ? `当前表：${activeTableName}`
                : "我可以帮你生成 SQL、解释结果、修复错误"}
            </div>
            <div className="agent-empty-state-chips">
              {emptySuggestions.map((s) => (
                <button
                  key={s}
                  className="btn-secondary"
                  onClick={() => chat.send(s)}
                  style={{ fontSize: "0.66rem", padding: "3px 8px" }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      {/* Composer */}
      <AgentComposer
        disabled={chat.isRunning}
        placeholder={
          activeTableName
            ? `问 DataBox：${activeTableName} 相关的查询…`
            : "问 DataBox：生成 SQL、解释结果、修复错误…"
        }
        workspaceContext={workspaceContext}
        onSubmit={(question) => chat.send(question)}
      />

      {/* Debug drawer */}
      <DebugDrawer
        open={debugOpen}
        onClose={() => setDebugOpen(false)}
        workspaceContext={workspaceContext}
        response={chat.finalResponse}
        steps={debugSteps}
        traceEvents={debugTrace}
        runtimeEvents={
          chat.finalResponse?.events ||
          ([] as AgentRuntimeEvent[])
        }
      />
    </aside>
  );
}
