/** Core workspace types. */

import type { ResultViewArtifact } from "./agentArtifact";

export type WorkspaceTabType =
  | "smart-query"
  | "table"
  | "sql"
  | "multi-table"
  | "query-result"
  | "artifact-result"
  | "conversation-history"
  | "datasource-settings";

export interface WorkspaceTab {
  id: string;
  title: string;
  type: WorkspaceTabType;
  tableId?: string;
  datasourceId?: string;
  datasourceDbType?: string | null;
  selectedTables?: string[];
  queryText?: string;
  conversationId?: string;
  artifactResult?: ResultViewArtifact;
}

export interface ContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  type: "database" | "schema" | "table" | "multi-table";
  targetNode: string;
}
