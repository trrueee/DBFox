import type { RequestedResourceRef } from "../../lib/api/generated/types.gen";
import { useConversationContextStore } from "../../stores/conversationContextStore";
import { useConversationStore } from "../../stores/conversationStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";

export function getCurrentConversationContextSelection(): RequestedResourceRef[] {
  const projectId = useWorkspaceStore.getState().activeProjectId;
  if (!projectId) return [];
  const surface = useWorkspaceStore.getState().mainSurfaceByProject[projectId];
  const conversationState = useConversationStore.getState();
  const conversationId = conversationState.activeConversationId;
  const detail = conversationId ? conversationState.detailById[conversationId] : undefined;
  if (surface?.kind === "conversation" && conversationId && detail?.project_id === projectId) {
    return [...detail.resource_intents];
  }
  return [...(useConversationContextStore.getState().byProject[projectId] ?? [])];
}

export async function replaceCurrentConversationContextSelection(
  refs: readonly RequestedResourceRef[],
): Promise<void> {
  const projectId = useWorkspaceStore.getState().activeProjectId;
  if (!projectId) throw new Error("Please select a project first.");
  const surface = useWorkspaceStore.getState().mainSurfaceByProject[projectId];
  const conversationState = useConversationStore.getState();
  const conversationId = conversationState.activeConversationId;
  const detail = conversationId ? conversationState.detailById[conversationId] : undefined;
  if (surface?.kind === "conversation" && conversationId && detail?.project_id === projectId) {
    await conversationState.setResourceIntents(conversationId, refs);
    return;
  }
  useConversationContextStore.getState().replace(projectId, refs);
}

export async function addCurrentConversationContextResource(
  ref: RequestedResourceRef,
): Promise<void> {
  const selected = getCurrentConversationContextSelection();
  const key = resourceKey(ref);
  if (selected.some((candidate) => resourceKey(candidate) === key)) return;
  await replaceCurrentConversationContextSelection([...selected, { kind: ref.kind, id: ref.id }]);
}

export async function removeCurrentConversationContextResource(
  ref: RequestedResourceRef,
): Promise<void> {
  const key = resourceKey(ref);
  await replaceCurrentConversationContextSelection(
    getCurrentConversationContextSelection().filter((candidate) => resourceKey(candidate) !== key),
  );
}

function resourceKey(ref: RequestedResourceRef): string {
  return JSON.stringify([ref.kind, ref.id]);
}
