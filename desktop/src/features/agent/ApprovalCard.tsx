import { useState } from "react";
import { api } from "../../lib/api";
import type { AgentApproval, AgentRunResponse, AgentRuntimeEvent } from "./types";

interface ApprovalCardProps {
  approval?: AgentApproval | null;
  response?: AgentRunResponse | null;
  disabled?: boolean;
  onOpenSql?: (sql: string) => void;
  onRuntimeEvent?: (event: AgentRuntimeEvent) => void;
  onResumeComplete?: (response: AgentRunResponse) => void;
}

export function ApprovalCard({
  approval,
  response,
  disabled,
  onOpenSql,
  onRuntimeEvent,
  onResumeComplete,
}: ApprovalCardProps) {
  const [resolvedApproval, setResolvedApproval] = useState<AgentApproval | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const currentApproval = resolvedApproval && (!approval || resolvedApproval.id === approval.id)
    ? resolvedApproval
    : approval || null;

  if (!currentApproval) return null;

  const policy = currentApproval.policy_decision || {};
  const requested = currentApproval.requested_action || {};
  const sql = stringifyValue(requested.safe_sql) || stringifyValue(requested.sql) || response?.sql || "";
  const messages = listOfStrings(policy.messages);
  const blockedReasons = listOfStrings(policy.blocked_reasons);
  const isPending = currentApproval.status === "pending";

  const resolve = async (decision: "approved" | "rejected") => {
    setBusy(true);
    setError(null);
    try {
      if (decision === "approved") {
        const resumed = await api.streamResumeAgentRun(currentApproval.run_id, currentApproval.id, {
          onEvent: onRuntimeEvent,
          note: "Reviewed in DataBox Agent UI.",
        });
        setResolvedApproval(resumed.approval || { ...currentApproval, status: "approved" });
        onResumeComplete?.(resumed);
      } else {
        const rejected = await api.rejectAgentApproval(
          currentApproval.run_id,
          currentApproval.id,
          "Rejected in DataBox Agent UI.",
        );
        setResolvedApproval(rejected.approval || { ...currentApproval, status: "rejected" });
        onResumeComplete?.(rejected);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Approval action failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section style={{ padding: 8, background: "var(--bg-secondary)", border: "1px solid var(--border-light)", borderRadius: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <div>
          <strong>Approval required</strong>
          <div style={{ marginTop: 3, color: "var(--text-muted)" }}>
            {currentApproval.reason || "Manual review is required before execution."}
          </div>
        </div>
        <span className={`status-badge ${statusClass(currentApproval.status)}`}>
          {currentApproval.status}
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "86px 1fr", gap: 4, marginTop: 8 }}>
        <span style={{ color: "var(--text-muted)" }}>Risk</span>
        <span>{currentApproval.risk_level}</span>
        <span style={{ color: "var(--text-muted)" }}>Step</span>
        <span>{currentApproval.step_name} → execute_sql</span>
        <span style={{ color: "var(--text-muted)" }}>Blocked</span>
        <span>{blockedReasons.length ? blockedReasons.join(", ") : "-"}</span>
      </div>

      {messages.length ? (
        <div style={{ marginTop: 8 }}>
          <strong style={{ fontSize: "0.64rem" }}>TrustGate messages</strong>
          <ul style={{ margin: "4px 0 0", paddingLeft: 16 }}>
            {messages.map((message) => <li key={message}>{message}</li>)}
          </ul>
        </div>
      ) : null}

      {expanded ? (
        <pre style={{ whiteSpace: "pre-wrap", fontFamily: "var(--font-mono)", fontSize: "0.64rem", background: "#fff", padding: 6, margin: "8px 0 0", overflowX: "auto" }}>
          {sql || "-"}
        </pre>
      ) : null}

      {error ? <div style={{ color: "var(--accent-red)", marginTop: 7 }}>{error}</div> : null}

      <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
        {isPending ? (
          <>
            <button className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold bg-primary text-primary-foreground rounded-sm cursor-pointer border-none hover:brightness-110 transition-colors" disabled={disabled || busy} onClick={() => void resolve("approved")}>
              {busy ? "Resuming..." : "Approve execute"}
            </button>
            <button className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border bg-transparent rounded-sm cursor-pointer hover:bg-accent text-foreground transition-colors" disabled={disabled || busy} onClick={() => void resolve("rejected")}>
              Reject
            </button>
          </>
        ) : (
          <span style={{ color: "var(--text-muted)" }}>
            {resolvedApprovalMessage(currentApproval.status)}
          </span>
        )}
        <button className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-muted-foreground bg-transparent border border-border rounded-sm cursor-pointer hover:bg-accent hover:text-foreground transition-colors" type="button" onClick={() => setExpanded((value) => !value)}>
          {expanded ? "Hide SQL" : "View SQL"}
        </button>
        {sql && onOpenSql ? (
          <button className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-muted-foreground bg-transparent border border-border rounded-sm cursor-pointer hover:bg-accent hover:text-foreground transition-colors" type="button" onClick={() => onOpenSql(sql)}>
            Open SQL
          </button>
        ) : null}
      </div>
    </section>
  );
}

function stringifyValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function listOfStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function statusClass(status: AgentApproval["status"]): string {
  if (status === "approved") return "status-badge-success";
  if (status === "rejected" || status === "expired") return "status-badge-error";
  return "status-badge-neutral";
}

function resolvedApprovalMessage(status: AgentApproval["status"]): string {
  if (status === "approved") return "Approval resolved. Resume is in progress or completed.";
  if (status === "expired") return "Approval expired because SQL was revised.";
  return "Approval rejected.";
}
