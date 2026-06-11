import { Loader2, ShieldAlert } from "lucide-react";
import type { WorkspaceTab } from "../../mock/databoxMock";
import { ArtifactRenderer } from "./artifacts/ArtifactRenderer";
import { FollowUpInput } from "./queryResult/FollowUpInput";
import { QueryMessages } from "./queryResult/QueryMessages";
import { QueryResultHeader } from "./queryResult/QueryResultHeader";

interface QueryResultWorkspaceProps {
  tab: WorkspaceTab;
  onOpenSqlConsole: () => void;
  onSetSqlQuery: (sql: string) => void;
  onSendFollowUp: (tabId: string, text: string) => void;
  onApproveAgent: (tabId: string) => void;
  onRejectAgent: (tabId: string) => void;
  onToast: (message: string) => void;
}

const RISK_LABELS: Record<string, string> = {
  safe: "低风险",
  warning: "需要确认",
  danger: "高风险",
};

export function QueryResultWorkspace({
  tab,
  onOpenSqlConsole,
  onSetSqlQuery,
  onSendFollowUp,
  onApproveAgent,
  onRejectAgent,
  onToast,
}: QueryResultWorkspaceProps) {
  const approval = tab.agentApproval;
  const isRunning = tab.agentStatus === "running";

  return (
    <div className="hifi-query-result-workspace hifi-tab-pane">
      <QueryResultHeader queryText={tab.queryText || ""} />

      <div className="hifi-query-result-messages">
        <QueryMessages messages={tab.chatMessages || []} />

        {approval && (
          <div className={`hifi-approval-card ${approval.riskLevel === "danger" ? "hifi-approval-danger" : ""}`}>
            <div className="hifi-approval-head">
              <ShieldAlert size={14} />
              <span className="hifi-approval-title">执行前需要你的确认</span>
              <span className={`hifi-approval-risk hifi-approval-risk-${approval.riskLevel}`}>
                {RISK_LABELS[approval.riskLevel] || approval.riskLevel}
              </span>
            </div>
            {approval.reason && <div className="hifi-approval-reason">{approval.reason}</div>}
            {approval.sql && <pre className="hifi-approval-sql">{approval.sql}</pre>}
            <div className="hifi-approval-actions">
              <button className="hifi-approval-btn hifi-approval-approve" onClick={() => onApproveAgent(tab.id)}>
                批准并继续
              </button>
              <button className="hifi-approval-btn hifi-approval-reject" onClick={() => onRejectAgent(tab.id)}>
                拒绝
              </button>
            </div>
          </div>
        )}

        {((tab.artifacts?.length ?? 0) > 0 || !isRunning) && (
          <ArtifactRenderer
            artifacts={tab.artifacts ?? []}
            onOpenSqlConsole={onOpenSqlConsole}
            onSetSqlQuery={onSetSqlQuery}
            onToast={onToast}
          />
        )}
      </div>

      {isRunning && (
        <div className="hifi-agent-running-bar">
          <Loader2 size={12} className="hifi-agent-running-spinner" />
          <span>Agent 正在执行，结果会实时更新…</span>
        </div>
      )}

      <FollowUpInput tabId={tab.id} onSendFollowUp={onSendFollowUp} />
    </div>
  );
}
