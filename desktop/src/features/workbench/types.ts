import type { QueryResult } from "../../lib/api";

export type WorkbenchTabType = "query" | "table" | "er" | "datasources" | "history" | "diagnostics";
export type TableSubTab = "data" | "schema" | "er" | "design";
export type WorkbenchAction = "execute" | "stop" | "validate" | "export" | "format";

export interface WorkbenchTab {
  id: string;
  type: WorkbenchTabType;
  title: string;
  dirty?: boolean;
  closable?: boolean;
  connectionId?: string;
  databaseName?: string;
  tableName?: string;
  activeSubTab?: TableSubTab;
  sqlDraft?: string;
  resultState?: "idle" | "running" | "success" | "error" | "timeout" | "cancelled";
  lastQueryResultPreview?: QueryResult | null;
  lastError?: string | null;
  lastExecutedAt?: number;
  actionTrigger?: {
    type: WorkbenchAction;
    nonce: number;
  };
}

export type QueryTabStatePatch = Pick<
  WorkbenchTab,
  "resultState" | "sqlDraft" | "dirty" | "lastQueryResultPreview" | "lastError"
>;
