import { BASE_URL, ENGINE_TOKEN, request } from "../../lib/api/client";
import type {
  ConversationCreateInput,
  ConversationDetail,
  ConversationMessageInput,
  ConversationMessageStart,
  ConversationStreamEvent,
  ConversationSummary,
} from "../../types/conversation";

export const listConversations = () => request<ConversationSummary[]>("/conversations");

export const createConversation = (input: ConversationCreateInput) =>
  request<ConversationDetail>("/conversations", {
    method: "POST",
    body: JSON.stringify(input),
  });

export const getConversation = (conversationId: string) =>
  request<ConversationDetail>(`/conversations/${encodeURIComponent(conversationId)}`);

export const patchConversation = (
  conversationId: string,
  patch: { title?: string; context_tables?: string[]; archived?: boolean },
) =>
  request<ConversationDetail>(`/conversations/${encodeURIComponent(conversationId)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });

export const deleteConversation = (conversationId: string) =>
  request<{ status: "ok" }>(`/conversations/${encodeURIComponent(conversationId)}`, { method: "DELETE" });

export const prepareConversationMessage = (conversationId: string, input: ConversationMessageInput) =>
  request<ConversationMessageStart>(`/conversations/${encodeURIComponent(conversationId)}/messages`, {
    method: "POST",
    body: JSON.stringify(input),
  });

function parseSseEvent(rawEvent: string): ConversationStreamEvent | null {
  const dataLines = rawEvent
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart());
  if (dataLines.length === 0) return null;
  try {
    return JSON.parse(dataLines.join("\n")) as ConversationStreamEvent;
  } catch {
    return null;
  }
}

export async function startConversationMessageStream(
  conversationId: string,
  input: ConversationMessageInput,
  options?: { signal?: AbortSignal; onEvent?: (event: ConversationStreamEvent) => void },
): Promise<void> {
  const response = await fetch(`${BASE_URL}/conversations/${encodeURIComponent(conversationId)}/messages/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Local-Token": ENGINE_TOKEN },
    body: JSON.stringify(input),
    signal: options?.signal,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Conversation stream failed.");
  }
  if (!response.body) throw new Error("Conversation stream is not supported.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const rawEvent = buffer.slice(0, boundary).trim();
        buffer = buffer.slice(boundary + 2);
        if (rawEvent) {
          const event = parseSseEvent(rawEvent);
          if (event) options?.onEvent?.(event);
        }
        boundary = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.releaseLock();
  }
}
