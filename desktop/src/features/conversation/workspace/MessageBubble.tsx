import type { TableArtifact, ResultViewArtifact } from "../../../types/agentArtifact";
import type { AgentApproval } from "../../../lib/api/types";
import type {
  ConversationArtifact,
  ConversationMessage,
  ConversationRun,
} from "../../../types/conversation";
import { MarkdownContent } from "../../workspace/queryResult/MarkdownContent";
import { ArtifactEvidencePanel } from "./ArtifactEvidencePanel";
import { DataReferencePanel } from "./DataReferencePanel";
import { RunTracePanel } from "./RunTracePanel";

interface MessageBubbleProps {
  message: ConversationMessage;
  run?: ConversationRun;
  artifacts: ConversationArtifact[];
  onOpenSqlConsole: (sql?: string) => void;
  onOpenResultTab?: (artifact: TableArtifact | ResultViewArtifact) => void;
  onResolveApproval?: (runId: string, approvalId: string, approved: boolean) => void;
}

export function MessageBubble({
  message,
  run,
  artifacts,
  onOpenSqlConsole,
  onOpenResultTab,
  onResolveApproval,
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  const messageClass = isUser ? `conv-message conv-message-${message.role}` : "conv-message conv-message-answer";
  return (
    <article className={messageClass}>
      <div className="conv-message-body">
        {isUser ? (
          <p>{message.content}</p>
        ) : (
          <>
            {run && <RunTracePanel run={run} />}
            {run?.status === "failed" && (
              <div className="conv-error-card">{run.error_message || "Agent stopped."}</div>
            )}
            {run?.status === "waiting_approval" && run.approval?.status === "pending" && (
              <ApprovalCard
                runId={run.id}
                approval={run.approval}
                onOpenSqlConsole={onOpenSqlConsole}
                onResolveApproval={onResolveApproval}
              />
            )}
            <div className="conv-answer-document">
              <MarkdownContent content={message.content || (message.status === "streaming" ? "Thinking..." : "")} />
            </div>
          </>
        )}
        {!isUser && <DataReferencePanel artifacts={artifacts} onOpenSqlConsole={onOpenSqlConsole} />}
        {!isUser && (
          <ArtifactEvidencePanel
            artifacts={artifacts}
            onOpenSqlConsole={onOpenSqlConsole}
            onOpenResultTab={onOpenResultTab}
          />
        )}
      </div>
    </article>
  );
}

function ApprovalCard({
  runId,
  approval,
  onOpenSqlConsole,
  onResolveApproval,
}: {
  runId: string;
  approval: AgentApproval;
  onOpenSqlConsole: (sql?: string) => void;
  onResolveApproval?: (runId: string, approvalId: string, approved: boolean) => void;
}) {
  const sql = approvalSql(approval);
  return (
    <section className={`conv-approval-card conv-approval-${approval.risk_level}`} aria-label="Approval required">
      <div className="conv-approval-heading">
        <strong>需要审批</strong>
        <span>风险级别：{approval.risk_level}</span>
      </div>
      {approval.reason && <p>{approval.reason}</p>}
      {sql && <pre>{sql}</pre>}
      <div className="conv-approval-actions">
        <button type="button" onClick={() => onResolveApproval?.(runId, approval.id, true)}>
          批准执行
        </button>
        <button type="button" onClick={() => onResolveApproval?.(runId, approval.id, false)}>
          拒绝
        </button>
        {sql && (
          <>
            <button type="button" onClick={() => void navigator.clipboard?.writeText(sql)}>
              复制 SQL
            </button>
            <button type="button" onClick={() => onOpenSqlConsole(sql)}>
              在 SQL Console 查看
            </button>
          </>
        )}
      </div>
    </section>
  );
}

function approvalSql(approval: AgentApproval): string {
  const action = approval.requested_action;
  if (!action || typeof action !== "object") return "";
  const record = action as Record<string, unknown>;
  if (typeof record.sql === "string") return record.sql;
  const args = record.args;
  if (args && typeof args === "object" && typeof (args as Record<string, unknown>).sql === "string") {
    return (args as Record<string, string>).sql;
  }
  return "";
}
