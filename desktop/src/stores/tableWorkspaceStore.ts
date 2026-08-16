import { create } from "zustand";

import type { TableTabDatasourceContext } from "../types/workspace";
import { useWorkspaceStore } from "./workspaceStore";

interface TableWorkspaceState {
  selectedTables: string[];
  tableSubTabs: Record<string, string>;
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
  openMultiTable: (tables: string[]) => void;
}

export type TableWorkspaceStore = TableWorkspaceState & TableWorkspaceActions;

function tableTabId(tableName: string, datasource?: TableTabDatasourceContext) {
  return datasource?.id ? `table-${datasource.id}-${tableName}` : `table-${tableName}`;
}

export const useTableWorkspaceStore = create<TableWorkspaceStore>()((set) => ({
  selectedTables: [],
  tableSubTabs: {},

  setSelectedTables: (tables) =>
    set((state) => ({
      selectedTables: typeof tables === "function" ? tables(state.selectedTables) : tables,
    })),

  setTableSubTabs: (updater) =>
    set((state) => ({
      tableSubTabs: typeof updater === "function" ? updater(state.tableSubTabs) : updater,
    })),

  openTable: (tableName, initialSubtab = "preview", datasource) => {
    const tabId = tableTabId(tableName, datasource);
    useWorkspaceStore.getState().openDockTab({
      id: tabId,
      kind: "table",
      title: tableName,
      closeable: true,
      tableId: tableName,
      datasourceId: datasource?.id,
      datasourceDbType: datasource?.dbType ?? null,
    });
    set((state) => ({
      selectedTables: [tableName],
      tableSubTabs: initialSubtab
        ? { ...state.tableSubTabs, [tabId]: initialSubtab }
        : state.tableSubTabs,
    }));
  },

  openMultiTable: (tables) => {
    if (tables.length === 0) return;
    const canonicalTables = Array.from(new Set(tables)).sort();
    const tabId = `multi-table-${canonicalTables.join("|")}`;
    const title = `Workspace: ${canonicalTables.slice(0, 2).join(" & ")}${canonicalTables.length > 2 ? "..." : ""}`;
    useWorkspaceStore.getState().openDockTab({
      id: tabId,
      kind: "multi-table",
      title,
      closeable: true,
      selectedTables: canonicalTables,
    });
  },
}));
