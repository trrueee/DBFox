import { useRef, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, FileCode } from "lucide-react";
import { SQLCard } from "./SQLCard";
import { ErrorMessage } from "./ErrorMessage";
import { SuggestionChips } from "./SuggestionChips";
import type { ChatMessage, ActivityStepState } from "./useAgentChat";
import type { AgentArtifact, AgentApproval, FollowUpSuggestion } from "../../lib/api";
import type { AgentRunResponse } from "../../lib/api";

interface MessageListProps {
  messages: ChatMessage[];
  isRunning?: boolean;
  finalResponse?: AgentRunResponse | null;
  approval?: AgentApproval | null;
  suggestions?: FollowUpSuggestion[];
  isProd?: boolean;
  onInsertSql?: (sql: string) => void;
  onRunSql?: (sql: string) => void;
  onExplainSql?: (sql: string) => void;
  onRetry?: () => void;
  onFixSql?: () => void;
  onOpenSettings?: () => void;
  onAsk?: (question: string) => void;
  onResumeApproval?: (runId: string, approvalId: string) => void;
  onRejectApproval?: (runId: string, approvalId: string) => void;
}

export function MessageList({
  messages,
  finalResponse,
  approval,
  suggestions,
  isProd = false,
  onInsertSql,
  onRunSql,
  onExplainSql,
  onRetry,
  onFixSql,
  onOpenSettings,
  onAsk,
  onResumeApproval,
  onRejectApproval,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (!messages.length) return null;

  return (
    <div className="message-list">
      {messages.map((msg) => {
        switch (msg.role) {
          case "user":
            return <UserBubble key={msg.id} message={msg.question} />;
          case "assistant":
            return <AssistantBubble key={msg.id} content={msg.content} />;
          case "artifact":
            return (
              <ArtifactBubble
                key={msg.id}
                artifact={msg.artifact}
                isProd={isProd}
                onInsertSql={onInsertSql}
                onRunSql={onRunSql}
                onExplainSql={onExplainSql}
              />
            );
          case "activity":
            return (
              <ActivityBubble key={msg.id} label={msg.label} steps={msg.steps} status={msg.status} collapsed={msg.collapsed} />
            );
          case "approval":
            return (
              <ApprovalBubble
                key={msg.id}
                runId={msg.runId}
                approval={approval}
                onResume={onResumeApproval}
                onReject={onRejectApproval}
              />
            );
          case "error":
            return (
              <ErrorBubble
                key={msg.id}
                code={msg.code}
                detail={msg.detail}
                onRetry={onRetry}
                onFixSql={onFixSql}
                onOpenSettings={onOpenSettings}
              />
            );
          default:
            return null;
        }
      })}
      {suggestions && suggestions.length > 0 && finalResponse && (
        <div style={{ marginTop: 8 }}>
          <SuggestionChips
            suggestions={suggestions}
            onAsk={onAsk}
          />
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}

// ── Sub-components ──

function UserBubble({ message }: { message: string }) {
  return (
    <div className="chat-bubble chat-bubble-user">
      <div className="chat-bubble-text">{message}</div>
    </div>
  );
}

function AssistantBubble({ content }: { content: string }) {
  return (
    <div className="chat-bubble chat-bubble-assistant">
      <div className="chat-bubble-text">{content}</div>
    </div>
  );
}

function ArtifactBubble({
  artifact,
  isProd,
  onInsertSql,
  onRunSql,
  onExplainSql,
}: {
  artifact: AgentArtifact;
  isProd: boolean;
  onInsertSql?: (sql: string) => void;
  onRunSql?: (sql: string) => void;
  onExplainSql?: (sql: string) => void;
}) {
  const type = artifact.type;

  if (type === "sql" || type === "sql_suggestion") {
    const sql = typeof artifact.payload.sql === "string" ? artifact.payload.sql : "";
    if (!sql) return null;
    return (
      <div className="artifact-bubble">
        <SQLCard
          sql={sql}
          title={artifact.title || "SQL 查询建议"}
          isProd={isProd}
          onCopy={() => {}}
          onInsert={onInsertSql ? () => onInsertSql(sql) : undefined}
          onRun={onRunSql ? () => onRunSql(sql) : undefined}
          onExplain={onExplainSql ? () => onExplainSql(sql) : undefined}
        />
      </div>
    );
  }

  if (type === "table") {
    const rows = Array.isArray(artifact.payload.rows) ? artifact.payload.rows as Array<Record<string, unknown>> : [];
    const columns = Array.isArray(artifact.payload.columns) ? artifact.payload.columns as string[] : [];
    return (
      <div className="artifact-bubble">
        <div className="table-artifact-card">
          <div className="table-artifact-header">
            <FileCode size={12} />
            {artifact.title || "查询结果"}
            {artifact.payload.rowCount !== undefined && (
              <span className="table-artifact-count">{String(artifact.payload.rowCount)} 行</span>
            )}
          </div>
          {rows.length > 0 && (
            <div className="table-artifact-preview">
              <table className="data-table">
                <thead>
                  <tr>
                    {columns.slice(0, 6).map((col) => (
                      <th key={col}>{col}</th>
                    ))}
                    {columns.length > 6 && <th>…</th>}
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, 5).map((row, i) => (
                    <tr key={i}>
                      {columns.slice(0, 6).map((col) => (
                        <td key={col}>{formatCell(row[col])}</td>
                      ))}
                      {columns.length > 6 && <td>…</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
              {rows.length > 5 && (
                <div className="table-artifact-more">… 还有 {rows.length - 5} 行</div>
              )}
            </div>
          )}
        </div>
      </div>
    );
  }

  if (type === "error") {
    const errMsg = typeof artifact.payload.error === "string" ? artifact.payload.error : "Agent 执行出错";
    return (
      <div className="artifact-bubble">
        <ErrorBubble code="UNKNOWN" detail={errMsg} />
      </div>
    );
  }

  return null;
}

function ActivityBubble({
  label,
  steps,
  status,
  collapsed: initialCollapsed,
}: {
  label: string;
  steps: ActivityStepState[];
  status: "running" | "completed" | "failed";
  collapsed: boolean;
}) {
  const [expanded, setExpanded] = useState(!initialCollapsed);

  return (
    <div className={`activity-bubble activity-${status}`}>
      <button
        className="activity-toggle"
        onClick={() => setExpanded(!expanded)}
        type="button"
      >
        <span className="activity-indicator">
          {status === "running" && <span className="animate-spin" style={{ display: "inline-block", fontSize: 11 }}>↻</span>}
          {status === "completed" && <span style={{ color: "var(--accent-green)" }}>✓</span>}
          {status === "failed" && <span style={{ color: "var(--accent-red)" }}>✗</span>}
        </span>
        <span className="activity-label">
          {status === "running" ? label : "已完成"}
        </span>
        {steps.length > 0 && (
          <span className="activity-expand">
            {expanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
            <span style={{ fontSize: "0.6rem" }}>查看过程</span>
          </span>
        )}
      </button>
      {expanded && steps.length > 0 && (
        <div className="activity-steps">
          {steps.map((step) => (
            <div key={step.name} className={`activity-step activity-step-${step.status}`}>
              <span className="activity-step-indicator">
                {step.status === "running" ? "●" : step.status === "completed" ? "✓" : "✗"}
              </span>
              <span>{step.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ApprovalBubble({
  runId,
  approval,
  onResume,
  onReject,
}: {
  runId: string;
  approval?: AgentApproval | null;
  onResume?: (runId: string, approvalId: string) => void;
  onReject?: (runId: string, approvalId: string) => void;
}) {
  if (!approval) return null;
  const isPending = approval.status === "pending";
  const sql =
    (approval.requested_action as Record<string, unknown>)?.safe_sql as string ||
    (approval.requested_action as Record<string, unknown>)?.sql as string ||
    "";

  return (
    <div className="approval-bubble">
      <div className="approval-bubble-header">
        <strong>这个操作需要确认</strong>
        <span className="status-badge status-badge-neutral">{approval.risk_level}</span>
      </div>
      <div className="approval-bubble-reason">
        {approval.reason || "Agent 准备执行一个需要审批的操作。"}
      </div>
      {sql && <pre className="approval-bubble-sql"><code>{sql}</code></pre>}
      {isPending && (
        <div className="approval-bubble-actions">
          <button
            className="btn-primary"
            onClick={() => onResume?.(runId, approval.id)}
            style={{ fontSize: "0.68rem", padding: "3px 10px" }}
          >
            允许执行
          </button>
          <button
            className="btn-secondary"
            onClick={() => onReject?.(runId, approval.id)}
            style={{ fontSize: "0.68rem", padding: "3px 10px" }}
          >
            取消
          </button>
        </div>
      )}
    </div>
  );
}

function ErrorBubble({
  code,
  detail,
  onRetry,
  onFixSql,
  onOpenSettings,
}: {
  code: string;
  detail: string;
  onRetry?: () => void;
  onFixSql?: () => void;
  onOpenSettings?: () => void;
}) {
  return (
    <div className="artifact-bubble">
      <ErrorMessage
        code={code}
        detail={detail}
        onRetry={onRetry}
        onFixSql={onFixSql}
        onOpenSettings={onOpenSettings}
      />
    </div>
  );
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "NULL";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
