import { CORE_DOCK_VIEW_TYPES } from "../features/dlc/coreContributionIds";
import { selectActiveConversationId, useWorkspaceStore } from "./workspaceStore";

export function openExecutionDock(conversationId: string, jobId?: string): void {
  const workspace = useWorkspaceStore.getState();
  if (selectActiveConversationId(workspace) !== conversationId) return;
  workspace.openDockTab({
    viewKey: [CORE_DOCK_VIEW_TYPES.execution, conversationId, jobId ?? "jobs"].join(":"),
    viewType: CORE_DOCK_VIEW_TYPES.execution,
    title: jobId ? "运行输出" : "本机任务",
    closeable: true,
    sessionId: conversationId,
    target: { type: "conversation", id: conversationId },
    stateKey: jobId,
  });
}
