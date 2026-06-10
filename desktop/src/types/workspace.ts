export type WorkspaceTabType =
  | "smart-query"
  | "table"
  | "sql"
  | "multi-table"
  | "query-result";

export type TableSubTab = "preview" | "schema" | "er" | "samples" | "usage";

export type WorkspaceTab = {
  id: string;
  title: string;
  type: WorkspaceTabType;
  tableName?: string;
  tableNames?: string[];
  query?: string;
  initialSubTab?: TableSubTab;
};

export type DataSourceContextMenuKind = "database" | "schema" | "table" | "multi-table";

export type DataSourceContextMenuState = {
  show: boolean;
  x: number;
  y: number;
  kind: DataSourceContextMenuKind;
  target: string;
};

export type ContextDrawerType = "props" | "ai-suggest" | "query-context";

export type ContextDrawerState = {
  open: boolean;
  type: ContextDrawerType;
  title?: string;
  payload?: {
    tableName?: string;
    tableNames?: string[];
    query?: string;
  };
};
