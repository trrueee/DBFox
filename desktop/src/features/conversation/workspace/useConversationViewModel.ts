import { useMemo } from "react";
import { useConversationStore } from "../../../stores/conversationStore";
import type { ConversationArtifact, ConversationMessage, ConversationRun } from "../../../types/conversation";

export function useConversationViewModel(conversationId: string) {
  const detail = useConversationStore((state) => state.detailById[conversationId]);
  const messagesById = useConversationStore((state) => state.messagesById);
  const runsById = useConversationStore((state) => state.runsById);
  const artifactsById = useConversationStore((state) => state.artifactsById);
  const openConversation = useConversationStore((state) => state.openConversation);
  const sendMessage = useConversationStore((state) => state.sendMessage);
  const cancelRun = useConversationStore((state) => state.cancelRun);
  const resolveApproval = useConversationStore((state) => state.resolveApproval);

  const messages = useMemo<ConversationMessage[]>(
    () => detail?.messages.map((item) => messagesById[item.id] || item) || [],
    [detail, messagesById],
  );

  const runs = useMemo<ConversationRun[]>(
    () => detail?.runs.map((item) => runsById[item.id] || item) || [],
    [detail, runsById],
  );

  const artifacts = useMemo<ConversationArtifact[]>(
    () =>
      detail?.artifacts.map((item) => artifactsById[item.id] || item) ||
      Object.values(artifactsById).filter((item) => item.conversation_id === conversationId),
    [artifactsById, conversationId, detail],
  );

  const runningRun = useMemo(
    () => runs.find((run) => run.status === "running" || run.status === "waiting_approval") || null,
    [runs],
  );

  return {
    detail,
    messages,
    runs,
    artifacts,
    runningRun,
    openConversation,
    sendMessage,
    cancelRun,
    resolveApproval,
  };
}
