import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "../../../components/ui";
import { useTableWorkspaceStore } from "../../../stores/tableWorkspaceStore";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import { useConversationStore } from "../../../stores/conversationStore";
import type { DataSource } from "../../../lib/api/types";
import type { ConversationDetail } from "../../../types/conversation";
import { DataSourceTree } from "../DataSourceTree";

const datasourceState = vi.hoisted(() => ({
  activeDatasourceId: "ds-1",
  setActiveDatasourceId: vi.fn((id: string) => {
    datasourceState.activeDatasourceId = id;
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
    activeProject: {
      id: "project-1",
      name: "订单分析",
      datasource_count: 1,
      status: "active",
      workspace_root: "C:/demo",
    },
    loadingProjects: false,
    projectError: "",
  }),
}));

vi.mock("../useDatasourceState", () => ({
  useDatasourceState: () => ({
    datasources,
    activeDatasourceId: datasourceState.activeDatasourceId,
    activeDatasource: datasources.find((item) => item.id === datasourceState.activeDatasourceId) ?? null,
    setActiveDatasourceId: datasourceState.setActiveDatasourceId,
    tables: [
    {
      id: "table-1",
      table_name: "orders",
      table_schema: "",
      table_comment: "Orders",
      module_tag: "billing",
      ai_description: "",
      business_terms: "",
      columns_count: 0,
      semantic_tags: "",
      subject_area: "",
    },
    ],
    loadingSchema: false,
    schemaError: "",
  }),
}));

const datasources = [
  { id: "ds-1", name: "primary", db_type: "mysql", status: "active", database_name: "creatorhub", connection_generation: 1, project_id: "project-1" },
  { id: "ds-2", name: "analytics", db_type: "postgresql", status: "active", database_name: "analytics", connection_generation: 1, project_id: "project-2" },
] as DataSource[];

const openConversation = vi.fn(async () => ({} as ConversationDetail));

describe("DataSourceTree", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    datasourceState.activeDatasourceId = "ds-1";
    useWorkspaceStore.setState({
      activeProjectId: "project-1",
      projectShell: {},
    });
    useTableWorkspaceStore.setState({ selectedTables: [], tableSubTabs: {} });
    useConversationStore.setState({
      activeConversationId: null,
      summaries: [
        { id: "conv-1", datasource_id: "ds-1", title: "分析订单趋势", updated_at: "2026-08-15T08:00:00Z" },
        { id: "conv-2", datasource_id: "ds-2", title: "分析用户留存", updated_at: "2026-08-15T07:00:00Z" },
      ],
      openConversation,
    });
  });

  it("selects a connection from the connection entity list", () => {
    renderTree();

    fireEvent.click(screen.getByRole("button", { name: "analytics" }));

    expect(datasourceState.setActiveDatasourceId).toHaveBeenCalledWith("ds-2");
  });

  it("keeps the table tree inside a DBFox scroll area", () => {
    const { container } = renderTree();

    expect(container.querySelector(".ds-tree-scroll-area")).toBeTruthy();
    expect(container.querySelector(".dbfox-scroll-area-viewport")?.textContent).toContain("orders");
  });

  it("uses the datasource brand icon for the connection and keeps the generic icon for the database", () => {
    const { container } = renderTree();

    expect(container.querySelector('[data-db="mysql"]')).toBeTruthy();
    expect(screen.getByRole("button", { name: "creatorhub" }).querySelector(".ds-schema-icon")).toBeTruthy();
  });

  it("does not expose the removed table-context drag interaction", () => {
    renderTree();

    expect(screen.getByRole("button", { name: "orders" }).getAttribute("draggable")).toBeNull();
  });

  it("removes the legacy sidebar routes and keeps the new-conversation and settings entries", () => {
    const onOpenSettings = vi.fn();
    renderTree({ onOpenSettings });

    expect(screen.queryByRole("button", { name: "SQL 控制台" })).toBeNull();
    expect(screen.queryByRole("button", { name: "数据源管理" })).toBeNull();
    expect(screen.queryByPlaceholderText("搜索表或字段")).toBeNull();
    expect(screen.getByRole("button", { name: "primary 新对话" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "设置" }));

    expect(onOpenSettings).toHaveBeenCalledOnce();
  });
});

function renderTree(overrides: {
  onOpenSettings?: () => void;
} = {}) {
  return render(
    <TooltipProvider>
      <DataSourceTree
        collapsed={false}
        onToggleCollapse={vi.fn()}
        onTableClick={vi.fn()}
        onTableDoubleClick={vi.fn()}
        onNodeContextMenu={vi.fn()}
        onNewConnection={vi.fn()}
        onNewProject={vi.fn()}
        onOpenSettings={overrides.onOpenSettings ?? vi.fn()}
      />
    </TooltipProvider>,
  );
}
