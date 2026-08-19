import { beforeEach, describe, expect, it } from "vitest";

import { useArtifactDockStore } from "../artifactDockStore";
import { useSqlConsoleStore } from "../sqlConsoleStore";
import { useTableWorkspaceStore } from "../tableWorkspaceStore";
import { useWorkspaceFileStore } from "../workspaceFileStore";
import { useWorkspaceStore } from "../workspaceStore";

function reset() {
  useWorkspaceStore.setState({
    activeProjectId: "",
    dock: { open: false, activeViewKey: null },
    dockTabs: [],
    settingsOpen: false,
  });
  useSqlConsoleStore.setState({ sqlConsoleState: {} });
  useTableWorkspaceStore.setState({
    selectedTables: [],
    tableSubTabs: {},
    tableStateByTabId: {},
    multiTableStateByTabId: {},
  });
  useWorkspaceFileStore.setState({ fileStateByKey: {} });
  useArtifactDockStore.setState({ artifactById: {}, conversationIdByArtifactId: {} });
}

describe("sqlConsoleStore", () => {
  beforeEach(reset);

  it("keeps one canonical SQL console view and draft per Project", () => {
    useWorkspaceStore.getState().setActiveProject("project-1");
    useSqlConsoleStore.getState().openConsole("ds-a", "mysql", "SELECT 1");

    let shell = useWorkspaceStore.getState();
    expect(shell.dockTabs).toHaveLength(1);
    expect(shell.dockTabs[0]).toMatchObject({
      viewKey: "dbfox.data.sql-console:project-1",
      viewType: "dbfox.data.sql-console",
      stateKey: "sql-project-1",
    });
    expect(useSqlConsoleStore.getState().sqlConsoleState["sql-project-1"].draftSql).toBe("SELECT 1");
    expect(useSqlConsoleStore.getState().sqlConsoleState["sql-project-1"].datasourceId).toBe("ds-a");

    useSqlConsoleStore.getState().openConsole("ds-b", "postgresql", undefined);
    shell = useWorkspaceStore.getState();
    expect(shell.dockTabs).toHaveLength(1);
    expect(useSqlConsoleStore.getState().sqlConsoleState["sql-project-1"].datasourceId).toBe("ds-b");
    expect(useSqlConsoleStore.getState().sqlConsoleState["sql-project-1"].draftSql).toBe("SELECT 1");

    useWorkspaceStore.getState().setActiveProject("project-2");
    useSqlConsoleStore.getState().openConsole("ds-c", "sqlite", "SELECT 2");
    expect(useWorkspaceStore.getState().dockTabs.map((tab) => tab.viewKey)).toEqual([
      "dbfox.data.sql-console:project-1",
      "dbfox.data.sql-console:project-2",
    ]);
    expect(useSqlConsoleStore.getState().sqlConsoleState["sql-project-2"].draftSql).toBe("SELECT 2");
  });

  it("patches only an existing SQL console state", () => {
    useSqlConsoleStore.getState().patchSqlConsoleState("sql-project-missing", { draftSql: "x" });
    expect(useSqlConsoleStore.getState().sqlConsoleState["sql-project-missing"]).toBeUndefined();

    useWorkspaceStore.getState().setActiveProject("project-1");
    useSqlConsoleStore.getState().openConsole("ds-a", "mysql", "SELECT 1");
    useSqlConsoleStore.getState().patchSqlConsoleState("sql-project-1", { draftSql: "SELECT 2" });
    expect(useSqlConsoleStore.getState().sqlConsoleState["sql-project-1"].draftSql).toBe("SELECT 2");
  });
});

describe("tableWorkspaceStore", () => {
  beforeEach(reset);

  it("deduplicates Table views by datasource + canonical table", () => {
    useTableWorkspaceStore.getState().openTable("users", "preview", { id: "ds-1", dbType: "mysql" });
    useTableWorkspaceStore.getState().openTable("users", "schema", { id: "ds-1", dbType: "mysql" });

    const shell = useWorkspaceStore.getState();
    expect(shell.dockTabs.filter((tab) => tab.viewType === "dbfox.data.table")).toHaveLength(1);
    expect(shell.dock.activeViewKey).toBe("dbfox.data.table:ds-1:users");
    expect(useTableWorkspaceStore.getState().tableSubTabs["dbfox.data.table:ds-1:users"]).toBe("schema");
    expect(useTableWorkspaceStore.getState().tableStateByTabId["dbfox.data.table:ds-1:users"]).toEqual({
      tableName: "users",
      datasourceId: "ds-1",
      datasourceDbType: "mysql",
    });
  });

  it("deduplicates MultiTable by the canonical sorted object set and scopes to datasource", () => {
    useTableWorkspaceStore.getState().openMultiTable(["orders", "users", "orders"], { id: "ds-1", dbType: "mysql" });
    expect(useWorkspaceStore.getState().dockTabs).toHaveLength(1);
    expect(useWorkspaceStore.getState().dockTabs[0].viewKey).toBe("dbfox.data.multi-table:ds-1:orders|users");
    expect(useTableWorkspaceStore.getState().multiTableStateByTabId["dbfox.data.multi-table:ds-1:orders|users"]).toEqual({
      datasourceId: "ds-1",
      datasourceDbType: "mysql",
      tables: ["orders", "users"],
    });

    useTableWorkspaceStore.getState().openMultiTable(["users", "orders"], { id: "ds-1", dbType: "mysql" });
    expect(useWorkspaceStore.getState().dockTabs).toHaveLength(1);
  });
});

describe("artifactDockStore", () => {
  beforeEach(reset);

  it("deduplicates Artifacts and Artifact views by canonical id", () => {
    useArtifactDockStore.getState().openArtifacts("conv-1");
    useArtifactDockStore.getState().openArtifacts("conv-1");
    expect(useWorkspaceStore.getState().dockTabs).toHaveLength(1);

    const artifact = {
      id: "artifact-1",
      type: "result_view" as const,
      title: "Result",
      sourceSqlArtifactId: "sql-1",
      columns: [],
      queryFingerprint: "fp",
    };
    useArtifactDockStore.getState().openArtifact(artifact, "conv-1");
    useArtifactDockStore.getState().openArtifact(artifact, "conv-1");
    expect(useWorkspaceStore.getState().dockTabs).toHaveLength(2);
    expect(useArtifactDockStore.getState().artifactById["artifact-1"]).toBe(artifact);
  });
});

describe("workspaceFileStore", () => {
  beforeEach(reset);

  it("opens a canonical Dock view per project file path", () => {
    useWorkspaceFileStore.getState().openFile("C:/demo/src/main.py", "main.py", "project-1");
    useWorkspaceFileStore.getState().openFile("C:/demo/src/main.py", "main.py", "project-1");

    const shell = useWorkspaceStore.getState();
    expect(shell.dockTabs).toHaveLength(1);
    expect(shell.dockTabs[0]).toMatchObject({
      viewType: "dbfox.workspace.file",
      viewKey: "dbfox.workspace.file:project-1:C:/demo/src/main.py",
      title: "main.py",
      projectId: "project-1",
    });
    expect(
      useWorkspaceFileStore.getState().fileStateByKey[
        "dbfox.workspace.file:project-1:C:/demo/src/main.py"
      ],
    ).toEqual({
      projectId: "project-1",
      filePath: "C:/demo/src/main.py",
      fileName: "main.py",
    });
  });
});
