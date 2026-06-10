export type MockModule = {
  name: string;
  tables: string[];
};

export type MockColumn = {
  name: string;
  type: string;
  desc: string;
};

export const dataSourceModules: MockModule[] = [
  { name: "账号模块", tables: ["id_users", "id_organizations", "id_departments"] },
  { name: "内容模块", tables: ["note_infos", "video_infos"] },
  { name: "互动模块", tables: ["comment_infos", "like_infos", "favorite_infos"] },
  { name: "流量模块", tables: ["video_watch_records"] },
  { name: "配置表", tables: ["config_system", "config_dict"] },
];

export const tableColumns: Record<string, MockColumn[]> = {
  id_users: [
    { name: "id", type: "bigint", desc: "用户主键" },
    { name: "tenant_id", type: "bigint", desc: "租户 ID" },
    { name: "name", type: "varchar", desc: "用户姓名" },
    { name: "account", type: "varchar", desc: "登录账号" },
    { name: "status", type: "varchar", desc: "用户状态" },
  ],
  comment_infos: [
    { name: "id", type: "bigint", desc: "评论主键" },
    { name: "note_id", type: "bigint", desc: "笔记 ID" },
    { name: "user_id", type: "bigint", desc: "评论用户" },
    { name: "content", type: "text", desc: "评论内容" },
    { name: "status", type: "varchar", desc: "审核状态" },
  ],
  video_infos: [
    { name: "id", type: "bigint", desc: "视频主键" },
    { name: "title", type: "varchar", desc: "视频标题" },
    { name: "duration", type: "varchar", desc: "时长" },
    { name: "play_count", type: "bigint", desc: "播放量" },
    { name: "status", type: "varchar", desc: "视频状态" },
  ],
};

export const defaultColumns = tableColumns.id_users;
