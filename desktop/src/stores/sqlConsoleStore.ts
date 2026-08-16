import { create } from "zustand";

import { useWorkspaceStore } from "./workspaceStore";
import { defaultSql } from "../features/workspace/defaultSql";
import type { ConsoleEntry, SqlConsoleTabState } from "../features/workspace/SqlConsoleWorkspace";

interface SqlConsoleStateStore {
  sqlConsoleState: Record<string, SqlConsoleTabState>;
}

interface SqlConsoleActions {
  openConsole: (
    datasourceId: string,
    datasourceDbType?: string | null,
    initialSql?: string,
    activate?: boolean,
  ) => void;
  patchSqlConsoleState: (tabId: string, patch: Partial<SqlConsoleTabState>) => void;
  appendSqlConsoleEntries: (tabId: string, entries: ConsoleEntry[]) => void;
}

export type SqlConsoleStore = SqlConsoleStateStore & SqlConsoleActions;

function consoleKey(projectId: string, datasourceId: string) {
  return projectId || datasourceId;
}

export const useSqlConsoleStore = create<SqlConsoleStore>()((set) => ({
  sqlConsoleState: {},

  openConsole: (datasourceId, datasourceDbType, initialSql, activate = true) =>
    set((state) => {
      const shell = useWorkspaceStore.getState();
      const projectKey = consoleKey(shell.activeProjectId, datasourceId);
      const stateKey = `sql-${projectKey}`;
      const tabId = `console-${projectKey}`;
      const existing = state.sqlConsoleState[stateKey];
      const tab = {
        id: tabId,
        kind: "console" as const,
        title: "SQL 控制台",
        closeable: false,
        stateKey,
        datasourceId,
        datasourceDbType: datasourceDbType ?? null,
      };
      shell.openDockTab(tab, activate);
      return {
        sqlConsoleState: {
          ...state.sqlConsoleState,
          [stateKey]: {
            draftSql: initialSql ?? existing?.draftSql ?? defaultSql,
            entries: existing?.entries ?? [],
            running: existing?.running ?? false,
          },
        },
      };
    }),

  patchSqlConsoleState: (tabId, patch) =>
    set((state) => {
      const current = state.sqlConsoleState[tabId];
      if (!current) return state;
      return {
        sqlConsoleState: {
          ...state.sqlConsoleState,
          [tabId]: { ...current, ...patch },
        },
      };
    }),

  appendSqlConsoleEntries: (tabId, entries) =>
    set((state) => {
      const current = state.sqlConsoleState[tabId];
      if (!current) return state;
      return {
        sqlConsoleState: {
          ...state.sqlConsoleState,
          [tabId]: { ...current, entries: [...current.entries, ...entries] },
        },
      };
    }),
}));
