import { AlertTriangle, Loader2, XCircle } from "lucide-react";
import type { WorkspaceTab } from "../../mock/databoxMock";
import { FollowUpInput } from "./queryResult/FollowUpInput";
import { QueryResultHeader } from "./queryResult/QueryResultHeader";
import { AgentConversationThread } from "./queryResult/AgentConversationThread";

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

export function QueryResultWorkspace({
  tab,
  onOpenSqlConsole,
  onSetSqlQuery,
  onSendFollowUp,
  onCancelRun,
  onRegenerateRun,
  onToast,
}: QueryResultWorkspaceProps) {
  const isRunning = tab.agentStatus === "running";
  const isDone = tab.agentStatus === "completed" || tab.agentStatus === "failed";
  const hasAnswer = !!tab.agentAnswer?.answer;

  return (
    <div className="hifi-query-result-workspace hifi-tab-pane">
      <QueryResultHeader
        queryText={tab.queryText || ""}
        onRegenerate={isDone ? () => onRegenerateRun(tab.id) : undefined}
      />

      <div className="hifi-query-result-body">
        {isDone && tab.agentStatus === "failed" && !hasAnswer && (
          <div className="hifi-answer-error">
            <AlertTriangle size={14} />
            <span>Agent 未能完成分析</span>
            <span className="hifi-answer-error-hint">可以查看下方对话中的运行状态，或点击“重新生成”重试</span>
          </div>
        )}

        <AgentConversationThread
          tab={tab}
          onSendFollowUp={onSendFollowUp}
        />
      </div>

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
