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
  host: string | null;
  port: number;
  database_name: string;
  username: string | null;
  password_credential_id?: string | null;
  connection_mode: string;
  is_read_only?: boolean;
  env?: string;
  status: string;
  ssh_enabled?: boolean;
  ssh_host?: string;
  ssh_port?: number;
  ssh_username?: string;
  ssh_password_credential_id?: string | null;
  ssh_pkey_path?: string;
  ssh_key_passphrase_credential_id?: string | null;
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

export interface DataSourceTestParams {
  db_type?: string;
  host?: string | null;
  port?: number | null;
  database_name: string;
  username?: string | null;
  password_credential_id?: string | null;
  ssh_enabled?: boolean;
  ssh_host?: string | null;
  ssh_port?: number;
  ssh_username?: string | null;
  ssh_password_credential_id?: string | null;
  ssh_pkey_path?: string | null;
  ssh_key_passphrase_credential_id?: string | null;
  ssl_enabled?: boolean;
  ssl_ca_path?: string | null;
  ssl_cert_path?: string | null;
  ssl_key_path?: string | null;
  ssl_verify_identity?: boolean;
  credential_lease_id?: string | null;
}

export interface DataSourceCreateParams extends DataSourceTestParams {
  project_id?: string | null;
  name: string;
  connection_mode?: string;
  is_read_only?: boolean;
  env?: string;
}

export type DataSourceUpdateParams = DataSourceCreateParams;

/** Second-step confirmation payload for dangerous delete operations. */
export interface DeleteConfirm {
  token: string;
  text: string;
}

export interface SchemaSyncOptions {
  ai_enrich?: boolean;
  llm_credential_id?: string;
  api_base?: string;
  model_name?: string;
}

export interface SchemaAiEnrichResult {
  ai_enriched?: boolean;
  enriched_count?: number;
  reason?: string;
  errors?: string[];
  capped?: boolean;
  total_changed?: number;
  max_tables_per_run?: number;
}

/** Consolidated CRUD actions for datasource management. */
export interface DataSourceActions {
  createDatasource: (params: DataSourceCreateParams) => Promise<DataSource>;
  updateDatasource: (id: string, params: DataSourceUpdateParams) => Promise<DataSource>;
  deleteDatasource: (id: string, confirm?: DeleteConfirm) => Promise<unknown>;
  syncSchema: (id: string, options?: SchemaSyncOptions) => Promise<SchemaSyncResult>;
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
  ok?: boolean;
  message?: string;
  syncedTables?: number;
  tablesSynced?: number;
  tablesDropped?: number;
  columnsCreated?: number;
  columnsUpdated?: number;
  columnsRemoved?: number;
  warnings?: string[];
  aiEnrich?: SchemaAiEnrichResult;
}
