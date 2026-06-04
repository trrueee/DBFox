import { useState } from "react";
import { ArtifactInspector } from "./ArtifactInspector";
import { AgentComposer } from "./AgentComposer";
import { AgentNarrativeStream } from "./AgentNarrativeStream";
import { ApprovalCard } from "./ApprovalCard";
import { AgentStateInspector } from "./AgentStateInspector";
import { TraceDrawer } from "./TraceDrawer";
import type { AgentRunDraftState, AgentRunResponse, AgentRuntimeEvent, AgentStep, AgentVisibleEvent, AgentWorkspaceContext, FollowUpSuggestion } from "./types";

interface AgentWorkspaceProps {
  result?: AgentRunResponse | null;
  draft?: AgentRunDraftState | null;
  disabled?: boolean;
  replaying?: boolean;
  workspaceContext?: AgentWorkspaceContext | null;
  onOpenSql?: (sql: string) => void;
  onApplySql?: (sql: string) => void;
  onAsk?: (question: string, workspaceContext?: AgentWorkspaceContext | null) => void;
  onSuggestion?: (suggestion: FollowUpSuggestion, result: AgentRunResponse) => void;
  onRuntimeEvent?: (event: AgentRuntimeEvent) => void;
  onResumeComplete?: (response: AgentRunResponse) => void;
}

export function AgentWorkspace({
  result,
  draft,
  disabled,
  replaying,
  workspaceContext,
  onOpenSql,
  onApplySql,
  onAsk,
  onSuggestion,
  onRuntimeEvent,
  onResumeComplete,
}: AgentWorkspaceProps) {
  const isRunningDraft = Boolean(draft && draft.status === "running" && !result);
  const isWaitingApproval = result?.status === "waiting_approval" || draft?.status === "waiting_approval";
  const artifacts = result?.artifacts || draft?.artifacts || [];
  const events = result?.events || draftVisibleEvents(draft);
  const messageBlocks = result?.message_blocks || [];
  const suggestions = result?.suggestions || [];
  const steps = result?.steps || draftSteps(draft);
  const traceEvents = result?.trace_events || [];
  const success = result ? result.success || result.status === "waiting_approval" : draft?.status !== "failed";
  const error = result?.error || draft?.error || null;
  const answer = result?.answer || draft?.answer || null;
  const approval = result?.approval || draft?.approval || null;
  const threadId = result?.session_id || draft?.response?.session_id || null;
  const [selectedArtifactId, setSelectedArtifactId] = useState("");
  const activeArtifactId = selectedArtifactId && artifacts.some((artifact) => artifact.id === selectedArtifactId)
    ? selectedArtifactId
    : artifacts[0]?.id || "";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: "0.68rem", lineHeight: 1.45 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6 }}>
        <span className={`status-badge ${isWaitingApproval ? "status-badge-neutral" : success ? "status-badge-success" : "status-badge-error"}`}>
          {isWaitingApproval ? "Approval needed" : isRunningDraft ? "Agent running" : replaying ? "Agent replay" : success ? "Agent answer" : "Agent stopped"}
        </span>
        {error ? <span style={{ color: "var(--accent-red)", textAlign: "right" }}>{error}</span> : null}
      </div>

      <ApprovalCard
        approval={approval}
        response={result || draft?.response || null}
        disabled={disabled}
        onOpenSql={onOpenSql}
        onRuntimeEvent={onRuntimeEvent}
        onResumeComplete={onResumeComplete}
      />

      <WorkspaceContextIndicator context={workspaceContext} />

      <AgentStateInspector key={threadId || "agent-state"} threadId={threadId} />

      <AgentNarrativeStream
        events={events}
        messageBlocks={messageBlocks}
        fallbackAnswer={answer}
        fallbackArtifacts={artifacts}
        fallbackSuggestions={suggestions}
        onOpenSql={onOpenSql}
        onOpenArtifact={setSelectedArtifactId}
        onAsk={onAsk}
        onSuggestion={onSuggestion && result ? (suggestion) => onSuggestion(suggestion, result) : undefined}
      />

      <ArtifactInspector
        artifacts={artifacts}
        activeArtifactId={activeArtifactId}
        onActiveArtifactChange={setSelectedArtifactId}
        onOpenSql={onOpenSql}
        onApplySql={onApplySql}
      />
      {onAsk && result && !isWaitingApproval ? (
        <AgentComposer
          disabled={disabled}
          placeholder="Ask a follow-up about this result"
          workspaceContext={workspaceContext}
          onSubmit={onAsk}
        />
      ) : null}
      <TraceDrawer steps={steps} traceEvents={traceEvents} />
    </div>
  );
}

function WorkspaceContextIndicator({ context }: { context?: AgentWorkspaceContext | null }) {
  if (!context) return null;
  const hasSql = Boolean(context.selected_sql || context.active_sql);
  const hasResult = Boolean(context.last_query_result_preview);
  const selectedTable = context.selected_table_names?.[0] || "";
  const selectedArtifact = context.selected_artifact_id || "";
  return (
    <section style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4, padding: 7, background: "var(--bg-secondary)" }}>
      <ContextChip label="Current SQL" value={hasSql ? "ready" : "none"} active={hasSql} />
      <ContextChip label="Last result" value={hasResult ? "ready" : "none"} active={hasResult} />
      <ContextChip label="Selected table" value={selectedTable || "none"} active={Boolean(selectedTable)} />
      <ContextChip label="Selected artifact" value={selectedArtifact ? "ready" : "none"} active={Boolean(selectedArtifact)} />
    </section>
  );
}

function ContextChip({ label, value, active }: { label: string; value: string; active: boolean }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ color: "var(--text-muted)", fontSize: "0.58rem", fontWeight: 700 }}>{label}</div>
      <div
        style={{
          color: active ? "var(--text-primary)" : "var(--text-muted)",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
        title={value}
      >
        {value}
      </div>
    </div>
  );
}

function draftVisibleEvents(draft?: AgentRunDraftState | null): AgentVisibleEvent[] {
  if (!draft) return [];
  return draft.events.flatMap((event): AgentVisibleEvent[] => {
    if (event.type === "agent.artifact.created" && event.artifact) {
      return [{ type: "agent.artifact.created", artifact: event.artifact }];
    }
    if (event.type === "agent.answer.completed" && event.answer) {
      return [{ type: "agent.answer.completed", answer: event.answer }];
    }
    return [];
  });
}

function draftSteps(draft?: AgentRunDraftState | null): AgentStep[] {
  if (!draft) return [];
  return draft.events
    .filter((event) => event.type === "agent.step.completed" && event.step?.name)
    .map((event) => ({
      name: String(event.step?.name || ""),
      status: event.step?.status === "failed" || event.step?.status === "skipped" ? event.step.status : "success",
      error: typeof event.step?.error === "string" ? event.step.error : null,
      latency_ms: typeof event.step?.latency_ms === "number" ? event.step.latency_ms : 0,
    }));
}
