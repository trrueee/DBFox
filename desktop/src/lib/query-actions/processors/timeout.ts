import type { ActionProcessor, QueryActionIssue } from "../types";

export const TimeoutProcessor: ActionProcessor = {
  name: "timeout",
  meta: {
    phase: "beforeExecute",
    order: 100,
    repeatable: false,
    conflictsWith: [],
    description: "设置本次查询在客户端的最大超时时间，防止长查询挂死连接",
    usage: "@timeout [秒数]",
    examples: ["@timeout 10", "@timeout 60"],
  },

  parse(rest) {
    const trimmed = rest.trim().replace(/s$/i, "");
    if (!trimmed) {
      return { seconds: "30" };
    }
    return { seconds: trimmed };
  },

  validate(action) {
    const issues: QueryActionIssue[] = [];
    const secondsStr = action.args.seconds ?? "30";
    const n = Number(secondsStr);

    if (!Number.isInteger(n) || n < 1 || n > 600) {
      issues.push({
        code: "INVALID_TIMEOUT_SECONDS",
        level: "error",
        action: "timeout",
        message: `超时时间必须是 1 到 600 之间的整数秒，当前值为: ${secondsStr}`,
        stage: "validate",
      });
    }
    return issues;
  },

  apply(action, plan) {
    const secondsStr = action.args.seconds ?? "30";
    const n = Number(secondsStr);
    if (!Number.isInteger(n) || n < 1 || n > 600) {
      return;
    }
    plan.context.timeoutMs = n * 1000;
  },

  formatLabel(args) {
    return `超时 ${args.seconds ?? "30"}s`;
  },
};
