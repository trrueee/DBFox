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
    const n = parseInt(rest) || parseInt(rest.match(/(\d+)/)?.[0] ?? "100");
    return { rows: String(n) };
  },

  validate(_action, plan) {
    const issues: QueryActionIssue[] = [];
    if (/limit\s+\d+/i.test(plan.pureSql)) {
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
    const n = parseInt(action.args.rows ?? "100");
    if (!hasLimitClause(plan.compiledSql)) {
      plan.compiledSql = appendLimit(plan.compiledSql, n);
    }
  },

  formatLabel(args) {
    return `LIMIT ${args.rows ?? "100"}`;
  },
};
