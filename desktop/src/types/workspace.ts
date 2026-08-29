/**
 * 右栏 Dock Tab（P6 Canonical Envelope）：
 * Dock Shell 仅持有 viewKey、viewType、title、closeable 及可选的 projectId/target/stateKey。
 * 领域 payload 全部归 capability-owned store。
 */
export type { WorkspaceDockTab, WorkbenchReference } from "../../../sdk/frontend/index";

export type WorkspaceCenterMode = "home" | "conversation" | "project" | "project-create";

/** Fixed Main Surface states for Workbench Shell V2. */
export type MainSurfaceRef =
  | { kind: "conversation"; conversationId?: string }
  | { kind: "new-conversation" }
  | { kind: "project-overview" }
  | { kind: "project-create" }
  | { kind: "empty" };

export interface TableTabDatasourceContext {
  id: string;
  dbType?: string | null;
}

export interface ContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  type: "database" | "schema" | "table" | "multi-table";
  targetNode: string;
}
