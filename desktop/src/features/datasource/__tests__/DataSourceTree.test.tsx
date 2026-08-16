import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "../../../components/ui";
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
const projectFolderApi = vi.hoisted(() => ({
  listProjectFolder: vi.fn(),
}));

vi.mock("../../../lib/projectFolder", () => ({
  listProjectFolder: projectFolderApi.listProjectFolder,
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
    projectFolderApi.listProjectFolder.mockResolvedValue({
      path: "C:/demo",
      entries: [],
      truncated: false,
      error: null,
    });
    useWorkspaceStore.setState({
      activeProjectId: "project-1",
      sidebarEntityMode: "connections",
      projectSubMode: {},
      connectionSubMode: {},
      projectShell: {},
      selectedTables: [],
    });
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

  it("groups project conversations through datasource.project_id", () => {
    useWorkspaceStore.setState({ sidebarEntityMode: "projects", projectSubMode: { "project-1": "conversations" } });
    renderTree();

    expect(screen.getByRole("button", { name: "分析订单趋势" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "分析用户留存" })).toBeNull();
    expect(screen.getByRole("button", { name: "订单分析 新对话" })).toBeInTheDocument();
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

  it("switches between the current datasource data tree and its conversations", async () => {
    renderTree();

    fireEvent.click(screen.getAllByRole("tab", { name: "对话" })[0]);

    expect(screen.getByRole("button", { name: "分析订单趋势" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "分析用户留存" })).toBeNull();
    expect(screen.queryByRole("button", { name: "orders" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "分析订单趋势" }));
    await waitFor(() => expect(openConversation).toHaveBeenCalledWith("conv-1"));
  });

  it("lists the project folder in the files sub-mode and opens a file in the Dock", async () => {
    projectFolderApi.listProjectFolder.mockResolvedValueOnce({
      path: "C:/demo",
      entries: [
        { name: "src", path: "C:/demo/src", isDir: true },
        { name: "README.md", path: "C:/demo/README.md", isDir: false },
      ],
      truncated: false,
      error: null,
    });
    useWorkspaceStore.setState({
      sidebarEntityMode: "projects",
      projectSubMode: { "project-1": "files" },
    });
    renderTree();

    await waitFor(() => expect(projectFolderApi.listProjectFolder).toHaveBeenCalledWith("C:/demo"));
    const fileButton = await screen.findByRole("button", { name: "README.md" });
    fireEvent.click(fileButton);

    expect(useWorkspaceStore.getState().dockTabs).toHaveLength(1);
    expect(useWorkspaceStore.getState().dockTabs[0]).toMatchObject({
      kind: "file",
      filePath: "C:/demo/README.md",
      projectId: "project-1",
    });
  });

  it("lazy-loads an expanded project subfolder", async () => {
    projectFolderApi.listProjectFolder
      .mockResolvedValueOnce({
        path: "C:/demo",
        entries: [{ name: "src", path: "C:/demo/src", isDir: true }],
        truncated: false,
        error: null,
      })
      .mockResolvedValueOnce({
        path: "C:/demo/src",
        entries: [{ name: "main.py", path: "C:/demo/src/main.py", isDir: false }],
        truncated: false,
        error: null,
      });
    useWorkspaceStore.setState({
      sidebarEntityMode: "projects",
      projectSubMode: { "project-1": "files" },
    });
    renderTree();

    fireEvent.click(await screen.findByRole("button", { name: "src" }));
    await waitFor(() => expect(projectFolderApi.listProjectFolder).toHaveBeenCalledWith("C:/demo/src"));
    expect(await screen.findByRole("button", { name: "main.py" })).toBeInTheDocument();
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


  it("restores the project-scoped conversation after switching projects", async () => {
    useWorkspaceStore.setState({
      activeProjectId: "project-1",
      projectShell: {
        "project-1": {
          sidebarMode: "conversations",
          activeDatasourceId: "ds-1",
          activeConversationId: "conv-1",
        },
      },
    });
    renderTree();

    await waitFor(() => expect(openConversation).toHaveBeenCalledWith("conv-1"));
    expect(useWorkspaceStore.getState().centerMode).toBe("conversation");
  });
