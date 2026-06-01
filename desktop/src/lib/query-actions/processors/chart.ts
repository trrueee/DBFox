import type { ActionProcessor } from "../types";

export const ChartProcessor: ActionProcessor = {
  name: "chart",
  meta: {
    phase: "afterExecute",
    order: 100,
    repeatable: false,
    conflictsWith: ["explain"],
    description: "查询执行成功后，自动渲染 ECharts 可视化图表",
    usage: "@chart [类型: bar/line/pie] x=[标签字段] y=[数值字段]",
    examples: ["@chart bar", "@chart line x=date y=amount", "@chart pie x=category y=count"],
  },

  parse(rest) {
    const args: Record<string, string> = {};
    const parts = rest.trim().split(/\s+/).filter(Boolean);
    for (const part of parts) {
      const kv = part.match(/^(\w+)=(.+)$/);
      if (kv) {
        args[kv[1]] = kv[2];
      } else if (!args.type) {
        args.type = part;
      } else if (!args.x) {
        args.x = part.replace(/^x=/i, "");
      } else if (!args.y) {
        args.y = part.replace(/^y=/i, "");
      }
    }
    return args;
  },

  validate(action, _plan) {
    const validTypes = ["line", "bar", "pie"];
    const chartType = (action.args.type || "bar").toLowerCase();
    if (!validTypes.includes(chartType)) {
      return [{
        code: "INVALID_CHART_TYPE",
        level: "error",
        action: "chart",
        message: `不支持的图表类型: ${chartType}，支持 bar / line / pie`,
        stage: "validate",
      }];
    }
    return [];
  },

  apply(action, plan) {
    plan.context.chartConfig = {
      enabled: true,
      type: action.args.type || "bar",
      x: action.args.x ?? "",
      y: action.args.y ?? "",
    };
  },

  formatLabel(args) {
    const t = args.type || "bar";
    const x = args.x ? ` x=${args.x}` : "";
    const y = args.y ? ` y=${args.y}` : "";
    return `图表 ${t}${x}${y}`;
  },
};
