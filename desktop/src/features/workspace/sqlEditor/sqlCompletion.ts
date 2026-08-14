import {
  type CompletionContext,
  type CompletionResult,
} from "@codemirror/autocomplete";
import {
  MySQL,
  PostgreSQL,
  SQLite,
  StandardSQL,
  sql,
  type SQLDialect,
  type SQLNamespace,
} from "@codemirror/lang-sql";

import type { EngineColumn, EngineSchemaTable } from "../../../lib/api/schema";
import type { DataSource } from "../../../lib/api/types";
import { databaseTypeLabel } from "../databaseTypeLabel";

const SCHEMA_SECTION = { name: "Schema", rank: 0 } as const;
const TABLE_SECTION = { name: "数据表", rank: 1 } as const;
const COLUMN_SECTION = { name: "字段", rank: 0 } as const;
const KEYWORD_SECTION = { name: "SQL 关键字", rank: 2 } as const;

export function buildSqlLanguage(
  dbType: DataSource["db_type"] | null,
  tables: EngineSchemaTable[],
) {
  const dialect = resolveDialect(dbType);
  const { schema, defaultSchema } = buildSchemaNamespace(tables);
  return sql({
    dialect,
    schema,
    defaultSchema,
    upperCaseKeywords: true,
    keywordCompletion: (label, type) => ({
      label,
      type,
      boost: -20,
      section: KEYWORD_SECTION,
    }),
  });
}

function resolveDialect(dbType: DataSource["db_type"] | null): SQLDialect {
  if (dbType === "mysql") return MySQL;
  if (dbType === "postgresql") return PostgreSQL;
  if (dbType === "sqlite") return SQLite;
  return StandardSQL;
}

export function buildSchemaNamespace(tables: EngineSchemaTable[]): {
  schema: SQLNamespace;
  defaultSchema?: string;
} {
  const grouped: Record<string, SQLNamespace> = {};
  for (const table of tables) {
    const schemaName = table.table_schema?.trim() || "main";
    const current = grouped[schemaName];
    const children = current && !Array.isArray(current) && "children" in current
      ? current.children as Record<string, SQLNamespace>
      : {};
    children[table.table_name] = {
      self: {
        label: table.table_name,
        type: "class",
        detail: "数据表",
        boost: 20,
        section: TABLE_SECTION,
      },
      children: [],
    };
    grouped[schemaName] = {
      self: {
        label: schemaName,
        type: "namespace",
        detail: "Schema",
        boost: 10,
        section: SCHEMA_SECTION,
      },
      children,
    };
  }
  const schemaNames = Object.keys(grouped);
  return {
    schema: grouped,
    defaultSchema: schemaNames.length === 1 ? schemaNames[0] : undefined,
  };
}

export function createQualifiedColumnSource(
  tables: EngineSchemaTable[],
  loadColumns: (tableId: string) => Promise<EngineColumn[]>,
) {
  const tablesByName = new Map<string, EngineSchemaTable[]>();
  for (const table of tables) {
    const key = table.table_name.toLocaleLowerCase();
    tablesByName.set(key, [...(tablesByName.get(key) ?? []), table]);
  }

  return async (context: CompletionContext): Promise<CompletionResult | null> => {
    const match = context.matchBefore(/[A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?\.[\w$]*$/);
    if (!match) return null;
    const segments = match.text.split(".");
    const tableName = segments.at(-2)?.toLocaleLowerCase() ?? "";
    const schemaName = segments.length === 3 ? segments[0].toLocaleLowerCase() : null;
    const candidates = (tablesByName.get(tableName) ?? []).filter((table) => {
      if (!schemaName) return true;
      return (table.table_schema?.trim() || "main").toLocaleLowerCase() === schemaName;
    });
    if (candidates.length !== 1) return null;

    let columns: EngineColumn[];
    try {
      columns = await loadColumns(candidates[0].id);
    } catch {
      return null;
    }
    const dot = match.text.lastIndexOf(".");
    return {
      from: match.from + dot + 1,
      options: columns.map((column) => ({
        label: column.column_name,
        type: "property",
        detail: databaseTypeLabel(column.data_type || column.column_type) || undefined,
        info: column.column_comment || undefined,
        boost: 30,
        section: COLUMN_SECTION,
      })),
      validFor: /^[\w$]*$/,
    };
  };
}
