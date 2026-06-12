import { useEffect, useState } from "react";
import { Loader2, ShieldAlert, XCircle, ChevronDown, ChevronRight, AlertTriangle } from "lucide-react";
import type { WorkspaceTab } from "../../mock/databoxMock";
import { ArtifactRenderer } from "./artifacts/ArtifactRenderer";
import { FollowUpInput } from "./queryResult/FollowUpInput";
import { QueryMessages } from "./queryResult/QueryMessages";
import { QueryResultHeader } from "./queryResult/QueryResultHeader";
import { AnswerCard } from "./queryResult/AnswerCard";
import { FollowUpChips } from "./queryResult/FollowUpChips";
import { AgentTimelineView } from "./queryResult/AgentTimelineView";

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
  const [showThinking, setShowThinking] = useState(true);
  const latestAgentMessage = latestAiMessage(tab.chatMessages || []);
  const timeline = tab.agentTimeline || [];
  const visibleArtifacts = (tab.artifacts ?? []).filter(
    (artifact) => !(hasAnswer && artifact.type === "markdown" && artifact.title === "Agent stopped"),
  );

  useEffect(() => {
    if (isRunning) {
      setShowThinking(true);
      return;
    }
    if (tab.agentStatus === "completed" || (tab.agentStatus === "failed" && hasAnswer)) {
      setShowThinking(false);
    }
  }, [hasAnswer, isRunning, tab.agentStatus]);

  return (
    <div className="hifi-query-result-workspace hifi-tab-pane">
      <QueryResultHeader
        queryText={tab.queryText || ""}
        onRegenerate={isDone ? () => onRegenerateRun(tab.id) : undefined}
      />

      <div className="hifi-query-result-body">
        {/* Error state — agent failed without producing an answer */}
        {isDone && tab.agentStatus === "failed" && !hasAnswer && (
          <div className="hifi-answer-error">
            <AlertTriangle size={14} />
            <span>Agent 未能完成分析</span>
            <span className="hifi-answer-error-hint">展开下方"查看思考过程"了解详情，或点击"重新生成"重试</span>
          </div>
        )}

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
        {visibleArtifacts.length > 0 && (
          <ArtifactRenderer
            artifacts={visibleArtifacts}
            onOpenSqlConsole={onOpenSqlConsole}
            onSetSqlQuery={onSetSqlQuery}
            onToast={onToast}
          />
        )}

        {/* Collapsible thinking process */}
        {((tab.chatMessages?.length ?? 0) > 0 || timeline.length > 0) && (
          <div className="hifi-thinking-section">
            <button
              className="hifi-thinking-toggle"
              onClick={() => setShowThinking(!showThinking)}
            >
              {showThinking ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              <span>{isRunning ? "查看实时过程" : "查看思考过程"}</span>
              <span className="hifi-thinking-count">{timeline.length || tab.chatMessages?.length || 0} 条事件</span>
            </button>
            {showThinking && (
              <div className="hifi-thinking-body">
                {timeline.length > 0 ? (
                  <AgentTimelineView items={timeline} />
                ) : (
                  <QueryMessages messages={tab.chatMessages || []} />
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Running bar */}
      {isRunning && (
        <div className="hifi-agent-running-bar">
          <Loader2 size={12} className="hifi-agent-running-spinner" />
          <span className="hifi-agent-running-text">{latestAgentMessage || "AI 正在分析并生成回答，请稍候…"}</span>
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

function latestAiMessage(messages: NonNullable<WorkspaceTab["chatMessages"]>): string {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.sender === "ai" && message.text.trim()) {
      return message.text.replace(/[#*`|]/g, "").replace(/\s+/g, " ").trim();
    }
  }
  return "";
}
