export const sampleRows: Record<string, string[][]> = {
  id_users: [
    ["1", "10001", "张三", "zhangsan", "active"],
    ["2", "10001", "李四", "lisi", "active"],
    ["3", "10002", "王五", "wangwu", "inactive"],
  ],
  comment_infos: [
    ["101", "20001", "1", "这个系统界面不错", "active"],
    ["102", "20002", "2", "数据字典在哪里配置", "pending"],
  ],
  video_infos: [
    ["501", "智能问数新手引导", "03:45", "1240", "active"],
  ],
};

export const defaultRows = sampleRows.id_users;

export const demoSql = `SELECT
  u.name,
  COUNT(c.id) AS comment_count
FROM id_users u
LEFT JOIN comment_infos c ON u.id = c.user_id
GROUP BY u.id, u.name
ORDER BY comment_count DESC;`;

export const recentTables = ["id_users", "comment_infos", "video_infos", "note_infos"];

export const recommendedQuestions = [
  "分析近 7 天评论数据趋势",
  "查询活跃用户 Top 10",
  "统计本月新增笔记数量",
  "检查异常数据",
];
