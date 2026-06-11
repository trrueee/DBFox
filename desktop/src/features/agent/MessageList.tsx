import { useRef, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, FileCode } from "lucide-react";
import { SQLCard } from "./SQLCard";
import { ErrorMessage } from "./ErrorMessage";
import { SuggestionChips } from "./SuggestionChips";
import { Button } from "../../components/ui/button";
import { Badge } from "../../components/ui/badge";
import { Separator } from "../../components/ui/separator";
import { AgentTaskLensPanel } from "./AgentTaskLens";
import type { ChatMessage, ActivityStepState } from "./useAgentChat";
import type { AgentTaskLens } from "../../lib/api";
import type { AgentArtifact, AgentApproval, FollowUpSuggestion, AgentRunResponse } from "../../lib/api";

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
  messages, finalResponse, approval, suggestions, isProd = false,
  onInsertSql, onRunSql, onExplainSql, onRetry, onFixSql,
  onOpenSettings, onAsk, onResumeApproval, onRejectApproval,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (!messages.length) return null;

  return (
    <div className="flex flex-col gap-2 px-3 py-2 flex-1">
      {messages.map((msg) => {
        switch (msg.role) {
          case "user":
            return <UserBubble key={msg.id} message={msg.question} />;
          case "assistant":
            return <AssistantBubble key={msg.id} content={msg.content} />;
          case "artifact":
            return (
              <ArtifactBubble key={msg.id} artifact={msg.artifact} isProd={isProd}
                onInsertSql={onInsertSql} onRunSql={onRunSql} onExplainSql={onExplainSql} />
            );
          case "activity":
            return (
              <ActivityBubble
                key={msg.id}
                label={msg.label}
                steps={msg.steps}
                status={msg.status}
                collapsed={msg.collapsed}
                contextSummary={msg.contextSummary}
                taskLens={msg.taskLens}
                repairMode={msg.repairMode}
              />
            );
          case "approval":
            return <ApprovalBubble key={msg.id} runId={msg.runId} approval={approval}
              onResume={onResumeApproval} onReject={onRejectApproval} />;
          case "error":
            return <ErrorBubble key={msg.id} code={msg.code} detail={msg.detail}
              onRetry={onRetry} onFixSql={onFixSql} onOpenSettings={onOpenSettings} />;
          default:
            return null;
        }
      })}
      {suggestions && suggestions.length > 0 && finalResponse && (
        <div className="mt-2"><SuggestionChips suggestions={suggestions} onAsk={onAsk} /></div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}

// ── User Bubble ──
function UserBubble({ message }: { message: string }) {
  return (
    <div className="self-end max-w-[88%] px-3 py-1.5 rounded-md bg-[hsl(var(--primary)/0.12)] text-[hsl(var(--foreground))] border border-[hsl(var(--border))] text-[0.76rem] leading-relaxed whitespace-pre-wrap break-words">
      {message}
    </div>
  );
}

// ── Assistant Bubble ──
function AssistantBubble({ content }: { content: string }) {
  return (
    <div className="self-start max-w-[95%] py-1 text-[0.76rem] leading-relaxed text-[hsl(var(--foreground))] whitespace-pre-wrap break-words">
      {content}
    </div>
  );
}

// ── Artifact Bubble ──
function ArtifactBubble({
  artifact, isProd, onInsertSql, onRunSql, onExplainSql,
}: {
  artifact: AgentArtifact; isProd: boolean;
  onInsertSql?: (sql: string) => void;
  onRunSql?: (sql: string) => void;
  onExplainSql?: (sql: string) => void;
}) {
  const type = artifact.type;

  if (type === "sql" || type === "sql_suggestion") {
    const sql = typeof artifact.payload.sql === "string" ? artifact.payload.sql : "";
    if (!sql) return null;
    return (
      <div className="max-w-full">
        <SQLCard sql={sql} title={artifact.title || "SQL 查询建议"} isProd={isProd}
          onCopy={() => {}} onInsert={onInsertSql ? () => onInsertSql(sql) : undefined}
          onRun={onRunSql ? () => onRunSql(sql) : undefined}
          onExplain={onExplainSql ? () => onExplainSql(sql) : undefined} />
      </div>
    );
  }

  if (type === "table") {
    const rows = Array.isArray(artifact.payload.rows) ? artifact.payload.rows as Array<Record<string, unknown>> : [];
    const columns = Array.isArray(artifact.payload.columns) ? artifact.payload.columns as string[] : [];
    return (
      <div className="max-w-full">
        <div className="rounded border border-[hsl(var(--border))] bg-[hsl(var(--card))] overflow-hidden">
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-[hsl(var(--secondary))] border-b text-[0.68rem] font-semibold text-[hsl(var(--muted-foreground))]">
            <FileCode size={12} />
            {artifact.title || "查询结果"}
            {artifact.payload.rowCount !== undefined && (
              <span className="ml-auto text-[0.62rem] text-[hsl(var(--muted-foreground))] font-normal">{String(artifact.payload.rowCount)} 行</span>
            )}
          </div>
          {rows.length > 0 && (
            <div className="overflow-x-auto max-h-[180px] overflow-y-auto">
              <table className="w-full text-[0.7rem] border-collapse font-mono tabular-nums">
                <thead>
                  <tr>
                    {columns.slice(0, 6).map((col) => (
                      <th key={col} className="sticky top-0 px-2.5 py-1 text-left font-semibold text-[0.66rem] text-[hsl(var(--muted-foreground))] bg-[hsl(var(--secondary))] border-b whitespace-nowrap">{col}</th>
                    ))}
                    {columns.length > 6 && <th className="sticky top-0 px-2.5 py-1 bg-[hsl(var(--secondary))] border-b">…</th>}
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, 5).map((row, i) => (
                    <tr key={i} className="hover:bg-[hsl(var(--accent)/0.5)]">
                      {columns.slice(0, 6).map((col) => (
                        <td key={col} className="px-2.5 py-1 border-b border-[hsl(var(--border))] text-[hsl(var(--foreground))]">{formatCell(row[col])}</td>
                      ))}
                      {columns.length > 6 && <td className="px-2.5 py-1 border-b">…</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
              {rows.length > 5 && (
                <div className="px-3 py-1 text-[0.62rem] text-[hsl(var(--muted-foreground))] text-center border-t">… 还有 {rows.length - 5} 行</div>
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
      <div className="max-w-full">
        <ErrorBubble code="UNKNOWN" detail={errMsg} />
      </div>
    );
  }

  return null;
}

// ── Activity Bubble ──
function ActivityBubble({
  label, steps, status, collapsed: initialCollapsed, contextSummary, taskLens, repairMode,
}: {
  label: string; steps: ActivityStepState[];
  status: "running" | "completed" | "failed"; collapsed: boolean;
  contextSummary?: string | null; taskLens?: AgentTaskLens | null; repairMode?: boolean;
}) {
  const [expanded, setExpanded] = useState(!initialCollapsed);

  return (
    <div className="py-1">
      <button
        className="flex items-center gap-1.5 w-full text-left border-none bg-transparent cursor-pointer py-0.5 text-[0.7rem] text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] font-sans"
        onClick={() => setExpanded(!expanded)}
        type="button"
      >
        <span className="w-4 text-center shrink-0 text-[0.65rem]">
          {status === "running" && <span className="inline-block animate-spin">↻</span>}
          {status === "completed" && <span className="text-[hsl(var(--success))]">✓</span>}
          {status === "failed" && <span className="text-[hsl(var(--destructive))]">✗</span>}
        </span>
        <span className="font-medium">{status === "running" ? label : "已完成"}</span>
        {repairMode && status === "running" && (
          <Badge variant="outline" className="text-[0.58rem] py-0 px-1 h-4">SQL repair</Badge>
        )}
        {steps.length > 0 && (
          <span className="ml-auto flex items-center gap-1 text-[0.6rem] text-[hsl(var(--muted-foreground))]">
            {expanded ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
            查看过程
          </span>
        )}
      </button>
      {status === "running" && taskLens ? (
        <div className="mt-0.5 ml-[22px]">
          <AgentTaskLensPanel taskLens={taskLens} compact />
        </div>
      ) : null}
      {contextSummary && status === "running" && !taskLens?.current_focus && (
        <div className="mt-0.5 ml-[22px] text-[0.62rem] text-[hsl(var(--muted-foreground))] leading-snug">
          {contextSummary}
        </div>
      )}
      {expanded && steps.length > 0 && (
        <div className="mt-1 ml-[22px] flex flex-col gap-0.5">
          {steps.map((step) => (
            <div key={step.name} className="flex items-center gap-1.5 text-[0.66rem] text-[hsl(var(--muted-foreground))]">
              <span className={`w-3.5 text-center text-[0.58rem] ${
                step.status === "completed" ? "text-[hsl(var(--success))]" :
                step.status === "running" ? "text-[hsl(var(--primary))]" :
                "text-[hsl(var(--destructive))]"
              }`}>
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

// ── Approval Bubble ──
function ApprovalBubble({
  runId, approval, onResume, onReject,
}: {
  runId: string; approval?: AgentApproval | null;
  onResume?: (runId: string, approvalId: string) => void;
  onReject?: (runId: string, approvalId: string) => void;
}) {
  if (!approval) return null;
  const isPending = approval.status === "pending";
  const sql = (approval.requested_action as Record<string, unknown>)?.safe_sql as string
    || (approval.requested_action as Record<string, unknown>)?.sql as string || "";

  return (
    <div className="rounded border border-[hsl(var(--border))] bg-[hsl(var(--secondary))] p-2.5">
      <div className="flex items-center justify-between gap-2">
        <strong className="text-[0.72rem]">这个操作需要确认</strong>
        <Badge variant="secondary">{approval.risk_level}</Badge>
      </div>
      <div className="mt-1 text-[0.68rem] text-[hsl(var(--muted-foreground))]">
        {approval.reason || "Agent 准备执行一个需要审批的操作。"}
      </div>
      {sql && <pre className="mt-1.5 p-1.5 rounded border border-[hsl(var(--border))] bg-[hsl(var(--card))] font-mono text-[0.68rem] whitespace-pre-wrap overflow-x-auto text-[hsl(var(--foreground))]"><code>{sql}</code></pre>}
      {isPending && (
        <div className="flex gap-2 mt-2">
          <Button size="sm" onClick={() => onResume?.(runId, approval.id)} className="text-[0.7rem]">允许执行</Button>
          <Button variant="outline" size="sm" onClick={() => onReject?.(runId, approval.id)} className="text-[0.7rem]">取消</Button>
        </div>
      )}
    </div>
  );
}

// ── Error Bubble ──
function ErrorBubble({
  code, detail, onRetry, onFixSql, onOpenSettings,
}: {
  code: string; detail: string;
  onRetry?: () => void; onFixSql?: () => void; onOpenSettings?: () => void;
}) {
  return (
    <div className="max-w-full">
      <ErrorMessage code={code} detail={detail} onRetry={onRetry} onFixSql={onFixSql} onOpenSettings={onOpenSettings} />
    </div>
  );
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "NULL";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
