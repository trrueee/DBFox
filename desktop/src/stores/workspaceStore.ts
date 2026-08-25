import { create } from "zustand";
import type { WorkbenchReference } from "../../../sdk/frontend/index";
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
  scopeId: string;
  open: boolean;
  activeViewKey: string | null;
  tabs: WorkspaceDockTab[];
  reference: WorkbenchReference | null;
}

interface WorkspaceState {
  activeProjectId: string;
  projectShell: Record<string, ProjectShellState>;
  mainSurfaceByProject: Record<string, MainSurfaceRef>;
  workbenchByConversation: Record<string, ConversationWorkbenchState>;
  centerMode: WorkspaceCenterMode;
  centerReturnMode: WorkspaceCenterMode;
  pendingAsk: string | null;
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
  setWorkbenchReference: (reference: WorkbenchReference | null) => void;
  ensureActiveWorkbenchScope: () => string;
}

export type WorkspaceStore = WorkspaceState & WorkspaceActions;

let workbenchScopeSequence = 0;

function createWorkbenchScopeId(): string {
  const randomUuid = globalThis.crypto?.randomUUID;
  if (typeof randomUuid === "function") return randomUuid.call(globalThis.crypto);
  workbenchScopeSequence += 1;
  return `workbench-${workbenchScopeSequence}`;
}

function createWorkbench(): ConversationWorkbenchState {
  return {
    scopeId: createWorkbenchScopeId(),
    open: false,
    activeViewKey: null,
    tabs: [],
    reference: null,
  };
}

const EMPTY_WORKBENCH: ConversationWorkbenchState = Object.freeze({
  scopeId: "workbench-empty",
  open: false,
  activeViewKey: null,
  tabs: Object.freeze([]) as unknown as WorkspaceDockTab[],
  reference: null,
});

export function getActiveWorkbenchKey(
  state: Pick<WorkspaceState, "activeProjectId" | "projectShell" | "mainSurfaceByProject">,
  conversationIdOverride?: string,
): string {
  if (conversationIdOverride) return conversationIdOverride;
  const projectId = state.activeProjectId;
  if (!projectId) return "draft:default";
  const surface = state.mainSurfaceByProject[projectId];
  if (surface?.kind === "new-conversation") return `draft:${projectId}`;
  if (surface?.kind === "conversation" && surface.conversationId) {
    return surface.conversationId;
  }
  return state.projectShell[projectId]?.activeConversationId ?? `draft:${projectId}`;
}

export function selectActiveWorkbench(state: WorkspaceStore): ConversationWorkbenchState {
  return state.workbenchByConversation[getActiveWorkbenchKey(state)] ?? EMPTY_WORKBENCH;
}

export const selectActiveDockOpen = (state: WorkspaceStore): boolean =>
  selectActiveWorkbench(state).open;
export const selectActiveDockViewKey = (state: WorkspaceStore): string | null =>
  selectActiveWorkbench(state).activeViewKey;
export const selectActiveDockTabs = (state: WorkspaceStore): WorkspaceDockTab[] =>
  selectActiveWorkbench(state).tabs;
export const selectActiveWorkbenchScopeId = (state: WorkspaceStore): string =>
  selectActiveWorkbench(state).scopeId;
export const selectActiveWorkbenchReference = (
  state: WorkspaceStore,
): WorkbenchReference | null => selectActiveWorkbench(state).reference;

function updateActiveWorkbench(
  state: WorkspaceState,
  update: (workbench: ConversationWorkbenchState) => ConversationWorkbenchState,
): Pick<WorkspaceState, "workbenchByConversation"> {
  const key = getActiveWorkbenchKey(state);
  const current = state.workbenchByConversation[key] ?? createWorkbench();
  return {
    workbenchByConversation: {
      ...state.workbenchByConversation,
      [key]: update(current),
    },
  };
}

export const useWorkspaceStore = create<WorkspaceStore>()((set, get) => ({
  activeProjectId: "",
  projectShell: {},
  mainSurfaceByProject: {},
  workbenchByConversation: {},
  centerMode: "home",
  centerReturnMode: "home",
  pendingAsk: null,
  settingsOpen: false,
  settingsSection: "appearance",
  projectCreateOpen: false,

  setActiveProject: (activeProjectId) => set({ activeProjectId }),

  setProjectActiveConversation: (projectId, conversationId) =>
    set((state) => {
      const draftKey = `draft:${projectId}`;
      const nextWorkbenches = { ...state.workbenchByConversation };
      if (!nextWorkbenches[conversationId] && nextWorkbenches[draftKey]) {
        // The stable scope ID lets capability-owned state follow the draft
        // into the durable Conversation without copying domain state.
        nextWorkbenches[conversationId] = nextWorkbenches[draftKey];
        delete nextWorkbenches[draftKey];
      }
      return {
        projectShell: {
          ...state.projectShell,
          [projectId]: {
            ...(state.projectShell[projectId] ?? {}),
            activeConversationId: conversationId,
          },
        },
        workbenchByConversation: nextWorkbenches,
      };
    }),

  setProjectMainSurface: (projectId, surface) =>
    set((state) => ({
      mainSurfaceByProject: { ...state.mainSurfaceByProject, [projectId]: surface },
    })),

  openSettings: (settingsSection = "appearance") =>
    set({ settingsOpen: true, settingsSection }),
  closeSettings: () => set({ settingsOpen: false }),
  setSettingsSection: (settingsSection) => set({ settingsSection }),

  setDockOpen: (open) =>
    set((state) => updateActiveWorkbench(state, (workbench) => ({ ...workbench, open }))),

  setDockActiveTab: (activeViewKey) =>
    set((state) => ({
      ...updateActiveWorkbench(state, (workbench) => ({
        ...workbench,
        open: true,
        activeViewKey,
      })),
      settingsOpen: false,
    })),

  closeDockTab: (viewKey) =>
    set((state) => updateActiveWorkbench(state, (workbench) => {
      const tabs = workbench.tabs.filter((tab) => tab.viewKey !== viewKey);
      const activeIndex = workbench.tabs.findIndex(
        (tab) => tab.viewKey === workbench.activeViewKey,
      );
      const activeViewKey = workbench.activeViewKey === viewKey
        ? (tabs[Math.min(Math.max(activeIndex, 0), tabs.length - 1)]?.viewKey ?? null)
        : workbench.activeViewKey;
      return { ...workbench, tabs, activeViewKey };
    })),

  openDockTab: (tab, activate = true) =>
    set((state) => ({
      ...updateActiveWorkbench(state, (workbench) => {
        const existing = workbench.tabs.find((item) => item.viewKey === tab.viewKey);
        if (existing && existing.viewType !== tab.viewType) {
          throw new Error(
            `Cannot open tab with viewKey "${tab.viewKey}" and viewType "${tab.viewType}": already registered with viewType "${existing.viewType}".`,
          );
        }
        const tabs = existing
          ? workbench.tabs.map((item) => item.viewKey === tab.viewKey ? { ...item, ...tab } : item)
          : [...workbench.tabs, tab];
        return {
          ...workbench,
          tabs,
          open: activate ? true : workbench.open,
          activeViewKey: activate ? tab.viewKey : workbench.activeViewKey,
        };
      }),
      settingsOpen: false,
    })),

  updateDockTab: (viewKey, patch) =>
    set((state) => updateActiveWorkbench(state, (workbench) => {
      const safePatch = { ...patch };
      delete (safePatch as Record<string, unknown>).viewKey;
      delete (safePatch as Record<string, unknown>).viewType;
      return {
        ...workbench,
        tabs: workbench.tabs.map((tab) =>
          tab.viewKey === viewKey ? { ...tab, ...safePatch } : tab,
        ),
      };
    })),

  setWorkbenchReference: (reference) =>
    set((state) => updateActiveWorkbench(state, (workbench) => ({
      ...workbench,
      reference,
    }))),

  ensureActiveWorkbenchScope: () => {
    const state = get();
    const key = getActiveWorkbenchKey(state);
    const existing = state.workbenchByConversation[key];
    if (existing) return existing.scopeId;
    const created = createWorkbench();
    set({
      workbenchByConversation: {
        ...state.workbenchByConversation,
        [key]: created,
      },
    });
    return created.scopeId;
  },

  showSmartQueryHome: (initialAsk) =>
    set((state) => {
      const projectId = state.activeProjectId;
      return {
        centerMode: "home",
        centerReturnMode: "home",
        pendingAsk: initialAsk ?? null,
        settingsOpen: false,
        projectShell: projectId
          ? {
              ...state.projectShell,
              [projectId]: {
                ...(state.projectShell[projectId] ?? {}),
                activeConversationId: undefined,
              },
            }
          : state.projectShell,
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
      const targetConversationId = conversationId
        ?? (projectId ? state.projectShell[projectId]?.activeConversationId : undefined);
      return {
        centerMode: "conversation",
        centerReturnMode: "conversation",
        settingsOpen: false,
        mainSurfaceByProject: projectId
          ? {
              ...state.mainSurfaceByProject,
              [projectId]: targetConversationId
                ? { kind: "conversation", conversationId: targetConversationId }
                : { kind: "new-conversation" },
            }
          : state.mainSurfaceByProject,
        projectShell: projectId && targetConversationId
          ? {
              ...state.projectShell,
              [projectId]: {
                ...(state.projectShell[projectId] ?? {}),
                activeConversationId: targetConversationId,
              },
            }
          : state.projectShell,
      };
    }),

  openProjectCreate: () => set({ projectCreateOpen: true, settingsOpen: false }),
  closeProjectCreate: () => set({ projectCreateOpen: false }),
  setProjectCreateOpen: (projectCreateOpen) =>
    set((state) => ({
      projectCreateOpen,
      settingsOpen: projectCreateOpen ? false : state.settingsOpen,
    })),
  clearPendingAsk: () => set({ pendingAsk: null }),
}));
