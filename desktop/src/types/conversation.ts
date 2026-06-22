import type { AgentAnswer, AgentApproval, AgentRuntimeEvent } from "../lib/api/types";

export type ConversationRole = "user" | "assistant" | "system";
export type ConversationMessageStatus = "created" | "streaming" | "completed" | "failed" | "cancelled";
export type AgentRunStatus = "queued" | "running" | "waiting_approval" | "completed" | "failed" | "cancelled";
export type ConversationArtifactType = "sql" | "table" | "result_view" | "chart" | "markdown" | "agent_plan" | "query_plan" | "sql_suggestion" | "safety" | "error";

export interface ConversationSummary {
  id: string;
  title: string;
  datasource_id: string;
  updated_at: string | null;
  last_message: string;
  message_count: number;
  run_status: AgentRunStatus | null;
  artifact_count: number;
}

export interface ConversationMessage {
  id: string;
  conversation_id: string;
  role: ConversationRole;
  content: string;
  status: ConversationMessageStatus;
  sequence: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface ConversationRun {
  id: string;
  conversation_id: string;
  parent_run_id?: string | null;
  user_message_id?: string | null;
  assistant_message_id?: string | null;
  datasource_id: string;
  question: string;
  status: AgentRunStatus;
  error_code?: string | null;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  answer?: AgentAnswer | null;
  approval?: AgentApproval | null;
  events?: AgentRuntimeEvent[];
}

export interface ConversationArtifact {
  id: string;
  conversation_id: string;
  run_id: string;
  message_id?: string | null;
  semantic_id?: string | null;
  type: ConversationArtifactType;
  title: string;
  status: "created" | "running" | "completed" | "failed";
  sequence?: number | null;
  payload: Record<string, unknown>;
  presentation?: Record<string, unknown>;
  depends_on: string[];
  refs?: Record<string, unknown>;
  created_at?: string | null;
}

export interface ConversationDetail {
  id: string;
  title: string;
  datasource_id: string;
  context_tables: string[];
  created_at: string | null;
  updated_at: string | null;
  messages: ConversationMessage[];
  runs: ConversationRun[];
  artifacts: ConversationArtifact[];
  approvals: unknown[];
}

export interface ConversationCreateInput {
  datasource_id: string;
  title?: string;
  context_tables: string[];
}

export interface ConversationMessageInput {
  content: string;
  api_key?: string;
  api_base?: string;
  model_name?: string;
  execute?: boolean;
}

export interface ConversationMessageStart {
  conversation_id: string;
  user_message_id: string;
  assistant_message_id: string;
  run_id: string | null;
}

export type ConversationStreamEvent = AgentRuntimeEvent & {
  conversation_id?: string | null;
  message_id?: string | null;
  user_message_id?: string | null;
  assistant_message_id?: string | null;
};
