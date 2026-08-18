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
        workspace_root: "C:/demo",
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
        { id: "conv-1", datasource_id: "ds-1", title: "分析订单趋势", updated_at: "2026-08-15T08:00:00Z" },
      ],
      openConversation,
    });
  });

  it("renders project list", () => {
    renderSidebar();
    expect(screen.getByRole("button", { name: "订单分析" })).toBeInTheDocument();
  });

  it("renders conversations as Core (always visible)", () => {
    renderSidebar();
    expect(screen.getByText("对话")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "分析订单趋势" })).toBeInTheDocument();
  });

  it("renders connector selector tabs from contributions", () => {
    renderSidebar({ connectors: [dataConnector, workspaceConnector] });
    expect(screen.getByRole("button", { name: /数据库/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /文件/ })).toBeInTheDocument();
  });

  it("renders active connector content", () => {
    renderSidebar({ connectors: [dataConnector] });
    expect(screen.getByTestId("data-connector")).toBeInTheDocument();
  });

  it("mock contribution appears in connector selector", () => {
    renderSidebar({ connectors: [mockConnector] });
    expect(screen.getByRole("button", { name: /Mock/ })).toBeInTheDocument();
  });

  it("mock contribution renders in active slot when selected", () => {
    renderSidebar({ connectors: [dataConnector, mockConnector] });
    // Default is first connector (data)
    expect(screen.getByTestId("data-connector")).toBeInTheDocument();

    // Click mock tab
    fireEvent.click(screen.getByRole("button", { name: /Mock/ }));
    expect(screen.getByTestId("mock-connector")).toBeInTheDocument();
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

  it("conversations remain visible regardless of active connector", () => {
    renderSidebar({ connectors: [dataConnector, mockConnector] });
    expect(screen.getByText("对话")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "分析订单趋势" })).toBeInTheDocument();

    // Switch connector
    fireEvent.click(screen.getByRole("button", { name: /Mock/ }));
    // Conversations still visible
    expect(screen.getByText("对话")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "分析订单趋势" })).toBeInTheDocument();
  });

  it("settings entry works", () => {
    const onOpenSettings = vi.fn();
    renderSidebar({ onOpenSettings });
    fireEvent.click(screen.getByRole("button", { name: "设置" }));
    expect(onOpenSettings).toHaveBeenCalledOnce();
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
