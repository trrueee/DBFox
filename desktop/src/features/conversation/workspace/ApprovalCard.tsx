import { approvalStatusPresentation, riskLevelLabel } from "../../../lib/presentation";
import type { ConversationApproval } from "../../../types/conversation";
import { useEffect, useRef } from "react";

interface ApprovalCardProps {
  runId: string;
  approval: ConversationApproval;
  onOpenSqlConsole: (sql?: string) => void;
  onResolve?: (runId: string, approvalId: string, approved: boolean) => void;
}

export function ApprovalCard({ runId, approval, onOpenSqlConsole, onResolve }: ApprovalCardProps) {
  const sql = approvalSql(approval);
  const approveButtonRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    approveButtonRef.current?.focus({ preventScroll: true });
  }, [approval.id]);
  return (
    <section className={`conv-approval-card conv-approval-${approval.risk_level}`} aria-label="需要批准" aria-live="polite">
      <div className="conv-approval-heading">
        <strong>需要你的批准</strong>
        <span>{riskLevelLabel(approval.risk_level)}</span>
      </div>
      {approval.reason && <p>{approval.reason}</p>}
      {sql && <pre>{sql}</pre>}
      <div className="conv-approval-actions">
        <button ref={approveButtonRef} type="button" onClick={() => onResolve?.(runId, approval.id, true)}>
          批准执行
        </button>
        <button type="button" onClick={() => onResolve?.(runId, approval.id, false)}>
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
    </section>
  );
}

export function ApprovalAuditCard({
  approval,
  onOpenSqlConsole,
}: Pick<ApprovalCardProps, "approval" | "onOpenSqlConsole">) {
  const sql = approvalSql(approval);
  return (
    <section
      className={`conv-approval-card conv-approval-audit conv-approval-${approval.status}`}
      aria-label="批准记录"
    >
      <div className="conv-approval-heading">
        <strong>{approvalStatusPresentation(approval.status).label}</strong>
        <span>{riskLevelLabel(approval.risk_level)}</span>
      </div>
      <div className="conv-approval-meta">
        {approval.decided_by && <span>处理人：{approval.decided_by}</span>}
        <span>批准时间：{formatApprovalTime(approval.decided_at)}</span>
      </div>
      {approval.decision_note && <p>{approval.decision_note}</p>}
      {approval.reason && <p>批准原因：{approval.reason}</p>}
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

function approvalSql(approval: ConversationApproval): string {
  const action = approval.requested_action;
  if (!action || typeof action !== "object") return "";
  if (typeof action.sql === "string") return action.sql;
  const args = action.arguments;
  if (args && typeof args === "object" && typeof (args as Record<string, unknown>).sql === "string") {
    return (args as Record<string, string>).sql;
  }
  return "";
}

function formatApprovalTime(value?: string | null): string {
  if (!value) return "时间未记录";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间未记录";
  return date.toLocaleString("zh-CN", { hour12: false });
}
