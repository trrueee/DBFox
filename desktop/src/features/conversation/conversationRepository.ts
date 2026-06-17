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

export async function migrateLegacyConversations(): Promise<void> {
  if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) {
    return;
  }
  if (localStorage.getItem("dbfox_legacy_conversations_migrated") === "true") {
    return;
  }
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const records = await invoke<ConversationRecord[]>("list_conversations");
    if (records && records.length > 0) {
      for (const record of records) {
        const conversation = recordToConversation(record);
        await saveConversation(conversation);
      }
    }
    localStorage.setItem("dbfox_legacy_conversations_migrated", "true");
  } catch (err) {
    console.error("Failed to migrate legacy conversations:", err);
  }
}
