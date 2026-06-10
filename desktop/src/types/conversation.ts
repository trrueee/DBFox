import type { AgentArtifact } from "./agentArtifact";

export type ConversationRole = "user" | "assistant";

export interface ConversationMessage {
  id: string;
  role: ConversationRole;
  content: string;
  createdAt: number;
}

export interface Conversation {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  contextTables: string[];
  messages: ConversationMessage[];
  artifacts: AgentArtifact[];
}

export interface ConversationRecord {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  context_tables_json: string;
  messages_json: string;
  artifacts_json: string;
}

export function conversationToRecord(conversation: Conversation): ConversationRecord {
  return {
    id: conversation.id,
    title: conversation.title,
    created_at: conversation.createdAt,
    updated_at: conversation.updatedAt,
    context_tables_json: JSON.stringify(conversation.contextTables),
    messages_json: JSON.stringify(conversation.messages),
    artifacts_json: JSON.stringify(conversation.artifacts),
  };
}

export function recordToConversation(record: ConversationRecord): Conversation {
  return {
    id: record.id,
    title: record.title,
    createdAt: record.created_at,
    updatedAt: record.updated_at,
    contextTables: safeJsonParse<string[]>(record.context_tables_json, []),
    messages: safeJsonParse<ConversationMessage[]>(record.messages_json, []),
    artifacts: safeJsonParse<AgentArtifact[]>(record.artifacts_json, []),
  };
}

function safeJsonParse<T>(text: string, fallback: T): T {
  try {
    return JSON.parse(text) as T;
  } catch {
    return fallback;
  }
}
