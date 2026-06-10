import type { QueryResult } from "../../lib/api";

export type WorkbenchSubTab = "data" | "schema" | "er" | "design";
export type WorkbenchTabType = "query" | "table" | "er" | "datasources" | "history" | "diagnostics";
export type WorkbenchActionType = "execute" | "stop" | "validate" | "export" | "format";
export type QueryResultState = "idle" | "running" | "success" | "error" | "timeout" | "cancelled";

export interface WorkbenchTab {
  id: string;
  type: WorkbenchTabType;
  title: string;
  dirty?: boolean;
  closable?: boolean;
  connectionId?: string;
  databaseName?: string;
  tableName?: string;
  activeSubTab?: WorkbenchSubTab;
  sqlDraft?: string;
  resultState?: QueryResultState;
  lastQueryResultPreview?: QueryResult | null;
  lastError?: string | null;
  lastExecutedAt?: number;
  actionTrigger?: {
    type: WorkbenchActionType;
    nonce: number;
  };
}

export type QueryTabStatePatch = Pick<
  WorkbenchTab,
  "resultState" | "sqlDraft" | "dirty" | "lastQueryResultPreview" | "lastError"
>;
