import type { WorkspaceTab } from "../../mock/databoxMock";
import { AgentTaskView } from "../agentTask/AgentTaskView";

interface QueryResultWorkspaceProps {
  tab: WorkspaceTab;
  onOpenSqlConsole: (initialSql?: string) => void;
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
  onSendFollowUp,
  onApproveAgent,
  onRejectAgent,
  onCancelRun,
  onRegenerateRun,
  onToast,
}: QueryResultWorkspaceProps) {
  return (
    <AgentTaskView
      tab={tab}
      onCancel={onCancelRun}
      onRegenerate={onRegenerateRun}
      onApproveAgent={onApproveAgent}
      onRejectAgent={onRejectAgent}
      onSendFollowUp={onSendFollowUp}
      onOpenSqlConsole={onOpenSqlConsole}
      onToast={onToast}
    />
  );
}

