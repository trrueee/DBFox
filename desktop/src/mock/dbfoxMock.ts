// Core workspace types — canonical location: src/types/workspace.ts
// Re-exported here for backward compatibility with existing imports.
export type {
  WorkspaceTabType,
  AgentApprovalInfo,
  AgentTabStatus,
  WorkspaceTab,
  ContextMenuState,
} from "../types/workspace";

// ── Mock data ──

export const defaultSql = `SELECT
  u.name,
  count(c.id) as comment_count
FROM id_users u
LEFT JOIN comment_infos c ON u.id = c.user_id
GROUP BY u.id
ORDER BY comment_count DESC;`;
