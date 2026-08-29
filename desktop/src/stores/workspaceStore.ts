import { create } from "zustand";
import type { WorkbenchReference } from "../types/workspace";
import type {
  MainSurfaceRef,
  WorkspaceCenterMode,
  WorkspaceDockTab,
} from "../types/workspace";
import type { AppSettingsSection } from "../types/settings";

export interface ConversationWorkbenchState {
  scopeId: string;
  open: boolean;
  activeViewKey: string | null;
  tabs: WorkspaceDockTab[];
  references: WorkbenchReference[];
}

interface WorkspaceState {
  activeProjectId: string;
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
  promoteDraftWorkbenchToConversation: (projectId: string, conversationId: string) => void;
  setProjectMainSurface: (projectId: string, surface: MainSurfaceRef) => void;
  openSettings: (section?: AppSettingsSection) => void;
  closeSettings: () => void;
  setSettingsSection: (section: AppSettingsSection) => void;
  setDockOpen: (open: boolean) => void;
  setDockActiveTab: (viewKey: string) => void;
  closeDockTab: (viewKey: string) => void;
  reconcileDockViewTypes: (allowedViewTypes: readonly string[]) => void;
  showSmartQueryHome: (initialAsk?: string) => void;
  showProjectOverview: () => void;
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
  addWorkbenchReference: (reference: WorkbenchReference) => void;
  removeWorkbenchReference: (reference: WorkbenchReference) => void;
  clearWorkbenchReferences: () => void;
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
    references: [],
  };
}

const EMPTY_WORKBENCH: ConversationWorkbenchState = Object.freeze({
  scopeId: "workbench-empty",
  open: false,
  activeViewKey: null,
  tabs: Object.freeze([]) as unknown as WorkspaceDockTab[],
  references: Object.freeze([]) as unknown as WorkbenchReference[],
});

export function getActiveWorkbenchKey(
  state: Pick<WorkspaceState, "activeProjectId" | "mainSurfaceByProject">,
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
  return `draft:${projectId}`;
}

/** The shell surface is the sole authority for the selected Conversation. */
export function selectActiveConversationId(
  state: Pick<WorkspaceState, "activeProjectId" | "mainSurfaceByProject">,
): string | null {
  const surface = state.activeProjectId
    ? state.mainSurfaceByProject[state.activeProjectId]
    : undefined;
  return surface?.kind === "conversation" && surface.conversationId
    ? surface.conversationId
    : null;
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
export const selectActiveWorkbenchReferences = (
  state: WorkspaceStore,
): WorkbenchReference[] => selectActiveWorkbench(state).references;

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
    set((state) => ({
      mainSurfaceByProject: {
        ...state.mainSurfaceByProject,
        [projectId]: { kind: "conversation", conversationId },
      },
    })),

  promoteDraftWorkbenchToConversation: (projectId, conversationId) =>
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

  reconcileDockViewTypes: (allowedViewTypes) =>
    set((state) => {
      const allowed = new Set(allowedViewTypes);
      const workbenchByConversation = Object.fromEntries(
        Object.entries(state.workbenchByConversation).map(([key, workbench]) => {
          const tabs = workbench.tabs.filter((tab) => allowed.has(tab.viewType));
          const activeViewKey = tabs.some((tab) => tab.viewKey === workbench.activeViewKey)
            ? workbench.activeViewKey
            : (tabs[0]?.viewKey ?? null);
          return [key, {
            ...workbench,
            tabs,
            activeViewKey,
            open: tabs.length ? workbench.open : false,
          }];
        }),
      );
      return { workbenchByConversation };
    }),

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

  addWorkbenchReference: (reference) =>
    set((state) => updateActiveWorkbench(state, (workbench) => ({
      ...workbench,
      references: workbench.references.some(
        (item) => workbenchReferenceKey(item) === workbenchReferenceKey(reference),
      )
        ? workbench.references
        : [...workbench.references, reference].slice(-12),
    }))),

  removeWorkbenchReference: (reference) =>
    set((state) => updateActiveWorkbench(state, (workbench) => ({
      ...workbench,
      references: workbench.references.filter(
        (item) => workbenchReferenceKey(item) !== workbenchReferenceKey(reference),
      ),
    }))),

  clearWorkbenchReferences: () =>
    set((state) => updateActiveWorkbench(state, (workbench) => ({
      ...workbench,
      references: [],
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
        mainSurfaceByProject: projectId
          ? {
              ...state.mainSurfaceByProject,
              [projectId]: { kind: "new-conversation" },
            }
          : state.mainSurfaceByProject,
      };
    }),

  showProjectOverview: () =>
    set((state) => ({
      centerMode: "project",
      centerReturnMode: "project",
      pendingAsk: null,
      settingsOpen: false,
      mainSurfaceByProject: state.activeProjectId
        ? {
            ...state.mainSurfaceByProject,
            [state.activeProjectId]: { kind: "project-overview" },
          }
        : state.mainSurfaceByProject,
    })),

  openConversationCenter: (conversationId) =>
    set((state) => {
      const projectId = state.activeProjectId;
      const targetConversationId = conversationId
        ?? (projectId && state.mainSurfaceByProject[projectId]?.kind === "conversation"
          ? state.mainSurfaceByProject[projectId].conversationId
          : undefined);
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

function workbenchReferenceKey(reference: WorkbenchReference): string {
  if (reference.artifactId) return `artifact:${reference.artifactId}`;
  if (reference.object) {
    return `object:${reference.object.kind}:${reference.object.id}:${reference.object.version ?? ""}`;
  }
  if (reference.authority) {
    return `authority:${reference.authority.kind}:${reference.authority.id}:${reference.locator ?? ""}`;
  }
  return `locator:${reference.locator ?? reference.label}`;
}
