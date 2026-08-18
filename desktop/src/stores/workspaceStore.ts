import { create } from "zustand";
import type {
  MainSurfaceRef,
  WorkspaceCenterMode,
  WorkspaceDockTab,
} from "../types/workspace";
import type { AppSettingsSection } from "../types/settings";

export interface ProjectShellState {
  activeDatasourceId?: string;
  activeConversationId?: string;
}

interface WorkspaceState {
  activeProjectId: string;
  projectShell: Record<string, ProjectShellState>;
  mainSurfaceByProject: Record<string, MainSurfaceRef>;
  centerMode: WorkspaceCenterMode;
  centerReturnMode: WorkspaceCenterMode;
  pendingAsk: string | null;
  dock: { open: boolean; activeTabId: string | null };
  dockTabs: WorkspaceDockTab[];
  settingsOpen: boolean;
  settingsSection: AppSettingsSection;
}

interface WorkspaceActions {
  setActiveProject: (projectId: string) => void;
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
  openDockTab: (tab: WorkspaceDockTab, activate?: boolean) => void;
  updateDockTab: (tabId: string, patch: Partial<WorkspaceDockTab>) => void;
}

export type WorkspaceStore = WorkspaceState & WorkspaceActions;

export const useWorkspaceStore = create<WorkspaceStore>()((set, get) => ({
  activeProjectId: "",
  projectShell: {},
  mainSurfaceByProject: {},
  centerMode: "home",
  centerReturnMode: "home",
  pendingAsk: null,
  dock: { open: false, activeTabId: null },
  dockTabs: [],
  settingsOpen: false,
  settingsSection: "appearance",

  setActiveProject: (projectId) => set({ activeProjectId: projectId }),

  setProjectActiveDatasource: (projectId, datasourceId) =>
    set((state) => ({
      projectShell: {
        ...state.projectShell,
        [projectId]: {
          ...(state.projectShell[projectId] ?? {}),
          activeDatasourceId: datasourceId,
        },
      },
    })),

  setProjectActiveConversation: (projectId, conversationId) =>
    set((state) => ({
      projectShell: {
        ...state.projectShell,
        [projectId]: {
          ...(state.projectShell[projectId] ?? {}),
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


  openDockTab: (tab, activate = true) =>
    set((state) => {
      const tabExists = state.dockTabs.some((item) => item.id === tab.id);
      return {
        dock: {
          open: activate ? true : state.dock.open,
          activeTabId: activate ? tab.id : state.dock.activeTabId,
        },
        dockTabs: tabExists
          ? state.dockTabs.map((item) => (item.id === tab.id ? { ...item, ...tab } : item))
          : [...state.dockTabs, tab],
        settingsOpen: false,
      };
    }),

  updateDockTab: (tabId, patch) =>
    set((state) => ({
      dockTabs: state.dockTabs.map((tab) =>
        tab.id === tabId ? { ...tab, ...patch } : tab
      ),
    })),

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

}));
