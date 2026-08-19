import { beforeEach, describe, expect, it } from "vitest";
import { useWorkspaceStore } from "../workspaceStore";

function reset() {
  useWorkspaceStore.setState({
    activeProjectId: "",
    projectShell: {},
    mainSurfaceByProject: {},
    centerMode: "home",
    centerReturnMode: "home",
    pendingAsk: null,
    dock: { open: false, activeViewKey: null, activeTabId: null },
    dockTabs: [],
    settingsOpen: false,
    settingsSection: "appearance",
  });
}

describe("workspaceStore — Shell", () => {
  beforeEach(reset);

  it("keeps conversation selections scoped per Project", () => {
    useWorkspaceStore.getState().setActiveProject("project-1");
    useWorkspaceStore.getState().setProjectActiveConversation("project-1", "conv-1");

    useWorkspaceStore.getState().setActiveProject("project-2");
    useWorkspaceStore.getState().setProjectActiveConversation("project-2", "conv-2");

    expect(useWorkspaceStore.getState().projectShell["project-1"]).toEqual({
      activeConversationId: "conv-1",
    });
    expect(useWorkspaceStore.getState().projectShell["project-2"]).toEqual({
      activeConversationId: "conv-2",
    });
  });

  it("tracks the fixed Main Surface per Project", () => {
    useWorkspaceStore.getState().setActiveProject("project-1");
    useWorkspaceStore.getState().showSmartQueryHome("问一下");
    expect(useWorkspaceStore.getState().mainSurfaceByProject["project-1"]).toEqual({
      kind: "new-conversation",
    });

    useWorkspaceStore.getState().openConversationCenter("conv-9");
    expect(useWorkspaceStore.getState().mainSurfaceByProject["project-1"]).toEqual({
      kind: "conversation",
      conversationId: "conv-9",
    });
  });

  it("opens settings and switches sections", () => {
    useWorkspaceStore.getState().openSettings("model");
    expect(useWorkspaceStore.getState()).toMatchObject({
      settingsOpen: true,
      settingsSection: "model",
    });
    useWorkspaceStore.getState().setSettingsSection("appearance");
    expect(useWorkspaceStore.getState().settingsSection).toBe("appearance");
    useWorkspaceStore.getState().closeSettings();
    expect(useWorkspaceStore.getState().settingsOpen).toBe(false);
  });

  it("temporarily opens the New Project surface and returns home", () => {
    useWorkspaceStore.getState().openConversationCenter("conv-1");
    useWorkspaceStore.getState().openProjectCreate();

    expect(useWorkspaceStore.getState()).toMatchObject({
      centerMode: "project-create",
      centerReturnMode: "conversation",
    });

    useWorkspaceStore.getState().showSmartQueryHome();
    expect(useWorkspaceStore.getState().centerMode).toBe("home");
  });
});

describe("workspaceStore — Dock shell", () => {
  beforeEach(reset);

  it("opens, activates and closes the Dock", () => {
    useWorkspaceStore.getState().setDockOpen(true);
    expect(useWorkspaceStore.getState().dock.open).toBe(true);

    useWorkspaceStore.getState().setDockActiveTab("tab-1");
    expect(useWorkspaceStore.getState().dock).toEqual({
      open: true,
      activeViewKey: "tab-1",
      activeTabId: "tab-1",
    });
  });

  it("adds, updates, and deduplicates canonical Dock tabs by viewKey", () => {
    useWorkspaceStore.getState().openDockTab({
      viewKey: "dbfox.data.table:ds-1:orders",
      viewType: "dbfox.data.table",
      title: "orders",
      closeable: true,
      target: { type: "resource", kind: "database", id: "ds-1" },
    });
    useWorkspaceStore.getState().openDockTab({
      viewKey: "dbfox.data.table:ds-1:orders",
      viewType: "dbfox.data.table",
      title: "orders",
      closeable: true,
      target: { type: "resource", kind: "database", id: "ds-1" },
    });

    expect(useWorkspaceStore.getState().dockTabs).toHaveLength(1);

    useWorkspaceStore.getState().updateDockTab("dbfox.data.table:ds-1:orders", { title: "orders v2" });
    expect(useWorkspaceStore.getState().dockTabs[0].title).toBe("orders v2");
  });

  it("closes the active Dock tab and advances to its neighbor", () => {
    useWorkspaceStore.getState().openDockTab({
      viewKey: "dbfox.data.table:ds-1:orders",
      viewType: "dbfox.data.table",
      title: "orders",
      closeable: true,
      target: { type: "resource", kind: "database", id: "ds-1" },
    });
    useWorkspaceStore.getState().openDockTab({
      viewKey: "dbfox.data.table:ds-1:users",
      viewType: "dbfox.data.table",
      title: "users",
      closeable: true,
      target: { type: "resource", kind: "database", id: "ds-1" },
    });
    useWorkspaceStore.getState().closeDockTab("dbfox.data.table:ds-1:orders");

    const state = useWorkspaceStore.getState();
    expect(state.dockTabs.map((tab) => tab.viewKey)).toEqual(["dbfox.data.table:ds-1:users"]);
    expect(state.dock.activeViewKey).toBe("dbfox.data.table:ds-1:users");
  });
});
