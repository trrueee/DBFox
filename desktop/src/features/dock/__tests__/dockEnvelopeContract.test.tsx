import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "../../../components/ui";
import type { WorkspaceDockTab } from "../../../types/workspace";
import {
  selectActiveDockTabs,
  selectActiveDockViewKey,
  selectActiveWorkbench,
  useWorkspaceStore,
} from "../../../stores/workspaceStore";
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
    projectShell: {},
    mainSurfaceByProject: {},
    workbenchByConversation: {
      "draft:project-1": {
        scopeId: "dock-envelope-scope",
        open: true,
        activeViewKey: null,
        tabs: [],
        reference: null,
      },
    },
    settingsOpen: false,
  });
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
        target: { type: "resource", kind: "dbfox.data.database", id: "ds-1" },
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

    it("verifies dock store state contains only activeViewKey and no activeTabId", () => {
      const dock = selectActiveWorkbench(useWorkspaceStore.getState());
      expect("activeViewKey" in dock).toBe(true);
      expect("activeTabId" in (dock as unknown as Record<string, unknown>)).toBe(false);
    });
  });

  describe("B. Canonical viewKey Identity", () => {
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

      expect(selectActiveDockViewKey(useWorkspaceStore.getState())).toBe("custom:2");

      useWorkspaceStore.getState().setDockActiveTab("custom:1");
      expect(selectActiveDockViewKey(useWorkspaceStore.getState())).toBe("custom:1");

      useWorkspaceStore.getState().updateDockTab("custom:1", { title: "Custom 1 Renamed" });
      expect(selectActiveDockTabs(useWorkspaceStore.getState())[0].title).toBe("Custom 1 Renamed");

      useWorkspaceStore.getState().closeDockTab("custom:1");
      expect(selectActiveDockTabs(useWorkspaceStore.getState()).map((t) => t.viewKey)).toEqual(["custom:2"]);
      expect(selectActiveDockViewKey(useWorkspaceStore.getState())).toBe("custom:2");
    });

    it("prevents updateDockTab from mutating canonical viewKey or viewType", () => {
      useWorkspaceStore.getState().openDockTab({
        viewKey: "custom:immutable",
        viewType: "test.view",
        title: "Immutable Identity",
        closeable: true,
      });

      // Attempt to patch viewKey and viewType
      (useWorkspaceStore.getState().updateDockTab as (key: string, patch: Record<string, unknown>) => void)(
        "custom:immutable",
        { viewKey: "hacked:key", viewType: "hacked.type", title: "Legitimate Title" },
      );

      const tab = selectActiveDockTabs(useWorkspaceStore.getState())[0];
      expect(tab.viewKey).toBe("custom:immutable");
      expect(tab.viewType).toBe("test.view");
      expect(tab.title).toBe("Legitimate Title");
    });

    it("rejects openDockTab when the same viewKey is opened with a conflicting viewType", () => {
      useWorkspaceStore.getState().openDockTab({
        viewKey: "conflict:1",
        viewType: "type.alpha",
        title: "Alpha",
        closeable: true,
      });

      expect(() => {
        useWorkspaceStore.getState().openDockTab({
          viewKey: "conflict:1",
          viewType: "type.beta",
          title: "Beta",
          closeable: true,
        });
      }).toThrow(/Cannot open tab with viewKey "conflict:1" and viewType "type\.beta": already registered with viewType "type\.alpha"/);
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

      const tab = selectActiveDockTabs(useWorkspaceStore.getState())[0];
      expect(tab.viewKey).toBe("core.artifact:art-100");
      expect(tab.viewType).toBe("core.artifact");
      expect(tab.target).toEqual({ type: "artifact", id: "art-100" });

      expect(useArtifactDockStore.getState().artifactById["art-100"]).toBe(artifact);
      expect(useArtifactDockStore.getState().conversationIdByArtifactId["art-100"]).toBe("conv-88");
    });
  });

  describe("F. Registry Composition & Duplicate Rejection", () => {
    it("assembles only capability-neutral Core dock views", () => {
      const views = productDockViews();
      const viewTypes = views.map((v) => v.viewType);

      expect(viewTypes).toContain("core.artifacts");
      expect(viewTypes).toContain("core.artifact");
      expect(viewTypes).toEqual(["core.artifacts", "core.artifact"]);
    });

    it("fails closed deterministically on duplicate viewType registration", () => {
      const duplicateContribution: DockViewContribution = {
        viewType: "core.artifact",
        icon: () => null,
        resolveTitle: () => "Duplicate Artifact",
        isVisible: () => true,
        render: () => null,
      };

      expect(() => {
        createDockViewRegistry([
          ...productDockViews(),
          duplicateContribution,
        ]);
      }).toThrow(/Duplicate Dock viewType contribution detected: "core\.artifact"/);
    });
  });

  describe("G. Unknown ViewType Fallback & Generic Empty State", () => {
    it("renders graceful unknown fallback state without crashing", async () => {
      useWorkspaceStore.setState({ workbenchByConversation: { "draft:project-1": {
        scopeId: "future-scope", open: true, activeViewKey: "future:99", reference: null, tabs: [{
          viewKey: "future:99",
          viewType: "future.third-party.extension",
          title: "Future View",
          closeable: true,
        }],
      } } });

      render(
        <TooltipProvider>
          <WorkspaceDock
            activeConversationId="conv-1"
            showToast={vi.fn()}
          />
        </TooltipProvider>,
      );

      expect(await screen.findByRole("tab", { name: "Future View" })).toBeTruthy();
      expect(screen.getByText("未知视图")).toBeTruthy();
      expect(screen.getByText(/该 Dock 视图类型暂无渲染器：future\.third-party\.extension/)).toBeTruthy();
    });

    it("renders capability-neutral empty state when no tabs are open", () => {
      useWorkspaceStore.setState({ workbenchByConversation: { "draft:project-1": {
        scopeId: "empty-scope", open: true, activeViewKey: null, tabs: [], reference: null,
      } } });

      render(
        <TooltipProvider>
          <WorkspaceDock
            activeConversationId="conv-1"
            showToast={vi.fn()}
          />
        </TooltipProvider>,
      );

      expect(screen.getByText("没有打开的标签")).toBeTruthy();
      expect(screen.getByText("从左侧资源或对话打开对象后，会在这里继续查看和操作。")).toBeTruthy();
    });
  });

  describe("H. Test-Only Third Dock View Proof (Zero WorkspaceDock Edits)", () => {
    it("injects and renders custom third-party contribution through WorkspaceDock registry prop", async () => {
      const customView: DockViewContribution = {
        viewType: "test.example.custom-panel",
        icon: () => <span data-testid="custom-icon">✨</span>,
        resolveTitle: (tab) => `Custom: ${tab.title}`,
        isVisible: () => true,
        render: (tab, ctx) => (
          <div data-testid="custom-rendered-view">
            <h3>Rendered {tab.title}</h3>
            <p>Active project: {ctx.activeProjectId}</p>
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
      useWorkspaceStore.setState({ workbenchByConversation: { "draft:project-1": {
        scopeId: "custom-scope", open: true, activeViewKey: "custom:my-tool", reference: null, tabs: [{
          viewKey: "custom:my-tool",
          viewType: "test.example.custom-panel",
          title: "My Extension",
          closeable: true,
        }],
      } } });

      // Render standard unmodified WorkspaceDock with customRegistry passed in
      render(
        <TooltipProvider>
          <WorkspaceDock
            registry={customRegistry}
            activeConversationId="conv-demo"
            showToast={vi.fn()}
          />
        </TooltipProvider>,
      );

      // 1. Tab rendered in shell
      const tabButton = await screen.findByRole("tab", { name: "My Extension" });
      expect(tabButton).toBeTruthy();

      // 2. Custom icon rendered in tab
      expect(screen.getByTestId("custom-icon")).toBeTruthy();

      // 3. Custom renderer ACTUALLY rendered in DOM
      expect(screen.getByTestId("custom-rendered-view")).toBeTruthy();
      expect(screen.getByText("Rendered My Extension")).toBeTruthy();
      expect(screen.getByText("Active project: project-1")).toBeTruthy();

      // 4. Closing the tab closes it and removes the rendered view
      const closeButton = screen.getByRole("button", { name: "关闭 My Extension" });
      fireEvent.click(closeButton);

      expect(selectActiveDockTabs(useWorkspaceStore.getState())).toHaveLength(0);
      expect(screen.queryByTestId("custom-rendered-view")).toBeNull();
      expect(screen.getByText("没有打开的标签")).toBeTruthy();
    });
  });
});
