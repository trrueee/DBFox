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

export interface ConversationWorkbenchState {
  open: boolean;
  activeViewKey: string | null;
  tabs: WorkspaceDockTab[];
}

interface WorkspaceState {
  activeProjectId: string;
  projectShell: Record<string, ProjectShellState>;
  mainSurfaceByProject: Record<string, MainSurfaceRef>;
  workbenchByConversation: Record<string, ConversationWorkbenchState>;
  centerMode: WorkspaceCenterMode;
  centerReturnMode: WorkspaceCenterMode;
  pendingAsk: string | null;
  dock: { open: boolean; activeViewKey: string | null };
  dockTabs: WorkspaceDockTab[];
  settingsOpen: boolean;
  settingsSection: AppSettingsSection;
  projectCreateOpen: boolean;
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
  closeProjectCreate: () => void;
  setProjectCreateOpen: (open: boolean) => void;
  clearPendingAsk: () => void;
  openDockTab: (tab: WorkspaceDockTab, activate?: boolean) => void;
  updateDockTab: (
    viewKey: string,
    patch: Partial<Omit<WorkspaceDockTab, "viewKey" | "viewType">>,
  ) => void;
}

export type WorkspaceStore = WorkspaceState & WorkspaceActions;

function getActiveConversationKey(state: WorkspaceState, conversationIdOverride?: string): string {
  if (conversationIdOverride) return conversationIdOverride;
  const projectId = state.activeProjectId;
  if (!projectId) return "draft:default";
  const convId = state.projectShell[projectId]?.activeConversationId;
  if (convId) return convId;
  const surface = state.mainSurfaceByProject[projectId];
  if (surface && surface.kind === "conversation" && surface.conversationId) {
    return surface.conversationId;
  }
  return `draft:${projectId}`;
}

export const useWorkspaceStore = create<WorkspaceStore>()((set, get) => ({
  activeProjectId: "",
  projectShell: {},
  mainSurfaceByProject: {},
  workbenchByConversation: {},
  centerMode: "home",
  centerReturnMode: "home",
  pendingAsk: null,
  dock: { open: false, activeViewKey: null },
  dockTabs: [],
  settingsOpen: false,
  settingsSection: "appearance",
  projectCreateOpen: false,

  setActiveProject: (projectId) =>
    set((state) => {
      const storedConvId = state.projectShell[projectId]?.activeConversationId;
      const targetKey = storedConvId || (projectId ? `draft:${projectId}` : "draft:default");
      const currentWorkbench = state.workbenchByConversation[targetKey];
      return {
        activeProjectId: projectId,
        dock: currentWorkbench ? { open: currentWorkbench.open, activeViewKey: currentWorkbench.activeViewKey } : { open: false, activeViewKey: null },
        dockTabs: currentWorkbench ? currentWorkbench.tabs : [],
      };
    }),

  setProjectActiveConversation: (projectId, conversationId) =>
    set((state) => {
      const nextProjectShell = {
        ...state.projectShell,
        [projectId]: {
          ...(state.projectShell[projectId] ?? {}),
          activeConversationId: conversationId,
        },
      };
      const draftKey = `draft:${projectId}`;
      const draftWorkbench = state.workbenchByConversation[draftKey];
      const existingWorkbench = state.workbenchByConversation[conversationId];
      const currentWorkbench = existingWorkbench ?? draftWorkbench;

      const nextWorkbenchByConversation = { ...state.workbenchByConversation };
      if (!existingWorkbench && draftWorkbench) {
        nextWorkbenchByConversation[conversationId] = draftWorkbench;
        delete nextWorkbenchByConversation[draftKey];
      }

      const isCurrentProject = state.activeProjectId === projectId;

      return {
        projectShell: nextProjectShell,
        workbenchByConversation: nextWorkbenchByConversation,
        ...(isCurrentProject
          ? {
              dock: currentWorkbench
                ? { open: currentWorkbench.open, activeViewKey: currentWorkbench.activeViewKey }
                : { open: false, activeViewKey: null },
              dockTabs: currentWorkbench ? currentWorkbench.tabs : [],
            }
          : {}),
      };
    }),

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

  setDockOpen: (open) =>
    set((state) => {
      const key = getActiveConversationKey(state);
      const prevWorkbench = state.workbenchByConversation[key] ?? {
        open: state.dock.open,
        activeViewKey: state.dock.activeViewKey,
        tabs: state.dockTabs,
      };
      const updatedWorkbench: ConversationWorkbenchState = {
        ...prevWorkbench,
        open,
      };
      return {
        dock: { ...state.dock, open },
        workbenchByConversation: {
          ...state.workbenchByConversation,
          [key]: updatedWorkbench,
        },
      };
    }),

  setDockActiveTab: (viewKey) =>
    set((state) => {
      const key = getActiveConversationKey(state);
      const prevWorkbench = state.workbenchByConversation[key] ?? {
        open: state.dock.open,
        activeViewKey: state.dock.activeViewKey,
        tabs: state.dockTabs,
      };
      const updatedWorkbench: ConversationWorkbenchState = {
        ...prevWorkbench,
        open: true,
        activeViewKey: viewKey,
      };
      return {
        dock: { ...state.dock, open: true, activeViewKey: viewKey },
        workbenchByConversation: {
          ...state.workbenchByConversation,
          [key]: updatedWorkbench,
        },
        settingsOpen: false,
      };
    }),

  closeDockTab: (viewKey) => {
    const state = get();
    const key = getActiveConversationKey(state);
    const { dock, dockTabs } = state;
    const nextTabs = dockTabs.filter((tab) => tab.viewKey !== viewKey);
    const currentActiveKey = dock.activeViewKey;
    const activeIndex = dockTabs.findIndex((tab) => tab.viewKey === currentActiveKey);
    const nextActiveKey =
      activeIndex >= 0 && dockTabs[activeIndex]?.viewKey === viewKey
        ? (nextTabs[Math.min(activeIndex, nextTabs.length - 1)]?.viewKey ?? null)
        : currentActiveKey;
    const updatedWorkbench: ConversationWorkbenchState = {
      open: dock.open,
      activeViewKey: nextActiveKey,
      tabs: nextTabs,
    };
    set({
      dockTabs: nextTabs,
      dock: { open: dock.open, activeViewKey: nextActiveKey },
      workbenchByConversation: {
        ...state.workbenchByConversation,
        [key]: updatedWorkbench,
      },
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
      const nextTabs = existing
        ? state.dockTabs.map((item) =>
            item.viewKey === tab.viewKey ? { ...item, ...tab } : item,
          )
        : [...state.dockTabs, tab];
      const nextDock = {
        open: activate ? true : state.dock.open,
        activeViewKey: nextActiveKey,
      };
      const key = getActiveConversationKey(state);
      const updatedWorkbench: ConversationWorkbenchState = {
        open: nextDock.open,
        activeViewKey: nextDock.activeViewKey,
        tabs: nextTabs,
      };

      return {
        dock: nextDock,
        dockTabs: nextTabs,
        workbenchByConversation: {
          ...state.workbenchByConversation,
          [key]: updatedWorkbench,
        },
        settingsOpen: false,
      };
    }),

  updateDockTab: (viewKey, patch) =>
    set((state) => {
      const safePatch = { ...patch };
      delete (safePatch as Record<string, unknown>).viewKey;
      delete (safePatch as Record<string, unknown>).viewType;
      const nextTabs = state.dockTabs.map((tab) =>
        tab.viewKey === viewKey ? { ...tab, ...safePatch } : tab,
      );
      const key = getActiveConversationKey(state);
      const prevWorkbench = state.workbenchByConversation[key] ?? {
        open: state.dock.open,
        activeViewKey: state.dock.activeViewKey,
        tabs: state.dockTabs,
      };
      return {
        dockTabs: nextTabs,
        workbenchByConversation: {
          ...state.workbenchByConversation,
          [key]: {
            ...prevWorkbench,
            tabs: nextTabs,
          },
        },
      };
    }),

  showSmartQueryHome: (initialAsk) =>
    set((state) => {
      const projectId = state.activeProjectId;
      const homeKey = projectId ? `project:${projectId}` : "__default__";
      const homeWorkbench = state.workbenchByConversation[homeKey];
      return {
        centerMode: "home",
        centerReturnMode: "home",
        pendingAsk: initialAsk ?? null,
        settingsOpen: false,
        dock: homeWorkbench ? { open: homeWorkbench.open, activeViewKey: homeWorkbench.activeViewKey } : { open: false, activeViewKey: null },
        dockTabs: homeWorkbench ? homeWorkbench.tabs : [],
        mainSurfaceByProject: projectId
          ? {
              ...state.mainSurfaceByProject,
              [projectId]: { kind: "new-conversation" },
            }
          : state.mainSurfaceByProject,
      };
    }),

  openConversationCenter: (conversationId) =>
    set((state) => {
      const projectId = state.activeProjectId;
      const targetConvId = conversationId || (projectId ? state.projectShell[projectId]?.activeConversationId : undefined);
      const targetKey = targetConvId || (projectId ? `project:${projectId}` : "__default__");
      const targetWorkbench = state.workbenchByConversation[targetKey];

      return {
        centerMode: "conversation",
        centerReturnMode: "conversation",
        settingsOpen: false,
        dock: targetWorkbench ? { open: targetWorkbench.open, activeViewKey: targetWorkbench.activeViewKey } : { open: false, activeViewKey: null },
        dockTabs: targetWorkbench ? targetWorkbench.tabs : [],
        mainSurfaceByProject: projectId
          ? {
              ...state.mainSurfaceByProject,
              [projectId]: {
                kind: "conversation",
                conversationId: conversationId || undefined,
              },
            }
          : state.mainSurfaceByProject,
        projectShell: projectId && conversationId
          ? {
              ...state.projectShell,
              [projectId]: {
                ...(state.projectShell[projectId] ?? {}),
                activeConversationId: conversationId,
              },
            }
          : state.projectShell,
      };
    }),

  openProjectCreate: () =>
    set({
      projectCreateOpen: true,
      settingsOpen: false,
    }),

  closeProjectCreate: () => set({ projectCreateOpen: false }),

  setProjectCreateOpen: (projectCreateOpen) =>
    set((state) => ({
      projectCreateOpen,
      settingsOpen: projectCreateOpen ? false : state.settingsOpen,
    })),

  clearPendingAsk: () => set({ pendingAsk: null }),
}));
