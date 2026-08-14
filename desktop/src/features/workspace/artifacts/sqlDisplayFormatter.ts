import {
  duckdb,
  formatDialect,
  mysql,
  postgresql,
  sql as standardSql,
  sqlite,
  type DialectOptions,
} from "sql-formatter";

const DIALECTS: Readonly<Record<string, DialectOptions>> = {
  duckdb,
  mysql,
  postgres: postgresql,
  postgresql,
  sqlite,
};

export function formatSqlForDisplay(sql: string, dialect?: string): string {
  if (!sql.trim()) return sql;

  try {
    return formatDialect(sql, {
      dialect: resolveSqlDialect(dialect),
      keywordCase: "upper",
      tabWidth: 2,
      linesBetweenQueries: 1,
      logicalOperatorNewline: "before",
      expressionWidth: 64,
    });
  } catch {
    return sql;
  }
}

function resolveSqlDialect(dialect?: string): DialectOptions {
  return DIALECTS[dialect?.trim().toLowerCase() ?? ""] ?? standardSql;
}
