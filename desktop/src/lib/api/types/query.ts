import type { AgentArtifact } from "./artifact";

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

export interface MetricObservationResult {
  dimension: string;
  metric: string;
  value: number | string;
  delta?: number | string;
  context?: string;
}

export interface ResultSort {
  column: string;
  direction: "asc" | "desc";
}

export type ResultFilterOperator =
  | "equals"
  | "not_equals"
  | "contains"
  | "starts_with"
  | "ends_with"
  | "gt"
  | "gte"
  | "lt"
  | "lte"
  | "is_null"
  | "is_not_null"
  | "in"
  | "not_in";

export interface ResultFilter {
  column: string;
  operator: ResultFilterOperator;
  value?: unknown;
}

export interface ResultPageRequest {
  page: number;
  pageSize: number;
  sort?: ResultSort[] | null;
  filters?: ResultFilter[] | null;
  search?: string | null;
  countMode?: "none" | "exact" | "estimate";
}

export interface ResultExportRequest {
  sort?: ResultSort[] | null;
  filters?: ResultFilter[] | null;
  search?: string | null;
}

export interface TableResultPageRequest {
  datasourceId: string;
  tableId?: string | null;
  tableName: string;
  page: number;
  pageSize: number;
  sort?: ResultSort[] | null;
  filters?: ResultFilter[] | null;
  search?: string | null;
  countMode?: "none" | "exact" | "estimate";
}

export interface TableResultExportRequest {
  datasourceId: string;
  tableId?: string | null;
  tableName: string;
  sort?: ResultSort[] | null;
  filters?: ResultFilter[] | null;
  search?: string | null;
}

export interface ConsoleExecuteRequest {
  datasourceId: string;
  sql: string;
  question?: string | null;
  sessionId?: string | null;
  executionId?: string | null;
}

export interface ConsoleExecuteResponse {
  runId: string;
  sessionId: string;
  sqlArtifactId: string;
  safetyArtifactId?: string | null;
  resultArtifactId?: string | null;
  artifacts: AgentArtifact[];
  warnings: string[];
  notices: string[];
}

export interface ResultPageResponse {
  columns: string[];
  rows: Record<string, unknown>[];
  page: number;
  pageSize: number;
  rowCount?: number | null;
  hasNextPage: boolean;
  latencyMs: number;
  consistency: "live_reexecution" | "live_query";
  originalExecutedAt?: string | null;
  viewExecutedAt: string;
  viewExecutionId: string;
  datasourceGeneration: number;
  queryFingerprint: string;
  warnings?: string[] | null;
  notices?: string[] | null;
}

export interface ChartDataResponse {
  series: Array<{ label: string; value: number; x?: string | number }>;
  sampleSize: number;
  truncated: boolean;
  consistency: "live_reexecution";
  originalExecutedAt?: string | null;
  viewExecutedAt: string;
  viewExecutionId: string;
  datasourceGeneration: number;
  queryFingerprint: string;
}

