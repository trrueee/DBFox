import type { AgentArtifact } from "../types/agentArtifact";

export type WorkspaceTabType = "smart-query" | "table" | "sql" | "multi-table" | "query-result" | "conversation-history";

export interface WorkspaceTab {
  id: string;
  title: string;
  type: WorkspaceTabType;
  tableId?: string;
  selectedTables?: string[];
  queryText?: string;
  conversationId?: string;
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
