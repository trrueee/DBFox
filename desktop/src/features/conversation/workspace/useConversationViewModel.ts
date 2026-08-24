import { useMemo, useRef } from "react";
import { useMutation } from "@tanstack/react-query";
import { getUserErrorMessage } from "../../../lib/api/client";
import type { RequestedResourceRef } from "../../../lib/api/generated/types.gen";
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
    requestedResources: readonly RequestedResourceRef[];
  } | null>(null);
  const detail = useConversationStore((state) => state.detailById[conversationId]);
  const artifactsById = useConversationStore((state) => state.artifactsById);
  const streamError = useConversationStore((state) => state.streamErrorById[conversationId]);
  const openConversationAction = useConversationStore((state) => state.openConversation);
  const sendMessageAction = useConversationStore((state) => state.sendMessage);
  const setResourceIntentsAction = useConversationStore((state) => state.setResourceIntents);
  const cancelRunAction = useConversationStore((state) => state.cancelRun);
  const resolveApprovalAction = useConversationStore((state) => state.resolveApproval);
  const resolveQuestionAction = useConversationStore((state) => state.resolveQuestion);
  const selectArtifact = useConversationStore((state) => state.selectArtifact);
  const loadRunArtifacts = useConversationStore((state) => state.loadRunArtifacts);
  const openMutation = useMutation({
    mutationFn: openConversationAction,
  });
  const sendMutation = useMutation({
    mutationFn: ({
      targetConversationId,
      content,
      mode,
      idempotencyKey,
      requestedResources,
    }: {
      targetConversationId: string;
      content: string;
      mode: ConversationDeliveryMode;
      idempotencyKey: string;
      requestedResources: readonly RequestedResourceRef[];
    }) => sendMessageAction(
      targetConversationId,
      content,
      mode,
      idempotencyKey,
      requestedResources,
    ),
  });
  const cancelMutation = useMutation({
    mutationFn: cancelRunAction,
  });
  const resourceIntentsMutation = useMutation({
    mutationFn: ({
      targetConversationId,
      resourceIntents,
    }: {
      targetConversationId: string;
      resourceIntents: Parameters<typeof setResourceIntentsAction>[1];
    }) => setResourceIntentsAction(targetConversationId, resourceIntents),
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
    conversationLoadError: openMutation.error
      ? getUserErrorMessage(openMutation.error, "对话载入失败，请重试。")
      : null,
    streamError: streamError ?? null,
    sendMessage: async (
      targetConversationId: string,
      content: string,
      mode: ConversationDeliveryMode,
      requestedResources: readonly RequestedResourceRef[] = [],
    ) => {
      let intent = pendingSendIntent.current;
      if (
        !intent
        || intent.conversationId !== targetConversationId
        || intent.content !== content
        || intent.mode !== mode
        || !sameRequestedResources(intent.requestedResources, requestedResources)
      ) {
        intent = {
          conversationId: targetConversationId,
          content,
          mode,
          idempotencyKey: globalThis.crypto.randomUUID(),
          requestedResources: [...requestedResources],
        };
        pendingSendIntent.current = intent;
      }
      await sendMutation.mutateAsync({
        targetConversationId,
        content,
        mode,
        idempotencyKey: intent.idempotencyKey,
        requestedResources: intent.requestedResources,
      });
      if (pendingSendIntent.current === intent) pendingSendIntent.current = null;
    },
    sending: sendMutation.isPending,
    sendError: sendMutation.error
      ? getUserErrorMessage(sendMutation.error, "消息发送失败，请重试。")
      : null,
    setResourceIntents: (resourceIntents: Parameters<typeof setResourceIntentsAction>[1]) =>
      resourceIntentsMutation.mutateAsync({ targetConversationId: conversationId, resourceIntents }),
    updatingResourceIntents: resourceIntentsMutation.isPending,
    resourceIntentError: resourceIntentsMutation.error
      ? getUserErrorMessage(resourceIntentsMutation.error, "对话上下文更新失败，请重试。")
      : null,
    cancelRun: (runId: string) => cancelMutation.mutateAsync(runId),
    cancelling: cancelMutation.isPending,
    resolveApproval: (runId: string, approvalId: string, approved: boolean) =>
      approvalMutation.mutateAsync({ runId, approvalId, approved }),
    resolvingApprovalId: approvalMutation.isPending
      ? approvalMutation.variables?.approvalId ?? null
      : null,
    approvalError: approvalMutation.error
      ? getUserErrorMessage(approvalMutation.error, "审批提交失败，请重试。")
      : null,
    resolveQuestion: (
      runId: string,
      questionId: string,
      response: { selected_value?: string; text?: string },
    ) => questionMutation.mutateAsync({ runId, questionId, response }),
    resolvingQuestionId: questionMutation.isPending
      ? questionMutation.variables?.questionId ?? null
      : null,
    questionError: questionMutation.error
      ? getUserErrorMessage(questionMutation.error, "回答提交失败，请重试。")
      : null,
    selectArtifact,
    loadRunArtifacts,
  };
}

function sameRequestedResources(
  left: readonly RequestedResourceRef[],
  right: readonly RequestedResourceRef[],
): boolean {
  if (left.length !== right.length) return false;
  return left.every((ref, index) => (
    ref.kind === right[index]?.kind && ref.id === right[index]?.id
  ));
}
