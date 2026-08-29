import { useMemo, useRef } from "react";
import { useMutation } from "@tanstack/react-query";
import type { WorkbenchReference } from "../../../types/workspace";
import { useConversationStore } from "../../../stores/conversationStore";
import { isTerminalRun } from "../conversationState";
import type {
  ConversationArtifact,
  ConversationDeliveryMode,
  ConversationRun,
  ConversationRunItem,
} from "../../../types/conversation";

export function useConversationViewModel(conversationId: string) {
  const pendingSendIntent = useRef<{
    conversationId: string;
    content: string;
    mode: ConversationDeliveryMode;
    idempotencyKey: string;
    references: readonly WorkbenchReference[];
  } | null>(null);
  const detail = useConversationStore((state) => state.detailById[conversationId]);
  const artifactsById = useConversationStore((state) => state.artifactsById);
  const streamError = useConversationStore((state) => state.streamErrorById[conversationId]);
  const streamState = useConversationStore((state) => state.streamStateById[conversationId]);
  const openConversationAction = useConversationStore((state) => state.openConversation);
  const loadOlderHistoryAction = useConversationStore((state) => state.loadOlderHistory);
  const sendMessageAction = useConversationStore((state) => state.sendMessage);
  const cancelRunAction = useConversationStore((state) => state.cancelRun);
  const resolveApprovalAction = useConversationStore((state) => state.resolveApproval);
  const resolveQuestionAction = useConversationStore((state) => state.resolveQuestion);
  const selectArtifact = useConversationStore((state) => state.selectArtifact);
  const loadRunArtifacts = useConversationStore((state) => state.loadRunArtifacts);
  const openMutation = useMutation({
    mutationFn: openConversationAction,
  });
  const historyMutation = useMutation({
    mutationKey: ["conversation-history", conversationId],
    mutationFn: () => loadOlderHistoryAction(conversationId),
  });
  const sendMutation = useMutation({
    mutationFn: ({
      targetConversationId,
      content,
      mode,
      idempotencyKey,
      references,
    }: {
      targetConversationId: string;
      content: string;
      mode: ConversationDeliveryMode;
      idempotencyKey: string;
      references: readonly WorkbenchReference[];
    }) => sendMessageAction(
      targetConversationId,
      content,
      mode,
      idempotencyKey,
      references,
    ),
  });
  const cancelMutation = useMutation({
    mutationFn: cancelRunAction,
  });
  const approvalMutation = useMutation({
    mutationFn: ({
      runId,
      approvalId,
      approved,
    }: {
      runId: string;
      approvalId: string;
      approved: boolean;
    }) => resolveApprovalAction(runId, approvalId, approved),
    onError: async () => {
      await openConversationAction(conversationId).catch(() => undefined);
    },
  });
  const questionMutation = useMutation({
    mutationFn: ({
      runId,
      questionId,
      response,
    }: {
      runId: string;
      questionId: string;
      response: { selected_value?: string; text?: string };
    }) => resolveQuestionAction(runId, questionId, response),
    onError: async () => {
      await openConversationAction(conversationId).catch(() => undefined);
    },
  });

  const items = useMemo<ConversationRunItem[]>(
    () => detail?.items || [],
    [detail],
  );
  const runs = useMemo<ConversationRun[]>(
    () => detail?.runs || [],
    [detail],
  );
  const artifacts = useMemo<ConversationArtifact[]>(
    () => Object.values(artifactsById).filter(
      (artifact) => artifact.session_id === conversationId,
    ),
    [artifactsById, conversationId],
  );
  const runningRun = useMemo(
    () => runs.find((run) => !isTerminalRun(run.status)) || null,
    [runs],
  );

  return {
    detail,
    items,
    runs,
    artifacts,
    runningRun,
    openConversation: openMutation.mutateAsync,
    conversationLoadError: openMutation.error ?? null,
    hasOlderHistory: Boolean(
      detail?.pagination?.items.has_more || detail?.pagination?.runs.has_more,
    ),
    loadOlderHistory: historyMutation.mutateAsync,
    loadingOlderHistory: historyMutation.isPending,
    olderHistoryLoaded: historyMutation.isSuccess,
    historyLoadError: historyMutation.error ?? null,
    streamError: streamError ?? null,
    streamState: streamState ?? "idle",
    sendMessage: async (
      targetConversationId: string,
      content: string,
      mode: ConversationDeliveryMode,
      references: readonly WorkbenchReference[] = [],
    ) => {
      let intent = pendingSendIntent.current;
      if (
        !intent
        || intent.conversationId !== targetConversationId
        || intent.content !== content
        || intent.mode !== mode
        || JSON.stringify(intent.references) !== JSON.stringify(references)
      ) {
        intent = {
          conversationId: targetConversationId,
          content,
          mode,
          idempotencyKey: globalThis.crypto.randomUUID(),
          references: [...references],
        };
        pendingSendIntent.current = intent;
      }
      await sendMutation.mutateAsync({
        targetConversationId,
        content,
        mode,
        idempotencyKey: intent.idempotencyKey,
        references: intent.references,
      });
      if (pendingSendIntent.current === intent) pendingSendIntent.current = null;
    },
    sending: sendMutation.isPending,
    sendError: sendMutation.error ?? null,
    cancelRun: (runId: string) => cancelMutation.mutateAsync(runId),
    cancelling: cancelMutation.isPending,
    resolveApproval: (runId: string, approvalId: string, approved: boolean) =>
      approvalMutation.mutateAsync({ runId, approvalId, approved }),
    resolvingApprovalId: approvalMutation.isPending
      ? approvalMutation.variables?.approvalId ?? null
      : null,
    approvalError: approvalMutation.error ?? null,
    resolveQuestion: (
      runId: string,
      questionId: string,
      response: { selected_value?: string; text?: string },
    ) => questionMutation.mutateAsync({ runId, questionId, response }),
    resolvingQuestionId: questionMutation.isPending
      ? questionMutation.variables?.questionId ?? null
      : null,
    questionError: questionMutation.error ?? null,
    selectArtifact,
    loadRunArtifacts,
  };
}
