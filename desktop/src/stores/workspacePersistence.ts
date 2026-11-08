import { createJSONStorage } from "zustand/middleware";
import { z } from "zod";
import type { WorkspaceStore } from "./workspaceStore";

export const WORKSPACE_STORAGE_KEY = "dbfox-workspace-v1";
const identity = z.string().min(1).max(4096);
const resource = z.object({ kind: identity, id: identity });
const object = resource.extend({ version: z.union([z.string(), z.number(), z.null()]).optional() });
const tabSchema = z.object({
  viewKey: identity, viewType: identity, title: z.string().max(240), closeable: z.boolean(),
  preview: z.boolean().optional(), projectId: identity.optional(), sessionId: identity.optional(),
  stateKey: identity.optional(), selectedViewId: identity.optional(),
  target: z.discriminatedUnion("type", [
    z.object({ type: z.literal("object"), object, authority: resource.optional(), locator: identity.optional() }),
    z.object({ type: z.literal("artifact"), id: identity }),
    z.object({ type: z.literal("conversation"), id: identity }),
  ]).optional(),
});
const surfaceSchema = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("conversation"), conversationId: identity }),
  z.object({ kind: z.literal("new-conversation") }),
  z.object({ kind: z.literal("project-overview") }),
]);
const snapshotSchema = z.object({
  activeProjectId: z.string().max(4096),
  sidebarCollapsed: z.boolean().default(false),
  mainSurfaceByProject: z.record(identity, surfaceSchema),
  workbenchByConversation: z.record(identity, z.object({
    scopeId: identity, open: z.boolean(), activeViewKey: identity.nullable(),
    tabs: z.array(tabSchema).max(12), dockWidth: z.number().min(320).max(2400).optional(),
  })),
});

/** Optional layout preferences must never make navigation fail on quota/permission errors. */
export const workspaceStorage = createJSONStorage(() => ({
  getItem: (name: string) => { try { return localStorage.getItem(name); } catch { return null; } },
  setItem: (name: string, value: string) => { try { if (localStorage.getItem(name) !== value) localStorage.setItem(name, value); } catch { /* Best-effort UI layout only. */ } },
  removeItem: (name: string) => { try { localStorage.removeItem(name); } catch { /* Best-effort UI layout only. */ } },
}));

function retainActive<T>(entries: [string, T][], activeKey: string, limit: number): [string, T][] {
  const active = entries.find(([key]) => key === activeKey);
  return active
    ? [...entries.filter(([key]) => key !== activeKey).slice(-(limit - 1)), active]
    : entries.slice(-limit);
}

export function workspaceSnapshot(state: WorkspaceStore) {
  const surface = state.mainSurfaceByProject[state.activeProjectId];
  const activeWorkbenchKey = (surface?.kind === "conversation" && surface.conversationId) || `draft:${state.activeProjectId}`;
  return {
    activeProjectId: state.activeProjectId,
    sidebarCollapsed: state.sidebarCollapsed,
    mainSurfaceByProject: Object.fromEntries(retainActive(Object.entries(state.mainSurfaceByProject), state.activeProjectId, 40)
      .flatMap(([key, surface]) => {
        const parsed = surfaceSchema.safeParse(surface);
        return parsed.success ? [[key, parsed.data]] : [];
      })),
    workbenchByConversation: Object.fromEntries(retainActive(Object.entries(state.workbenchByConversation)
      .filter(([, value]) => value.tabs.length > 0 || value.open || value.dockWidth !== undefined), activeWorkbenchKey, 40)
      .map(([key, value]) => [key, {
        scopeId: value.scopeId, open: value.open, activeViewKey: value.activeViewKey,
        dockWidth: value.dockWidth,
        tabs: retainActive(value.tabs.map(tab => [tab.viewKey, tab]), value.activeViewKey ?? "", 12).flatMap(([, tab]) => {
          const parsed = tabSchema.safeParse({ ...tab, title: tab.title.slice(0, 240) });
          return parsed.success ? [parsed.data] : [];
        }),
      }])),
  };
}

export function restoreWorkspaceSnapshot(value: unknown, current: WorkspaceStore): WorkspaceStore {
  const parsed = snapshotSchema.safeParse(value);
  if (!parsed.success) return current;
  const saved = parsed.data;
  const surface = saved.mainSurfaceByProject[saved.activeProjectId];
  const mode = surface?.kind === "conversation" ? "conversation"
    : surface?.kind === "project-overview" ? "project" : "home";
  return {
    ...current, ...saved, centerMode: mode, centerReturnMode: mode,
    // Restore navigation identities; execution, drafts and resource authority are read afresh.
    workbenchByConversation: Object.fromEntries(Object.entries(saved.workbenchByConversation)
      .map(([key, workbench]) => [key, { ...workbench, references: [] }])),
  };
}
