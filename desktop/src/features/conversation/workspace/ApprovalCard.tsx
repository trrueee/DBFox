import { useEffect, useRef } from "react";
import { riskLevelLabel } from "../../../lib/presentation";
import type { ApprovalItem } from "../../../types/conversation";

interface ApprovalCardProps {
  approval: ApprovalItem;
  onOpenSqlConsole: (sql?: string) => void;
  submitting?: boolean;
  error?: string | null;
  onResolve?: (runId: string, approvalId: string, approved: boolean) => Promise<void> | void;
}

export function ApprovalCard({
  approval,
  onOpenSqlConsole,
  submitting = false,
  error,
  onResolve,
}: ApprovalCardProps) {
  const sql = approvalSql(approval);
  const approveButtonRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    approveButtonRef.current?.focus({ preventScroll: true });
  }, [approval.id]);
  return (
    <section
      className={`conv-approval-card conv-approval-${approval.payload.risk_level}`}
      aria-label="需要批准"
      aria-live="polite"
    >
      <div className="conv-approval-heading">
        <strong>需要你的批准</strong>
        <span>{riskLevelLabel(approval.payload.risk_level)}</span>
      </div>
      {approval.payload.reason && <p>{approval.payload.reason}</p>}
      {sql && <pre>{sql}</pre>}
      <div className="conv-approval-actions">
        <button
          ref={approveButtonRef}
          type="button"
          disabled={submitting}
          onClick={() => void Promise.resolve(
            onResolve?.(approval.run_id, approval.id, true),
          ).catch(() => undefined)}
        >
          {submitting ? "正在提交…" : "批准执行"}
        </button>
        <button
          type="button"
          disabled={submitting}
          onClick={() => void Promise.resolve(
            onResolve?.(approval.run_id, approval.id, false),
          ).catch(() => undefined)}
        >
          拒绝
        </button>
        {sql && (
          <>
            <button type="button" onClick={() => void navigator.clipboard?.writeText(sql)}>
              复制 SQL
            </button>
            <button type="button" onClick={() => onOpenSqlConsole(sql)}>
              在 SQL 工作台查看
            </button>
          </>
        )}
      </div>
      {error && <p className="conv-action-error" role="alert">{error}</p>}
    </section>
  );
}

export function ApprovalAuditCard({
  approval,
  onOpenSqlConsole,
}: Pick<ApprovalCardProps, "approval" | "onOpenSqlConsole">) {
  const sql = approvalSql(approval);
  const approved = approval.payload.decision === "approved";
  return (
    <section
      className={`conv-approval-card conv-approval-audit conv-approval-${approval.status}`}
      aria-label="批准记录"
    >
      <div className="conv-approval-heading">
        <strong>{approved ? "已批准" : "已拒绝"}</strong>
        <span>{riskLevelLabel(approval.payload.risk_level)}</span>
      </div>
      {approval.payload.decision_note && <p>{approval.payload.decision_note}</p>}
      {approval.payload.reason && <p>审批原因：{approval.payload.reason}</p>}
      {sql && <pre>{sql}</pre>}
      {sql && (
        <div className="conv-approval-actions">
          <button type="button" onClick={() => void navigator.clipboard?.writeText(sql)}>
            复制 SQL
          </button>
          <button type="button" onClick={() => onOpenSqlConsole(sql)}>
            在 SQL 工作台查看
          </button>
        </div>
      )}
    </section>
  );
}

function approvalSql(approval: ApprovalItem): string {
  const action = approval.payload.requested_action;
  if (typeof action.sql === "string") return action.sql;
  const args = action.arguments;
  if (args && typeof args === "object" && typeof (args as Record<string, unknown>).sql === "string") {
    return String((args as Record<string, unknown>).sql);
  }
  return "";
}
