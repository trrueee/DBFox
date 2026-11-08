import type { WorkbenchReference } from "../../types/workspace";
import { selectActiveWorkbench, useWorkspaceStore } from "../../stores/workspaceStore";
import { useConversationStore } from "../../stores/conversationStore";
import { openArtifactDock } from "../../stores/artifactDockStore";
import { useDlcStore } from "../dlc/extensionStore";
import { openAttachmentDock } from "../conversation/attachmentDock";

/** Navigate an exact reference. Viewing never adds or changes execution authority. */
export function openWorkbenchReference(reference: WorkbenchReference, sessionId?: string): void {
  if (reference.object?.kind === "dbfox.core.attachment") {
    if (!sessionId) throw new Error("请在原会话打开附件。");
    openAttachmentDock(reference, sessionId);
    return;
  }
  if (reference.artifactId) {
    const artifact = useConversationStore.getState().artifactsById[reference.artifactId];
    if (!artifact) throw new Error("成果尚未载入，请在原对话中打开。");
    openArtifactDock(artifact);
    return;
  }
  if (!reference.object) throw new Error("此引用暂不可预览。");
  const views = useDlcStore.getState().contributions.dockViews.filter(view => view.objectKinds?.includes(reference.object!.kind));
  if (views.length !== 1) throw new Error(views.length ? "多个扩展提供此资源的预览，请检查扩展设置。" : "请启用支持此资源的扩展。");
  const scope = useWorkspaceStore.getState().ensureActiveWorkbenchScope();
  const state = useWorkspaceStore.getState();
  const existing = selectActiveWorkbench(state).tabs.find(tab => tab.viewType === views[0].viewType
    && tab.target?.type === "object" && tab.target.object.kind === reference.object!.kind
    && tab.target.object.id === reference.object!.id && tab.target.object.version === reference.object!.version
    && tab.target.authority?.id === reference.authority?.id && tab.target.authority?.kind === reference.authority?.kind
    && tab.target.locator === reference.locator);
  if (existing) { state.setDockActiveTab(existing.viewKey); return; }
  const identity = JSON.stringify([scope, reference.object.kind, reference.object.id, reference.object.version,
    reference.authority?.kind, reference.authority?.id, reference.locator]);
  state.openDockTab({ viewKey: `reference:${identity}`,
    viewType: views[0].viewType, title: reference.label, closeable: true, preview: true, projectId: state.activeProjectId,
    target: { type: "object", object: reference.object, authority: reference.authority, locator: reference.locator },
    stateKey: identity,
  });
}
