import type { WorkbenchReference } from "../../types/workspace";
import { selectActiveConversationId, selectActiveWorkbench, useWorkspaceStore } from "../../stores/workspaceStore";
import { useConversationStore } from "../../stores/conversationStore";
import { openArtifactDock } from "../../stores/artifactDockStore";
import { useDlcStore } from "../dlc/extensionStore";
import { openAttachmentDock } from "../conversation/attachmentDock";
import { getDockView, visibleDockTabs } from "../dock/dockViewComposition";

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
  const { object, authority, locator } = reference;
  if (!object) throw new Error("此引用暂不可预览。");
  const state = useWorkspaceStore.getState();
  const workbench = selectActiveWorkbench(state);
  const activeConversationId = selectActiveConversationId(state);
  const owner = activeConversationId ?? workbench.draftConversationId;
  if (sessionId && owner !== sessionId) throw new Error("会话已切换，请在原会话打开引用。");

  const existing = visibleDockTabs(workbench.tabs, {
    activeProjectId: state.activeProjectId, activeConversationId, workbenchScopeId: workbench.scopeId,
  }).filter((tab) => {
    const target = tab.target;
    return target?.type === "object" && target.object.kind === object.kind && target.object.id === object.id
      && (target.object.version ?? null) === (object.version ?? null) && target.locator === locator
      && (!authority || (target.authority?.kind === authority.kind && target.authority?.id === authority.id))
      && (!tab.projectId || tab.projectId === state.activeProjectId) && (!tab.sessionId || tab.sessionId === owner)
      && getDockView(tab.viewType);
  });
  if (existing.length > 1) throw new Error("该对象对应多个页签，请在工作区选择。");
  if (existing.length === 1) {
    state.setDockActiveTab(existing[0].viewKey);
    return;
  }

  const views = useDlcStore.getState().contributions.dockViews.filter(view => view.objectKinds?.includes(object.kind));
  if (views.length !== 1) throw new Error(views.length ? "多个扩展提供此资源的预览，请检查扩展设置。" : "请从项目工作区打开，或启用支持此对象的扩展。");
  const scope = state.ensureActiveWorkbenchScope();
  const identity = JSON.stringify([scope, object.kind, object.id, object.version ?? null, authority?.kind, authority?.id, locator]);
  state.openDockTab({ viewKey: `reference:${identity}`,
    viewType: views[0].viewType, title: reference.label, closeable: true, preview: true, projectId: state.activeProjectId,
    target: { type: "object", object, authority, locator },
    stateKey: identity,
  });
}
