import { request } from "../../lib/api/client";

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
  rows: Array<Record<string, unknown>>;
  rowCount: number;
  latencyMs: number;
  warnings?: string[];
  notices?: string[];
  truncated?: boolean;
  cellTruncated?: boolean;
  historyId?: string;
  executionId?: string;
}

export async function listDatasources() {
  return request<EngineDataSource[]>("/datasources");
}

export async function listTables(datasourceId: string) {
  return request<EngineSchemaTable[]>("/schema/tables?datasource_id=" + encodeURIComponent(datasourceId));
}

export async function listColumns(tableId: string) {
  return request<EngineColumn[]>("/schema/tables/" + encodeURIComponent(tableId) + "/columns");
}

export async function executeSql(datasourceId: string, sql: string, question?: string) {
  return request<EngineSqlResult>("/query/execute", {
    method: "POST",
    body: JSON.stringify({
      datasource_id: datasourceId,
      sql,
      question,
      execution_id: "frontend-" + Date.now(),
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

export function quoteIdentifier(identifier: string, dbType = "mysql") {
  if (dbType === "postgresql") return "\"" + identifier.replaceAll("\"", "\"\"") + "\"";
  if (dbType === "sqlite") return "\"" + identifier.replaceAll("\"", "\"\"") + "\"";
  return "`" + identifier.replaceAll("`", "``") + "`";
}
