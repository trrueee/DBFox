import { invoke } from "@tauri-apps/api/core";
import type { Conversation, ConversationRecord } from "../../types/conversation";
import { conversationToRecord, recordToConversation } from "../../types/conversation";

export async function listConversations(): Promise<Conversation[]> {
  const records = await invoke<ConversationRecord[]>("list_conversations");
  return records.map(recordToConversation);
}

export async function saveConversation(conversation: Conversation): Promise<void> {
  await invoke("save_conversation", { conversation: conversationToRecord(conversation) });
}

export async function deleteConversation(conversationId: string): Promise<void> {
  await invoke("delete_conversation", { id: conversationId });
}
