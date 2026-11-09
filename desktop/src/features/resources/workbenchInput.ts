import { zConversationInputReference } from "../../lib/api/generated/zod.gen";
import { useConversationStore } from "../../stores/conversationStore";
import {
  selectActiveConversationId,
  selectActiveWorkbench,
  useWorkspaceStore,
} from "../../stores/workspaceStore";
import type { WorkbenchReference } from "../../types/workspace";
import { ATTACHMENT_RESOURCE_KIND } from "../conversation/attachmentRepository";
import { activeDockTab, getDockView, visibleDockTabs } from "../dock/dockViewComposition";

/** Capture one visible subject. Explicit user references take precedence. */
export function captureWorkbenchInput(
  references: readonly WorkbenchReference[],
  conversationId: string | null,
): readonly WorkbenchReference[] {
  if (references.length) return references;
  const state = useWorkspaceStore.getState();
  const workbench = selectActiveWorkbench(state);
  const activeConversationId = selectActiveConversationId(state);
  const currentConversation = activeConversationId ?? workbench.draftConversationId ?? null;
  if (!workbench.open || currentConversation !== conversationId) return references;

  const visibleTabs = visibleDockTabs(workbench.tabs, {
    activeProjectId: state.activeProjectId, activeConversationId, workbenchScopeId: workbench.scopeId,
  });
  const tab = activeDockTab(visibleTabs, workbench.activeViewKey);
  if (!tab?.target || !getDockView(tab.viewType) || (tab.projectId && tab.projectId !== state.activeProjectId)
    || (tab.sessionId && tab.sessionId !== conversationId)) return references;

  const label = `当前查看 · ${tab.title}`.slice(0, 500);
  const target = tab.target;
  if (target.type === "object" && target.object.kind !== ATTACHMENT_RESOURCE_KIND) {
    const reference = { label, object: { ...target.object }, locator: target.locator };
    return zConversationInputReference.safeParse(reference).success ? [reference] : references;
  }
  if (target.type === "artifact" && conversationId) {
    const artifact = useConversationStore.getState().artifactsById[target.id];
    if (artifact?.session_id === conversationId && artifact.status === "completed" && artifact.visibility !== "internal") {
      return [{ label, artifactId: artifact.id }];
    }
  }
  return references;
}
