import { create } from "zustand";
import type {
  MainSurfaceRef,
  WorkspaceCenterMode,
  WorkspaceDockTab,
} from "../types/workspace";
import type { AppSettingsSection } from "../types/settings";

export interface ProjectShellState {
  activeConversationId?: string;
}

interface WorkspaceState {
  activeProjectId: string;
  projectShell: Record<string, ProjectShellState>;
  mainSurfaceByProject: Record<string, MainSurfaceRef>;
  centerMode: WorkspaceCenterMode;
  centerReturnMode: WorkspaceCenterMode;
  pendingAsk: string | null;
  dock: { open: boolean; activeViewKey: string | null };
  dockTabs: WorkspaceDockTab[];
  settingsOpen: boolean;
  settingsSection: AppSettingsSection;
}

interface WorkspaceActions {
  setActiveProject: (projectId: string) => void;
  setProjectActiveConversation: (projectId: string, conversationId: string) => void;
  setProjectMainSurface: (projectId: string, surface: MainSurfaceRef) => void;
  openSettings: (section?: AppSettingsSection) => void;
  closeSettings: () => void;
  setSettingsSection: (section: AppSettingsSection) => void;
  setDockOpen: (open: boolean) => void;
  setDockActiveTab: (viewKey: string) => void;
  closeDockTab: (viewKey: string) => void;
  showSmartQueryHome: (initialAsk?: string) => void;
  openConversationCenter: (conversationId?: string) => void;
  openProjectCreate: () => void;
  clearPendingAsk: () => void;
  openDockTab: (tab: WorkspaceDockTab, activate?: boolean) => void;
  updateDockTab: (
    viewKey: string,
    patch: Partial<Omit<WorkspaceDockTab, "viewKey" | "viewType">>,
  ) => void;
}

export type WorkspaceStore = WorkspaceState & WorkspaceActions;

export const useWorkspaceStore = create<WorkspaceStore>()((set, get) => ({
  activeProjectId: "",
  projectShell: {},
  mainSurfaceByProject: {},
  centerMode: "home",
  centerReturnMode: "home",
  pendingAsk: null,
  dock: { open: false, activeViewKey: null },
  dockTabs: [],
  settingsOpen: false,
  settingsSection: "appearance",

  setActiveProject: (projectId) => set({ activeProjectId: projectId }),

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

  setDockActiveTab: (viewKey) =>
    set((state) => ({
      dock: { ...state.dock, open: true, activeViewKey: viewKey },
      settingsOpen: false,
    })),

  closeDockTab: (viewKey) => {
    const { dock, dockTabs } = get();
    const nextTabs = dockTabs.filter((tab) => tab.viewKey !== viewKey);
    const currentActiveKey = dock.activeViewKey;
    const activeIndex = dockTabs.findIndex((tab) => tab.viewKey === currentActiveKey);
    const nextActiveKey =
      activeIndex >= 0 && dockTabs[activeIndex]?.viewKey === viewKey
        ? (nextTabs[Math.min(activeIndex, nextTabs.length - 1)]?.viewKey ?? null)
        : currentActiveKey;
    set({
      dockTabs: nextTabs,
      dock: { ...dock, activeViewKey: nextActiveKey },
    });
  },

  openDockTab: (tab, activate = true) =>
    set((state) => {
      const existing = state.dockTabs.find((item) => item.viewKey === tab.viewKey);
      if (existing && existing.viewType !== tab.viewType) {
        throw new Error(
          `Cannot open tab with viewKey "${tab.viewKey}" and viewType "${tab.viewType}": already registered with viewType "${existing.viewType}".`,
        );
      }
      const nextActiveKey = activate ? tab.viewKey : state.dock.activeViewKey;
      return {
        dock: {
          open: activate ? true : state.dock.open,
          activeViewKey: nextActiveKey,
        },
        dockTabs: existing
          ? state.dockTabs.map((item) =>
              item.viewKey === tab.viewKey ? { ...item, ...tab } : item,
            )
          : [...state.dockTabs, tab],
        settingsOpen: false,
      };
    }),

  updateDockTab: (viewKey, patch) =>
    set((state) => {
      const safePatch = { ...patch };
      delete (safePatch as Record<string, unknown>).viewKey;
      delete (safePatch as Record<string, unknown>).viewType;
      return {
        dockTabs: state.dockTabs.map((tab) =>
          tab.viewKey === viewKey ? { ...tab, ...safePatch } : tab,
        ),
      };
    }),

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
