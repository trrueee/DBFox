const ENGINE_PORT = import.meta.env.VITE_LOCAL_ENGINE_PORT || "18625";
const ENGINE_TOKEN = import.meta.env.VITE_LOCAL_ENGINE_TOKEN || "";
const BASE_URL = `http://127.0.0.1:${ENGINE_PORT}/api/v1`;

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Local-Token": ENGINE_TOKEN,
      ...(options.headers || {}),
    },
  });

  const text = await response.text();
  const payload = (() => { if (!text) return null; try { return JSON.parse(text); } catch { return { message: text }; } })();
  if (!response.ok) {
    const error = new Error(payload?.detail?.message || payload?.message || "Request failed") as Error & {
      code?: string;
      checks?: unknown[];
    };
    error.code = payload?.detail?.code || payload?.code;
    error.checks = payload?.detail?.checks || payload?.checks || [];
    throw error;
  }

  return payload as T;
}

export interface ConfirmationRequired {
  success: false;
  requires_confirmation: true;
  confirm_token: string;
  impact_summary: string;
  expected_confirm_text: string;
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

export interface DatabaseEnvironment {
  id: string;
  project_id: string;
  name: string;
  runtime: string;
  engine_type: string;
  engine_version: string;
  image: string;
  container_name: string;
  host: string;
  port: number;
  database_name: string;
  username: string;
  datasource_id?: string;
  status: string;
  last_health_status?: string;
  last_health_at?: string;
  last_error?: string;
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

export interface TableDesignDraft {
  id: string;
  project_id: string;
  table_name: string;
  table_comment?: string;
  columns: any[];
  indexes: any[];
  created_at?: string;
  updated_at?: string;
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

export interface TableDesignColumn {
  name: string;
  type: string;
  nullable: boolean;
  default_value?: string | null;
  primary_key: boolean;
  auto_increment: boolean;
  comment?: string | null;
}

export interface TableDesignIndex {
  name?: string | null;
  columns: string[];
  unique: boolean;
}

export interface TableDesignDDLRequest {
  table_name: string;
  table_comment?: string | null;
  engine?: string;
  charset?: string;
  collation?: string;
  columns: TableDesignColumn[];
  indexes?: TableDesignIndex[];
}

export interface TableDesignDDLResponse {
  ddl: string;
  warnings: string[];
  summary: {
    tableName: string;
    columns: number;
    indexes: number;
    primaryKey: string[];
    dialect: string;
  };
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
  type: "query_plan" | "sql" | "safety" | "table" | "chart" | "insight" | "recommendation" | "error";
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
  event_id?: string | null;
  sequence?: number | null;
  created_at_ms?: number | null;
  type: "agent.trace.step_started" | "agent.trace.step_completed";
  step_id: string;
  name: string;
  status?: "success" | "failed" | "skipped" | null;
  input?: Record<string, unknown> | null;
  output?: Record<string, unknown> | null;
  error?: string | null;
  latency_ms?: number | null;
}

export interface AgentRunResponse {
  run_id: string;
  session_id: string;
  parent_run_id?: string | null;
  success: boolean;
  question: string;
  context_summary?: string | null;
  referenced_artifact_ids?: string[];
  query_plan?: AgentQueryPlan | null;
  sql?: string | null;
  safety?: Record<string, unknown> | null;
  execution?: {
    success?: boolean;
    columns?: string[];
    rows?: Array<Record<string, unknown>>;
    rowCount?: number;
    latencyMs?: number;
    warnings?: string[];
    reason?: string;
    revise_suggestion?: string;
  } | null;
  explanation?: string | null;
  chart_suggestion?: AgentChartSuggestion | null;
  result_profile?: ResultProfile | null;
  answer?: AgentAnswer | null;
  suggestions?: FollowUpSuggestion[];
  artifacts?: AgentArtifact[];
  message_blocks?: AgentMessageBlock[];
  events?: AgentVisibleEvent[];
  trace_events?: AgentTraceEvent[];
  steps: AgentStep[];
  error?: string | null;
}

export interface AgentRunConfig {
  apiKey?: string;
  apiBase?: string;
  model?: string;
  optimizeRag?: boolean;
  execute?: boolean;
  sessionId?: string;
  parentRunId?: string;
  followUpContext?: AgentFollowUpContext;
}

export type AgentRuntimeEventType =
  | "agent.run.started"
  | "agent.step.started"
  | "agent.step.completed"
  | "agent.artifact.created"
  | "agent.answer.completed"
  | "agent.run.completed"
  | "agent.run.failed";

export interface AgentRuntimeEvent {
  event_id: string;
  run_id: string;
  sequence: number;
  created_at_ms: number;
  type: AgentRuntimeEventType;
  step?: (Partial<AgentStep> & Record<string, unknown>) | null;
  artifact?: AgentArtifact | null;
  answer?: AgentAnswer | null;
  response?: AgentRunResponse | null;
  error?: string | null;
}

export interface AgentRunDraftState {
  runId?: string;
  status: "idle" | "running" | "failed" | "completed";
  question: string;
  events: AgentRuntimeEvent[];
  artifacts: AgentArtifact[];
  answer?: AgentAnswer | null;
  response?: AgentRunResponse | null;
  error?: string | null;
}

export function createAgentRunDraft(question: string): AgentRunDraftState {
  return {
    status: "running",
    question,
    events: [],
    artifacts: [],
    answer: null,
    response: null,
    error: null,
  };
}

export function reduceAgentRuntimeEvent(draft: AgentRunDraftState, event: AgentRuntimeEvent): AgentRunDraftState {
  const next: AgentRunDraftState = {
    ...draft,
    runId: event.run_id || draft.runId,
    events: [...draft.events, event],
  };

  if (event.type === "agent.run.started") {
    const question = typeof event.step?.question === "string" ? event.step.question : draft.question;
    return { ...next, question, status: "running", error: null };
  }

  if (event.type === "agent.artifact.created" && event.artifact) {
    return {
      ...next,
      artifacts: mergeArtifacts(draft.artifacts, [event.artifact]),
    };
  }

  if (event.type === "agent.answer.completed") {
    return { ...next, answer: event.answer || draft.answer || null };
  }

  if (event.type === "agent.run.completed" && event.response) {
    return {
      ...next,
      status: "completed",
      response: event.response,
      answer: event.response.answer || draft.answer || null,
      artifacts: mergeArtifacts(draft.artifacts, event.response.artifacts || []),
      error: null,
    };
  }

  if (event.type === "agent.run.failed") {
    return {
      ...next,
      status: "failed",
      response: event.response || draft.response || null,
      answer: event.response?.answer || draft.answer || null,
      artifacts: mergeArtifacts(draft.artifacts, event.response?.artifacts || []),
      error: event.error || event.response?.error || "Agent stream failed.",
    };
  }

  return next;
}

function mergeArtifacts(current: AgentArtifact[], incoming: AgentArtifact[]): AgentArtifact[] {
  const byId = new Map(current.map((artifact) => [artifact.id, artifact]));
  for (const artifact of incoming) {
    byId.set(artifact.id, artifact);
  }
  return Array.from(byId.values());
}

function buildAgentRunPayload(datasourceId: string, question: string, config?: AgentRunConfig) {
  return {
    datasource_id: datasourceId,
    question,
    session_id: config?.sessionId || config?.followUpContext?.session_id,
    parent_run_id: config?.parentRunId || config?.followUpContext?.parent_run_id,
    follow_up_context: config?.followUpContext,
    api_key: config?.apiKey,
    api_base: config?.apiBase,
    model_name: config?.model,
    optimize_rag: config?.optimizeRag ?? true,
    execute: config?.execute ?? true,
  };
}

function parseSseEvent(rawEvent: string): AgentRuntimeEvent | null {
  const dataLines = rawEvent
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart());
  if (dataLines.length === 0) return null;
  return JSON.parse(dataLines.join("\n")) as AgentRuntimeEvent;
}

async function streamAgentRun(
  datasourceId: string,
  question: string,
  config?: AgentRunConfig,
  options?: { signal?: AbortSignal; onEvent?: (event: AgentRuntimeEvent) => void },
): Promise<AgentRunResponse> {
  const response = await fetch(`${BASE_URL}/query/agent-run/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Local-Token": ENGINE_TOKEN,
    },
    body: JSON.stringify(buildAgentRunPayload(datasourceId, question, config)),
    signal: options?.signal,
  });

  if (!response.ok) {
    const text = await response.text();
    const payload = (() => { if (!text) return null; try { return JSON.parse(text); } catch { return { message: text }; } })();
    const error = new Error(payload?.detail?.message || payload?.message || "Request failed") as Error & { code?: string; checks?: unknown[] };
    error.code = payload?.detail?.code || payload?.code;
    error.checks = payload?.detail?.checks || payload?.checks || [];
    throw error;
  }

  if (!response.body) {
    throw new Error("Agent stream is not supported by this browser runtime.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResponse: AgentRunResponse | null = null;

  const processText = (text: string) => {
    buffer += text;
    buffer = buffer.replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const rawEvent = buffer.slice(0, boundary).trim();
      buffer = buffer.slice(boundary + 2);
      if (rawEvent) {
        const event = parseSseEvent(rawEvent);
        if (event) {
          options?.onEvent?.(event);
          if (event.response) {
            finalResponse = event.response;
          } else if (event.type === "agent.run.failed") {
            throw new Error(event.error || "Agent stream failed.");
          }
        }
      }
      boundary = buffer.indexOf("\n\n");
    }
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      processText(decoder.decode(value, { stream: true }));
    }
    const remaining = decoder.decode();
    if (remaining) processText(remaining);
    if (buffer.trim()) processText("\n\n");
  } finally {
    reader.releaseLock();
  }

  if (!finalResponse) {
    throw new Error("Agent stream ended without a final response.");
  }
  return finalResponse;
}

export interface QueryResult {
  success: boolean;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  rowCount: number;
  latencyMs: number;
  guardrail: GuardrailCheckResult;
  historyId: string;
  executionId?: string;
  truncated?: boolean;
  responseBytes?: number;
  maxResponseBytes?: number;
  warnings?: string[];
  connectMs?: number;
  guardrailMs?: number;
  executeMs?: number;
  fetchMs?: number;
  serializeMs?: number;
  totalMs?: number;
}

export interface QueryHistory {
  id: string;
  question: string;
  submitted_sql: string;
  generated_sql: string;
  safe_sql: string;
  executed_sql: string;
  guardrail_result: "pass" | "warn" | "reject";
  guardrail_checks?: string;
  execution_status: "success" | "failed" | "timeout" | "cancelled";
  execution_time_ms: number;
  rows_returned: number;
  columns_returned: number;
  error_message: string;
  created_at: string;
}

export interface ERDiagramData {
  nodes: Array<{
    id: string;
    label: string;
    comment: string;
    module_tag: string;
    fields: Array<{
      name: string;
      type: string;
      is_pk: boolean;
      is_fk: boolean;
      comment: string;
    }>;
  }>;
  edges: Array<{
    id: string;
    source: string;
    sourceHandle: string;
    target: string;
    targetHandle: string;
    label: string;
    edge_type: "real" | "inferred";
  }>;
}

export const api = {
  listProjects: () => request<Project[]>("/projects"),

  createProject: (params: { name: string; description?: string }) =>
    request<Project>("/projects", { method: "POST", body: JSON.stringify(params) }),

  listEnvironments: (projectId: string) =>
    request<DatabaseEnvironment[]>(`/projects/${encodeURIComponent(projectId)}/environments`),

  createLocalMysqlEnvironment: (params: { project_id: string; name: string; mysql_version?: string; seed_demo?: boolean }) =>
    request<DatabaseEnvironment>("/environments/local-mysql", { method: "POST", body: JSON.stringify(params) }),

  startEnvironment: (environmentId: string) =>
    request<DatabaseEnvironment>(`/environments/${environmentId}/start`, { method: "POST" }),

  stopEnvironment: (environmentId: string) =>
    request<DatabaseEnvironment>(`/environments/${environmentId}/stop`, { method: "POST" }),

  checkEnvironmentHealth: (environmentId: string) =>
    request<{ environment: DatabaseEnvironment; health: any }>(`/environments/${environmentId}/health`),

  getEnvironmentLogs: (environmentId: string, tail = 200) =>
    request<{ environmentId: string; logs: string }>(`/environments/${environmentId}/logs?tail=${tail}`),

  checkDockerStatus: () =>
    request<{ available: boolean }>("/environments/docker-status"),

  destroyEnvironment: (environmentId: string) =>
    request<{ ok: boolean; message: string }>(`/environments/${environmentId}`, { method: "DELETE" }),

  rebuildEnvironment: (environmentId: string) =>
    request<DatabaseEnvironment>(`/environments/${environmentId}/rebuild`, { method: "POST" }),

  listBackups: (projectId: string, datasourceId?: string) =>
    request<BackupRecord[]>(
      `/projects/${encodeURIComponent(projectId)}/backups${
        datasourceId ? `?datasource_id=${encodeURIComponent(datasourceId)}` : ""
      }`,
    ),

  createBackup: (datasourceId: string, label?: string) =>
    request<BackupRecord>("/backups", {
      method: "POST",
      body: JSON.stringify({ datasource_id: datasourceId, label }),
    }),

  restorePrecheck: (backupId: string) =>
    request<{
      ok: boolean;
      warnings: string[];
      errors: string[];
      filePath: string;
      fileSizeBytes: number;
      checksumSha256?: string;
    }>(`/backups/${backupId}/restore-precheck`, { method: "POST" }),

  restoreBackup: (backupId: string, confirm?: { token: string; text: string }) => {
    const query = confirm ? `?confirm_token=${encodeURIComponent(confirm.token)}&confirm_text=${encodeURIComponent(confirm.text)}` : "";
    return request<DangerousOperationResult<{
      success: boolean;
      backup_id: string;
      datasource_id: string;
      database_name: string;
      message: string;
    }>>(`/backups/${backupId}/restore${query}`, { method: "POST" });
  },

  testConnection: (params: unknown) =>
    request<any>("/datasources/test", { method: "POST", body: JSON.stringify(params) }),

  createDatasource: (params: unknown) =>
    request<DataSource>("/datasources", { method: "POST", body: JSON.stringify(params) }),

  listDatasources: (projectId?: string) =>
    request<DataSource[]>(projectId ? `/datasources?project_id=${encodeURIComponent(projectId)}` : "/datasources"),

  checkDatasourceHealth: (id: string) =>
    request<DataSourceHealthResult>(`/datasources/${id}/health`, { method: "POST" }),

  deleteDatasource: (id: string, confirm?: { token: string; text: string }) => {
    const query = confirm ? `?confirm_token=${encodeURIComponent(confirm.token)}&confirm_text=${encodeURIComponent(confirm.text)}` : "";
    return request<DangerousOperationResult<{ success: boolean; message: string }>>(`/datasources/${id}${query}`, { method: "DELETE" });
  },

  syncSchema: (id: string) =>
    request<any>(`/datasources/${id}/sync`, { method: "POST" }),

  listTables: (datasourceId: string) =>
    request<SchemaTable[]>(`/schema/tables?datasource_id=${datasourceId}`),

  listColumns: (tableId: string) =>
    request<SchemaColumn[]>(`/schema/tables/${tableId}/columns`),

  getERDiagram: (datasourceId: string) =>
    request<ERDiagramData>(`/schema/er-diagram?datasource_id=${datasourceId}`),

  generateCreateTableDDL: (params: TableDesignDDLRequest) =>
    request<TableDesignDDLResponse>("/schema/design/create-table-ddl", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  generateSchemaAlteration: (params: {
    datasource_id: string;
    instruction: string;
    api_key?: string;
    api_base?: string;
    model?: string;
  }) =>
    request<{ ddl: string; model: string; mode: string }>("/schema/design/ai-modify", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  executeTableDesignDDL: (datasourceId: string, ddl: string, confirm?: { token: string; text: string }) =>
    request<DangerousOperationResult<any>>("/schema/design/execute-ddl", {
      method: "POST",
      body: JSON.stringify({
        datasource_id: datasourceId,
        ddl,
        confirm_token: confirm?.token,
        confirm_text: confirm?.text,
      }),
    }),

  generateTestData: (params: { datasource_id: string; table_name: string; row_count?: number; language?: string }, confirm?: { token: string; text: string }) =>
    request<DangerousOperationResult<{ success: boolean; tableName: string; insertedRows: number; latencyMs: number; message: string }>>("/schema/generate-test-data", {
      method: "POST",
      body: JSON.stringify({
        ...params,
        confirm_token: confirm?.token,
        confirm_text: confirm?.text,
      }),
    }),

  validateSql: (sql: string, options?: { datasourceId?: string; signal?: AbortSignal }) =>
    request<GuardrailCheckResult>("/query/validate", {
      method: "POST",
      body: JSON.stringify({ sql, datasource_id: options?.datasourceId }),
      signal: options?.signal,
    }),

  executeSql: (datasourceId: string, sql: string, question?: string, executionId?: string, signal?: AbortSignal) =>
    request<QueryResult>("/query/execute", {
      method: "POST",
      body: JSON.stringify({ datasource_id: datasourceId, sql, question, execution_id: executionId }),
      signal,
    }),

  cancelQuery: (executionId: string) =>
    request<{ success: boolean; cancelled: boolean; executionId: string; message: string }>("/query/cancel", {
      method: "POST",
      body: JSON.stringify({ execution_id: executionId }),
    }),

  listHistory: (datasourceId?: string, filters?: { search?: string; status?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (datasourceId) params.set("datasource_id", datasourceId);
    if (filters?.search) params.set("search", filters.search);
    if (filters?.status && filters.status !== "all") params.set("status", filters.status);
    if (filters?.limit) params.set("limit", String(filters.limit));
    const query = params.toString();
    return request<QueryHistory[]>(`/query/history${query ? `?${query}` : ""}`);
  },

  deleteHistory: (historyId: string) =>
    request<{ success: boolean; deleted: number }>(`/query/history/${encodeURIComponent(historyId)}`, {
      method: "DELETE",
    }),

  clearHistory: (datasourceId: string) =>
    request<{ success: boolean; deleted: number }>(
      `/query/history?datasource_id=${encodeURIComponent(datasourceId)}`,
      { method: "DELETE" },
    ),

  generateSql: (datasourceId: string, question: string, config?: { apiKey?: string; apiBase?: string; model?: string; optimizeRag?: boolean }, signal?: AbortSignal) =>
    request<GeneratedSqlResult>("/query/generate", {
      method: "POST",
      body: JSON.stringify({
        datasource_id: datasourceId,
        question,
        api_key: config?.apiKey,
        api_base: config?.apiBase,
        model_name: config?.model,
        optimize_rag: config?.optimizeRag ?? false,
      }),
      signal,
    }),

  runAgentQuery: (datasourceId: string, question: string, config?: AgentRunConfig, signal?: AbortSignal) =>
    request<AgentRunResponse>("/query/agent-run", {
      method: "POST",
      body: JSON.stringify(buildAgentRunPayload(datasourceId, question, config)),
      signal,
    }),

  streamAgentQuery: (
    datasourceId: string,
    question: string,
    config?: AgentRunConfig,
    options?: { signal?: AbortSignal; onEvent?: (event: AgentRuntimeEvent) => void },
  ) => streamAgentRun(datasourceId, question, config, options),

  getAgentRun: (runId: string) =>
    request<AgentRunResponse | null>(`/query/agent-runs/${encodeURIComponent(runId)}`),

  listAgentSessionRuns: (sessionId: string) =>
    request<any[]>(`/query/agent-sessions/${encodeURIComponent(sessionId)}/runs`),

  getRecentAgentRun: (datasourceId: string) =>
    request<AgentRunResponse | null>(`/query/agent-runs/recent?datasource_id=${encodeURIComponent(datasourceId)}`),

  listGoldenSql: (datasourceId: string) =>
    request<any[]>(`/golden-sql?datasource_id=${datasourceId}`),

  createGoldenSql: (datasourceId: string, question: string, goldenSql: string) =>
    request<any>("/golden-sql", {
      method: "POST",
      body: JSON.stringify({ datasource_id: datasourceId, question, golden_sql: goldenSql }),
    }),

  deleteGoldenSql: (id: string) =>
    request<any>(`/golden-sql/${id}`, { method: "DELETE" }),

  runBenchmark: (datasourceId: string, config?: { apiKey?: string; apiBase?: string; model?: string; optimizeRag?: boolean }) =>
    request<any>("/golden-sql/run-benchmark", {
      method: "POST",
      body: JSON.stringify({
        datasource_id: datasourceId,
        api_key: config?.apiKey,
        api_base: config?.apiBase,
        model_name: config?.model,
        optimize_rag: config?.optimizeRag ?? false,
      }),
    }),

  getLlmStats: (datasourceId: string) =>
    request<any>(`/llm-logs/stats?datasource_id=${datasourceId}`),

  startDemoMysql: (projectId?: string) =>
    request<DataSource>("/demo/start", { method: "POST", body: JSON.stringify({ project_id: projectId }) }),

  listTableDesignDrafts: (projectId: string) =>
    request<TableDesignDraft[]>(`/schema/design/drafts?project_id=${projectId}`),

  getTableDesignDraft: (draftId: string) =>
    request<TableDesignDraft>(`/schema/design/drafts/${draftId}`),

  saveTableDesignDraft: (req: {
    project_id: string;
    draft_id?: string;
    table_name: string;
    table_comment?: string;
    columns: any[];
    indexes: any[];
  }) =>
    request<TableDesignDraft>("/schema/design/drafts/save", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  deleteTableDesignDraft: (draftId: string) =>
    request<any>(`/schema/design/drafts/${draftId}`, { method: "DELETE" }),

  generateTableDesignAi: (prompt: string, config?: { apiKey?: string; apiBase?: string; model?: string }) =>
    request<TableDesignAiResponse>("/schema/design/ai-generate", {
      method: "POST",
      body: JSON.stringify({
        prompt,
        api_key: config?.apiKey,
        api_base: config?.apiBase,
        model_name: config?.model,
      }),
    }),
};

export interface TableDesignAiResponse {
  table_name: string;
  table_comment: string;
  columns: Array<{
    name: string;
    type: string;
    nullable: boolean;
    primary_key: boolean;
    auto_increment: boolean;
    default_value: string | null;
    comment: string;
  }>;
  indexes: Array<{
    name: string;
    columns: string[];
    unique: boolean;
  }>;
}
