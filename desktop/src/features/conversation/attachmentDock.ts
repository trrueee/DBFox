import type { ConversationInputReference } from "../../lib/api/generated/types.gen";
import { useDlcStore } from "../dlc/extensionStore";
import { selectActiveConversationId, selectActiveWorkbench, useWorkspaceStore } from "../../stores/workspaceStore";
import { ATTACHMENT_RESOURCE_KIND } from "./attachmentRepository";

export function attachmentExtensions(): string[] {
  return [...new Set(useDlcStore.getState().contributions.dockViews.flatMap(view => view.attachmentExtensions ?? []))];
}

export function openAttachmentDock(reference: Pick<ConversationInputReference, "label" | "object" | "locator">, sessionId: string): void {
  if (reference.object?.kind !== ATTACHMENT_RESOURCE_KIND) return;
  const state = useWorkspaceStore.getState();
  const owner = selectActiveConversationId(state) ?? selectActiveWorkbench(state).draftConversationId;
  if (owner !== sessionId) throw new Error("会话已切换，请在原会话打开附件。");
  const extension = reference.label.split(".").at(-1)?.toLowerCase();
  const candidates = useDlcStore.getState().contributions.dockViews.filter(view => extension && view.attachmentExtensions?.includes(extension));
  if (candidates.length !== 1) throw new Error(candidates.length ? "有多个文件预览扩展匹配，请检查扩展设置。" : "文件预览能力不可用，请启用支持此格式的扩展。");
  state.openDockTab({
    viewKey: `attachment:${sessionId}:${reference.object.id}`, viewType: candidates[0].viewType,
    title: reference.label, closeable: true, projectId: state.activeProjectId, sessionId,
    stateKey: state.ensureActiveWorkbenchScope(), target: { type: "object", object: reference.object, locator: reference.locator ?? undefined },
  });
}
