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
    dock: { open: false, activeTabId: null },
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
      activeTabId: "tab-1",
    });
  });

  it("adds, updates, and deduplicates generic Dock tabs", () => {
    useWorkspaceStore.getState().openDockTab({
      id: "table-ds-1-orders",
      kind: "table",
      title: "orders",
      closeable: true,
      tableId: "orders",
      datasourceId: "ds-1",
    });
    useWorkspaceStore.getState().openDockTab({
      id: "table-ds-1-orders",
      kind: "table",
      title: "orders",
      closeable: true,
      tableId: "orders",
      datasourceId: "ds-1",
      datasourceDbType: "mysql",
    });

    expect(useWorkspaceStore.getState().dockTabs).toHaveLength(1);
    expect(useWorkspaceStore.getState().dockTabs[0].datasourceDbType).toBe("mysql");

    useWorkspaceStore.getState().updateDockTab("table-ds-1-orders", { title: "orders v2" });
    expect(useWorkspaceStore.getState().dockTabs[0].title).toBe("orders v2");
  });

  it("closes the active Dock tab and advances to its neighbor", () => {
    useWorkspaceStore.getState().openDockTab({
      id: "table-ds-1-orders",
      kind: "table",
      title: "orders",
      closeable: true,
      datasourceId: "ds-1",
    });
    useWorkspaceStore.getState().openDockTab({
      id: "table-ds-1-users",
      kind: "table",
      title: "users",
      closeable: true,
      datasourceId: "ds-1",
    });
    useWorkspaceStore.getState().closeDockTab("table-ds-1-orders");

    const state = useWorkspaceStore.getState();
    expect(state.dockTabs.map((tab) => tab.id)).toEqual(["table-ds-1-users"]);
    expect(state.dock.activeTabId).toBe("table-ds-1-users");
  });
});
