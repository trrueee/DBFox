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
  columns: TableDesignColumn[];
  indexes: TableDesignIndex[];
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
  columns?: unknown[];
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

export interface DeleteResponse {
  success: boolean;
  message: string;
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

export interface TableDesignDDLRequest {
  table_name: string;
  instruction?: string;
  ddl?: string;
}
