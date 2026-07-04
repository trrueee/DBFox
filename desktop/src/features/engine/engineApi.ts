import type { DataSource } from "../../lib/api/types";

export type EngineDataSource = DataSource;

export function quoteIdentifier(identifier: string, dbType = "mysql") {
  if (dbType === "postgresql") return "\"" + identifier.replaceAll("\"", "\"\"") + "\"";
  if (dbType === "sqlite") return "\"" + identifier.replaceAll("\"", "\"\"") + "\"";
  return "`" + identifier.replaceAll("`", "``") + "`";
}
