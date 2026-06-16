export interface ConfirmationRequired {
  success: false;
  requires_confirmation: true;
  confirm_token: string;
  impact_summary: string;
  expected_confirm_text: string;
  message?: string;
}

export type DangerousOperationResult<T> = T | ConfirmationRequired;

export interface DataSource {
  id: string;
  project_id?: string;
  environment_id?: string;
  name: string;
  db_type?: string;
  host: string;
  port: number;
  database_name: string;
  username: string;
  connection_mode: string;
  is_read_only?: boolean;
  env?: string;
  status: string;
  ssh_enabled?: boolean;
  ssh_host?: string;
  ssh_port?: number;
  ssh_username?: string;
  ssh_pkey_path?: string;
  ssl_enabled?: boolean;
  ssl_ca_path?: string;
  ssl_cert_path?: string;
  ssl_key_path?: string;
  ssl_verify_identity?: boolean;
  last_test_at?: string;
  last_test_status?: string;
  last_test_error?: string;
  last_test_latency_ms?: number | null;
  last_test_readonly?: boolean | null;
  last_test_server_version?: string | null;
  last_test_tables_count?: number | null;
  last_test_warnings?: string[];
  last_sync_at?: string;
  last_sync_status?: string;
  last_sync_error?: string;
  created_at: string;
}

export interface DataSourceCreateParams {
  project_id?: string | null;
  name: string;
  db_type?: string;
  host?: string | null;
  port?: number | null;
  database_name: string;
  username?: string | null;
  password?: string | null;
  connection_mode?: string;
  is_read_only?: boolean;
  env?: string;
  ssh_enabled?: boolean;
  ssh_host?: string | null;
  ssh_port?: number;
  ssh_username?: string | null;
  ssh_password?: string | null;
  ssh_pkey_path?: string | null;
  ssh_pkey_passphrase?: string | null;
  ssl_enabled?: boolean;
  ssl_ca_path?: string | null;
  ssl_cert_path?: string | null;
  ssl_key_path?: string | null;
  ssl_verify_identity?: boolean;
}

export type DataSourceUpdateParams = DataSourceCreateParams;

/** Second-step confirmation payload for dangerous delete operations. */
export interface DeleteConfirm {
  token: string;
  text: string;
}

/** Consolidated CRUD actions for datasource management. */
export interface DataSourceActions {
  createDatasource: (params: DataSourceCreateParams) => Promise<DataSource>;
  updateDatasource: (id: string, params: DataSourceUpdateParams) => Promise<DataSource>;
  deleteDatasource: (id: string, confirm?: DeleteConfirm) => Promise<unknown>;
  syncSchema: (id: string) => Promise<unknown>;
  checkHealth: (id: string) => Promise<DataSourceHealthResult>;
}
export interface DataSourceHealthResult {
  ok: boolean;
  status: "success" | "failed";
  checkedAt?: string;
  latencyMs?: number;
  serverVersion?: string;
  readonly?: boolean | null;
  tablesCount?: number;
  warnings: string[];
  message: string;
  datasource: DataSource;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  status: string;
  datasource_count: number;
  created_at: string;
  updated_at: string;
}

export interface BackupRecord {
  id: string;
  project_id: string;
  datasource_id: string;
  environment_id?: string;
  label: string;
  backup_type: string;
  status: string;
  file_path?: string;
  file_size_bytes?: number;
  checksum_sha256?: string;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  error_message?: string;
  created_at?: string;
}

export interface SchemaTable {
  id: string;
  table_name: string;
  table_comment: string;
  table_type: string;
  row_count_estimate: number;
  columns_count: number;
  module_tag?: string;
}

export interface SchemaColumn {
  id: string;
  column_name: string;
  data_type: string;
  column_type: string;
  is_nullable: boolean;
  column_default: string;
  column_comment: string;
  is_primary_key: boolean;
  is_foreign_key: boolean;
  foreign_table_id?: string;
  foreign_column_id?: string;
}

export interface DataSourceTestResult {
  success?: boolean;
  message?: string;
  serverVersion?: string;
  readonly?: boolean;
  tablesCount?: number;
  warnings?: string[];
}

export interface SchemaSyncResult {
  success?: boolean;
  message?: string;
  syncedTables?: number;
  [key: string]: unknown;
}

export interface GoldenSqlRecord {
  id: string;
  data_source_id: string;
  question: string;
  golden_sql: string;
  created_at: string | null;
}

export interface BenchmarkDetail {
  golden_id: string;
  question: string;
  golden_sql: string;
  generated_sql: string;
  status: "passed" | "failed";
  match_type: "lexical" | "execution" | "none";
  latency_ms: number;
  error_message: string;
}

export interface BenchmarkResult {
  success: boolean;
  total_queries: number;
  passed_count: number;
  accuracy_rate: number;
  avg_latency_ms: number;
  details: BenchmarkDetail[];
}

export interface LlmStats {
  total_calls: number;
  success_count?: number;
  failed_count?: number;
  success_rate: number;
  avg_latency_ms: number;
  guardrail_total?: number;
  guardrail_blocked?: number;
  guardrail_approved?: number;
  guardrail_block_rate: number;
  chart_data: Array<{ date: string; value: number }>;
  model_dist: Array<{ name: string; value: number }>;
}

export interface GuardrailCheckResult {
  result: "pass" | "warn" | "reject";
  originalSql: string;
  safeSql: string;
  checks: Array<{
    rule: string;
    level: "warn" | "reject";
    message: string;
  }>;
  message: string;
}

export interface QueryPlan {
  intent: string;
  tables: string[];
  metrics: Array<{
    name: string;
    expression: string;
    source_column: string;
  }>;
  dimensions: Array<{
    name: string;
    column: string;
    transform: string | null;
  }>;
  filters: Array<{
    column: string;
    operator: string;
    value: string;
  }>;
  joins: Array<{
    left_table: string;
    right_table: string;
    condition: string;
  }>;
  order_by: string | null;
  limit: number;
  warnings?: string[];
  mode?: string;
}

export interface TrustGateResult {
  sql: string;
  schemaWarnings: string[];
  guardrail: GuardrailCheckResult;
  riskLevel: "safe" | "warning" | "danger";
  requiresConfirmation: boolean;
  messages: string[];
  canExecute?: boolean;
}

export interface GeneratedSqlResult {
  sql: string;
  model: string;
  latencyMs: number;
  guardrail: GuardrailCheckResult;
  trustGate?: TrustGateResult;
  mode: "offline" | "online";
  schemaValidationWarnings: string[];
  queryPlan?: QueryPlan;
  selectedTables?: string[];
  selectedColumns?: string[];
  schemaLinkingReasons?: unknown[];
  schemaContextSize?: number;
  originalSchemaTableCount?: number;
  selectedSchemaTableCount?: number;
}

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

export interface AgentArtifact {
  id: string;
  semantic_id?: string | null;
  type: "agent_plan" | "query_plan" | "sql" | "sql_suggestion" | "safety" | "table" | "chart" | "insight" | "recommendation" | "error";
  title: string;
  payload: Record<string, unknown>;
  presentation: {
    mode: "inline" | "dock" | "both" | "hidden";
    priority: number;
    collapsed?: boolean;
  };
  refs?: Record<string, unknown>;
  produced_by_step?: string | null;
  depends_on?: string[];
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

export interface ResultProfile {
  row_count: number;
  column_profiles: Record<string, Record<string, unknown>>;
  detected_patterns: string[];
  notable_facts: string[];
  anomalies: string[];
  limitations: string[];
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
  parentRunId?: string | null;
  followUpContext?: AgentFollowUpContext | null;
  apiKey?: string;
  apiBase?: string;
  model?: string;
  workspaceContext?: AgentWorkspaceContext | null;
  optimizeRag?: boolean;
  execute?: boolean;
}

export interface AgentRunResponse {
  run_id: string;
  session_id: string;
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
  result_profile?: ResultProfile | null;
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
  | "agent.answer.completed"
  | "agent.approval.required"
  | "agent.approval.resolved"
  | "agent.checkpoint.saved"
  | "agent.run.waiting_approval"
  | "agent.run.resumed"
  | "agent.run.completed"
  | "agent.run.failed"
  | "agent.run.cancelled";

export interface AgentRuntimeEvent {
  event_id: string;
  run_id: string;
  sequence: number;
  created_at_ms: number;
  type: AgentRuntimeEventType;
  step?: Record<string, unknown> | null;
  artifact?: AgentArtifact | null;
  artifact_delta?: Record<string, unknown> | null;
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

export interface AgentArtifactRecord {
  id: string;
  run_id?: string;
  type?: string;
  title?: string;
  payload?: Record<string, unknown>;
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

export interface QueryResult {
  columns: string[];
  rows: Record<string, unknown>[];
  rowCount: number;
  latencyMs: number;
  totalMs?: number;
  success?: boolean;
}

export interface ERNode {
  id: string;
  label: string;
  fields: Array<{
    name: string;
    type: string;
    is_pk: boolean;
    is_fk: boolean;
    comment?: string;
  }>;
  comment: string;
  row_count_estimate?: number;
  module_tag: string;
}

export interface EREdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string;
  targetHandle?: string;
  edge_type?: "real" | "inferred";
  label?: string;
}

export interface ERDiagramData {
  nodes: ERNode[];
  edges: EREdge[];
}
