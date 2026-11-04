import { beforeEach, describe, expect, it, vi } from "vitest";
import { selectActiveWorkbench, useWorkspaceStore } from "../workspaceStore";
import { WORKSPACE_STORAGE_KEY, restoreWorkspaceSnapshot, workspaceSnapshot, workspaceStorage } from "../workspacePersistence";

beforeEach(() => {
  localStorage.clear();
  useWorkspaceStore.setState({ activeProjectId: "p1", mainSurfaceByProject: { p1: { kind: "conversation", conversationId: "c1" } }, workbenchByConversation: {}, sidebarCollapsed: false, pendingAsk: null });
});

describe("workspace navigation persistence", () => {
  it("restores the last conversation, Dock tabs and manual width without persisting task inputs or authority", async () => {
    const store = useWorkspaceStore.getState();
    store.openDockTab({ viewKey: "file:one", viewType: "dbfox.workspace.file", title: "report.md", closeable: true, projectId: "p1", target: { type: "object", object: { kind: "workspace.file", id: "one" }, locator: "report.md" } });
    store.setDockWidth(640);
    store.setDraftInput("private unsent message");
    store.setSidebarCollapsed(true);
    store.addWorkbenchReference({ label: "private reference", locator: "untrusted text" });
    useWorkspaceStore.setState({ pendingAsk: "must not replay" });

    const saved = localStorage.getItem(WORKSPACE_STORAGE_KEY)!;
    expect(saved).toContain("report.md");
    expect(saved).not.toMatch(/private unsent|private reference|untrusted text|must not replay|draftInput|references|pendingAsk/);

    useWorkspaceStore.setState({ activeProjectId: "", mainSurfaceByProject: {}, workbenchByConversation: {}, sidebarCollapsed: false, pendingAsk: null });
    localStorage.setItem(WORKSPACE_STORAGE_KEY, saved);
    await useWorkspaceStore.persist.rehydrate();
    const restored = useWorkspaceStore.getState();
    expect(restored.activeProjectId).toBe("p1");
    expect(restored.mainSurfaceByProject.p1).toEqual({ kind: "conversation", conversationId: "c1" });
    expect(restored.sidebarCollapsed).toBe(true);
    expect(selectActiveWorkbench(restored)).toMatchObject({ dockWidth: 640, activeViewKey: "file:one", references: [] });
    expect(selectActiveWorkbench(restored).draftInput).toBeUndefined();
    expect(restored.pendingAsk).toBeNull();
  });

  it("strips unknown domain payloads and credentials at the storage boundary", () => {
    const state = useWorkspaceStore.getState();
    const saved = workspaceSnapshot(state);
    const restored = restoreWorkspaceSnapshot({ ...saved, apiKey: "never restore", workbenchByConversation: { c1: { scopeId: "s1", open: true, activeViewKey: "a", references: [{ label: "secret" }], draftInput: "do something", tabs: [{ viewKey: "a", viewType: "artifact", title: "Report", closeable: true, payload: { sql: "private sql" }, target: { type: "artifact", id: "result-1", apiKey: "secret" } }] } } }, state);
    expect(JSON.stringify(workspaceSnapshot(restored))).not.toMatch(/secret|private sql|do something|apiKey|payload/);
    expect(selectActiveWorkbench(restored).tabs[0].target).toEqual({ type: "artifact", id: "result-1" });
  });

  it("ignores corrupt saved layouts and unavailable optional storage", async () => {
    const current = useWorkspaceStore.getState();
    expect(restoreWorkspaceSnapshot({ activeProjectId: 42 }, current)).toBe(current);
    const get = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("denied"); });
    expect(await workspaceStorage?.getItem(WORKSPACE_STORAGE_KEY)).toBeNull();
    expect(() => workspaceStorage?.setItem(WORKSPACE_STORAGE_KEY, { state: workspaceSnapshot(current), version: 1 })).not.toThrow();
    get.mockRestore();
  });

  it("bounds saved layouts while retaining an older active project, conversation and tab", () => {
    const state = useWorkspaceStore.getState();
    const tabs = Array.from({ length: 20 }, (_, i) => ({ viewKey: `t${i}`, viewType: "artifact", title: `Tab ${i}`, closeable: true }));
    const workbench = { scopeId: "s1", open: true, activeViewKey: "t0", tabs, references: [] };
    const saved = workspaceSnapshot({ ...state, mainSurfaceByProject: Object.fromEntries([ ["p1", state.mainSurfaceByProject.p1], ...Array.from({ length: 50 }, (_, i) => [`project${i}`, { kind: "new-conversation" as const }]) ]), workbenchByConversation: { c1: workbench, ...Object.fromEntries(Array.from({ length: 50 }, (_, i) => [`c${i + 2}`, workbench])) } });
    expect(Object.keys(saved.mainSurfaceByProject)).toHaveLength(40);
    expect(saved.mainSurfaceByProject.p1).toBeDefined();
    expect(Object.keys(saved.workbenchByConversation)).toHaveLength(40);
    expect(saved.workbenchByConversation.c1.tabs).toHaveLength(12);
    expect(saved.workbenchByConversation.c1.tabs.some(tab => tab.viewKey === "t0")).toBe(true);
  });
});
