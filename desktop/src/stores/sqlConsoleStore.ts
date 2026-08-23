import { create } from "zustand";

import { useWorkspaceStore } from "./workspaceStore";
import { defaultSql } from "../features/workspace/defaultSql";
import type { ConsoleEntry } from "../features/workspace/SqlConsoleWorkspace";

export type SqlConsoleTabState = {
  datasourceId: string;
  datasourceDbType?: string | null;
  draftSql: string;
  entries: ConsoleEntry[];
  running: boolean;
};

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
  patchSqlConsoleState: (stateKeyOrViewKey: string, patch: Partial<SqlConsoleTabState>) => void;
  appendSqlConsoleEntries: (stateKeyOrViewKey: string, entries: ConsoleEntry[]) => void;
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
      const viewKey = `dbfox.data.sql-console:${projectKey}`;
      const existing = state.sqlConsoleState[stateKey];
      const tab = {
        viewKey,
        viewType: "dbfox.data.sql-console",
        title: "SQL 控制台",
        closeable: false,
        stateKey,
        projectId: shell.activeProjectId || undefined,
        target: {
          type: "resource" as const,
          kind: "dbfox.data.database",
          id: datasourceId,
        },
      };
      shell.openDockTab(tab, activate);
      return {
        sqlConsoleState: {
          ...state.sqlConsoleState,
          [stateKey]: {
            datasourceId,
            datasourceDbType: datasourceDbType ?? null,
            draftSql: initialSql ?? existing?.draftSql ?? defaultSql,
            entries: existing?.entries ?? [],
            running: existing?.running ?? false,
          },
        },
      };
    }),

  patchSqlConsoleState: (key, patch) =>
    set((state) => {
      const current = state.sqlConsoleState[key];
      if (!current) return state;
      return {
        sqlConsoleState: {
          ...state.sqlConsoleState,
          [key]: { ...current, ...patch },
        },
      };
    }),

  appendSqlConsoleEntries: (key, entries) =>
    set((state) => {
      const current = state.sqlConsoleState[key];
      if (!current) return state;
      return {
        sqlConsoleState: {
          ...state.sqlConsoleState,
          [key]: { ...current, entries: [...current.entries, ...entries] },
        },
      };
    }),
}));
