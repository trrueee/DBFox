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

  const payload = await response.json();
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

export interface DataSource {
  id: string;
  name: string;
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


export interface SchemaTable {
  id: string;
  table_name: string;
  table_comment: string;
  table_type: string;
  row_count_estimate: number;
  columns_count: number;
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
  }>;
}

export const api = {
  testConnection: (params: unknown) =>
    request<any>("/datasources/test", { method: "POST", body: JSON.stringify(params) }),

  createDatasource: (params: unknown) =>
    request<DataSource>("/datasources", { method: "POST", body: JSON.stringify(params) }),

  listDatasources: () => request<DataSource[]>("/datasources"),

  deleteDatasource: (id: string) =>
    request<{ success: boolean; message: string }>(`/datasources/${id}`, { method: "DELETE" }),

  syncSchema: (id: string) =>
    request<any>(`/datasources/${id}/sync`, { method: "POST" }),

  listTables: (datasourceId: string) =>
    request<SchemaTable[]>(`/schema/tables?datasource_id=${datasourceId}`),

  listColumns: (tableId: string) =>
    request<SchemaColumn[]>(`/schema/tables/${tableId}/columns`),

  getERDiagram: (datasourceId: string) =>
    request<ERDiagramData>(`/schema/er-diagram?datasource_id=${datasourceId}`),

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

  startDemoMysql: () =>
    request<DataSource>("/demo/start", { method: "POST" }),
};

