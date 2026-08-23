import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "../../../components/ui";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import { useConversationStore } from "../../../stores/conversationStore";
import type { DataSource } from "../../../lib/api/types";
import type { ConversationDetail } from "../../../types/conversation";
import type { ResourceConnectorContribution } from "../../resources/types";
import { ProjectResourceSidebar } from "../../resources/ProjectResourceSidebar";

const datasourceState = vi.hoisted(() => ({
  activeDatasourceId: "ds-1",
  setActiveDatasourceId: vi.fn((id: string) => {
    datasourceState.activeDatasourceId = id;
  }),
}));

vi.mock("../../datasource/useDatasourceState", () => ({
  useDatasourceState: (projectId?: string) => ({
    datasources: projectId
      ? datasources.filter((d) => d.project_id === projectId)
      : datasources,
    activeDatasourceId: datasourceState.activeDatasourceId,
    activeDatasource: datasources.find((item) => item.id === datasourceState.activeDatasourceId) ?? null,
    setActiveDatasourceId: datasourceState.setActiveDatasourceId,
    tables: [],
    loadingSchema: false,
    schemaError: "",
  }),
}));

vi.mock("../../projects/useProjectState", () => ({
  useProjectState: () => ({
    projects: [
      {
        id: "project-1",
        name: "订单分析",
        datasource_count: 1,
        status: "active",
      },
    ],
    loadingProjects: false,
    projectError: "",
  }),
}));

const datasources = [
  { id: "ds-1", name: "primary", db_type: "mysql", status: "active", database_name: "creatorhub", connection_generation: 1, project_id: "project-1" },
] as DataSource[];

const openConversation = vi.fn(async () => ({} as ConversationDetail));

// Mock connector for conformance proof
const mockConnector: ResourceConnectorContribution = {
  id: "test.mock",
  title: "Mock",
  icon: "🧪",
  render: (context) => <div data-testid="mock-connector">Mock Content for {context.projectId}</div>,
  addLabel: "Add Mock",
  onAdd: vi.fn(),
};

const dataConnector: ResourceConnectorContribution = {
  id: "dbfox.data",
  title: "数据库",
  icon: "🗄️",
  render: () => <div data-testid="data-connector">Data Content</div>,
  addLabel: "新建数据库",
  onAdd: vi.fn(),
};

const workspaceConnector: ResourceConnectorContribution = {
  id: "dbfox.workspace",
  title: "文件",
  icon: "📄",
  render: () => <div data-testid="workspace-connector">Workspace Content</div>,
};

describe("ProjectResourceSidebar", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    datasourceState.activeDatasourceId = "ds-1";
    useWorkspaceStore.setState({
      activeProjectId: "project-1",
      projectShell: {},
    });
    useConversationStore.setState({
      activeConversationId: null,
      summaries: [
        { id: "conv-1", project_id: "project-1", title: "分析订单趋势", updated_at: "2026-08-15T08:00:00Z" },
      ],
      openConversation,
    });
  });

  it("renders a single project as identity rather than a fake switch action", () => {
    renderSidebar();
    expect(screen.getByText("订单分析")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "切换项目" })).toBeNull();
  });

  it("renders conversations as Core (always visible)", () => {
    renderSidebar();
    expect(screen.getByText("对话")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "分析订单趋势" })).toBeInTheDocument();
  });

  it("renders only conversations owned by the active project", () => {
    useConversationStore.setState({
      activeConversationId: null,
      summaries: [
        { id: "conv-direct", project_id: "project-1", title: "工作区对话", updated_at: "2026-08-19T08:00:00Z" },
        { id: "conv-other", project_id: "project-other", title: "其他工作区对话", updated_at: "2026-08-16T08:00:00Z" },
      ],
      openConversation,
    });

    renderSidebar();
    expect(screen.getByRole("button", { name: "工作区对话" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "其他工作区对话" })).toBeNull();
  });

  it("renders host-owned collapsible resource sections from contributions", () => {
    renderSidebar({ connectors: [dataConnector, workspaceConnector] });
    const dataHeader = screen.getByRole("button", { name: /数据库/ });
    const workspaceHeader = screen.getByRole("button", { name: /文件/ });
    expect(dataHeader).toHaveAttribute("aria-expanded", "true");
    expect(workspaceHeader).toHaveAttribute("aria-expanded", "false");
  });

  it("renders only the first connector content by default", () => {
    renderSidebar({ connectors: [dataConnector, workspaceConnector] });
    expect(screen.getByTestId("data-connector")).toBeInTheDocument();
    expect(screen.queryByTestId("workspace-connector")).toBeNull();
  });

  it("expands and collapses sections independently", () => {
    renderSidebar({ connectors: [dataConnector, mockConnector] });

    fireEvent.click(screen.getByRole("button", { name: /Mock/ }));
    expect(screen.getByTestId("mock-connector")).toBeInTheDocument();
    expect(screen.getByTestId("data-connector")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /数据库/ }));
    expect(screen.queryByTestId("data-connector")).toBeNull();
    expect(screen.getByTestId("mock-connector")).toBeInTheDocument();
  });

  it("keeps conversations visible regardless of section expansion", () => {
    renderSidebar({ connectors: [dataConnector, mockConnector] });
    expect(screen.getByText("对话")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "分析订单趋势" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Mock/ }));
    expect(screen.getByText("对话")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "分析订单趋势" })).toBeInTheDocument();
  });

  it("add resource button is present when addable contributions exist", () => {
    renderSidebar({ connectors: [dataConnector, mockConnector, workspaceConnector] });
    expect(screen.getByRole("button", { name: "添加资源" })).toBeInTheDocument();
  });

  it("add resource button is absent when no addable contributions exist", () => {
    // workspaceConnector has no addLabel/onAdd
    renderSidebar({ connectors: [workspaceConnector] });
    expect(screen.queryByRole("button", { name: "添加资源" })).toBeNull();
  });

  it("addable contributions are correctly filtered from composition", () => {
    const allConnectors = [dataConnector, mockConnector, workspaceConnector];
    const addable = allConnectors.filter((c) => c.onAdd && c.addLabel);
    expect(addable).toHaveLength(2);
    expect(addable.map((c) => c.id)).toEqual(["dbfox.data", "test.mock"]);
  });

  it("settings entry works", () => {
    const onOpenSettings = vi.fn();
    renderSidebar({ onOpenSettings });
    fireEvent.click(screen.getByRole("button", { name: "设置" }));
    expect(onOpenSettings).toHaveBeenCalledOnce();
  });

  it("stays deterministic when the connector list shrinks", () => {
    // Start with 2 connectors; the first is expanded by default.
    const { rerender } = render(
      <TooltipProvider>
        <ProjectResourceSidebar
          collapsed={false}
          onToggleCollapse={vi.fn()}
          onNewProject={vi.fn()}
          onOpenSettings={vi.fn()}
          connectors={[dataConnector, mockConnector]}
        />
      </TooltipProvider>,
    );
    expect(screen.getByTestId("data-connector")).toBeInTheDocument();

    // Remove mock — data section remains expanded.
    rerender(
      <TooltipProvider>
        <ProjectResourceSidebar
          collapsed={false}
          onToggleCollapse={vi.fn()}
          onNewProject={vi.fn()}
          onOpenSettings={vi.fn()}
          connectors={[dataConnector]}
        />
      </TooltipProvider>,
    );
    expect(screen.getByTestId("data-connector")).toBeInTheDocument();
  });

  it("survives a synthetic 20-DLC stress composition", () => {
    const synthetic: ResourceConnectorContribution[] = Array.from({ length: 20 }, (_, index) => ({
      id: `synthetic.dlc-${index}`,
      title: `DLC ${index} 的一个相当长的资源标题`,
      icon: "🧩",
      render: () => <div data-testid={`synthetic-content-${index}`}>content</div>,
    }));

    renderSidebar({ connectors: [dataConnector, ...synthetic] });

    // All 21 section headers render; only the first is expanded by default.
    for (let index = 0; index < 20; index += 1) {
      expect(screen.getByRole("button", { name: new RegExp(synthetic[index].title) })).toHaveAttribute(
        "aria-expanded",
        "false",
      );
      expect(screen.queryByTestId(`synthetic-content-${index}`)).toBeNull();
    }
    expect(screen.getByTestId("data-connector")).toBeInTheDocument();

    // Expanding one DLC keeps the rest collapsed.
    fireEvent.click(screen.getByRole("button", { name: new RegExp(synthetic[7].title) }));
    expect(screen.getByTestId("synthetic-content-7")).toBeInTheDocument();
    expect(screen.queryByTestId("synthetic-content-8")).toBeNull();
  });
});

function renderSidebar(overrides: {
  connectors?: ResourceConnectorContribution[];
  onOpenSettings?: () => void;
} = {}) {
  return render(
    <TooltipProvider>
      <ProjectResourceSidebar
        collapsed={false}
        onToggleCollapse={vi.fn()}
        onNewProject={vi.fn()}
        onOpenSettings={overrides.onOpenSettings ?? vi.fn()}
        connectors={overrides.connectors ?? [dataConnector]}
      />
    </TooltipProvider>,
  );
}
