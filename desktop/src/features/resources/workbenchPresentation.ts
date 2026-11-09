import { useEffect } from "react";
import { getRuntimeSession } from "../../lib/api/client";
import {
  acknowledgeWorkbenchPresentationApiV1ConversationsConversationIdWorkbenchPresentationsInvocationIdReceiptPost as acknowledgePresentation,
  claimWorkbenchPresentationApiV1ConversationsConversationIdWorkbenchPresentationsInvocationIdClaimPost as claimPresentation,
} from "../../lib/api/generated/sdk.gen";
import type { WorkbenchPresentation, WorkbenchPresentationReceipt } from "../../lib/api/generated/types.gen";
import { openArtifactDock } from "../../stores/artifactDockStore";
import { selectActiveConversationId, selectActiveWorkbench, selectActiveWorkbenchScopeId, useWorkspaceStore, type WorkspaceStore } from "../../stores/workspaceStore";
import type { ConversationRunItem } from "../../types/conversation";
import { activeDockTab, visibleDockTabs } from "../dock/dockViewComposition";

function matchesWorkbench(state: WorkspaceStore, projectId: string, conversationId: string, scopeId: string) {
  return state.activeProjectId === projectId && selectActiveConversationId(state) === conversationId
    && selectActiveWorkbenchScopeId(state) === scopeId;
}

export function applyWorkbenchPresentation(
  presentation: WorkbenchPresentation,
  scopeId: string,
): WorkbenchPresentationReceipt["outcome"] {
  const state = useWorkspaceStore.getState();
  if (!matchesWorkbench(state, presentation.project_id, presentation.conversation_id, scopeId)
    || presentation.expires_at_ms <= Date.now()) return "not_opened";

  openArtifactDock({ id: presentation.artifact_id, title: presentation.title }, { projectId: presentation.project_id });
  const applied = useWorkspaceStore.getState();
  if (!matchesWorkbench(applied, presentation.project_id, presentation.conversation_id, scopeId)) return "not_opened";
  const workbench = selectActiveWorkbench(applied);
  const selected = activeDockTab(visibleDockTabs(workbench.tabs, {
    activeProjectId: presentation.project_id, activeConversationId: presentation.conversation_id, workbenchScopeId: scopeId,
  }), workbench.activeViewKey);
  return workbench.open && selected?.target?.type === "artifact" && selected.target.id === presentation.artifact_id
    ? "opened"
    : "not_opened";
}

/** The durable Invocation event wakes the Renderer; delivery itself is single-use. */
export function useWorkbenchPresentation(
  conversationId: string,
  runId: string | undefined,
  items: readonly ConversationRunItem[],
) {
  const invocationId = runId ? items.find((item) => item.type === "function_call"
    && item.run_id === runId && item.payload.name === "workbench_open_artifact"
    && item.status === "in_progress")?.id : undefined;

  useEffect(() => {
    if (!invocationId) return;
    const initial = useWorkspaceStore.getState();
    if (selectActiveConversationId(initial) !== conversationId) return;
    const projectId = initial.activeProjectId;
    const scopeId = initial.ensureActiveWorkbenchScope();
    const generation = getRuntimeSession().generation;
    const controller = new AbortController();
    const path = { conversation_id: conversationId, invocation_id: invocationId };
    const deadline = Date.now() + 7_000;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const claim = async () => {
      const current = useWorkspaceStore.getState();
      if (controller.signal.aborted || Date.now() >= deadline || !matchesWorkbench(current, projectId, conversationId, scopeId)
        || getRuntimeSession().generation !== generation) return;
      try {
        const { data } = await claimPresentation({
          path, signal: controller.signal, throwOnError: true,
        });
        if (controller.signal.aborted || getRuntimeSession().generation !== generation) return;
        if (!data) {
          timer = setTimeout(() => void claim(), 250);
          return;
        }
        if (data.invocation_id !== invocationId || data.conversation_id !== conversationId) return;
        const outcome = applyWorkbenchPresentation(data, scopeId);
        await acknowledgePresentation({
          path, body: { outcome }, signal: controller.signal, throwOnError: true,
        });
      } catch {
        // A lost reply stays unconfirmed. The durable tool call is never replayed here.
      }
    };

    const stop = () => {
      controller.abort();
      clearTimeout(timer);
    };
    const unsubscribe = useWorkspaceStore.subscribe((current) => {
      if (!matchesWorkbench(current, projectId, conversationId, scopeId)) stop();
    });
    timer = setTimeout(() => void claim(), 0);
    return () => {
      unsubscribe();
      stop();
    };
  }, [conversationId, invocationId]);
}
