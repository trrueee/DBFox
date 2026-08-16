/** Core workspace types. */

import type { ResultViewArtifact } from "./agentArtifact";

export type WorkspaceDockTabKind =
  | "console"
  | "table"
  | "artifacts"
  | "artifact"
  | "multi-table"
  | "file";

/** 右栏 Dock Tab（V3）：固定 Tab 不可关闭，临时 Tab 可关闭。 */
export interface WorkspaceDockTab {
  id: string;
  kind: WorkspaceDockTabKind;
  title: string;
  closeable: boolean;
  stateKey?: string;
  datasourceId?: string;
  datasourceDbType?: string | null;
  tableId?: string;
  conversationId?: string;
  artifact?: ResultViewArtifact;
  selectedTables?: string[];
  projectId?: string;
  filePath?: string;
  fileName?: string;
}

export type WorkspaceCenterMode = "home" | "conversation" | "project-create";

/** Fixed Main Surface states for Workbench Shell V2. */
export type MainSurfaceRef =
  | { kind: "conversation"; conversationId?: string }
  | { kind: "new-conversation" }
  | { kind: "project-create" }
  | { kind: "empty" };

export interface ContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  type: "database" | "schema" | "table" | "multi-table";
  targetNode: string;
}
