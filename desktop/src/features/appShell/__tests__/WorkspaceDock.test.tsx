import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "../../../components/ui";
import { useSqlConsoleStore } from "../../../stores/sqlConsoleStore";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import { useDlcStore } from "../../dlc/extensionStore";
import { WorkspaceDock } from "../WorkspaceDock";

vi.mock("../../datasource/useDatasourceState", () => ({
  useDatasourceState: () => ({
    datasources: [{
      id: "ds-1",
      name: "creatorhub",
      db_type: "mysql",
      status: "active",
      database_name: "creatorhub",
      connection_generation: 1,
    }],
    activeDatasourceId: "ds-1",
    activeDatasource: {
      id: "ds-1",
      name: "creatorhub",
      db_type: "mysql",
      status: "active",
      database_name: "creatorhub",
      connection_generation: 1,
    },
  }),
}));

vi.mock("../../workspace/SqlConsoleWorkspace", () => ({
  SqlConsoleWorkspace: (props: Record<string, unknown>) => (
    <div data-testid="sql-console" data-tab-id={String(props.tabId)} />
  ),
}));
vi.mock("../../workspace/TableWorkspace", () => ({
  TableWorkspace: () => <div data-testid="table-workspace" />,
}));
vi.mock("../../workspace/MultiTableWorkspace", () => ({
  MultiTableWorkspace: () => <div data-testid="multi-table-workspace" />,
}));
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
        activeDatasourceId="ds-1"
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
    useWorkspaceStore.setState({
      centerMode: "home",
      pendingAsk: null,
      dock: { open: true, activeViewKey: "dbfox.data.sql-console:ds-1" },
      dockTabs: [{
        viewKey: "dbfox.data.sql-console:ds-1",
        viewType: "dbfox.data.sql-console",
        title: "SQL 控制台",
        closeable: false,
        stateKey: "sql-ds-1",
        target: { type: "resource", kind: "database", id: "ds-1" },
      }],
      settingsOpen: false,
    });
    useSqlConsoleStore.setState({
      sqlConsoleState: {
        "sql-ds-1": {
          datasourceId: "ds-1",
          datasourceDbType: "mysql",
          draftSql: "SELECT 1",
          entries: [],
          running: false,
        },
      },
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
    useWorkspaceStore.setState({
      dock: { open: false, activeViewKey: "dbfox.data.sql-console:ds-1" },
    });
    renderDock();

    expect(screen.getByRole("button", { name: "展开工作台 Dock" })).toBeTruthy();
    expect(screen.queryByRole("tab", { name: "SQL 控制台" })).toBeNull();
  });

  it("opens the selected rail tool instead of an unrelated fallback tab", async () => {
    useWorkspaceStore.setState({
      dock: { open: false, activeViewKey: null },
      dockTabs: [
        ...useWorkspaceStore.getState().dockTabs,
        {
          viewKey: "core.artifacts:conv-1",
          viewType: "core.artifacts",
          title: "工件",
          closeable: false,
          target: { type: "conversation", id: "conv-1" },
        },
      ],
    });
    const view = render(
      <TooltipProvider>
        <WorkspaceDock
          activeDatasourceId="ds-1"
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
    useWorkspaceStore.setState({
      dock: { open: true, activeViewKey: "acme.runtime.view:1" },
      dockTabs: [{
        viewKey: "acme.runtime.view:1",
        viewType: "acme.runtime.view",
        title: "Runtime DLC",
        closeable: true,
      }],
    });
    useDlcStore.getState().setProjectionResult("snap-dlc", {}, {
      connectors: [],
      requestedResources: [],
      dockViews: [{
        viewType: "acme.runtime.view",
        icon: () => null,
        resolveTitle: () => "Runtime DLC",
        isVisible: () => true,
        render: () => <div data-testid="dlc-dock-view">DLC Dock</div>,
      }],
      artifactRenderers: [],
    });

    renderDock();
    expect(await screen.findByTestId("dlc-dock-view")).toBeTruthy();
  });
});
