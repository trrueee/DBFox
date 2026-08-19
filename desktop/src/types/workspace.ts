export type DockTargetRef =
  | {
      type: "resource";
      kind: string;
      id: string;
      version?: string | number | null;
    }
  | {
      type: "artifact";
      id: string;
    }
  | {
      type: "conversation";
      id: string;
    };

/**
 * 右栏 Dock Tab（P6 Canonical Envelope）：
 * Dock Shell 仅持有 viewKey、viewType、title、closeable 及可选的 projectId/target/stateKey。
 * 领域 payload 全部归 capability-owned store。
 */
export interface WorkspaceDockTab {
  viewKey: string;
  viewType: string;
  title: string;
  closeable: boolean;
  projectId?: string;
  target?: DockTargetRef;
  stateKey?: string;
}

export type WorkspaceCenterMode = "home" | "conversation" | "project-create";

/** Fixed Main Surface states for Workbench Shell V2. */
export type MainSurfaceRef =
  | { kind: "conversation"; conversationId?: string }
  | { kind: "new-conversation" }
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
