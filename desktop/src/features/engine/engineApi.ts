import { engineRequest } from "./engineClient";

export interface EngineDataSource {
  id: string;
  name: string;
  db_type: string;
  host: string;
  port: number;
  database_name: string;
  status: string;
  last_sync_status?: string | null;
  last_test_status?: string | null;
  last_test_latency_ms?: number | null;
}

export interface EngineSchemaTable {
  id: string;
  table_name: string;
  table_comment: string;
  table_type?: string | null;
  row_count_estimate?: number | null;
  columns_count?: number | null;
  module_tag?: string | null;
}

export interface EngineColumn {
  id: string;
  column_name: string;
  data_type: string;
  column_type: string;
  is_nullable: boolean;
  column_default: string;
  column_comment: string;
  is_primary_key: boolean;
  is_foreign_key: boolean;
  foreign_table_id?: string | null;
  foreign_column_id?: string | null;
}

export interface EngineSqlResult {
  success: boolean;
  columns: string[];
  rows: Array<Record<string, string | null>>;
  rowCount: number;
  latencyMs: number;
  warnings?: string[];
  truncated?: boolean;
  historyId?: string;
  executionId?: string;
}

export interface LlmProviderPreset {
  provider: string;
  label: string;
  base_url: string;
  models: string[];
}

export interface LlmConfig {
  id: string;
  provider: string;
  model: string;
  base_url: string;
  temperature: number;
  max_tokens: number;
  enabled: boolean;
  has_api_key: boolean;
  api_key_preview: string;
  updated_at?: string | null;
}

export interface SaveLlmConfigPayload {
  provider: string;
  model: string;
  base_url?: string;
  api_key?: string;
  temperature: number;
  max_tokens: number;
  enabled: boolean;
}

export async function listDatasources() {
  return engineRequest<EngineDataSource[]>("/datasources");
}

export async function listTables(datasourceId: string) {
  return engineRequest<EngineSchemaTable[]>(`/schema/tables?datasource_id=${encodeURIComponent(datasourceId)}`);
}

export async function listColumns(tableId: string) {
  return engineRequest<EngineColumn[]>(`/schema/tables/${encodeURIComponent(tableId)}/columns`);
}

export async function executeSql(datasourceId: string, sql: string, question?: string) {
  return engineRequest<EngineSqlResult>("/query/execute", {
    method: "POST",
    body: JSON.stringify({
      datasource_id: datasourceId,
      sql,
      question,
      execution_id: `frontend-${Date.now()}`,
    }),
  });
}

export async function getDefaultDatasource() {
  const datasources = await listDatasources();
  return datasources[0] ?? null;
}

export async function resolveTableByName(tableName: string) {
  const datasource = await getDefaultDatasource();
  if (!datasource) return null;
  const tables = await listTables(datasource.id);
  const table = tables.find((item) => item.table_name === tableName) ?? null;
  return table ? { datasource, table } : null;
}

export async function listLlmProviders() {
  return engineRequest<LlmProviderPreset[]>("/llm/providers");
}

export async function getLlmConfig() {
  return engineRequest<LlmConfig>("/llm/config");
}

export async function saveLlmConfig(payload: SaveLlmConfigPayload) {
  return engineRequest<LlmConfig>("/llm/config", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function resolveLlmConfig(provider: string, model: string, baseUrl?: string) {
  return engineRequest<{ provider: string; base_url: string }>("/llm/resolve", {
    method: "POST",
    body: JSON.stringify({ provider, model, base_url: baseUrl }),
  });
}

export function quoteIdentifier(identifier: string, dbType = "mysql") {
  if (dbType === "postgresql") return `"${identifier.replaceAll('"', '""')}"`;
  if (dbType === "sqlite") return `"${identifier.replaceAll('"', '""')}"`;
  return `\`${identifier.replaceAll("`", "``")}\``;
}
