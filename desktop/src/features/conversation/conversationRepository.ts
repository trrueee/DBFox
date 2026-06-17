import type { Conversation, ConversationRecord } from "../../types/conversation";
import { conversationToRecord, recordToConversation } from "../../types/conversation";
import { request } from "../../lib/api/client";

async function listViaEngine(): Promise<Conversation[]> {
  const records = await request<ConversationRecord[]>("/conversations");
  return records.map(recordToConversation);
}

async function saveViaEngine(conversation: Conversation): Promise<void> {
  const record = conversationToRecord(conversation);
  await request(`/conversations/${encodeURIComponent(record.id)}`, {
    method: "PUT",
    body: JSON.stringify(record),
  });
}

async function deleteViaEngine(conversationId: string): Promise<void> {
  await request(`/conversations/${encodeURIComponent(conversationId)}`, {
    method: "DELETE",
  });
}

export async function listConversations(): Promise<Conversation[]> {
  return listViaEngine();
}

export async function saveConversation(conversation: Conversation): Promise<void> {
  await saveViaEngine(conversation);
}

export async function deleteConversation(conversationId: string): Promise<void> {
  await deleteViaEngine(conversationId);
}
