import { beforeEach, describe, expect, it } from "vitest";
import {
  selectActiveDockOpen,
  selectActiveDockTabs,
  selectActiveDockViewKey,
  useWorkspaceStore,
} from "../workspaceStore";

function reset() {
  useWorkspaceStore.setState({
    activeProjectId: "",
    projectShell: {},
    mainSurfaceByProject: {},
    centerMode: "home",
    centerReturnMode: "home",
    pendingAsk: null,
    workbenchByConversation: {},
    settingsOpen: false,
    settingsSection: "appearance",
    projectCreateOpen: false,
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

  it("opens and closes the New Project modal dialog without disrupting centerMode", () => {
    useWorkspaceStore.getState().openConversationCenter("conv-1");
    useWorkspaceStore.getState().openProjectCreate();

    expect(useWorkspaceStore.getState()).toMatchObject({
      projectCreateOpen: true,
      centerMode: "conversation",
    });

    useWorkspaceStore.getState().closeProjectCreate();
    expect(useWorkspaceStore.getState().projectCreateOpen).toBe(false);
    expect(useWorkspaceStore.getState().centerMode).toBe("conversation");
  });
});

describe("workspaceStore — Dock shell", () => {
  beforeEach(reset);

  it("opens, activates and closes the Dock", () => {
    useWorkspaceStore.getState().setDockOpen(true);
    expect(selectActiveDockOpen(useWorkspaceStore.getState())).toBe(true);

    useWorkspaceStore.getState().setDockActiveTab("tab-1");
    expect(selectActiveDockOpen(useWorkspaceStore.getState())).toBe(true);
    expect(selectActiveDockViewKey(useWorkspaceStore.getState())).toBe("tab-1");
  });

  it("adds, updates, and deduplicates canonical Dock tabs by viewKey", () => {
    useWorkspaceStore.getState().openDockTab({
      viewKey: "dbfox.data.table:ds-1:orders",
      viewType: "dbfox.data.table",
      title: "orders",
      closeable: true,
      target: { type: "resource", kind: "dbfox.data.database", id: "ds-1" },
    });
    useWorkspaceStore.getState().openDockTab({
      viewKey: "dbfox.data.table:ds-1:orders",
      viewType: "dbfox.data.table",
      title: "orders",
      closeable: true,
      target: { type: "resource", kind: "dbfox.data.database", id: "ds-1" },
    });

    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toHaveLength(1);

    useWorkspaceStore.getState().updateDockTab("dbfox.data.table:ds-1:orders", { title: "orders v2" });
    expect(selectActiveDockTabs(useWorkspaceStore.getState())[0].title).toBe("orders v2");
  });

  it("disallows modifying viewKey and viewType through updateDockTab", () => {
    useWorkspaceStore.getState().openDockTab({
      viewKey: "dbfox.data.table:ds-1:orders",
      viewType: "dbfox.data.table",
      title: "orders",
      closeable: true,
    });

    (useWorkspaceStore.getState().updateDockTab as (key: string, patch: Record<string, unknown>) => void)(
      "dbfox.data.table:ds-1:orders",
      { viewKey: "illegal:key", viewType: "illegal.type", title: "orders updated" },
    );

    const tab = selectActiveDockTabs(useWorkspaceStore.getState())[0];
    expect(tab.viewKey).toBe("dbfox.data.table:ds-1:orders");
    expect(tab.viewType).toBe("dbfox.data.table");
    expect(tab.title).toBe("orders updated");
  });

  it("throws when opening the same viewKey with mismatched viewType", () => {
    useWorkspaceStore.getState().openDockTab({
      viewKey: "conflict:1",
      viewType: "type.one",
      title: "One",
      closeable: true,
    });

    expect(() => {
      useWorkspaceStore.getState().openDockTab({
        viewKey: "conflict:1",
        viewType: "type.two",
        title: "Two",
        closeable: true,
      });
    }).toThrow(/already registered with viewType "type\.one"/);
  });

  it("closes the active Dock tab and advances to its neighbor", () => {
    useWorkspaceStore.getState().openDockTab({
      viewKey: "dbfox.data.table:ds-1:orders",
      viewType: "dbfox.data.table",
      title: "orders",
      closeable: true,
      target: { type: "resource", kind: "dbfox.data.database", id: "ds-1" },
    });
    useWorkspaceStore.getState().openDockTab({
      viewKey: "dbfox.data.table:ds-1:users",
      viewType: "dbfox.data.table",
      title: "users",
      closeable: true,
      target: { type: "resource", kind: "dbfox.data.database", id: "ds-1" },
    });
    useWorkspaceStore.getState().closeDockTab("dbfox.data.table:ds-1:orders");

    const state = useWorkspaceStore.getState();
    expect(selectActiveDockTabs(state).map((tab) => tab.viewKey)).toEqual(["dbfox.data.table:ds-1:users"]);
    expect(selectActiveDockViewKey(state)).toBe("dbfox.data.table:ds-1:users");
  });

  it("isolates Workbench tabs per Conversation and restores them on switch", () => {
    useWorkspaceStore.getState().setActiveProject("project-1");

    // In Conversation A: open orders and SQL tabs
    useWorkspaceStore.getState().openConversationCenter("conv-A");
    useWorkspaceStore.getState().openDockTab({
      viewKey: "dbfox.data.table:ds-1:orders",
      viewType: "dbfox.data.table",
      title: "orders",
      closeable: true,
    });
    useWorkspaceStore.getState().openDockTab({
      viewKey: "dbfox.data.sql:ds-1",
      viewType: "dbfox.data.sql-console",
      title: "SQL Console",
      closeable: true,
    });
    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toHaveLength(2);
    expect(selectActiveDockViewKey(useWorkspaceStore.getState())).toBe("dbfox.data.sql:ds-1");

    // Switch to Conversation B: starts empty
    useWorkspaceStore.getState().openConversationCenter("conv-B");
    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toHaveLength(0);
    expect(selectActiveDockOpen(useWorkspaceStore.getState())).toBe(false);

    // In Conversation B: open Piano Studio tab
    useWorkspaceStore.getState().openDockTab({
      viewKey: "dbfox.music:warm-light",
      viewType: "dbfox.music.piano-studio",
      title: "Warm Light",
      closeable: true,
    });
    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toHaveLength(1);
    expect(selectActiveDockViewKey(useWorkspaceStore.getState())).toBe("dbfox.music:warm-light");

    // Switch back to Conversation A: restores orders and SQL tabs with active tab
    useWorkspaceStore.getState().openConversationCenter("conv-A");
    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toHaveLength(2);
    expect(selectActiveDockViewKey(useWorkspaceStore.getState())).toBe("dbfox.data.sql:ds-1");
    expect(selectActiveDockOpen(useWorkspaceStore.getState())).toBe(true);

    // Switch back to Conversation B: restores Warm Light tab
    useWorkspaceStore.getState().openConversationCenter("conv-B");
    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toHaveLength(1);
    expect(selectActiveDockViewKey(useWorkspaceStore.getState())).toBe("dbfox.music:warm-light");
  });

  it("migrates draft workbench tabs to the new conversation upon creation", () => {
    useWorkspaceStore.getState().setActiveProject("project-1");
    useWorkspaceStore.getState().showSmartQueryHome("New draft");

    // Open a tab while on draft screen
    useWorkspaceStore.getState().openDockTab({
      viewKey: "dbfox.data.sql:ds-draft",
      viewType: "dbfox.data.sql-console",
      title: "SQL Console Draft",
      closeable: true,
    });
    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toHaveLength(1);

    // New conversation is created
    useWorkspaceStore.getState().setProjectActiveConversation("project-1", "conv-new");
    useWorkspaceStore.getState().openConversationCenter("conv-new");
    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toHaveLength(1);
    expect(selectActiveDockTabs(useWorkspaceStore.getState())[0].viewKey).toBe("dbfox.data.sql:ds-draft");

    // And workbenchByConversation for draft is transferred to conv-new
    expect(useWorkspaceStore.getState().workbenchByConversation["conv-new"]?.tabs).toHaveLength(1);
    expect(useWorkspaceStore.getState().workbenchByConversation["draft:project-1"]).toBeUndefined();
  });
});
