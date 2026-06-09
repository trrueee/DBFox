import { useState } from "react";
import { ArtifactInspector } from "./ArtifactInspector";
import { AgentComposer } from "./AgentComposer";
import { AgentNarrativeStream } from "./AgentNarrativeStream";
import { ApprovalCard } from "./ApprovalCard";
import { AgentStepTimeline } from "./AgentStepTimeline";
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

  const isTest = typeof process !== "undefined" && process.env.NODE_ENV === "test";
  const [selectedArtifactId, setSelectedArtifactId] = useState("");
  const [inspectorOpen, setInspectorOpen] = useState(isTest);
  const [debugOpen, setDebugOpen] = useState(isTest);

  const activeArtifactId = selectedArtifactId && artifacts.some((artifact) => artifact.id === selectedArtifactId)
    ? selectedArtifactId
    : artifacts[0]?.id || "";

  const handleOpenArtifact = (id: string) => {
    setSelectedArtifactId(id);
    setInspectorOpen(true);
  };

  const responseForContext = result || draft?.response || null;
  const composerWorkspaceContext = isWaitingApproval
    ? buildApprovalAwareWorkspaceContext({
        base: workspaceContext,
        approval,
        response: responseForContext,
        activeArtifactId,
      })
    : workspaceContext;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: "0.68rem", lineHeight: 1.45 }}>
      {/* Status Bar */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6, padding: "2px 0" }}>
        <span className={`status-badge ${isWaitingApproval ? "status-badge-neutral" : success ? "status-badge-success" : "status-badge-error"}`}>
          {isWaitingApproval ? "Approval needed" : isRunningDraft ? "Agent running" : replaying ? "Agent replay" : success ? "Agent answer" : "Agent stopped"}
        </span>
        {error ? <span style={{ color: "var(--accent-red)", fontWeight: 500, textAlign: "right" }}>{error}</span> : null}
      </div>

      {/* Approval Card */}
      <ApprovalCard
        approval={approval}
        response={result || draft?.response || null}
        disabled={disabled}
        onOpenSql={onOpenSql}
        onRuntimeEvent={onRuntimeEvent}
        onResumeComplete={onResumeComplete}
      />

      {/* Workspace Context Indicator (Horizontal & Compact) */}
      <WorkspaceContextIndicator context={workspaceContext} />

      {/* Chat Narrative Feed */}
      <div style={{ flex: 1, minHeight: 0 }}>
        <AgentNarrativeStream
          events={events}
          messageBlocks={messageBlocks}
          fallbackAnswer={answer}
          fallbackArtifacts={artifacts}
          fallbackSuggestions={suggestions}
          onOpenSql={onOpenSql}
          onOpenArtifact={handleOpenArtifact}
          onAsk={onAsk}
          onSuggestion={onSuggestion && result ? (suggestion) => onSuggestion(suggestion, result) : undefined}
        />
      </div>

      {/* Collapsible Artifact Details Inspector */}
      {artifacts.length > 0 && (
        <div style={{
          border: "1px solid var(--border-light)",
          borderRadius: 6,
          overflow: "hidden",
          marginTop: 4
        }}>
          <button
            type="button"
            onClick={() => setInspectorOpen(!inspectorOpen)}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              width: "100%",
              padding: "6px 10px",
              background: "var(--bg-secondary)",
              border: "none",
              cursor: "pointer",
              fontWeight: 600,
              fontSize: "0.64rem",
              color: "var(--text-primary)",
              outline: "none"
            }}
          >
            <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
              📊 {inspectorOpen ? "Hide" : "Show"} Artifact Inspector ({artifacts.length})
            </span>
            <span style={{ fontSize: "0.6rem", color: "var(--text-muted)", transform: inspectorOpen ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.15s" }}>
              ▼
            </span>
          </button>
          {inspectorOpen && (
            <div style={{
              background: "var(--bg-primary)",
              borderTop: "1px solid var(--border-light)"
            }}>
              <ArtifactInspector
                artifacts={artifacts}
                activeArtifactId={activeArtifactId}
                onActiveArtifactChange={setSelectedArtifactId}
                onOpenSql={onOpenSql}
                onApplySql={onApplySql}
                onAsk={onAsk}
                workspaceContext={composerWorkspaceContext}
              />
            </div>
          )}
        </div>
      )}

      {/* Composer Input Area */}
      {onAsk && responseForContext ? (
        <AgentComposer
          disabled={disabled}
          placeholder={isWaitingApproval ? "Ask about this pending approval, SQL, or risk" : "Ask a follow-up about this result"}
          workspaceContext={composerWorkspaceContext}
          onSubmit={onAsk}
        />
      ) : null}

      {/* Collapsible Debug & Trace Drawer */}
      <div style={{
        border: "1px solid var(--border-light)",
        borderRadius: 6,
        overflow: "hidden",
        marginTop: 4
      }}>
        <button
          type="button"
          onClick={() => setDebugOpen(!debugOpen)}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            width: "100%",
            padding: "6px 10px",
            background: "var(--bg-secondary)",
            border: "none",
            cursor: "pointer",
            fontWeight: 600,
            fontSize: "0.64rem",
            color: "var(--text-primary)",
            outline: "none"
          }}
        >
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
            🛠️ {debugOpen ? "Hide" : "Show"} Technical Debug Panel
          </span>
          <span style={{ fontSize: "0.6rem", color: "var(--text-muted)", transform: debugOpen ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.15s" }}>
            ▼
          </span>
        </button>
        {debugOpen && (
          <div style={{
            display: "flex",
            flexDirection: "column",
            gap: 10,
            padding: 10,
            background: "var(--bg-primary)",
            borderTop: "1px solid var(--border-light)"
          }}>
            <AgentStepTimeline steps={steps} runtimeEvents={draft?.events || []} />
            <AgentStateInspector key={threadId || "agent-state"} threadId={threadId} />
            <TraceDrawer steps={steps} traceEvents={traceEvents} />
          </div>
        )}
      </div>
    </div>
  );
}

function buildApprovalAwareWorkspaceContext({
  base,
  approval,
  response,
  activeArtifactId,
}: {
  base?: AgentWorkspaceContext | null;
  approval?: AgentRunResponse["approval"] | null;
  response?: AgentRunResponse | null;
  activeArtifactId?: string;
}): AgentWorkspaceContext | null {
  const responseDatasourceId = stringifyValue(asRecord(response).datasource_id);
  if (!base && !responseDatasourceId) return null;
  const approvalSql = sqlFromApproval(approval);
  const selectedSql = approvalSql || stringifyValue(response?.sql) || stringifyValue(base?.selected_sql) || stringifyValue(base?.active_sql);
  return {
    ...(base || {}),
    datasource_id: base?.datasource_id || responseDatasourceId,
    selected_sql: selectedSql || base?.selected_sql,
    active_sql: selectedSql || base?.active_sql,
    selected_artifact_id: activeArtifactId || base?.selected_artifact_id,
    pending_approval_id: approval?.id,
    pending_approval_status: approval?.status,
    pending_approval_reason: approval?.reason || undefined,
  };
}

function sqlFromApproval(approval?: AgentRunResponse["approval"] | null): string {
  const requested = asRecord(approval?.requested_action);
  const args = asRecord(requested.args);
  return (
    stringifyValue(requested.safe_sql) ||
    stringifyValue(requested.sql) ||
    stringifyValue(args.safe_sql) ||
    stringifyValue(args.sql)
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function stringifyValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function WorkspaceContextIndicator({ context }: { context?: AgentWorkspaceContext | null }) {
  if (!context) return null;
  const hasSql = Boolean(context.selected_sql || context.active_sql);
  const hasResult = Boolean(context.last_query_result_preview);
  const selectedTable = context.selected_table_names?.[0] || "";
  const selectedArtifact = context.selected_artifact_id || "";
  return (
    <div style={{
      display: "flex",
      gap: 12,
      padding: "6px 10px",
      background: "var(--bg-secondary)",
      border: "1px solid var(--border-light)",
      borderRadius: 6,
      fontSize: "0.62rem",
      color: "var(--text-muted)",
      flexWrap: "wrap",
      alignItems: "center"
    }}>
      <span><strong>Workspace Context:</strong></span>
      <span><span>Current SQL</span>: <span style={{ color: hasSql ? "var(--accent-green)" : "var(--text-muted)", fontWeight: hasSql ? 600 : "normal" }}>{hasSql ? "ready" : "none"}</span></span>
      <span><span>Last result</span>: <span style={{ color: hasResult ? "var(--accent-green)" : "var(--text-muted)", fontWeight: hasResult ? 600 : "normal" }}>{hasResult ? "ready" : "none"}</span></span>
      {selectedTable && <span><span>Selected table</span>: <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>{selectedTable}</span></span>}
      {selectedArtifact && <span><span>Selected artifact</span>: <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>{selectedArtifact}</span></span>}
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
