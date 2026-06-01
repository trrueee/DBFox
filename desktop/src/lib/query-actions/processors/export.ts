import type { ActionProcessor } from "../types";

export const ExportProcessor: ActionProcessor = {
  name: "export",
  meta: {
    phase: "afterExecute",
    order: 100,
    repeatable: false,
    conflictsWith: ["explain"],
    description: "查询执行成功后，自动将数据导出并触发浏览器本地下载",
    usage: "@export [格式: csv/json]",
    examples: ["@export csv", "@export json", "@export csv filename=orders.csv"],
  },

  parse(rest) {
    const args: Record<string, string> = {};
    const parts = rest.trim().split(/\s+/).filter(Boolean);
    let posIdx = 0;
    for (const part of parts) {
      const kv = part.match(/^(\w+)=(.+)$/);
      if (kv) {
        args[kv[1]] = kv[2].replace(/^["']|["']$/g, "");
      } else {
        const key = posIdx === 0 ? "type" : posIdx === 1 ? "path" : `_${posIdx}`;
        args[key] = part.replace(/^["']|["']$/g, "");
        posIdx++;
      }
    }
    return args;
  },

  validate(action, _plan) {
    const format = (action.args.type || "csv").toLowerCase();
    if (!["csv", "json"].includes(format)) {
      return [{
        code: "INVALID_EXPORT_FORMAT",
        level: "error",
        action: "export",
        message: `不支持的导出格式: ${format}，当前支持 csv / json`,
        stage: "validate",
      }];
    }
    return [];
  },

  apply(action, plan) {
    const format = (action.args.type || "csv").toLowerCase() as "csv" | "json";
    const path = action.args.path ?? action.args.filename ?? `databox_export.${format}`;
    plan.context.exportConfig = {
      enabled: true,
      format,
      path,
      chunkSize: parseInt(action.args.chunk ?? action.args.chunkSize ?? "5000"),
    };
  },

  formatLabel(args) {
    const fmt = args.type || "csv";
    const p = args.path ?? args.filename ?? "";
    const display = p ? ` → ${p}` : "";
    return `自动导出 ${fmt}${display}`;
  },
};
