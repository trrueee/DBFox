export function stripTrailingSemicolon(sql: string): string {
  return sql.replace(/;\s*$/, "").trim();
}

export function hasLimitClause(sql: string): boolean {
  return /\blimit\s+\d+\b/i.test(sql);
}

export function appendLimit(sql: string, rows: number): string {
  return `${stripTrailingSemicolon(sql)} LIMIT ${rows};`;
}

export function prependExplain(sql: string): string {
  const clean = stripTrailingSemicolon(sql);
  if (/^\s*explain\s/i.test(clean)) return `${clean};`;
  return `EXPLAIN ${clean};`;
}
