import { beforeEach, describe, expect, it } from "vitest";
import { useWorkspaceStore } from "../workspaceStore";

function reset() {
  useWorkspaceStore.setState({
    activeProjectId: "",
    sidebarEntityMode: "connections",
    projectSubMode: {},
    connectionSubMode: {},
    projectShell: {},
    mainSurfaceByProject: {},
    centerMode: "home",
    centerReturnMode: "home",
    pendingAsk: null,
    dock: { open: false, activeTabId: null },
    dockTabs: [],
    sqlConsoleState: {},
    selectedTables: [],
    tableSubTabs: {},
    settingsOpen: false,
    settingsSection: "appearance",
  });
}

describe("workspaceStore — Shell", () => {
  beforeEach(reset);

  it("keeps sidebar and datasource selections scoped per real Project", () => {
    useWorkspaceStore.getState().setActiveProject("project-1");
    useWorkspaceStore.getState().setProjectSidebarMode("project-1", "conversations");
    useWorkspaceStore.getState().setProjectActiveDatasource("project-1", "ds-a");

    useWorkspaceStore.getState().setActiveProject("project-2");
    useWorkspaceStore.getState().setProjectSidebarMode("project-2", "data");

    expect(useWorkspaceStore.getState().projectShell["project-1"]).toEqual({
      sidebarMode: "conversations",
      activeDatasourceId: "ds-a",
    });
    expect(useWorkspaceStore.getState().projectShell["project-2"]).toEqual({
      sidebarMode: "data",
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

  it("switches sidebar entity mode and keeps per-entity sub modes independent", () => {
    useWorkspaceStore.getState().setSidebarEntityMode("projects");
    useWorkspaceStore.getState().setProjectSubMode("project-1", "files");
    useWorkspaceStore.getState().setSidebarEntityMode("connections");
    useWorkspaceStore.getState().setConnectionSubMode("ds-1", "database");

    const state = useWorkspaceStore.getState();
    expect(state.sidebarEntityMode).toBe("connections");
    expect(state.projectSubMode["project-1"]).toBe("files");
    expect(state.connectionSubMode["ds-1"]).toBe("database");
  });
});

describe("workspaceStore — Dock", () => {
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

  it("keeps one canonical SQL console view per Project", () => {
    useWorkspaceStore.getState().setActiveProject("project-1");
    useWorkspaceStore.getState().openDockConsole("ds-a", "mysql", "SELECT 1", true);

    let state = useWorkspaceStore.getState();
    expect(state.dockTabs).toHaveLength(1);
    expect(state.dockTabs[0]).toMatchObject({
      id: "console-project-1",
      stateKey: "sql-project-1",
      datasourceId: "ds-a",
    });
    expect(state.sqlConsoleState["sql-project-1"].draftSql).toBe("SELECT 1");

    useWorkspaceStore.getState().openDockConsole("ds-b", "postgresql", undefined, true);
    state = useWorkspaceStore.getState();
    expect(state.dockTabs).toHaveLength(1);
    expect(state.dockTabs[0].datasourceId).toBe("ds-b");
    expect(state.sqlConsoleState["sql-project-1"].draftSql).toBe("SELECT 1");

    useWorkspaceStore.getState().setActiveProject("project-2");
    useWorkspaceStore.getState().openDockConsole("ds-c", "sqlite", "SELECT 2", true);
    expect(useWorkspaceStore.getState().dockTabs.map((tab) => tab.id)).toEqual([
      "console-project-1",
      "console-project-2",
    ]);
    expect(useWorkspaceStore.getState().sqlConsoleState["sql-project-2"].draftSql).toBe("SELECT 2");
  });

  it("deduplicates Table dock views by datasource + canonical table", () => {
    useWorkspaceStore.getState().openDockTable("users", "preview", { id: "ds-1", dbType: "mysql" });
    useWorkspaceStore.getState().openDockTable("users", "schema", { id: "ds-1", dbType: "mysql" });

    const state = useWorkspaceStore.getState();
    expect(state.dockTabs.filter((tab) => tab.kind === "table")).toHaveLength(1);
    expect(state.dock.activeTabId).toBe("table-ds-1-users");
    expect(state.tableSubTabs["table-ds-1-users"]).toBe("schema");
  });

  it("opens a project file in a canonical Dock view and keeps one tab per path", () => {
    useWorkspaceStore.getState().setActiveProject("project-1");
    useWorkspaceStore.getState().openDockFile("C:/demo/src/main.py", "main.py", "project-1");

    let state = useWorkspaceStore.getState();
    expect(state.dockTabs).toHaveLength(1);
    expect(state.dockTabs[0]).toMatchObject({
      kind: "file",
      id: "file-project-1-C:/demo/src/main.py",
      title: "main.py",
      projectId: "project-1",
      filePath: "C:/demo/src/main.py",
    });
    expect(state.dock.activeTabId).toBe("file-project-1-C:/demo/src/main.py");

    useWorkspaceStore.getState().openDockFile("C:/demo/src/main.py", "main.py", "project-1");
    state = useWorkspaceStore.getState();
    expect(state.dockTabs).toHaveLength(1);
    expect(state.dockTabs[0].fileName).toBe("main.py");
  });

  it("deduplicates Artifacts and Artifact views by canonical id", () => {
    useWorkspaceStore.getState().openDockArtifacts("conv-1");
    useWorkspaceStore.getState().openDockArtifacts("conv-1");
    expect(useWorkspaceStore.getState().dockTabs).toHaveLength(1);

    const artifact = {
      id: "artifact-1",
      type: "result_view" as const,
      title: "Result",
      sourceSqlArtifactId: "sql-1",
      columns: [],
      queryFingerprint: "fp",
    };
    useWorkspaceStore.getState().openDockArtifact(artifact, "conv-1");
    useWorkspaceStore.getState().openDockArtifact(artifact, "conv-1");
    expect(useWorkspaceStore.getState().dockTabs).toHaveLength(2);
  });

  it("deduplicates MultiTable by the canonical sorted object set", () => {
    useWorkspaceStore.getState().openDockMultiTable(["orders", "users", "orders"]);
    const first = useWorkspaceStore.getState();
    expect(first.dockTabs).toHaveLength(1);
    expect(first.dockTabs[0].selectedTables).toEqual(["orders", "users"]);
    expect(first.dockTabs[0].id).toBe("multi-table-orders|users");

    useWorkspaceStore.getState().openDockMultiTable(["users", "orders"]);
    expect(useWorkspaceStore.getState().dockTabs).toHaveLength(1);
  });

  it("closes the active Dock tab and advances to its neighbor", () => {
    useWorkspaceStore.getState().openDockTable("orders", "preview", { id: "ds-1" });
    useWorkspaceStore.getState().openDockTable("users", "preview", { id: "ds-1" });
    useWorkspaceStore.getState().closeDockTab("table-ds-1-orders");

    const state = useWorkspaceStore.getState();
    expect(state.dockTabs.map((tab) => tab.id)).toEqual(["table-ds-1-users"]);
    expect(state.dock.activeTabId).toBe("table-ds-1-users");
  });

  it("patches SQL console state only for an open console tab", () => {
    useWorkspaceStore.getState().setActiveProject("project-1");
    useWorkspaceStore.getState().openDockConsole("ds-a", "mysql", "SELECT 1");
    useWorkspaceStore.getState().patchSqlConsoleState("sql-project-1", {
      draftSql: "SELECT 2",
    });
    expect(useWorkspaceStore.getState().sqlConsoleState["sql-project-1"].draftSql).toBe(
      "SELECT 2",
    );

    useWorkspaceStore.getState().patchSqlConsoleState("sql-project-missing", {
      draftSql: "SELECT 3",
    });
    expect(
      useWorkspaceStore.getState().sqlConsoleState["sql-project-missing"],
    ).toBeUndefined();
  });
});
