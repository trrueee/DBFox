export type SqlTokenKind =
  | "keyword"
  | "function"
  | "string"
  | "number"
  | "comment"
  | "operator"
  | "identifier"
  | "punctuation"
  | "whitespace";

export interface SqlToken {
  text: string;
  kind: SqlTokenKind;
}

export type SqlStatementKind = "read" | "write" | "ddl" | "other";

export interface SqlStatementSegment {
  text: string;
  kind: SqlStatementKind;
}

const SQL_KEYWORDS = new Set([
  "ADD",
  "ALL",
  "ALTER",
  "AND",
  "AS",
  "ASC",
  "BETWEEN",
  "BY",
  "CASE",
  "CAST",
  "CREATE",
  "DELETE",
  "DESC",
  "DISTINCT",
  "DROP",
  "ELSE",
  "END",
  "EXISTS",
  "FROM",
  "GROUP",
  "HAVING",
  "IN",
  "INNER",
  "INSERT",
  "INTO",
  "IS",
  "JOIN",
  "LEFT",
  "LIKE",
  "LIMIT",
  "NOT",
  "NULL",
  "ON",
  "OR",
  "ORDER",
  "OUTER",
  "RIGHT",
  "SELECT",
  "SET",
  "THEN",
  "UNION",
  "UPDATE",
  "VALUES",
  "WHEN",
  "WHERE",
  "WITH",
]);

const SQL_FUNCTIONS = new Set([
  "AVG",
  "COALESCE",
  "COUNT",
  "DATE",
  "FIELD",
  "MAX",
  "MIN",
  "ROUND",
  "SUM",
]);

const READ_STATEMENTS = new Set(["SELECT", "SHOW", "DESCRIBE", "EXPLAIN", "WITH"]);
const WRITE_STATEMENTS = new Set(["INSERT", "UPDATE", "DELETE", "REPLACE", "MERGE"]);
const DDL_STATEMENTS = new Set(["ALTER", "CREATE", "DROP", "TRUNCATE", "RENAME"]);

export function tokenizeSql(sql: string): SqlToken[] {
  const tokens: SqlToken[] = [];
  let index = 0;

  const push = (text: string, kind: SqlTokenKind) => {
    if (text) tokens.push({ text, kind });
  };

  while (index < sql.length) {
    const current = sql[index];
    const next = sql[index + 1];

    if (/\s/.test(current)) {
      const start = index;
      index += 1;
      while (index < sql.length && /\s/.test(sql[index])) index += 1;
      push(sql.slice(start, index), "whitespace");
      continue;
    }

    if (current === "-" && next === "-") {
      const start = index;
      index += 2;
      while (index < sql.length && sql[index] !== "\n") index += 1;
      push(sql.slice(start, index), "comment");
      continue;
    }

    if (current === "/" && next === "*") {
      const start = index;
      index += 2;
      while (index < sql.length && !(sql[index] === "*" && sql[index + 1] === "/")) index += 1;
      index = Math.min(index + 2, sql.length);
      push(sql.slice(start, index), "comment");
      continue;
    }

    if (current === "'" || current === '"' || current === "`") {
      const quote = current;
      const start = index;
      index += 1;
      while (index < sql.length) {
        if (sql[index] === quote) {
          if (sql[index + 1] === quote) {
            index += 2;
            continue;
          }
          index += 1;
          break;
        }
        index += 1;
      }
      push(sql.slice(start, index), quote === "'" ? "string" : "identifier");
      continue;
    }

    if (/\d/.test(current)) {
      const start = index;
      index += 1;
      while (index < sql.length && /[\d.]/.test(sql[index])) index += 1;
      push(sql.slice(start, index), "number");
      continue;
    }

    if (/[A-Za-z_]/.test(current)) {
      const start = index;
      index += 1;
      while (index < sql.length && /[A-Za-z0-9_$]/.test(sql[index])) index += 1;
      const text = sql.slice(start, index);
      const normalized = text.toUpperCase();
      if (SQL_KEYWORDS.has(normalized)) {
        push(text, "keyword");
      } else if (SQL_FUNCTIONS.has(normalized)) {
        push(text, "function");
      } else {
        push(text, "identifier");
      }
      continue;
    }

    if (/[=<>!+\-*/%|&]/.test(current)) {
      const start = index;
      index += 1;
      while (index < sql.length && /[=<>!+\-*/%|&]/.test(sql[index])) index += 1;
      push(sql.slice(start, index), "operator");
      continue;
    }

    push(current, "punctuation");
    index += 1;
  }

  return tokens;
}

export function splitSqlStatements(sql: string): SqlStatementSegment[] {
  const segments: SqlStatementSegment[] = [];
  let start = 0;
  let index = 0;
  let quote: string | null = null;
  let lineComment = false;
  let blockComment = false;

  const push = (end: number) => {
    const text = sql.slice(start, end);
    if (text) segments.push({ text, kind: classifySqlStatement(text) });
  };

  while (index < sql.length) {
    const current = sql[index];
    const next = sql[index + 1];

    if (lineComment) {
      if (current === "\n") lineComment = false;
      index += 1;
      continue;
    }

    if (blockComment) {
      if (current === "*" && next === "/") {
        blockComment = false;
        index += 2;
        continue;
      }
      index += 1;
      continue;
    }

    if (quote) {
      if (current === quote) {
        if (sql[index + 1] === quote) {
          index += 2;
          continue;
        }
        quote = null;
      }
      index += 1;
      continue;
    }

    if (current === "-" && next === "-") {
      lineComment = true;
      index += 2;
      continue;
    }

    if (current === "/" && next === "*") {
      blockComment = true;
      index += 2;
      continue;
    }

    if (current === "'" || current === '"' || current === "`") {
      quote = current;
      index += 1;
      continue;
    }

    if (current === ";") {
      push(index + 1);
      start = index + 1;
    }
    index += 1;
  }

  push(sql.length);
  return segments.filter((segment) => segment.text.trim().length > 0);
}

export function classifySqlStatement(sql: string): SqlStatementKind {
  const keyword = firstSqlKeyword(sql);
  if (!keyword) return "other";
  if (READ_STATEMENTS.has(keyword)) return "read";
  if (WRITE_STATEMENTS.has(keyword)) return "write";
  if (DDL_STATEMENTS.has(keyword)) return "ddl";
  return "other";
}

export function firstSqlKeyword(sql: string) {
  const match = sql.match(/^\s*(?:--[^\n]*\n\s*|\/\*[\s\S]*?\*\/\s*)*([A-Za-z_][A-Za-z0-9_$]*)/);
  return match?.[1]?.toUpperCase() ?? "";
}
