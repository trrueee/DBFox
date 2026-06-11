import { useState } from "react";
import { Loader2, ShieldAlert, XCircle, ChevronDown, ChevronRight } from "lucide-react";
import type { WorkspaceTab } from "../../mock/databoxMock";
import { ArtifactRenderer } from "./artifacts/ArtifactRenderer";
import { FollowUpInput } from "./queryResult/FollowUpInput";
import { QueryMessages } from "./queryResult/QueryMessages";
import { QueryResultHeader } from "./queryResult/QueryResultHeader";
import { AnswerCard } from "./queryResult/AnswerCard";
import { FollowUpChips } from "./queryResult/FollowUpChips";

interface QueryResultWorkspaceProps {
  tab: WorkspaceTab;
  onOpenSqlConsole: () => void;
  onSetSqlQuery: (sql: string) => void;
  onSendFollowUp: (tabId: string, text: string) => void;
  onApproveAgent: (tabId: string) => void;
  onRejectAgent: (tabId: string) => void;
  onCancelRun: (tabId: string) => void;
  onRegenerateRun: (tabId: string) => void;
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
  onCancelRun,
  onRegenerateRun,
  onToast,
}: QueryResultWorkspaceProps) {
  const approval = tab.agentApproval;
  const isRunning = tab.agentStatus === "running";
  const isDone = tab.agentStatus === "completed" || tab.agentStatus === "failed";
  const hasAnswer = !!tab.agentAnswer?.answer;
  const [showThinking, setShowThinking] = useState(false);

  return (
    <div className="hifi-query-result-workspace hifi-tab-pane">
      <QueryResultHeader
        queryText={tab.queryText || ""}
        onRegenerate={isDone ? () => onRegenerateRun(tab.id) : undefined}
      />

      <div className="hifi-query-result-body">
        {/* Answer card — the main result */}
        {hasAnswer && tab.agentAnswer && (
          <AnswerCard answer={tab.agentAnswer} />
        )}

        {/* Follow-up suggestion chips */}
        {isDone && tab.agentSuggestions && tab.agentSuggestions.length > 0 && (
          <FollowUpChips
            suggestions={tab.agentSuggestions}
            onSendFollowUp={onSendFollowUp}
            tabId={tab.id}
          />
        )}

        {/* Approval card */}
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

        {/* Artifacts — charts, tables, SQL */}
        {((tab.artifacts?.length ?? 0) > 0) && (
          <ArtifactRenderer
            artifacts={tab.artifacts ?? []}
            onOpenSqlConsole={onOpenSqlConsole}
            onSetSqlQuery={onSetSqlQuery}
            onToast={onToast}
          />
        )}

        {/* Collapsible thinking process */}
        {!isRunning && (tab.chatMessages?.length ?? 0) > 0 && (
          <div className="hifi-thinking-section">
            <button
              className="hifi-thinking-toggle"
              onClick={() => setShowThinking(!showThinking)}
            >
              {showThinking ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              <span>查看思考过程</span>
              <span className="hifi-thinking-count">{tab.chatMessages?.length ?? 0} 条消息</span>
            </button>
            {showThinking && (
              <div className="hifi-thinking-body">
                <QueryMessages messages={tab.chatMessages || []} />
              </div>
            )}
          </div>
        )}
      </div>

      {/* Running bar */}
      {isRunning && (
        <div className="hifi-agent-running-bar">
          <Loader2 size={12} className="hifi-agent-running-spinner" />
          <span>AI 正在分析并生成回答，请稍候…</span>
          <button
            className="hifi-agent-cancel-btn"
            title="取消运行"
            onClick={() => onCancelRun(tab.id)}
          >
            <XCircle size={14} />
            <span>取消</span>
          </button>
        </div>
      )}

      <FollowUpInput tabId={tab.id} onSendFollowUp={onSendFollowUp} />
    </div>
  );
}
