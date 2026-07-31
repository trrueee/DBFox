import { useMemo, useRef } from "react";
import { useMutation } from "@tanstack/react-query";
import { getUserErrorMessage } from "../../../lib/api/client";
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
  } | null>(null);
  const detail = useConversationStore((state) => state.detailById[conversationId]);
  const artifactsById = useConversationStore((state) => state.artifactsById);
  const openConversationAction = useConversationStore((state) => state.openConversation);
  const sendMessageAction = useConversationStore((state) => state.sendMessage);
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
    }: {
      targetConversationId: string;
      content: string;
      mode: ConversationDeliveryMode;
      idempotencyKey: string;
    }) => sendMessageAction(targetConversationId, content, mode, idempotencyKey),
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
    sendMessage: async (
      targetConversationId: string,
      content: string,
      mode: ConversationDeliveryMode,
    ) => {
      let intent = pendingSendIntent.current;
      if (
        !intent
        || intent.conversationId !== targetConversationId
        || intent.content !== content
        || intent.mode !== mode
      ) {
        intent = {
          conversationId: targetConversationId,
          content,
          mode,
          idempotencyKey: globalThis.crypto.randomUUID(),
        };
        pendingSendIntent.current = intent;
      }
      await sendMutation.mutateAsync({
        targetConversationId,
        content,
        mode,
        idempotencyKey: intent.idempotencyKey,
      });
      if (pendingSendIntent.current === intent) pendingSendIntent.current = null;
    },
    sending: sendMutation.isPending,
    sendError: sendMutation.error
      ? getUserErrorMessage(sendMutation.error, "消息发送失败，请重试。")
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
