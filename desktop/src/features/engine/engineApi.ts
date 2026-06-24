import type { DataSource } from "../../lib/api/types";

export type EngineDataSource = DataSource;

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

export async function executeSql(datasourceId: string, sql: string, question?: string) {
  const { queryApi } = await import("../../lib/api/query");
  return queryApi.executeSql(datasourceId, sql, question, "frontend-" + Date.now()) as Promise<EngineSqlResult>;
}

export function quoteIdentifier(identifier: string, dbType = "mysql") {
  if (dbType === "postgresql") return "\"" + identifier.replaceAll("\"", "\"\"") + "\"";
  if (dbType === "sqlite") return "\"" + identifier.replaceAll("\"", "\"\"") + "\"";
  return "`" + identifier.replaceAll("`", "``") + "`";
}
