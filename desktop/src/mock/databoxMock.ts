import type { AgentArtifact } from "../types/agentArtifact";

export type WorkspaceTabType = "smart-query" | "table" | "sql" | "multi-table" | "query-result";

export interface WorkspaceTab {
  id: string;
  title: string;
  type: WorkspaceTabType;
  tableId?: string;
  selectedTables?: string[];
  queryText?: string;
  chatMessages?: { id: number; sender: "user" | "ai"; text: string }[];
  artifacts?: AgentArtifact[];
}

export interface ContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  type: "database" | "schema" | "table" | "multi-table";
  targetNode: string;
}

export const treeModules = [
  {
    name: "账号模块",
    tables: [
      { name: "id_users", comment: "用户基本信息" },
      { name: "id_organizations", comment: "组织架构信息" },
      { name: "id_departments", comment: "部门信息" },
    ],
  },
  {
    name: "内容模块",
    tables: [
      { name: "note_infos", comment: "笔记信息" },
      { name: "video_infos", comment: "视频信息" },
    ],
  },
  {
    name: "互动模块",
    tables: [
      { name: "comment_infos", comment: "评论数据" },
      { name: "like_infos", comment: "点赞数据" },
      { name: "favorite_infos", comment: "收藏数据" },
    ],
  },
  {
    name: "流量模块",
    tables: [{ name: "video_watch_records", comment: "视频观看记录" }],
  },
  {
    name: "配置表",
    tables: [
      { name: "config_system", comment: "系统配置" },
      { name: "config_dict", comment: "数据字典" },
    ],
  },
  {
    name: "系统类",
    tables: [{ name: "data_migrations", comment: "数据迁移记录" }],
  },
];

export const defaultSql = `SELECT 
  u.name, 
  count(c.id) as comment_count 
FROM id_users u 
LEFT JOIN comment_infos c ON u.id = c.user_id 
GROUP BY u.id 
ORDER BY comment_count DESC;`;

export const generatedSql = `SELECT 
  DATE(created_at) as date,
  count(id) as total_comments
FROM comment_infos
WHERE created_at >= CURDATE() - INTERVAL 7 DAY
GROUP BY DATE(created_at)
ORDER BY date;`;

export const demoAgentArtifacts: AgentArtifact[] = [
  {
    id: "trend-comments-7d",
    type: "chart",
    title: "数据趋势分析",
    description: "最近 7 天评论量趋势，后端 Agent 可替换为真实图表数据。",
    chartType: "line",
    unit: "条",
    series: [
      { label: "11-11", value: 420 },
      { label: "11-12", value: 760 },
      { label: "11-13", value: 610 },
      { label: "11-14", value: 1180 },
      { label: "11-15", value: 530 },
      { label: "11-16", value: 980 },
      { label: "11-17", value: 1432 },
    ],
  },
  {
    id: "generated-sql-comments-7d",
    type: "sql",
    title: "生成的 SQL 查询",
    description: "可一键打开到 SQL 工作台继续修改和运行。",
    sql: generatedSql,
  },
  {
    id: "summary-table-comments-7d",
    type: "table",
    title: "关键指标摘要",
    columns: ["指标", "当前值", "环比"],
    rows: [
      ["评论总量", "5,932", "+18.4%"],
      ["活跃用户", "1,284", "+9.7%"],
      ["异常评论", "37", "-4.1%"],
    ],
  },
  {
    id: "analysis-note-comments-7d",
    type: "markdown",
    title: "分析说明",
    content: "评论量在 11-17 出现峰值，建议进一步按渠道、内容类型和组织部门拆解，定位增长来源。",
  },
];
