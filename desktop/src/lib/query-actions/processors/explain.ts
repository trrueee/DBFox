import type { ActionProcessor } from "../types";
import { prependExplain } from "../sql-utils";

export const ExplainProcessor: ActionProcessor = {
  name: "explain",
  meta: {
    phase: "compile",
    order: 900, // Should execute after limit to avoid wrapping issues
    repeatable: false,
    conflictsWith: ["export"],
    description: "查看 SQL 的执行计划与性能剖析，分析索引命中情况",
    usage: "@explain",
    examples: ["@explain"],
  },

  parse(_rest) {
    return {};
  },

  validate(_action, plan) {
    if (/^\s*explain\s/i.test(plan.pureSql)) {
      return [{
        code: "ALREADY_EXPLAIN",
        level: "warning",
        action: "explain",
        message: "SQL 已是 EXPLAIN 查询",
        stage: "validate",
      }];
    }
    return [];
  },

  apply(_action, plan) {
    plan.compiledSql = prependExplain(plan.compiledSql);
  },

  formatLabel() {
    return "执行计划";
  },
};
