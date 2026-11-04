import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "../../../components/ui";
import { useConversationStore } from "../../../stores/conversationStore";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import { useDlcStore } from "../../dlc/extensionStore";
import { createStagedExtensionHost } from "../../dlc/extensionHost";
import type {
  ConnectorContext,
  ResourceConnectorContribution,
} from "../../resources/types";
import type { DockViewContribution } from "../../dock/types";
import { ProjectWorkbench } from "../../resources/ProjectWorkbench";
import { WorkspaceDock } from "../WorkspaceDock";
import type { WorkspaceDockTab } from "../../../types/workspace";

function setTestWorkbench(tabs: WorkspaceDockTab[], activeViewKey: string | null) {
  useWorkspaceStore.setState({
    workbenchByConversation: {
      "draft:project-1": {
        scopeId: "visual-test-scope",
        open: true,
        activeViewKey,
        tabs,
        references: [],
      },
    },
  });
}

vi.mock("../../projects/useProjectState", () => ({
  useProjectState: () => ({
    activeProject: { id: "project-1", name: "订单分析", status: "active" },
    projects: [{ id: "project-1", name: "订单分析", status: "active" }],
    loadingProjects: false,
    projectError: "",
  }),
}));

function syntheticConnector(index: number): ResourceConnectorContribution {
  return {
    id: `synthetic.dlc-${index}`,
    title: `扩展 ${index} 的一个相当长的资源标题用于验证省略号`,
    icon: "🧩",
    render: (context: ConnectorContext) => (
      <div data-testid={`synthetic-resource-${index}`}>
        content of {context.projectId}
      </div>
    ),
  };
}

function syntheticDockView(index: number): DockViewContribution {
  return {
    viewType: `synthetic.dock-${index}`,
    icon: () => <span aria-hidden="true">🧩</span>,
    resolveTitle: () => `扩展视图 ${index} 的一个相当长的标签标题`,
    isVisible: () => true,
    render: () => <div data-testid={`synthetic-dock-content-${index}`}>dock view</div>,
  };
}

describe("DLC visual conformance (spec §20/§34)", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    useDlcStore.getState().reset();
    useWorkspaceStore.setState({
      activeProjectId: "project-1",
      centerMode: "home",
      mainSurfaceByProject: {},
      pendingAsk: null,
      settingsOpen: false,
      workbenchByConversation: {},
    });
    useConversationStore.setState({ summaries: [] });
  });

  it("renders registered connectors in uniform Dock workbench frames", () => {
    const connectors = Array.from({ length: 10 }, (_, index) => syntheticConnector(index));
    useDlcStore.getState().setProjectionResult("workbench-test", {}, { connectors, dockViews: [], artifactViews: [] });
    render(<TooltipProvider>{connectors.map(connector => <ProjectWorkbench key={connector.id} connectorId={connector.id} projectId="project-1" />)}</TooltipProvider>);
    expect(screen.getAllByRole("region")).toHaveLength(10);
    connectors.forEach((_, index) => {
      expect(screen.getByTestId(`synthetic-resource-${index}`).closest(".project-workbench__body")).toBeTruthy();
    });
    expect(screen.queryByText("资源")).not.toBeInTheDocument();
  });

  it("keeps empty and unavailable workbenches usable", () => {
    const connector = { id: "synthetic.empty", title: "空扩展", icon: null, render: () => null };
    useDlcStore.getState().setProjectionResult("empty-test", {}, { connectors: [connector], dockViews: [], artifactViews: [] });
    const { rerender } = render(<ProjectWorkbench connectorId={connector.id} projectId="project-1" />);
    expect(screen.getByRole("region", { name: "空扩展工作台" })).toBeTruthy();
    rerender(<ProjectWorkbench connectorId="disabled" projectId="project-1" />);
    expect(screen.getByText("此工作台暂不可用")).toBeTruthy();
  });

  it("routes 10 synthetic DLC dock views through the host frame", () => {
    const dockViews = Array.from({ length: 10 }, (_, index) => syntheticDockView(index));
    const tabs = dockViews.map((view, index) => ({
      viewKey: `${view.viewType}:1`,
      viewType: view.viewType,
      title: view.resolveTitle?.({} as never) ?? `view-${index}`,
      closeable: true,
    }));
    setTestWorkbench(tabs, tabs[3].viewKey);
    useDlcStore.getState().setProjectionResult("snap-conformance", {}, {
      connectors: [],
      dockViews,
      artifactViews: [],
    });

    render(
      <TooltipProvider>
        <WorkspaceDock
          activeConversationId={null}
          showToast={vi.fn()}
        />
      </TooltipProvider>,
    );

    // All DLC tabs are reachable through the host tab strip.
    const tabButtons = screen.getAllByRole("tab");
    expect(tabButtons).toHaveLength(10);

    // The active DLC view renders inside the host-owned viewport.
    expect(screen.getByTestId("synthetic-dock-content-3").closest(".workspace-dock__content")).toBeTruthy();

    // Switching activation stays within the host contract.
    fireEvent.click(screen.getByRole("tab", { name: /扩展视图 7/ }));
    expect(screen.getByTestId("synthetic-dock-content-7")).toBeInTheDocument();
  });

  it("ellipsizes long DLC titles in the tab strip", () => {
    const dockViews = [syntheticDockView(0)];
    setTestWorkbench([{
        viewKey: "synthetic.dock-0:1",
        viewType: "synthetic.dock-0",
        title: dockViews[0].resolveTitle?.({} as never) ?? "",
        closeable: true,
      }], "synthetic.dock-0:1");
    useDlcStore.getState().setProjectionResult("snap-conformance", {}, {
      connectors: [],
      dockViews,
      artifactViews: [],
    });

    render(
      <TooltipProvider>
        <WorkspaceDock
          activeConversationId={null}
          showToast={vi.fn()}
        />
      </TooltipProvider>,
    );

    const title = screen.getByRole("tab", { name: /扩展视图 0/ }).querySelector(".workspace-dock__tab-title");
    expect(title).toBeTruthy();
    // CSS enforces ellipsis; the full text stays available as the tooltip.
    expect(title?.getAttribute("title") ?? title?.textContent).toContain("扩展视图 0");
  });

  it("fails closed when a broken DLC dock view renders", () => {
    const staged = createStagedExtensionHost("synthetic.broken", {
      openDockTab: vi.fn(),
      invokeOperation: async <TOutput,>() => ({} as TOutput),
    });
    staged.host.dockViews.register({
      viewType: "synthetic.broken.view",
      icon: () => null,
      resolveTitle: () => "Broken View",
      isVisible: () => true,
      render: () => {
        throw new Error("renderer exploded");
      },
    });
    setTestWorkbench([{
        viewKey: "synthetic.broken.view:1",
        viewType: "synthetic.broken.view",
        title: "Broken View",
        closeable: true,
      }], "synthetic.broken.view:1");
    useDlcStore.getState().setProjectionResult("snap-broken", {}, staged.getContributions());

    render(
      <TooltipProvider>
        <WorkspaceDock
          activeConversationId={null}
          showToast={vi.fn()}
        />
      </TooltipProvider>,
    );

    // The host survives: the boundary shows an alert, the tab strip remains.
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Broken View/ })).toBeInTheDocument();
  });
});
