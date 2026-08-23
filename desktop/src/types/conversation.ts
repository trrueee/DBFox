import type { AgentArtifactPayload } from "../lib/api/types/artifact";
import type { RequestedResourceRef, RunProjection } from "../lib/api/generated/types.gen";

/**
 * Product projection types consumed by the timeline and artifact workspace.
 * The wire contract and its runtime validation are generated from OpenAPI;
 * conversationWireSchema is the only boundary that normalizes API defaults
 * into these stricter UI invariants.
 */
export type AgentRunStatus = RunProjection["status"];

export type CompletionDisposition = "complete" | "bounded_partial";
export type CompletionLimitationCode =
  | "TURN_BUDGET_REACHED"
  | "TOOL_BUDGET_REACHED"
  | "TOKEN_BUDGET_REACHED"
  | "COST_BUDGET_REACHED"
  | "DEADLINE_REACHED"
  | "INSUFFICIENT_EVIDENCE"
  | "TOOL_REJECTED"
  | "PROVIDER_LIMIT"
  | "NO_PROGRESS";
export type ConversationDeliveryMode = "queue" | "steer" | "cancel_and_replace";

export interface ConversationSummary {
  id: string;
  title: string;
  project_id?: string | null;
  updated_at: string | null;
  selected_artifact_id?: string | null;
  last_message?: string;
  run_status?: AgentRunStatus | null;
  message_count?: number;
  artifact_count?: number;
}

export interface ConversationRun {
  id: string;
  session_id: string;
  input_id: string;
  session_sequence: number;
  user_message_id: string;
  question: string;
  status: AgentRunStatus;
  version: number;
  current_turn_id?: string | null;
  cancel_requested: boolean;
  result: Record<string, unknown>;
  error: { code: string; message: string } | null;
}

export type RunItemType =
  | "message"
  | "plan"
  | "function_call"
  | "function_call_output"
  | "approval"
  | "question";
export type RunItemStatus =
  | "pending"
  | "in_progress"
  | "waiting"
  | "completed"
  | "failed"
  | "cancelled";

export interface ArtifactReference {
  artifact_id: string;
  label?: string | null;
}

export interface ConversationEvidence {
  id: string;
  claim_id: string;
  artifact_id: string;
  label: string;
  observed_at: string;
  locator: Record<string, unknown>;
  value?: unknown;
}

export interface ToolPresentation {
  title: string;
  category: "explore" | "query" | "visualize" | "manage";
  visibility: "summary" | "details" | "developer";
  progress: "indeterminate" | "determinate" | "none";
}

export interface ConversationPlanStep {
  id: string;
  title: string;
  status: "pending" | "in_progress" | "completed" | "blocked" | "skipped";
  evidence_required?: boolean;
  artifact_ids?: string[];
  note?: string | null;
}

interface RunItemBase<TType extends RunItemType, TPayload> {
  id: string;
  type: TType;
  session_id: string;
  run_id: string;
  turn_id?: string | null;
  sequence: number;
  revision: number;
  status: RunItemStatus;
  created_at: string;
  completed_at?: string | null;
  payload: TPayload;
}

export type MessageItem = RunItemBase<"message", {
  role: "user" | "assistant";
  phase?: "commentary" | "final_answer" | null;
  content: string;
  evidence: ConversationEvidence[];
  artifact_refs: ArtifactReference[];
  completion_disposition?: CompletionDisposition | null;
  limitation_codes: CompletionLimitationCode[];
}>;
export type UserMessageItem = MessageItem & { payload: MessageItem["payload"] & { role: "user" } };
export type AssistantMessageItem = MessageItem & {
  payload: MessageItem["payload"] & {
    role: "assistant";
    phase?: "commentary" | "final_answer" | null;
  };
};
export type PlanItem = RunItemBase<"plan", {
  objective: string;
  steps: ConversationPlanStep[];
  summary?: string | null;
}>;
export type FunctionCallItem = RunItemBase<"function_call", {
  call_id: string;
  name: string;
  tool_version: string;
  presentation: ToolPresentation;
  arguments: Record<string, unknown>;
  attempt: number;
}>;
export type FunctionCallOutputItem = RunItemBase<"function_call_output", {
  call_id: string;
  output: string;
  summary: string;
  artifact_refs: ArtifactReference[];
  error_code?: string | null;
  error_message?: string | null;
}>;
export type ApprovalItem = RunItemBase<"approval", {
  version: number;
  tool_invocation_id?: string | null;
  risk_level: "safe" | "warning" | "danger";
  reason?: string | null;
  requested_action: Record<string, unknown>;
  decision?: string | null;
  decision_note?: string | null;
}>;
export type QuestionItem = RunItemBase<"question", {
  version: number;
  question: string;
  reason: string;
  options: Array<{ value: string; label: string; description?: string | null }>;
  allow_free_text: boolean;
  response?: Record<string, unknown> | null;
}>;
export type ConversationRunItem =
  | MessageItem
  | PlanItem
  | FunctionCallItem
  | FunctionCallOutputItem
  | ApprovalItem
  | QuestionItem;

export type ConversationArtifactType =
  | "analysis_plan"
  | "sql"
  | "result_view"
  | "chart"
  | "markdown"
  | "safety"
  | "error";
export type ConversationArtifactVisibility = "primary" | "supporting" | "internal";

export interface ArtifactRelation {
  relation: "validated_by" | "executed_as" | "visualized_as" | "derived_from" | "supports";
  artifact_id: string;
}

export interface ConversationArtifact {
  id: string;
  session_id: string;
  run_id: string;
  turn_id?: string | null;
  semantic_key?: string | null;
  version: number;
  type: ConversationArtifactType;
  title: string;
  status: "creating" | "completed" | "failed" | "stale";
  visibility: ConversationArtifactVisibility;
  summary?: string | null;
  payload: AgentArtifactPayload;
  payload_ref?: string | null;
  provenance: Record<string, unknown>;
  relations: ArtifactRelation[];
}

export interface ConversationDetail {
  protocol_version: 2;
  id: string;
  title: string;
  project_id?: string | null;
  resource_intents: RequestedResourceRef[];
  selected_artifact_id?: string | null;
  context_epoch?: number;
  runs: ConversationRun[];
  items: ConversationRunItem[];
  pagination?: {
    items: { has_more: boolean; next_before_sequence: number | null };
    runs: { has_more: boolean; next_before_sequence: number | null };
  };
  cursor?: number;
}

export interface ConversationCreateInput {
  project_id: string;
  title?: string;
  resource_intents: RequestedResourceRef[];
}

export type RuntimeEventType =
  | "run.started"
  | "run.updated"
  | "run.completed"
  | "run.failed"
  | "run.cancelled"
  | "run.item.started"
  | "run.item.updated"
  | "run.item.completed"
  | "run.item.failed"
  | "run.item.cancelled";

export interface RuntimeEventEnvelope {
  event_id: string;
  event_type: RuntimeEventType;
  event_version: number;
  session_id: string;
  run_id?: string | null;
  turn_id?: string | null;
  sequence: number;
  timestamp: string;
  payload: { run?: ConversationRun; item?: ConversationRunItem };
}

export interface RunItemDeltaEnvelope {
  session_id: string;
  run_id: string;
  turn_id?: string | null;
  item_id: string;
  item_type: RunItemType;
  field: "content";
  revision: number;
  offset: number;
  content: string;
}

export type ConversationStreamEvent =
  | { kind: "event"; event: RuntimeEventEnvelope }
  | { kind: "delta"; delta: RunItemDeltaEnvelope };
