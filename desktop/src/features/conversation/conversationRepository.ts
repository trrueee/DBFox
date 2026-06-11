import type { Conversation, ConversationRecord } from "../../types/conversation";
import { conversationToRecord, recordToConversation } from "../../types/conversation";
import { request } from "../../lib/api/client";

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

async function listViaTauri(): Promise<Conversation[]> {
  const { invoke } = await import("@tauri-apps/api/core");
  const records = await invoke<ConversationRecord[]>("list_conversations");
  return records.map(recordToConversation);
}

async function saveViaTauri(conversation: Conversation): Promise<void> {
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("save_conversation", { conversation: conversationToRecord(conversation) });
}

async function deleteViaTauri(conversationId: string): Promise<void> {
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("delete_conversation", { id: conversationId });
}

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
  if (isTauriRuntime()) {
    return listViaTauri();
  }
  return listViaEngine();
}

export async function saveConversation(conversation: Conversation): Promise<void> {
  if (isTauriRuntime()) {
    await saveViaTauri(conversation);
    return;
  }
  await saveViaEngine(conversation);
}

export async function deleteConversation(conversationId: string): Promise<void> {
  if (isTauriRuntime()) {
    await deleteViaTauri(conversationId);
    return;
  }
  await deleteViaEngine(conversationId);
}
