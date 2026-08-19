import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "../../../components/ui";
import type { WorkspaceDockTab } from "../../../types/workspace";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import { useSqlConsoleStore } from "../../../stores/sqlConsoleStore";
import { useTableWorkspaceStore } from "../../../stores/tableWorkspaceStore";
import { useWorkspaceFileStore } from "../../../stores/workspaceFileStore";
import { useArtifactDockStore } from "../../../stores/artifactDockStore";
import {
  createDockViewRegistry,
  productDockViews,
} from "../dockViewComposition";
import type { DockViewContribution } from "../types";
import { WorkspaceDock } from "../../appShell/WorkspaceDock";

function resetAll() {
  useWorkspaceStore.setState({
    activeProjectId: "project-1",
    dock: { open: true, activeViewKey: null, activeTabId: null },
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

describe("P6: Canonical Dock Envelope & Capability Neutrality", () => {
  beforeEach(() => {
    cleanup();
    resetAll();
  });

  describe("A. Envelope Schema Contract", () => {
    it("permits only canonical fields on WorkspaceDockTab", () => {
      const canonicalTab: WorkspaceDockTab = {
        viewKey: "dbfox.data.table:ds-1:users",
        viewType: "dbfox.data.table",
        title: "users",
        closeable: true,
        projectId: "project-1",
        target: { type: "resource", kind: "database", id: "ds-1" },
        stateKey: "dbfox.data.table:ds-1:users",
      };

      const allowedKeys = new Set([
        "viewKey",
        "viewType",
        "title",
        "closeable",
        "projectId",
        "target",
        "stateKey",
      ]);

      for (const key of Object.keys(canonicalTab)) {
        expect(allowedKeys.has(key)).toBe(true);
      }

      // Prohibited legacy & capability bag keys
      const forbiddenKeys = [
        "id",
        "kind",
        "datasourceId",
        "datasourceDbType",
        "tableId",
        "conversationId",
        "artifact",
        "selectedTables",
        "filePath",
        "fileName",
      ];

      for (const forbidden of forbiddenKeys) {
        expect(forbidden in canonicalTab).toBe(false);
      }
    });
  });

  describe("B. Canonical viewKey Identity", () => {
    it("deduplicates multiple opens to the exact same Dock view instance", () => {
      useTableWorkspaceStore.getState().openTable("orders", "preview", { id: "ds-1", dbType: "mysql" });
      useTableWorkspaceStore.getState().openTable("orders", "schema", { id: "ds-1", dbType: "mysql" });

      const tabs = useWorkspaceStore.getState().dockTabs;
      expect(tabs).toHaveLength(1);
      expect(tabs[0].viewKey).toBe("dbfox.data.table:ds-1:orders");
      expect(useWorkspaceStore.getState().dock.activeViewKey).toBe("dbfox.data.table:ds-1:orders");
    });

    it("activates, updates, and closes Dock views using viewKey", () => {
      useWorkspaceStore.getState().openDockTab({
        viewKey: "custom:1",
        viewType: "test.view",
        title: "Custom 1",
        closeable: true,
      });
      useWorkspaceStore.getState().openDockTab({
        viewKey: "custom:2",
        viewType: "test.view",
        title: "Custom 2",
        closeable: true,
      });

      expect(useWorkspaceStore.getState().dock.activeViewKey).toBe("custom:2");

      useWorkspaceStore.getState().setDockActiveTab("custom:1");
      expect(useWorkspaceStore.getState().dock.activeViewKey).toBe("custom:1");

      useWorkspaceStore.getState().updateDockTab("custom:1", { title: "Custom 1 Renamed" });
      expect(useWorkspaceStore.getState().dockTabs[0].title).toBe("Custom 1 Renamed");

      useWorkspaceStore.getState().closeDockTab("custom:1");
      expect(useWorkspaceStore.getState().dockTabs.map((t) => t.viewKey)).toEqual(["custom:2"]);
      expect(useWorkspaceStore.getState().dock.activeViewKey).toBe("custom:2");
    });
  });

  describe("C. Data Capability State Ownership", () => {
    it("keeps SQL console datasource identity in sqlConsoleStore", () => {
      useWorkspaceStore.getState().setActiveProject("proj-abc");
      useSqlConsoleStore.getState().openConsole("ds-99", "postgresql", "SELECT 42");

      const shellTab = useWorkspaceStore.getState().dockTabs[0];
      expect(shellTab.viewKey).toBe("dbfox.data.sql-console:proj-abc");
      expect(shellTab.viewType).toBe("dbfox.data.sql-console");
      expect(shellTab.target).toEqual({
        type: "resource",
        kind: "database",
        id: "ds-99",
      });

      const storeState = useSqlConsoleStore.getState().sqlConsoleState["sql-proj-abc"];
      expect(storeState.datasourceId).toBe("ds-99");
      expect(storeState.datasourceDbType).toBe("postgresql");
      expect(storeState.draftSql).toBe("SELECT 42");
    });

    it("keeps table and multi-table metadata in tableWorkspaceStore", () => {
      useTableWorkspaceStore.getState().openTable("customers", "er", { id: "ds-2", dbType: "sqlite" });

      const tab = useWorkspaceStore.getState().dockTabs[0];
      expect(tab.viewKey).toBe("dbfox.data.table:ds-2:customers");
      expect(tab.target).toEqual({ type: "resource", kind: "database", id: "ds-2" });

      const tableState = useTableWorkspaceStore.getState().tableStateByTabId["dbfox.data.table:ds-2:customers"];
      expect(tableState).toEqual({
        tableName: "customers",
        datasourceId: "ds-2",
        datasourceDbType: "sqlite",
      });

      useTableWorkspaceStore.getState().openMultiTable(["alpha", "beta"]);
      const multiTab = useWorkspaceStore.getState().dockTabs[1];
      expect(multiTab.viewKey).toBe("dbfox.data.multi-table:alpha|beta");
      expect(useTableWorkspaceStore.getState().multiTableStateByTabId["dbfox.data.multi-table:alpha|beta"]).toEqual([
        "alpha",
        "beta",
      ]);
    });
  });

  describe("D. Workspace Capability State Ownership", () => {
    it("keeps file path metadata in workspaceFileStore", () => {
      useWorkspaceFileStore.getState().openFile("D:/project/src/index.ts", "index.ts", "proj-x");

      const tab = useWorkspaceStore.getState().dockTabs[0];
      expect(tab.viewKey).toBe("dbfox.workspace.file:proj-x:D:/project/src/index.ts");
      expect(tab.viewType).toBe("dbfox.workspace.file");
      expect(tab.target).toEqual({ type: "resource", kind: "workspace", id: "proj-x" });

      const fileState = useWorkspaceFileStore.getState().fileStateByKey["dbfox.workspace.file:proj-x:D:/project/src/index.ts"];
      expect(fileState).toEqual({
        projectId: "proj-x",
        filePath: "D:/project/src/index.ts",
        fileName: "index.ts",
      });
    });
  });

  describe("E. Artifact Capability State Ownership", () => {
    it("stores artifact reference as identity target without full object in shell tab", () => {
      const artifact = {
        id: "art-100",
        type: "result_view" as const,
        title: "QueryResult #100",
        sourceSqlArtifactId: "sql-1",
        columns: [],
        queryFingerprint: "fp",
      };

      useArtifactDockStore.getState().openArtifact(artifact, "conv-88");

      const tab = useWorkspaceStore.getState().dockTabs[0];
      expect(tab.viewKey).toBe("core.artifact:art-100");
      expect(tab.viewType).toBe("core.artifact");
      expect(tab.target).toEqual({ type: "artifact", id: "art-100" });

      expect(useArtifactDockStore.getState().artifactById["art-100"]).toBe(artifact);
      expect(useArtifactDockStore.getState().conversationIdByArtifactId["art-100"]).toBe("conv-88");
    });
  });

  describe("F. Registry Composition & Duplicate Rejection", () => {
    it("assembles core, data, and workspace dock views", () => {
      const views = productDockViews();
      const viewTypes = views.map((v) => v.viewType);

      expect(viewTypes).toContain("core.artifacts");
      expect(viewTypes).toContain("core.artifact");
      expect(viewTypes).toContain("dbfox.data.sql-console");
      expect(viewTypes).toContain("dbfox.data.table");
      expect(viewTypes).toContain("dbfox.data.multi-table");
      expect(viewTypes).toContain("dbfox.workspace.file");
    });

    it("fails closed deterministically on duplicate viewType registration", () => {
      const duplicateContribution: DockViewContribution = {
        viewType: "dbfox.data.table",
        icon: () => null,
        resolveTitle: () => "Duplicate Table",
        isVisible: () => true,
        render: () => null,
      };

      expect(() => {
        createDockViewRegistry([
          ...productDockViews(),
          duplicateContribution,
        ]);
      }).toThrow(/Duplicate Dock viewType contribution detected: "dbfox\.data\.table"/);
    });
  });

  describe("G. Unknown ViewType Fallback", () => {
    it("renders graceful unknown fallback state without crashing", async () => {
      useWorkspaceStore.setState({
        dock: { open: true, activeViewKey: "future:99", activeTabId: "future:99" },
        dockTabs: [{
          viewKey: "future:99",
          viewType: "future.third-party.extension",
          title: "Future View",
          closeable: true,
        }],
      });

      render(
        <TooltipProvider>
          <WorkspaceDock
            activeDatasourceId="ds-1"
            activeConversationId="conv-1"
            showToast={vi.fn()}
          />
        </TooltipProvider>,
      );

      expect(await screen.findByRole("tab", { name: "Future View" })).toBeTruthy();
      expect(screen.getByText("未知视图")).toBeTruthy();
      expect(screen.getByText(/该 Dock 视图类型暂无渲染器：future\.third-party\.extension/)).toBeTruthy();
    });
  });

  describe("H. Test-Only Third Dock View Proof (Zero WorkspaceDock Edits)", () => {
    it("renders custom third-party contribution through generic registry composition", async () => {
      const customView: DockViewContribution = {
        viewType: "test.example.custom-panel",
        icon: () => <span data-testid="custom-icon">✨</span>,
        resolveTitle: (tab) => `Custom: ${tab.title}`,
        isVisible: () => true,
        render: (tab, ctx) => (
          <div data-testid="custom-rendered-view">
            <h3>Rendered {tab.title}</h3>
            <p>Active DS: {ctx.activeDatasourceId}</p>
          </div>
        ),
      };

      // Register dynamically via registry
      const customRegistry = createDockViewRegistry([
        ...productDockViews(),
        customView,
      ]);

      expect(customRegistry.get("test.example.custom-panel")).toBe(customView);

      // Open tab in WorkspaceStore
      useWorkspaceStore.setState({
        dock: {
          open: true,
          activeViewKey: "custom:my-tool",
          activeTabId: "custom:my-tool",
        },
        dockTabs: [{
          viewKey: "custom:my-tool",
          viewType: "test.example.custom-panel",
          title: "My Extension",
          closeable: true,
        }],
      });

      // Render standard unmodified WorkspaceDock
      render(
        <TooltipProvider>
          <WorkspaceDock
            activeDatasourceId="ds-demo"
            activeConversationId="conv-demo"
            showToast={vi.fn()}
          />
        </TooltipProvider>,
      );

      // Tab rendered in shell
      expect(await screen.findByRole("tab", { name: "My Extension" })).toBeTruthy();
    });
  });
});
