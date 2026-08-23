import { useEffect } from "react";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useArtifactDockStore } from "../../stores/artifactDockStore";

/**
 * Product-level Dock bootstrap:
 * Ensures the Core-owned Artifacts view exists for the active conversation.
 * Capability Workbench views are opened explicitly by their DLC connectors.
 */
export function useProductDockBootstrap(activeConversationId: string | null) {
  const dockTabs = useWorkspaceStore((s) => s.dockTabs);
  const openDockArtifacts = useArtifactDockStore((s) => s.openArtifacts);

  // 当前对话保证有「✦ 工件」Tab，但不抢走用户当前打开的 Tab。
  useEffect(() => {
    if (
      activeConversationId
      && !dockTabs.some(
        (tab) =>
          tab.viewType === "core.artifacts"
          && tab.target?.type === "conversation"
          && tab.target.id === activeConversationId,
      )
    ) {
      openDockArtifacts(activeConversationId, false);
    }
  }, [activeConversationId, dockTabs, openDockArtifacts]);
}
