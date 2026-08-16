import { create } from "zustand";
import type {
  MainSurfaceRef,
  WorkspaceCenterMode,
  WorkspaceDockTab,
} from "../types/workspace";
import { defaultSql } from "../features/workspace/defaultSql";
import type { ConsoleEntry, SqlConsoleTabState } from "../features/workspace/SqlConsoleWorkspace";
import type { ResultViewArtifact } from "../types/agentArtifact";
import type { AppSettingsSection } from "../types/settings";

export type ProjectSidebarMode = "data" | "conversations";
export type SidebarEntityMode = "projects" | "connections";
export type ProjectSubMode = "conversations" | "files";
export type ConnectionSubMode = "conversations" | "database";

export interface ProjectShellState {
  sidebarMode: ProjectSidebarMode;
  activeDatasourceId?: string;
  activeConversationId?: string;
}

export interface TableTabDatasourceContext {
  id: string;
  dbType?: string | null;
}

interface WorkspaceState {
  activeProjectId: string;
  sidebarEntityMode: SidebarEntityMode;
  projectSubMode: Record<string, ProjectSubMode>;
  connectionSubMode: Record<string, ConnectionSubMode>;
  projectShell: Record<string, ProjectShellState>;
  mainSurfaceByProject: Record<string, MainSurfaceRef>;
  centerMode: WorkspaceCenterMode;
  centerReturnMode: WorkspaceCenterMode;
  pendingAsk: string | null;
  dock: { open: boolean; activeTabId: string | null };
  dockTabs: WorkspaceDockTab[];
  sqlConsoleState: Record<string, SqlConsoleTabState>;
  selectedTables: string[];
  tableSubTabs: Record<string, string>;
  settingsOpen: boolean;
  settingsSection: AppSettingsSection;
}

interface WorkspaceActions {
  setActiveProject: (projectId: string) => void;
  setSidebarEntityMode: (mode: SidebarEntityMode) => void;
  setProjectSubMode: (projectId: string, mode: ProjectSubMode) => void;
  setConnectionSubMode: (connectionId: string, mode: ConnectionSubMode) => void;
  setProjectSidebarMode: (projectId: string, mode: ProjectSidebarMode) => void;
  setProjectActiveDatasource: (projectId: string, datasourceId: string) => void;
  setProjectActiveConversation: (projectId: string, conversationId: string) => void;
  setProjectMainSurface: (projectId: string, surface: MainSurfaceRef) => void;
  openSettings: (section?: AppSettingsSection) => void;
  closeSettings: () => void;
  setSettingsSection: (section: AppSettingsSection) => void;
  setDockOpen: (open: boolean) => void;
  setDockActiveTab: (tabId: string) => void;
  closeDockTab: (tabId: string) => void;
  showSmartQueryHome: (initialAsk?: string) => void;
  openConversationCenter: (conversationId?: string) => void;
  openProjectCreate: () => void;
  clearPendingAsk: () => void;
  openDockConsole: (
    datasourceId: string,
    datasourceDbType?: string | null,
    initialSql?: string,
    activate?: boolean,
  ) => void;
  openDockTable: (
    tableName: string,
    initialSubtab?: string,
    datasource?: TableTabDatasourceContext,
  ) => void;
  openDockFile: (filePath: string, fileName?: string, projectId?: string) => void;
  openDockArtifacts: (conversationId: string, activate?: boolean) => void;
  openDockArtifact: (artifact: ResultViewArtifact, conversationId?: string) => void;
  openDockMultiTable: (tables: string[]) => void;
  patchSqlConsoleState: (tabId: string, patch: Partial<SqlConsoleTabState>) => void;
  appendSqlConsoleEntries: (tabId: string, entries: ConsoleEntry[]) => void;
  setSelectedTables: (tables: string[] | ((prev: string[]) => string[])) => void;
  setTableSubTabs: (
    updater: Record<string, string> | ((prev: Record<string, string>) => Record<string, string>),
  ) => void;
}

export type WorkspaceStore = WorkspaceState & WorkspaceActions;

function tableTabId(tableName: string, datasource?: TableTabDatasourceContext) {
  return datasource?.id ? `table-${datasource.id}-${tableName}` : `table-${tableName}`;
}

export const useWorkspaceStore = create<WorkspaceStore>()((set, get) => ({
  activeProjectId: "",
  sidebarEntityMode: "connections",
  projectSubMode: {},
  connectionSubMode: {},
  projectShell: {},
  mainSurfaceByProject: {},
  centerMode: "home",
  centerReturnMode: "home",
  pendingAsk: null,
  dock: { open: false, activeTabId: null },
  dockTabs: [],
  sqlConsoleState: {},
  selectedTables: [],
  tableSubTabs: {},
  settingsOpen: false,
  settingsSection: "appearance",

  setActiveProject: (projectId) => set({ activeProjectId: projectId }),
  setSidebarEntityMode: (mode) => set({ sidebarEntityMode: mode }),
  setProjectSubMode: (projectId, mode) =>
    set((state) => ({
      projectSubMode: { ...state.projectSubMode, [projectId]: mode },
    })),
  setConnectionSubMode: (connectionId, mode) =>
    set((state) => ({
      connectionSubMode: { ...state.connectionSubMode, [connectionId]: mode },
    })),

  setProjectSidebarMode: (projectId, mode) =>
    set((state) => ({
      projectShell: {
        ...state.projectShell,
        [projectId]: {
          ...(state.projectShell[projectId] ?? { sidebarMode: "data" }),
          sidebarMode: mode,
        },
      },
    })),

  setProjectActiveDatasource: (projectId, datasourceId) =>
    set((state) => ({
      projectShell: {
        ...state.projectShell,
        [projectId]: {
          ...(state.projectShell[projectId] ?? { sidebarMode: "data" }),
          activeDatasourceId: datasourceId,
        },
      },
    })),

  setProjectActiveConversation: (projectId, conversationId) =>
    set((state) => ({
      projectShell: {
        ...state.projectShell,
        [projectId]: {
          ...(state.projectShell[projectId] ?? { sidebarMode: "data" }),
          activeConversationId: conversationId,
        },
      },
    })),

  setProjectMainSurface: (projectId, surface) =>
    set((state) => ({
      mainSurfaceByProject: {
        ...state.mainSurfaceByProject,
        [projectId]: surface,
      },
    })),

  openSettings: (section = "appearance") =>
    set({ settingsOpen: true, settingsSection: section }),

  closeSettings: () => set({ settingsOpen: false }),

  setSettingsSection: (settingsSection) => set({ settingsSection }),

  patchSqlConsoleState: (tabId, patch) =>
    set((state) => {
      const isOpen = state.dockTabs.some(
        (tab) => tab.kind === "console" && (tab.stateKey ?? `sql-${tab.datasourceId}`) === tabId,
      );
      if (!isOpen) return state;
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
      const isOpen = state.dockTabs.some(
        (tab) => tab.kind === "console" && (tab.stateKey ?? `sql-${tab.datasourceId}`) === tabId,
      );
      if (!isOpen) return state;
      const current = state.sqlConsoleState[tabId];
      if (!current) return state;
      return {
        sqlConsoleState: {
          ...state.sqlConsoleState,
          [tabId]: { ...current, entries: [...current.entries, ...entries] },
        },
      };
    }),

  setSelectedTables: (tables) =>
    set((state) => ({
      selectedTables: typeof tables === "function" ? tables(state.selectedTables) : tables,
    })),

  setTableSubTabs: (updater) =>
    set((state) => ({
      tableSubTabs: typeof updater === "function" ? updater(state.tableSubTabs) : updater,
    })),

  setDockOpen: (open) => set((state) => ({ dock: { ...state.dock, open } })),

  setDockActiveTab: (tabId) =>
    set(() => ({ dock: { open: true, activeTabId: tabId }, settingsOpen: false })),

  closeDockTab: (tabId) => {
    const { dock, dockTabs } = get();
    const nextTabs = dockTabs.filter((tab) => tab.id !== tabId);
    const activeIndex = dockTabs.findIndex((tab) => tab.id === dock.activeTabId);
    const nextActiveId =
      activeIndex >= 0 && dockTabs[activeIndex]?.id === tabId
        ? (nextTabs[Math.min(activeIndex, nextTabs.length - 1)]?.id ?? null)
        : dock.activeTabId;
    set({ dockTabs: nextTabs, dock: { ...dock, activeTabId: nextActiveId } });
  },

  showSmartQueryHome: (initialAsk) =>
    set((state) => ({
      centerMode: "home",
      centerReturnMode: "home",
      pendingAsk: initialAsk ?? null,
      settingsOpen: false,
      mainSurfaceByProject: state.activeProjectId
        ? {
            ...state.mainSurfaceByProject,
            [state.activeProjectId]: { kind: "new-conversation" },
          }
        : state.mainSurfaceByProject,
    })),

  openConversationCenter: (conversationId) =>
    set((state) => ({
      centerMode: "conversation",
      centerReturnMode: "conversation",
      settingsOpen: false,
      mainSurfaceByProject: state.activeProjectId
        ? {
            ...state.mainSurfaceByProject,
            [state.activeProjectId]: {
              kind: "conversation",
              conversationId: conversationId || undefined,
            },
          }
        : state.mainSurfaceByProject,
    })),

  openProjectCreate: () =>
    set((state) => ({
      centerMode: "project-create",
      centerReturnMode: state.centerReturnMode,
      settingsOpen: false,
    })),

  clearPendingAsk: () => set({ pendingAsk: null }),

  openDockConsole: (datasourceId, datasourceDbType, initialSql, activate = true) =>
    set((state) => {
      // P4 F4：一个 Project 一个 canonical SQL Console view。Project 未选择时
      // 保留 datasource fallback，避免旧调用点破坏。
      const projectKey = state.activeProjectId || datasourceId;
      const tabId = `console-${projectKey}`;
      const consoleStateId = `sql-${projectKey}`;
      const existingConsole = state.sqlConsoleState[consoleStateId];
      const tabExists = state.dockTabs.some((tab) => tab.id === tabId);
      return {
        dock: {
          open: activate ? true : state.dock.open,
          activeTabId: activate ? tabId : state.dock.activeTabId,
        },
        dockTabs: tabExists
          ? state.dockTabs.map((tab) =>
              tab.id === tabId
                ? { ...tab, datasourceId, datasourceDbType: datasourceDbType ?? null }
                : tab,
            )
          : [
              ...state.dockTabs,
              {
                id: tabId,
                kind: "console",
                title: "SQL 控制台",
                closeable: false,
                stateKey: consoleStateId,
                datasourceId,
                datasourceDbType: datasourceDbType ?? null,
              },
            ],
        sqlConsoleState: {
          ...state.sqlConsoleState,
          [consoleStateId]: {
            draftSql: initialSql ?? existingConsole?.draftSql ?? defaultSql,
            entries: existingConsole?.entries ?? [],
            running: existingConsole?.running ?? false,
          },
        },
        settingsOpen: false,
      };
    }),

  openDockTable: (tableName, initialSubtab = "preview", datasource) =>
    set((state) => {
      const tabId = tableTabId(tableName, datasource);
      const tabExists = state.dockTabs.some((tab) => tab.id === tabId);
      return {
        dock: { open: true, activeTabId: tabId },
        dockTabs: tabExists
          ? state.dockTabs.map((tab) =>
              tab.id === tabId
                ? {
                    ...tab,
                    tableId: tableName,
                    datasourceId: datasource?.id,
                    datasourceDbType: datasource?.dbType ?? null,
                  }
                : tab,
            )
          : [
              ...state.dockTabs,
              {
                id: tabId,
                kind: "table",
                title: tableName,
                closeable: true,
                tableId: tableName,
                datasourceId: datasource?.id,
                datasourceDbType: datasource?.dbType ?? null,
              },
            ],
        selectedTables: [tableName],
        tableSubTabs: initialSubtab
          ? { ...state.tableSubTabs, [tabId]: initialSubtab }
          : state.tableSubTabs,
        settingsOpen: false,
      };
    }),

  openDockFile: (filePath, fileName, projectId) =>
    set((state) => {
      const resolvedName =
        fileName?.trim()
        || filePath.split("\\").flatMap((part) => part.split("/")).filter(Boolean).at(-1)
        || filePath;
      const tabId = `file-${projectId || "workspace"}-${filePath}`;
      const tab: WorkspaceDockTab = {
        id: tabId,
        kind: "file",
        title: resolvedName,
        closeable: true,
        projectId,
        filePath,
        fileName: resolvedName,
      };
      return {
        dock: { open: true, activeTabId: tabId },
        dockTabs: state.dockTabs.some((item) => item.id === tabId)
          ? state.dockTabs.map((item) =>
              item.id === tabId
                ? { ...item, title: resolvedName, filePath, fileName: resolvedName }
                : item,
            )
          : [...state.dockTabs, tab],
        settingsOpen: false,
      };
    }),

  openDockArtifacts: (conversationId, activate = true) =>
    set((state) => {
      const tabId = `artifacts-${conversationId}`;
      return {
        dock: {
          open: activate ? true : state.dock.open,
          activeTabId: activate ? tabId : state.dock.activeTabId,
        },
        dockTabs: state.dockTabs.some((tab) => tab.id === tabId)
          ? state.dockTabs
          : [
              ...state.dockTabs,
              {
                id: tabId,
                kind: "artifacts",
                title: "工件",
                closeable: false,
                conversationId,
              },
            ],
        settingsOpen: false,
      };
    }),

  openDockArtifact: (artifact, conversationId) =>
    set((state) => {
      const tabId = `artifact-${artifact.id}`;
      const tab: WorkspaceDockTab = {
        id: tabId,
        kind: "artifact",
        title: artifact.title,
        closeable: true,
        conversationId,
        artifact,
      };
      return {
        dock: { open: true, activeTabId: tabId },
        dockTabs: state.dockTabs.some((item) => item.id === tabId)
          ? state.dockTabs.map((item) =>
              item.id === tabId
                ? { ...item, title: artifact.title, artifact, conversationId }
                : item,
            )
          : [...state.dockTabs, tab],
        settingsOpen: false,
      };
    }),

  openDockMultiTable: (tables) => {
    if (tables.length === 0) return;
    // Canonical set identity: dedupe + stable sort; no counter-based tab id.
    const canonicalTables = Array.from(new Set(tables)).sort();
    const tabId = `multi-table-${canonicalTables.join("|")}`;
    const title = `Workspace: ${canonicalTables.slice(0, 2).join(" & ")}${canonicalTables.length > 2 ? "..." : ""}`;
    set((state) => ({
      dock: { open: true, activeTabId: tabId },
      dockTabs: state.dockTabs.some((tab) => tab.id === tabId)
        ? state.dockTabs
        : [
            ...state.dockTabs,
            {
              id: tabId,
              kind: "multi-table",
              title,
              closeable: true,
              selectedTables: canonicalTables,
            },
          ],
      settingsOpen: false,
    }));
  },
}));
