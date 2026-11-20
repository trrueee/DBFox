import { CORE_DOCK_VIEW_TYPES } from "../dlc/coreContributionIds";
import { selectActiveConversationId, selectActiveWorkbench, useWorkspaceStore } from "../../stores/workspaceStore";
import type { ComputerGrant } from "../../lib/api/generated/types.gen";
import { COMPUTER_RESOURCE_KIND } from "../../lib/api/computer";

export function openComputerDock(conversationId: string, grant?: ComputerGrant): void {
  const workspace = useWorkspaceStore.getState();
  const workbench = selectActiveWorkbench(workspace);
  if ((selectActiveConversationId(workspace) ?? workbench.draftConversationId) !== conversationId) return;
  workspace.openDockTab({
    viewKey: `${CORE_DOCK_VIEW_TYPES.computer}:${conversationId}`,
    viewType: CORE_DOCK_VIEW_TYPES.computer,
    title: "电脑", closeable: true, sessionId: conversationId,
    projectId: workspace.activeProjectId, stateKey: workbench.scopeId,
    target: grant ? { type: "object", object: { kind: COMPUTER_RESOURCE_KIND, id: grant.id, version: grant.version } }
      : { type: "conversation", id: conversationId },
  });
}
