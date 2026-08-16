import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "../../../components/ui";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import { WorkspaceDock } from "../WorkspaceDock";

const datasourceState = vi.hoisted(() => ({
  activeDatasourceId: "ds-1",
}));

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
    activeDatasourceId: datasourceState.activeDatasourceId,
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
    datasourceState.activeDatasourceId = "ds-1";
    useWorkspaceStore.setState({
      centerMode: "home",
      pendingAsk: null,
      dock: { open: true, activeTabId: "console-ds-1" },
      dockTabs: [{
        id: "console-ds-1",
        kind: "console",
        title: "SQL 控制台",
        closeable: false,
        datasourceId: "ds-1",
        datasourceDbType: "mysql",
      }],
      sqlConsoleState: {
        "sql-ds-1": { draftSql: "SELECT 1", entries: [], running: false },
      },
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
    useWorkspaceStore.setState({ dock: { open: false, activeTabId: "console-ds-1" } });
    renderDock();

    expect(screen.getByRole("button", { name: "展开工作台 Dock" })).toBeTruthy();
    expect(screen.queryByRole("tab", { name: "SQL 控制台" })).toBeNull();
  });

  it("opens the selected rail tool instead of an unrelated fallback tab", async () => {
    useWorkspaceStore.setState({
      dock: { open: false, activeTabId: null },
      dockTabs: [
        ...useWorkspaceStore.getState().dockTabs,
        {
          id: "artifacts-conv-1",
          kind: "artifacts",
          title: "工件",
          closeable: false,
          conversationId: "conv-1",
        },
      ],
    });
    const view = render(
      <TooltipProvider>
        <WorkspaceDock activeDatasourceId="ds-1" activeConversationId="conv-1" showToast={vi.fn()} />
      </TooltipProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "SQL 控制台" }));

    expect((await screen.findByRole("tab", { name: "SQL 控制台" })).getAttribute("aria-selected")).toBe("true");
    expect(view.getByTestId("sql-console")).toBeTruthy();
  });
});
