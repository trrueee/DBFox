import type { AgentArtifact } from "../types/agentArtifact";

export type WorkspaceTabType = "smart-query" | "table" | "sql" | "multi-table" | "query-result" | "conversation-history" | "llm-settings";

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

export const defaultSql = `SELECT 
  u.name, 
  count(c.id) as comment_count 
FROM id_users u 
LEFT JOIN comment_infos c ON u.id = c.user_id 
GROUP BY u.id 
ORDER BY comment_count DESC;`;
