import { useEffect, useRef, useState } from "react";
import {
  CheckIcon,
  ProhibitIcon,
  ClipboardTextIcon,
  ClockIcon,
  ArrowSquareOutIcon,
  CircleNotchIcon,
  ShieldWarningIcon,
  WarningIcon,
  XIcon,
  CaretDownIcon,
} from "@/components/icons";

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
import "../../../components/agent-elements/agent-interaction.css";

interface ApprovalCardProps {
  approval: ApprovalItem;
  onOpenSqlConsole?: (sql?: string) => void;
  submitting?: boolean;
  pendingCount?: number;
  error?: unknown;
  onResolve?: (runId: string, approvalId: string, approved: boolean) => Promise<void> | void;
}

export function ApprovalCard({
  approval,
  onOpenSqlConsole,
  submitting = false,
  pendingCount = 1,
  error,
  onResolve,
}: ApprovalCardProps) {
  const sql = approvalSql(approval);
  const operation = approvalOperation(approval);
  const safeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (document.activeElement === document.body) safeButtonRef.current?.focus({ preventScroll: true });
  }, [approval.id]);

  return (
    <Confirmation
      state="approval-requested"
      variant={approval.payload.risk_level === "danger" ? "destructive" : "default"}
      className="agent-approval gap-3"
      aria-label="需要批准"
      aria-live="polite"
      aria-busy={submitting || undefined}
      data-risk={approval.payload.risk_level}
    >
      <ShieldWarningIcon aria-hidden="true" />
      <ConfirmationRequest>
        <div className="col-start-2 grid gap-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <strong className="text-sm font-medium text-[var(--agent-text)]">需要你的批准</strong>
            <span className="text-xs text-[var(--agent-text-muted)]">{riskLevelLabel(approval.payload.risk_level)}</span>
          </div>
          {approval.payload.reason ? <ConfirmationTitle>{approval.payload.reason}</ConfirmationTitle> : null}
          {pendingCount > 1 ? <p className="m-0 text-sm text-[var(--agent-text-secondary)]">还有 {pendingCount} 项操作待批准，将逐项处理。</p> : null}
          <ApprovalOperation operation={operation} sql={sql} approval={approval} />
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
            {submitting ? <CircleNotchIcon className="animate-spin" aria-hidden="true" /> : null}
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
  const [expanded, setExpanded] = useState(false);
  const resolved = outcome === "approved" || outcome === "rejected";
  const decision = <ApprovalDecision title={title} message={approvalOutcomeMessage(outcome)} approval={approval} operation={operation} sql={sql} />;
  const decisionContent = <>
    {outcome === "approved" ? <ConfirmationAccepted>{decision}</ConfirmationAccepted>
      : outcome === "rejected" ? <ConfirmationRejected>{decision}</ConfirmationRejected> : decision}
    <SqlActions sql={sql} onOpenSqlConsole={onOpenSqlConsole} className="col-start-2" />
  </>;

  return (
    <Confirmation
      state={outcome === "pending" ? "approval-requested" : approved === false ? "output-denied" : "approval-responded"}
      approved={approved}
      role="status"
      aria-label="批准记录"
      className="agent-approval agent-approval--audit gap-2"
      data-status={outcome}
    >
      <ApprovalOutcomeIcon outcome={outcome} />
      {resolved ? <details className="agent-approval__history" onToggle={event => setExpanded(event.currentTarget.open)}>
        <summary><strong>{title}</strong><span>{operation}</span><CaretDownIcon size={16} aria-hidden="true" /></summary>
        {expanded ? <div className="agent-approval__history-body">{decisionContent}</div> : null}
      </details> : decisionContent}
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
      <ApprovalOperation operation={operation} sql={sql} approval={approval} />
    </div>
  );
}

type ApprovalOutcome = "pending" | "approved" | "rejected" | "expired" | "cancelled" | "failed";

function approvalOutcome(approval: ApprovalItem): ApprovalOutcome {
  if (approval.status === "waiting") return "pending";
  if (approval.status === "expired" || approval.payload.decision === "expired") return "expired";
  if (approval.status === "cancelled" || approval.payload.decision === "cancelled") return "cancelled";
  if (approval.status === "failed") return "failed";
  if (approval.payload.decision === "approved") return "approved";
  return approval.payload.decision === "rejected" ? "rejected" : "failed";
}

function approvalOutcomeTitle(outcome: ApprovalOutcome): string {
  if (outcome === "pending") return "等待批准";
  if (outcome === "approved") return "已批准";
  if (outcome === "rejected") return "已拒绝";
  if (outcome === "expired") return "批准请求已过期";
  if (outcome === "cancelled") return "批准请求已取消";
  return "批准请求未完成";
}

function approvalOutcomeMessage(outcome: ApprovalOutcome): string | undefined {
  if (outcome === "pending") return "此操作尚未执行，等待你的决定。";
  if (outcome === "expired") return "请求到期后未执行该操作；如仍需执行，请重新发起任务。";
  if (outcome === "cancelled") return "请求已随任务停止，未执行该操作。";
  if (outcome === "failed") return "请求未能完成，请根据任务错误提示继续处理。";
  return undefined;
}

function ApprovalOutcomeIcon({ outcome }: { outcome: ApprovalOutcome }) {
  if (outcome === "pending") return <ClockIcon aria-hidden="true" />;
  if (outcome === "approved") return <CheckIcon aria-hidden="true" />;
  if (outcome === "rejected") return <XIcon aria-hidden="true" />;
  if (outcome === "expired") return <ClockIcon aria-hidden="true" />;
  if (outcome === "cancelled") return <ProhibitIcon aria-hidden="true" />;
  return <WarningIcon aria-hidden="true" />;
}

function ApprovalOperation({ operation, sql, approval }: { operation: string; sql: string; approval: ApprovalItem }) {
  const parameters = approval.payload.requested_action.arguments;
  const review = approval.payload.requested_action.review;
  if (review && typeof review === "object" && "executable" in review && typeof review.executable === "string") {
    const details = review as Record<string, unknown>;
    const args = parameters && typeof parameters === "object" ? parameters as Record<string, unknown> : {};
    const command = typeof args.shell_script === "string"
      ? args.shell_script
      : Array.isArray(args.argv) ? JSON.stringify(args.argv.slice(1))
      : typeof args.text === "string" ? JSON.stringify(args.text) : undefined;
    return <div className="grid gap-2 rounded-md border border-[var(--agent-border)] bg-[var(--agent-surface-muted)] p-2.5 text-xs">
      <dl className="m-0 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1">
        <dt className="text-[var(--agent-text-muted)]">程序</dt>
        <dd className="m-0 break-all font-[var(--font-family-code)]">{review.executable}</dd>
        {typeof details.cwd === "string" ? <>
          <dt className="text-[var(--agent-text-muted)]">目录</dt>
          <dd className="m-0 break-all font-[var(--font-family-code)]">{details.cwd}</dd>
        </> : null}
        {typeof details.mode === "string" ? <>
          <dt className="text-[var(--agent-text-muted)]">方式</dt>
          <dd className="m-0">
            {details.mode === "windows_cmd" ? "Windows cmd " + String(details.shell_flags ?? "") : "直接运行程序"}
            {details.lifetime === "background" ? " · 允许后台运行" : " · 随当前任务结束"}
            {typeof details.timeout_seconds === "number" ? " · 最长 " + details.timeout_seconds + " 秒" : ""}
          </dd>
        </> : <>
          <dt className="text-[var(--agent-text-muted)]">操作</dt>
          <dd className="m-0">{typeof args.text === "string" ? (args.close ? "写入并关闭标准输入" : "写入标准输入") : "停止进程树"}</dd>
        </>}
      </dl>
      {command ? <pre className="m-0 max-h-40 overflow-auto whitespace-pre-wrap break-words font-[var(--font-family-code)]">{command}</pre> : null}
      {args.env && typeof args.env === "object" && Object.keys(args.env).length ? <details>
        <summary className="cursor-pointer">环境变量</summary>
        <pre className="m-0 max-h-40 overflow-auto whitespace-pre-wrap break-words font-[var(--font-family-code)]">{JSON.stringify(args.env, null, 2)}</pre>
      </details> : null}
    </div>;
  }
  const target = parameters && typeof parameters === "object" && "path" in parameters
    && typeof parameters.path === "string" ? parameters.path : undefined;
  const operationIdentity = (
    <div className="grid grid-cols-[48px_minmax(0,1fr)] gap-2">
      <span className="text-[var(--agent-text-muted)]">操作</span>
      <code className="break-all font-[var(--font-family-code)] text-[var(--agent-text-secondary)]">{operation}</code>
    </div>
  );
  return (
    <div className="grid gap-2 rounded-md border border-[var(--agent-border)] bg-[var(--agent-surface-muted)] p-2.5 text-xs">
      {sql ? operationIdentity : null}
      {target ? <div className="grid grid-cols-[48px_minmax(0,1fr)] gap-2"><span className="text-[var(--agent-text-muted)]">文件</span><code className="break-all font-[var(--font-family-code)]">{target}</code></div> : null}
      {sql ? <pre className="m-0 max-h-40 overflow-auto whitespace-pre-wrap break-words font-[var(--font-family-code)] text-[var(--agent-text-secondary)]">{sql}</pre> : null}
      {!sql ? (
        <details>
          <summary className="cursor-pointer text-[var(--agent-text-secondary)]">查看操作内容</summary>
          <div className="mt-2">{operationIdentity}</div>
          {parameters && typeof parameters === "object" ? (
            <pre className="m-0 mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words font-[var(--font-family-code)]">{JSON.stringify(parameters, null, 2)}</pre>
          ) : null}
        </details>
      ) : null}
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
        <ClipboardTextIcon aria-hidden="true" />
        复制 SQL
      </Button>
      {onOpenSqlConsole ? (
        <Button size="sm" variant="ghost" type="button" onClick={() => onOpenSqlConsole(sql)}>
          <ArrowSquareOutIcon aria-hidden="true" />
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
