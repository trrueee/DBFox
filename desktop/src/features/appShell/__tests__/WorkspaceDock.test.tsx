import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "../../../components/ui";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import { useDlcStore } from "../../dlc/extensionStore";
import { planDockTabWindow, WorkspaceDock } from "../WorkspaceDock";
import type { WorkspaceDockTab } from "../../../types/workspace";

function setWorkbench(
  open: boolean,
  activeViewKey: string | null,
  tabs: WorkspaceDockTab[],
) {
  useWorkspaceStore.setState({
    activeProjectId: "",
    mainSurfaceByProject: {},
    projectShell: {},
    workbenchByConversation: {
      "draft:default": {
        scopeId: "test-scope",
        open,
        activeViewKey,
        tabs,
        reference: null,
      },
    },
  });
}

vi.mock("../../conversation/ConversationHistoryPanel", () => ({
  ConversationHistoryPanel: () => <div data-testid="conversation-history" />,
}));
vi.mock("../../conversation/workspace/ArtifactDock", () => ({
  ArtifactDock: () => <div data-testid="artifact-dock" />,
}));
vi.mock("../../workspace/artifacts/TableArtifactView", () => ({
  TableArtifactView: () => <div data-testid="table-artifact" />,
}));

function renderDock() {
  return render(
    <TooltipProvider>
      <WorkspaceDock
        activeConversationId={null}
        showToast={vi.fn()}
      />
    </TooltipProvider>,
  );
}

describe("WorkspaceDock", () => {
  beforeEach(() => {
    cleanup();
    useDlcStore.getState().reset();
    useDlcStore.getState().setProjectionResult("snap-data", {}, {
      connectors: [],
      dockViews: [{
        viewType: "dbfox.data.sql-console",
        icon: () => null,
        resolveTitle: () => "SQL 控制台",
        isVisible: () => true,
        render: (view) => <div data-testid="sql-console" data-tab-id={view.stateKey} />,
      }],
      artifactRenderers: [],
    });
    setWorkbench(true, "dbfox.data.sql-console:ds-1", [{
      viewKey: "dbfox.data.sql-console:ds-1",
      viewType: "dbfox.data.sql-console",
      title: "SQL 控制台",
      closeable: false,
      stateKey: "sql-ds-1",
      target: { type: "resource", kind: "dbfox.data.database", id: "ds-1" },
    }]);
    useWorkspaceStore.setState({
      centerMode: "home",
      pendingAsk: null,
      settingsOpen: false,
    });
  });

  it("renders the persistent console tab as an active dock tab", async () => {
    renderDock();

    const tab = await screen.findByRole("tab", { name: "SQL 控制台" });
    expect(tab.getAttribute("aria-selected")).toBe("true");
    expect(await screen.findByTestId("sql-console")).toHaveProperty("dataset.tabId", "sql-ds-1");
  });

  it("hides close controls for fixed tabs and exposes collapse", async () => {
    renderDock();

    await screen.findByRole("tab", { name: "SQL 控制台" });
    expect(screen.queryByRole("button", { name: "关闭 SQL 控制台" })).toBeNull();
    expect(screen.getByRole("button", { name: "收起工作台 Dock" })).toBeTruthy();
  });

  it("renders a collapsed rail when the dock is closed", async () => {
    useWorkspaceStore.getState().setDockOpen(false);
    renderDock();

    expect(screen.getByRole("button", { name: "展开工作台 Dock" })).toBeTruthy();
    expect(screen.queryByRole("tab", { name: "SQL 控制台" })).toBeNull();
  });

  it("opens the selected rail tool instead of an unrelated fallback tab", async () => {
    setWorkbench(false, null, [
        ...useWorkspaceStore.getState().workbenchByConversation["draft:default"].tabs,
        {
          viewKey: "core.artifacts:conv-1",
          viewType: "core.artifacts",
          title: "工件",
          closeable: false,
          target: { type: "conversation", id: "conv-1" },
        },
      ]);
    const view = render(
      <TooltipProvider>
        <WorkspaceDock
          activeConversationId="conv-1"
          showToast={vi.fn()}
        />
      </TooltipProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "SQL 控制台" }));

    expect((await screen.findByRole("tab", { name: "SQL 控制台" })).getAttribute("aria-selected")).toBe("true");
    expect(view.getByTestId("sql-console")).toBeTruthy();
  });

  it("renders active DLC Dock views through the production WorkspaceDock", async () => {
    setWorkbench(true, "acme.runtime.view:1", [{
        viewKey: "acme.runtime.view:1",
        viewType: "acme.runtime.view",
        title: "Runtime DLC",
        closeable: true,
      }]);
    useDlcStore.getState().setProjectionResult("snap-dlc", {}, {
      connectors: [],
      dockViews: [{
        viewType: "acme.runtime.view",
        icon: () => null,
        resolveTitle: () => "Runtime DLC",
        isVisible: () => true,
        render: (_view, context) => (
          <button
            type="button"
            data-testid="dlc-dock-view"
            onClick={() => context.onAsk({
              label: context.workbenchScopeId,
              authority: { kind: "acme.runtime.resource", id: "resource-1" },
              object: { kind: "acme.runtime.object", id: "object-1" },
              locator: "item:1",
            })}
          >
            DLC Dock
          </button>
        ),
      }],
      artifactRenderers: [],
    });

    renderDock();
    fireEvent.click(await screen.findByTestId("dlc-dock-view"));
    expect(
      useWorkspaceStore.getState().workbenchByConversation["draft:default"].reference,
    ).toEqual({
      label: "test-scope",
      authority: { kind: "acme.runtime.resource", id: "resource-1" },
      object: { kind: "acme.runtime.object", id: "object-1" },
      locator: "item:1",
    });
  });

  it("hides the overflow trigger when every tab fits", () => {
    renderDock();
    expect(screen.queryByRole("button", { name: /更多标签/ })).toBeNull();
  });

  it("exposes a keyboard-operable width separator", () => {
    renderDock();
    const separator = screen.getByRole("separator", { name: "调整工作台宽度" });
    expect(separator.getAttribute("aria-orientation")).toBe("vertical");
  });
});

describe("planDockTabWindow", () => {
  it("returns the full window when everything fits or measurement is unavailable", () => {
    expect(planDockTabWindow([100, 120], 400, 0)).toEqual({ start: 0, end: 2 });
    expect(planDockTabWindow([100, 120], 0, 1)).toEqual({ start: 0, end: 2 });
    expect(planDockTabWindow([], 400, 0)).toEqual({ start: 0, end: 0 });
  });

  it("truncates to a leading window and reserves room for the overflow trigger", () => {
    // limit = 300 - 30 = 270 → two 100px tabs fit, the third does not.
    expect(planDockTabWindow([100, 100, 100], 300, 0)).toEqual({ start: 0, end: 2 });
  });

  it("slides the window so an overflowing active tab stays visible", () => {
    // Active is the last tab; window slides to end at it.
    expect(planDockTabWindow([100, 100, 100], 300, 2)).toEqual({ start: 1, end: 3 });
    // Active in the middle stays inside the leading window.
    expect(planDockTabWindow([100, 100, 100], 300, 1)).toEqual({ start: 0, end: 2 });
  });

  it("always shows at least one tab even when nothing fits", () => {
    expect(planDockTabWindow([500], 300, 0)).toEqual({ start: 0, end: 1 });
    expect(planDockTabWindow([200, 200, 200], 150, 2)).toEqual({ start: 2, end: 3 });
  });
});
