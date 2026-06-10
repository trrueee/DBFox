import type { SchemaTable } from "../../lib/api";

const MODULE_PREFIXES: [string, string][] = [
  ["account_", "账号模块"],
  ["ai_", "AI 智能模块"],
  ["agent_", "任务模块"],
  ["auto_", "任务模块"],
  ["billing_", "计费模块"],
  ["content_", "内容模块"],
  ["id_", "身份组织模块"],
  ["login_", "认证会话模块"],
  ["media_", "媒体素材模块"],
  ["monitoring_", "监控模块"],
  ["nurture_", "客户培育模块"],
  ["notification_", "通知模块"],
  ["platform_", "平台账号模块"],
  ["publish_", "发布模块"],
  ["rbac_", "权限模块"],
  ["sales_", "销售模块"],
  ["token_", "Token 账户模块"],
  ["user_", "用户模块"],
  ["video_", "视频模块"],
  ["xhs_", "小红书模块"],
  ["audit_", "审计模块"],
  ["scheduler_", "调度模块"],
];

const MODULE_ORDER = [
  "账号模块",
  "身份组织模块",
  "认证会话模块",
  "平台账号模块",
  "Token 账户模块",
  "销售模块",
  "发布模块",
  "媒体素材模块",
  "视频模块",
  "小红书模块",
  "客户培育模块",
  "AI 智能模块",
  "任务模块",
  "计费模块",
  "审计模块",
  "权限模块",
  "监控模块",
  "通知模块",
  "用户模块",
  "内容模块",
  "调度模块",
  "通用模块",
];

export interface TableGroup {
  tag: string;
  tables: SchemaTable[];
}

export function getModuleTag(tableName: string): string {
  for (const [prefix, tag] of MODULE_PREFIXES) {
    if (tableName.startsWith(prefix)) return tag;
  }
  return "通用模块";
}

export function groupSchemaTables(tables: SchemaTable[], search: string): TableGroup[] {
  const query = search.trim().toLowerCase();
  const filtered = query
    ? tables.filter((table) =>
        table.table_name.toLowerCase().includes(query) ||
        table.table_comment.toLowerCase().includes(query),
      )
    : tables;

  const groups = new Map<string, SchemaTable[]>();
  for (const table of filtered) {
    const tag = table.module_tag || getModuleTag(table.table_name);
    groups.set(tag, [...(groups.get(tag) ?? []), table]);
  }

  return Array.from(groups.entries())
    .sort(([left], [right]) => {
      const leftIndex = MODULE_ORDER.indexOf(left);
      const rightIndex = MODULE_ORDER.indexOf(right);
      const normalizedLeft = leftIndex === -1 ? MODULE_ORDER.length : leftIndex;
      const normalizedRight = rightIndex === -1 ? MODULE_ORDER.length : rightIndex;
      return normalizedLeft - normalizedRight || left.localeCompare(right, "zh-Hans-CN");
    })
    .map(([tag, group]) => ({
      tag,
      tables: [...group].sort((a, b) => a.table_name.localeCompare(b.table_name)),
    }));
}
