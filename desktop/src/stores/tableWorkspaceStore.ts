import { create } from "zustand";

import type { TableTabDatasourceContext } from "../types/workspace";
import { useWorkspaceStore } from "./workspaceStore";

export interface TableViewState {
  tableName: string;
  datasourceId?: string;
  datasourceDbType?: string | null;
}

export interface MultiTableViewState {
  datasourceId?: string;
  datasourceDbType?: string | null;
  tables: string[];
}

interface TableWorkspaceState {
  selectedTables: string[];
  tableSubTabs: Record<string, string>;
  tableStateByTabId: Record<string, TableViewState>;
  multiTableStateByTabId: Record<string, MultiTableViewState>;
}

interface TableWorkspaceActions {
  setSelectedTables: (tables: string[] | ((prev: string[]) => string[])) => void;
  setTableSubTabs: (
    updater: Record<string, string> | ((prev: Record<string, string>) => Record<string, string>),
  ) => void;
  openTable: (
    tableName: string,
    initialSubtab?: string,
    datasource?: TableTabDatasourceContext,
  ) => void;
  openMultiTable: (
    tables: string[],
    datasource?: TableTabDatasourceContext,
  ) => void;
}

export type TableWorkspaceStore = TableWorkspaceState & TableWorkspaceActions;

function canonicalTableViewKey(tableName: string, datasource?: TableTabDatasourceContext) {
  return datasource?.id
    ? `dbfox.data.table:${datasource.id}:${tableName}`
    : `dbfox.data.table:${tableName}`;
}

function canonicalMultiTableViewKey(tables: string[], datasource?: TableTabDatasourceContext) {
  const canonicalTables = Array.from(new Set(tables)).sort();
  return datasource?.id
    ? `dbfox.data.multi-table:${datasource.id}:${canonicalTables.join("|")}`
    : `dbfox.data.multi-table:${canonicalTables.join("|")}`;
}

export const useTableWorkspaceStore = create<TableWorkspaceStore>()((set) => ({
  selectedTables: [],
  tableSubTabs: {},
  tableStateByTabId: {},
  multiTableStateByTabId: {},

  setSelectedTables: (tables) =>
    set((state) => ({
      selectedTables: typeof tables === "function" ? tables(state.selectedTables) : tables,
    })),

  setTableSubTabs: (updater) =>
    set((state) => ({
      tableSubTabs: typeof updater === "function" ? updater(state.tableSubTabs) : updater,
    })),

  openTable: (tableName, initialSubtab = "preview", datasource) => {
    const viewKey = canonicalTableViewKey(tableName, datasource);
    const target = datasource?.id
      ? {
          type: "resource" as const,
          kind: "database",
          id: datasource.id,
        }
      : undefined;

    useWorkspaceStore.getState().openDockTab({
      viewKey,
      viewType: "dbfox.data.table",
      title: tableName,
      closeable: true,
      target,
      stateKey: viewKey,
    });

    set((state) => ({
      selectedTables: [tableName],
      tableSubTabs: initialSubtab
        ? { ...state.tableSubTabs, [viewKey]: initialSubtab }
        : state.tableSubTabs,
      tableStateByTabId: {
        ...state.tableStateByTabId,
        [viewKey]: {
          tableName,
          datasourceId: datasource?.id,
          datasourceDbType: datasource?.dbType ?? null,
        },
      },
    }));
  },

  openMultiTable: (tables, datasource) => {
    if (tables.length === 0) return;
    const canonicalTables = Array.from(new Set(tables)).sort();
    const viewKey = canonicalMultiTableViewKey(canonicalTables, datasource);
    const title = `Workspace: ${canonicalTables.slice(0, 2).join(" & ")}${canonicalTables.length > 2 ? "..." : ""}`;
    const target = datasource?.id
      ? {
          type: "resource" as const,
          kind: "database",
          id: datasource.id,
        }
      : undefined;

    useWorkspaceStore.getState().openDockTab({
      viewKey,
      viewType: "dbfox.data.multi-table",
      title,
      closeable: true,
      target,
      stateKey: viewKey,
    });

    set((state) => ({
      selectedTables: canonicalTables,
      multiTableStateByTabId: {
        ...state.multiTableStateByTabId,
        [viewKey]: {
          datasourceId: datasource?.id,
          datasourceDbType: datasource?.dbType ?? null,
          tables: canonicalTables,
        },
      },
    }));
  },
}));
