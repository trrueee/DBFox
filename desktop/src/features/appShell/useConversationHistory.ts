import { useState, useCallback, useEffect } from "react";
import type { Conversation } from "../../types/conversation";
import {
  deleteConversation,
  listConversations,
  migrateLegacyConversations,
  saveConversation,
} from "../conversation/conversationRepository";
import { useToast } from "../../components/Toast";

interface UseConversationHistoryProps {
  onToast?: (msg: string) => void;
  onDeleteSuccess?: (conversationId: string) => void;
}

export function useConversationHistory(props?: UseConversationHistoryProps) {
  const { toast } = useToast();
  const onToast = props?.onToast || toast;
  const onDeleteSuccess = props?.onDeleteSuccess;
  const [conversations, setConversations] = useState<Conversation[]>([]);

  const refreshConversations = useCallback(async () => {
    try {
      const history = await listConversations();
      setConversations(history);
    } catch {
      onToast("读取 SQLite 对话历史失败");
    }
  }, [onToast]);

  useEffect(() => {
    const init = async () => {
      await migrateLegacyConversations();
      await refreshConversations();
    };
    void init();
  }, [refreshConversations]);

  const persistConversation = useCallback(async (conversation: Conversation) => {
    try {
      await saveConversation(conversation);
      setConversations((prev) =>
        [conversation, ...prev.filter((item) => item.id !== conversation.id)].sort(
          (a, b) => b.updatedAt - a.updatedAt
        )
      );
    } catch {
      onToast("写入 SQLite 对话历史失败");
    }
  }, [onToast]);

  const deleteConversationById = useCallback(async (conversationId: string) => {
    try {
      await deleteConversation(conversationId);
      setConversations((prev) => prev.filter((item) => item.id !== conversationId));
      onToast("已删除对话历史");
      if (onDeleteSuccess) {
        onDeleteSuccess(conversationId);
      }
    } catch {
      onToast("删除 SQLite 对话历史失败");
    }
  }, [onToast, onDeleteSuccess]);

  return {
    conversations,
    setConversations,
    refreshConversations,
    persistConversation,
    deleteConversationById,
  };
}
