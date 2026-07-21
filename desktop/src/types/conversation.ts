export type ConversationRole = "user" | "assistant" | "system";
export type ConversationMessageStatus = "created" | "streaming" | "completed" | "failed" | "cancelled";
export type AgentRunStatus = "created" | "queued" | "running" | "waiting_approval" | "waiting_input" | "cancelling" | "completed" | "failed" | "cancelled";
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

export type ConversationArtifactType = "analysis_plan" | "agent_plan" | "query_plan" | "sql_suggestion" | "sql" | "result_view" | "chart" | "markdown" | "safety" | "error";

export interface ConversationSummary {
  id: string;
  title: string;
  datasource_id: string;
  updated_at: string | null;
  selected_artifact_id?: string | null;
  last_message?: string;
  message_count?: number;
  run_status?: AgentRunStatus | null;
  artifact_count?: number;
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

export interface ConversationEvidence {
  id?: string;
  session_id?: string;
  run_id?: string;
  claim_id?: string;
  artifact_id: string;
  label: string;
  query_fingerprint: string;
  observed_at: string;
  locator?: { kind: string; value: Record<string, unknown> };
  value?: unknown;
}

export interface ConversationApproval {
  id: string;
  run_id: string;
  session_id: string;
  turn_id?: string;
  tool_invocation_id?: string;
  tool_name: string;
  status: "pending" | "approved" | "rejected" | "expired";
  version?: number;
  risk_level: "safe" | "warning" | "danger";
  reason: string;
  requested_action: Record<string, unknown>;
  expires_at?: string | null;
  step_name?: string;
  policy_decision?: Record<string, unknown>;
  created_at?: string;
  decided_at?: string | null;
  decision_note?: string | null;
  decided_by?: string | null;
}

export interface ConversationRun {
  id: string;
  conversation_id: string;
  input_id?: string;
  session_sequence?: number;
  user_message_id?: string;
  assistant_message_id?: string;
  datasource_id: string;
  question: string;
  status: AgentRunStatus;
  completion_disposition?: CompletionDisposition | null;
  limitation_codes?: CompletionLimitationCode[];
  version?: number;
  current_turn_id?: string | null;
  cancel_requested?: boolean;
  error_code?: string | null;
  error_message?: string | null;
  answer?: {
    answer: string;
    evidence: ConversationEvidence[];
    key_findings?: string[];
    caveats?: string[];
    recommendations?: string[];
    follow_up_questions?: string[];
  } | null;
  approval?: ConversationApproval | null;
}

export interface ArtifactRelation {
  relation: "validated_by" | "executed_as" | "visualized_as" | "derived_from" | "supports";
  artifact_id: string;
}

export interface ConversationArtifact {
  id: string;
  conversation_id: string;
  run_id: string;
  turn_id?: string | null;
  message_id?: string | null;
  semantic_id?: string | null;
  version?: number;
  type: ConversationArtifactType;
  title: string;
  status: "creating" | "completed" | "failed" | "stale";
  sequence?: number | null;
  summary?: string | null;
  payload: AgentArtifactPayload;
  payload_ref?: string | null;
  provenance?: Record<string, unknown>;
  relations?: ArtifactRelation[];
  depends_on: string[];
  created_at?: string | null;
}

export interface ConversationActivity {
  id: string;
  run_id: string;
  turn_id: string;
  kind: string;
  title: string;
  summary?: string | null;
  status: "pending" | "running" | "completed" | "failed" | "waiting" | "cancelled";
  tool_invocation_id?: string;
  artifact_ids?: string[];
  started_at?: string | null;
  completed_at?: string | null;
  steps?: ConversationPlanStep[];
  current_step_id?: string | null;
}

export interface ConversationPlanStep {
  id: string;
  title: string;
  status: "pending" | "in_progress" | "completed" | "blocked" | "skipped";
  evidence_required: boolean;
  artifact_ids: string[];
  note?: string | null;
}

export interface ConversationQuestion {
  id: string;
  run_id: string;
  turn_id: string;
  status: "pending" | "answered" | "expired" | "cancelled";
  version: number;
  question: string;
  reason: string;
  options: Array<{ value: string; label: string; description?: string | null }>;
  allow_free_text: boolean;
  response?: unknown;
}

export interface ConversationDetail {
  protocol_version?: 1;
  id: string;
  title: string;
  datasource_id: string;
  context_tables: string[];
  selected_artifact_id?: string | null;
  context_epoch?: number;
  created_at?: string | null;
  updated_at?: string | null;
  messages: ConversationMessage[];
  runs: ConversationRun[];
  activities?: ConversationActivity[];
  artifacts: ConversationArtifact[];
  evidence?: ConversationEvidence[];
  approvals: ConversationApproval[];
  questions?: ConversationQuestion[];
  cursor?: number;
}

export interface ConversationCreateInput {
  datasource_id: string;
  title?: string;
  context_tables: string[];
}

export type RuntimeEventType =
  | "session.input.admitted"
  | "session.input.promoted"
  | "session.context.updated"
  | "run.created"
  | "run.started"
  | "run.cancelling"
  | "run.cancelled"
  | "run.completed"
  | "run.failed"
  | "turn.started"
  | "turn.completed"
  | "activity.updated"
  | "plan.updated"
  | "tool.requested"
  | "tool.running"
  | "tool.completed"
  | "tool.failed"
  | "approval.requested"
  | "approval.resolved"
  | "question.requested"
  | "question.resolved"
  | "observation.created"
  | "artifact.created"
  | "artifact.updated"
  | "artifact.selected"
  | "answer.completed";

export interface RuntimeEventEnvelope {
  event_id: string;
  event_type: RuntimeEventType;
  event_version: number;
  session_id: string;
  run_id?: string | null;
  turn_id?: string | null;
  sequence: number;
  timestamp: string;
  payload: Record<string, unknown>;
}

export interface LiveDeltaEnvelope {
  session_id: string;
  run_id: string;
  turn_id: string;
  channel: "answer" | "reasoning_summary" | "tool_progress";
  operation: "append" | "replace";
  live_id: string;
  channel_revision: number;
  correlation_id: string;
  content: string;
}

export type ConversationStreamEvent =
  | { kind: "event"; event: RuntimeEventEnvelope }
  | { kind: "delta"; delta: LiveDeltaEnvelope };
import type { AgentArtifactPayload } from "../lib/api/types/artifact";
