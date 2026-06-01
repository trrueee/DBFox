import type { ActionProcessor, QueryActionIssue } from "../types";
import { appendLimit, hasLimitClause } from "../sql-utils";

export const LimitProcessor: ActionProcessor = {
  name: "limit",
  meta: {
    phase: "compile",
    order: 100,
    repeatable: false,
    conflictsWith: [],
    description: "限制返回结果的行数，避免大表全扫描占用网络带宽",
    usage: "@limit [行数]",
    examples: ["@limit 100", "@limit 10"],
  },

  parse(rest) {
    const trimmed = rest.trim();
    if (!trimmed) {
      return { rows: "100" };
    }
    return { rows: trimmed };
  },

  validate(action, plan) {
    const issues: QueryActionIssue[] = [];
    const rowsStr = action.args.rows ?? "100";
    const n = Number(rowsStr);

    if (!Number.isInteger(n) || n < 1 || n > 10000) {
      issues.push({
        code: "INVALID_LIMIT_ROWS",
        level: "error",
        action: "limit",
        message: `限制行数必须是 1 到 10000 之间的整数，当前值为: ${rowsStr}`,
        stage: "validate",
      });
    }

    if (hasLimitClause(plan.pureSql)) {
      issues.push({
        code: "LIMIT_ALREADY_EXISTS",
        level: "warning",
        action: "limit",
        message: "SQL 中已包含 LIMIT 子句，@limit 将被跳过",
        stage: "validate",
      });
    }
    return issues;
  },

  apply(action, plan) {
    const rowsStr = action.args.rows ?? "100";
    const n = Number(rowsStr);
    if (!Number.isInteger(n) || n < 1 || n > 10000) {
      return;
    }
    if (!hasLimitClause(plan.compiledSql)) {
      plan.compiledSql = appendLimit(plan.compiledSql, n);
    }
  },

  formatLabel(args) {
    return `LIMIT ${args.rows ?? "100"}`;
  },
};
