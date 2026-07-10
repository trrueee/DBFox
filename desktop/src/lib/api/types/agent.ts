import type { AgentArtifact } from "./artifact";

export interface AgentStep {
  name: string;
  status: "success" | "failed" | "skipped";
  input?: Record<string, unknown> | null;
  output?: Record<string, unknown> | null;
  error?: string | null;
  latency_ms: number;
  merge_strategy?: "reuse" | "new" | "always_new";
}

export interface AgentQueryPlan {
  analysis_goal: string;
  metrics: Array<Record<string, unknown>>;
  dimensions: Array<Record<string, unknown>>;
  filters: Array<Record<string, unknown>>;
  time_range?: Record<string, unknown> | null;
  candidate_tables: string[];
  assumptions: string[];
  risk_notes: string[];
  raw_plan?: Record<string, unknown> | null;
}

export interface AgentChartSuggestion {
  type: "bar" | "line" | "pie" | "table";
  x?: string | null;
  y?: string | null;
  reason?: string;
}

export interface AgentApproval {
  id: string;
  run_id: string;
  session_id: string;
  step_name: string;
  tool_name?: string | null;
  status: "pending" | "approved" | "rejected" | "expired";
  risk_level: "safe" | "warning" | "danger";
  reason?: string | null;
  policy_decision: Record<string, unknown>;
  requested_action?: Record<string, unknown> | null;
  created_at: string;
  expires_at?: string | null;
  decided_at?: string | null;
  decided_by?: string | null;
  decision_note?: string | null;
}

export interface AgentCheckpoint {
  id: string;
  run_id: string;
  session_id: string;
  checkpoint_index: number;
  status: string;
  current_step_name?: string | null;
  next_step_name?: string | null;
  created_at: string;
}

export interface FollowUpSuggestion {
  label: string;
  question: string;
  reason: string;
  action_type: "ask" | "chart" | "export" | "save_golden_sql";
}

export interface AgentContextArtifact {
  id: string;
  type: AgentArtifact["type"];
  title: string;
  summary?: string | null;
  payload?: Record<string, unknown>;
}

export interface AgentFollowUpContext {
  session_id?: string | null;
  parent_run_id?: string | null;
  previous_question?: string | null;
  previous_answer?: string | null;
  artifacts?: AgentContextArtifact[];
}

export interface AgentWorkspaceContext {
  project_id?: string | null;
  datasource_id: string;
  active_sql?: string | null;
  selected_sql?: string | null;
  last_query_result_preview?: Record<string, unknown> | null;
  last_error?: string | null;
  selected_table_ids?: string[];
  selected_table_names?: string[];
  selected_column_refs?: string[];
  selected_artifact_id?: string | null;
  recent_agent_run_id?: string | null;
  pending_approval_id?: string;
  pending_approval_status?: string;
  pending_approval_reason?: string;
  open_sql_tabs?: Array<Record<string, unknown>>;
  editor_annotations?: Array<Record<string, unknown>>;
  semantic_context?: Record<string, unknown>;
}

export interface AgentIntentPlan {
  intent:
    | "analysis"
    | "explain_sql"
    | "fix_sql"
    | "optimize_sql"
    | "rewrite_sql"
    | "explain_result"
    | "continue_from_artifact"
    | "explain_schema"
    | "unknown";
  confidence?: "low" | "medium" | "high";
  rationale?: string | null;
  requires_context?: string[];
}

export interface AgentPlanStep {
  id: string;
  tool_name: string;
  title?: string | null;
  args?: Record<string, unknown>;
  depends_on?: string[];
  required?: boolean;
}

export interface AgentPlanDraft {
  version: string;
  intent: AgentIntentPlan;
  steps: AgentPlanStep[];
  should_execute_sql?: boolean;
  context_summary?: string | null;
  safety_notes?: string[];
  model?: string | null;
  raw_response?: Record<string, unknown> | null;
}

export interface AgentAnswer {
  answer: string;
  key_findings: string[];
  evidence: Array<{
    artifact_id: string;
    label: string;
    value?: string | number | null;
  }>;
  caveats: string[];
  recommendations: string[];
  follow_up_questions: string[];
}

export interface AgentMessageBlock {
  block_id?: string | null;
  sequence?: number | null;
  type: "text" | "artifact_ref" | "answer" | "suggestions";
  content?: string | null;
  artifact_id?: string | null;
  display?: "compact" | "full" | null;
  answer?: AgentAnswer | null;
  suggestions?: FollowUpSuggestion[];
}

export interface AgentVisibleEvent {
  event_id?: string | null;
  sequence?: number | null;
  created_at_ms?: number | null;
  type:
    | "agent.narration.delta"
    | "agent.narration.completed"
    | "agent.artifact.created"
    | "agent.answer.delta"
    | "agent.answer.completed"
    | "agent.suggestions.created";
  content?: string | null;
  artifact?: AgentArtifact | null;
  answer?: AgentAnswer | null;
  suggestions?: FollowUpSuggestion[];
}

export interface AgentTraceEvent {
  id: string;
  run_id: string;
  event_type: string;
  node_name?: string | null;
  sequence: number;
  payload?: Record<string, unknown>;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Agent run — request config, response, runtime events (mirrors
// engine/agent_core/types.py AgentRunRequest/AgentRunResponse/AgentRuntimeEvent)
// ---------------------------------------------------------------------------

export interface AgentRunConfig {
  sessionId?: string | null;
  conversationId?: string | null;
  userMessageId?: string | null;
  assistantMessageId?: string | null;
  parentRunId?: string | null;
  followUpContext?: AgentFollowUpContext | null;
  llmCredentialId?: string;
  apiBase?: string;
  model?: string;
  workspaceContext?: AgentWorkspaceContext | null;
  optimizeRag?: boolean;
  execute?: boolean;
}

export interface AgentRunResponse {
  run_id: string;
  session_id: string;
  conversation_id?: string | null;
  user_message_id?: string | null;
  assistant_message_id?: string | null;
  parent_run_id?: string | null;
  success: boolean;
  status?: string | null;
  question: string;
  context_summary?: string | null;
  referenced_artifact_ids?: string[];
  query_plan?: Record<string, unknown> | null;
  sql?: string | null;
  safety?: Record<string, unknown> | null;
  execution?: Record<string, unknown> | null;
  explanation?: string | null;
  chart_suggestion?: Record<string, unknown> | null;
  answer?: AgentAnswer | null;
  suggestions?: FollowUpSuggestion[];
  artifacts: AgentArtifact[];
  message_blocks?: AgentMessageBlock[];
  events?: AgentVisibleEvent[];
  trace_events?: Array<Record<string, unknown>>;
  steps?: AgentStep[];
  error?: string | null;
  approval?: AgentApproval | null;
  checkpoint?: AgentCheckpoint | null;
  approval_context?: Record<string, unknown> | null;
  canvas?: Record<string, unknown> | null;
}

export type AgentRuntimeEventType =
  | "agent.run.started"
  | "agent.step.started"
  | "agent.step.completed"
  | "agent.progress.update"
  | "agent.context.update"
  | "agent.artifact.created"
  | "agent.artifact.delta"
  | "agent.answer.delta"
  | "agent.answer.completed"
  | "agent.approval.required"
  | "agent.approval.resolved"
  | "agent.checkpoint.saved"
  | "agent.run.waiting_approval"
  | "agent.run.resumed"
  | "agent.run.completed"
  | "agent.run.failed"
  | "agent.run.cancelled"
  | "agent.model.started"
  | "agent.model.completed"
  | "agent.tool.started"
  | "agent.tool.completed"
  | "agent.policy.allowed"
  | "agent.policy.blocked"
  | "agent.observe.applied"
  | "agent.finalized";

export interface AgentRuntimeEvent {
  event_id: string;
  run_id: string;
  conversation_id?: string | null;
  message_id?: string | null;
  user_message_id?: string | null;
  assistant_message_id?: string | null;
  sequence: number;
  created_at_ms: number;
  type: AgentRuntimeEventType;
  step?: Record<string, unknown> | null;
  artifact?: AgentArtifact | null;
  artifact_delta?: Record<string, unknown> | null;
  content?: string | null;
  // artifact_delta: { artifact_id: string; payload_merge: Record<string, unknown> }
  // list fields in payload_merge → append; scalar fields → replace
  answer?: AgentAnswer | null;
  response?: AgentRunResponse | null;
  approval?: AgentApproval | null;
  checkpoint?: AgentCheckpoint | null;
  error?: string | null;
  approval_context?: Record<string, unknown> | null;
  code?: string | null;
}

export interface AgentTaskLens {
  goal?: string;
  current_focus?: string;
  next_likely?: string;
  missing_evidence?: string[];
}

export interface AgentRunDraftState {
  runId?: string;
  status: "running" | "waiting_approval" | "completed" | "failed";
  question: string;
  events: AgentRuntimeEvent[];
  artifacts: AgentArtifact[];
  answer: AgentAnswer | null;
  response: AgentRunResponse | null;
  approval: AgentApproval | null;
  checkpoint: AgentCheckpoint | null;
  error: string | null;
  contextSummary?: string | null;
  taskLens?: AgentTaskLens | null;
}

export interface AgentSessionRunSummary {
  id: string;
  session_id: string;
  parent_run_id?: string | null;
  question?: string | null;
  status?: string | null;
  created_at?: string | null;
  [key: string]: unknown;
}


export interface AgentRuntimeEventRecord {
  id?: string;
  run_id?: string;
  sequence?: number;
  type?: string;
  payload?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface AgentTraceEventRecord {
  id?: string;
  run_id?: string;
  event_type?: string;
  sequence?: number;
  payload?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface AgentKernelThreadState {
  thread_id?: string;
  checkpoints?: AgentCheckpoint[];
  [key: string]: unknown;
}
