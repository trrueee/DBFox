import { useEffect, useRef } from "react";
import {
  Check,
  CircleOff,
  Clipboard,
  Clock3,
  ExternalLink,
  LoaderCircle,
  ShieldAlert,
  TriangleAlert,
  X,
} from "lucide-react";

import {
  Confirmation,
  ConfirmationAccepted,
  ConfirmationAction,
  ConfirmationActions,
  ConfirmationRejected,
  ConfirmationRequest,
  ConfirmationTitle,
} from "../../../components/ai-elements/confirmation";
import { Button } from "../../../components/ui/button";
import { ErrorDetails } from "../../../components/ui/error-details";
import { getUserErrorMessage } from "../../../lib/api/client";
import { riskLevelLabel } from "../../../lib/presentation";
import type { ApprovalItem } from "../../../types/conversation";

interface ApprovalCardProps {
  approval: ApprovalItem;
  onOpenSqlConsole?: (sql?: string) => void;
  submitting?: boolean;
  error?: unknown;
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
  const operation = approvalOperation(approval);
  const safeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    safeButtonRef.current?.focus({ preventScroll: true });
  }, [approval.id]);

  return (
    <Confirmation
      state="approval-requested"
      variant={approval.payload.risk_level === "danger" ? "destructive" : "default"}
      className="gap-3 border-[var(--agent-border)] bg-[var(--agent-surface-elevated)]"
      aria-label="需要批准"
      aria-live="polite"
      aria-busy={submitting || undefined}
      data-risk={approval.payload.risk_level}
    >
      <ShieldAlert aria-hidden="true" />
      <ConfirmationRequest>
        <div className="col-start-2 grid gap-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <strong className="text-sm font-medium text-[var(--agent-text)]">需要你的批准</strong>
            <span className="text-xs text-[var(--agent-text-muted)]">{riskLevelLabel(approval.payload.risk_level)}</span>
          </div>
          {approval.payload.reason ? <ConfirmationTitle>{approval.payload.reason}</ConfirmationTitle> : null}
          <ApprovalOperation operation={operation} sql={sql} />
        </div>
      </ConfirmationRequest>
      <ConfirmationActions className="col-start-2 w-full justify-between">
        <SqlActions sql={sql} onOpenSqlConsole={onOpenSqlConsole} />
        <div className="flex gap-2">
          <ConfirmationAction
            ref={safeButtonRef}
            variant="outline"
            disabled={submitting}
            onClick={() => void Promise.resolve(onResolve?.(approval.run_id, approval.id, false)).catch(() => undefined)}
          >
            拒绝
          </ConfirmationAction>
          <ConfirmationAction
            variant={approval.payload.risk_level === "danger" ? "destructive" : "default"}
            disabled={submitting}
            onClick={() => void Promise.resolve(onResolve?.(approval.run_id, approval.id, true)).catch(() => undefined)}
          >
            {submitting ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : null}
            {submitting ? "正在提交…" : "批准执行"}
          </ConfirmationAction>
        </div>
      </ConfirmationActions>
      {error ? (
        <div className="col-start-2 grid gap-1 text-sm text-[var(--color-danger)]">
          <p className="m-0">
            {typeof error === "string" ? error : getUserErrorMessage(error, "审批提交失败，请重试。")}
          </p>
          <ErrorDetails error={error} />
        </div>
      ) : null}
    </Confirmation>
  );
}

export function ApprovalAuditCard({
  approval,
  onOpenSqlConsole,
}: Pick<ApprovalCardProps, "approval" | "onOpenSqlConsole">) {
  const sql = approvalSql(approval);
  const operation = approvalOperation(approval);
  const outcome = approvalOutcome(approval);
  const approved = outcome === "approved" ? true : outcome === "rejected" ? false : undefined;
  const title = approvalOutcomeTitle(outcome);

  return (
    <Confirmation
      state={approved === false ? "output-denied" : "approval-responded"}
      approved={approved}
      role="status"
      aria-label="批准记录"
      className="my-2 gap-2 border-[var(--agent-border)] bg-[var(--agent-surface)]"
      data-status={outcome}
    >
      <ApprovalOutcomeIcon outcome={outcome} />
      {outcome === "approved" ? (
        <ConfirmationAccepted>
          <ApprovalDecision title={title} approval={approval} operation={operation} sql={sql} />
        </ConfirmationAccepted>
      ) : outcome === "rejected" ? (
        <ConfirmationRejected>
          <ApprovalDecision title={title} approval={approval} operation={operation} sql={sql} />
        </ConfirmationRejected>
      ) : (
        <ApprovalDecision
          title={title}
          message={approvalOutcomeMessage(outcome)}
          approval={approval}
          operation={operation}
          sql={sql}
        />
      )}
      <SqlActions sql={sql} onOpenSqlConsole={onOpenSqlConsole} className="col-start-2" />
    </Confirmation>
  );
}

function ApprovalDecision({ title, message, approval, operation, sql }: {
  title: string;
  message?: string;
  approval: ApprovalItem;
  operation: string;
  sql: string;
}) {
  return (
    <div className="col-start-2 grid gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <strong className="text-sm font-medium text-[var(--agent-text)]">{title}</strong>
        <span className="text-xs text-[var(--agent-text-muted)]">{riskLevelLabel(approval.payload.risk_level)}</span>
      </div>
      {message ? <p className="m-0 text-sm text-[var(--agent-text-secondary)]">{message}</p> : null}
      {approval.payload.decision_note ? <p className="m-0 text-sm text-[var(--agent-text-secondary)]">{approval.payload.decision_note}</p> : null}
      {approval.payload.reason ? <p className="m-0 text-sm text-[var(--agent-text-secondary)]">审批原因：{approval.payload.reason}</p> : null}
      <ApprovalOperation operation={operation} sql={sql} />
    </div>
  );
}

type ApprovalOutcome = "approved" | "rejected" | "expired" | "cancelled" | "failed";

function approvalOutcome(approval: ApprovalItem): ApprovalOutcome {
  if (approval.status === "expired" || approval.payload.decision === "expired") return "expired";
  if (approval.status === "cancelled" || approval.payload.decision === "cancelled") return "cancelled";
  if (approval.status === "failed") return "failed";
  return approval.payload.decision === "approved" ? "approved" : "rejected";
}

function approvalOutcomeTitle(outcome: ApprovalOutcome): string {
  if (outcome === "approved") return "已批准";
  if (outcome === "rejected") return "已拒绝";
  if (outcome === "expired") return "批准请求已过期";
  if (outcome === "cancelled") return "批准请求已取消";
  return "批准请求未完成";
}

function approvalOutcomeMessage(outcome: ApprovalOutcome): string | undefined {
  if (outcome === "expired") return "请求到期后未执行该操作；如仍需执行，请重新发起任务。";
  if (outcome === "cancelled") return "请求已随任务停止，未执行该操作。";
  if (outcome === "failed") return "请求未能完成，请根据任务错误提示继续处理。";
  return undefined;
}

function ApprovalOutcomeIcon({ outcome }: { outcome: ApprovalOutcome }) {
  if (outcome === "approved") return <Check aria-hidden="true" />;
  if (outcome === "rejected") return <X aria-hidden="true" />;
  if (outcome === "expired") return <Clock3 aria-hidden="true" />;
  if (outcome === "cancelled") return <CircleOff aria-hidden="true" />;
  return <TriangleAlert aria-hidden="true" />;
}

function ApprovalOperation({ operation, sql }: { operation: string; sql: string }) {
  return (
    <div className="grid gap-2 rounded-md border border-[var(--agent-border)] bg-[var(--agent-surface-muted)] p-2.5 text-xs">
      <div className="grid grid-cols-[48px_minmax(0,1fr)] gap-2">
        <span className="text-[var(--agent-text-muted)]">操作</span>
        <code className="break-all font-[var(--font-family-code)] text-[var(--agent-text-secondary)]">{operation}</code>
      </div>
      {sql ? <pre className="m-0 max-h-40 overflow-auto whitespace-pre-wrap break-words font-[var(--font-family-code)] text-[var(--agent-text-secondary)]">{sql}</pre> : null}
    </div>
  );
}

function SqlActions({ sql, onOpenSqlConsole, className = "" }: {
  sql: string;
  onOpenSqlConsole?: (sql?: string) => void;
  className?: string;
}) {
  if (!sql) return null;
  return (
    <div className={`flex flex-wrap gap-1 ${className}`}>
      <Button size="sm" variant="ghost" type="button" onClick={() => void navigator.clipboard?.writeText(sql)}>
        <Clipboard aria-hidden="true" />
        复制 SQL
      </Button>
      {onOpenSqlConsole ? (
        <Button size="sm" variant="ghost" type="button" onClick={() => onOpenSqlConsole(sql)}>
          <ExternalLink aria-hidden="true" />
          在 SQL 工作台查看
        </Button>
      ) : null}
    </div>
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

function approvalOperation(approval: ApprovalItem): string {
  const action = approval.payload.requested_action;
  for (const key of ["name", "operation", "type", "tool_name"]) {
    if (typeof action[key] === "string" && action[key].trim()) return action[key].trim();
  }
  return "待授权操作";
}
