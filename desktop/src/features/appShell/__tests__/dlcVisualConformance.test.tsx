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
import { ResourceViewContainer } from "../../resources/ResourceViewContainer";
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

  it("renders 10 synthetic DLC connectors as uniform host-owned Resource View sections", () => {
    const connectors = Array.from({ length: 10 }, (_, index) => syntheticConnector(index));
    render(
      <TooltipProvider>
        <ResourceViewContainer projectId="project-1" connectors={connectors} />
      </TooltipProvider>,
    );

    // Host owns the section chrome; every DLC gets the identical contract.
    expect(screen.getByText("资源")).toBeInTheDocument();
    const headers = screen.getAllByRole("button", { name: /扩展 \d+/ });
    expect(headers).toHaveLength(10);
    expect(headers[0]).toHaveAttribute("aria-expanded", "true");
    for (let index = 1; index < 10; index += 1) {
      expect(headers[index]).toHaveAttribute("aria-expanded", "false");
    }

    // Only the expanded section mounts DLC content, inside the host-owned slot.
    expect(screen.getByTestId("synthetic-resource-0")).toBeInTheDocument();
    expect(screen.getByTestId("synthetic-resource-0").closest(".resource-view__body")).toBeTruthy();

    // Expanding a late section keeps the host chrome intact.
    fireEvent.click(screen.getByRole("button", { name: /扩展 9/ }));
    expect(screen.getByTestId("synthetic-resource-9").closest(".resource-view__body")).toBeTruthy();
    expect(screen.getByText("资源")).toBeInTheDocument();
  });

  it("keeps an empty DLC connector section usable without crashing", () => {
    const emptyConnector: ResourceConnectorContribution = {
      id: "synthetic.empty",
      title: "空扩展",
      icon: "🫙",
      render: () => null,
    };
    render(
      <TooltipProvider>
        <ResourceViewContainer projectId="project-1" connectors={[emptyConnector]} />
      </TooltipProvider>,
    );

    const header = screen.getByRole("button", { name: /空扩展/ });
    expect(header).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(header);
    expect(header).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(header);
    expect(header).toHaveAttribute("aria-expanded", "true");
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
