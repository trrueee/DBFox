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
  const payload = text ? JSON.parse(text) : null;
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
  last_sync_at?: string;
  last_sync_status?: string;
  last_sync_error?: string;
  created_at: string;
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

  validateSql: (sql: string, signal?: AbortSignal) =>
    request<GuardrailCheckResult>("/query/validate", {
      method: "POST",
      body: JSON.stringify({ sql }),
      signal,
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

  listHistory: (datasourceId: string) =>
    request<QueryHistory[]>(`/query/history?datasource_id=${datasourceId}`),

  generateSql: (datasourceId: string, question: string, config?: { apiKey?: string; apiBase?: string; model?: string; optimizeRag?: boolean }, signal?: AbortSignal) =>
    request<any>("/query/generate", {
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
