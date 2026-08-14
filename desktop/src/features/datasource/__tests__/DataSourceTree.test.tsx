import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "../../../components/ui";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import type { DataSource } from "../../../lib/api/types";
import { DataSourceTree } from "../DataSourceTree";

const datasourceState = vi.hoisted(() => ({
  activeDatasourceId: "ds-1",
  setActiveDatasourceId: vi.fn((id: string) => {
    datasourceState.activeDatasourceId = id;
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
  { id: "ds-1", name: "primary", db_type: "mysql", status: "active", database_name: "creatorhub", connection_generation: 1 },
  { id: "ds-2", name: "analytics", db_type: "postgres", status: "active", database_name: "analytics", connection_generation: 1 },
] as DataSource[];

describe("DataSourceTree", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    datasourceState.activeDatasourceId = "ds-1";
    useWorkspaceStore.setState({
      selectedTables: [],
      tabs: [{ id: "smart-query", title: "智能问数", type: "smart-query" }],
      activeTabId: "smart-query",
    });
  });

  it("selects a datasource through the DBFox dropdown menu", () => {
    renderTree();

    fireEvent.pointerDown(screen.getByRole("button", { name: "选择数据源 primary" }), { button: 0, ctrlKey: false });
    fireEvent.click(screen.getByRole("menuitem", { name: /analytics/ }));

    expect(datasourceState.setActiveDatasourceId).toHaveBeenCalledWith("ds-2");
  });

  it("keeps the table tree inside a DBFox scroll area", () => {
    const { container } = renderTree();

    expect(container.querySelector(".ds-tree-scroll-area")).toBeTruthy();
    expect(container.querySelector(".dbfox-scroll-area-viewport")?.textContent).toContain("orders");
  });

  it("does not expose the removed table-context drag interaction", () => {
    renderTree();

    expect(screen.getByRole("button", { name: "orders" }).getAttribute("draggable")).toBeNull();
  });

  it("exposes common workspace routes and a dedicated settings entry", () => {
    const onOpenSqlConsole = vi.fn();
    const onOpenConnectionManager = vi.fn();
    const onOpenSettings = vi.fn();
    renderTree({ onOpenSqlConsole, onOpenConnectionManager, onOpenSettings });

    fireEvent.click(screen.getByRole("button", { name: "SQL 控制台" }));
    fireEvent.click(screen.getByRole("button", { name: "数据源管理" }));
    fireEvent.click(screen.getByRole("button", { name: "设置" }));

    expect(onOpenSqlConsole).toHaveBeenCalledOnce();
    expect(onOpenSqlConsole).toHaveBeenCalledWith();
    expect(onOpenConnectionManager).toHaveBeenCalledOnce();
    expect(onOpenSettings).toHaveBeenCalledOnce();
  });
});

function renderTree(overrides: {
  onOpenSqlConsole?: () => void;
  onOpenConnectionManager?: () => void;
  onOpenSettings?: () => void;
} = {}) {
  return render(
    <TooltipProvider>
      <DataSourceTree
        treeSearch=""
        collapsed={false}
        onToggleCollapse={vi.fn()}
        onTreeSearchChange={vi.fn()}
        onTableClick={vi.fn()}
        onTableDoubleClick={vi.fn()}
        onNodeContextMenu={vi.fn()}
        onRefresh={vi.fn()}
        onNewConnection={vi.fn()}
        onOpenSqlConsole={overrides.onOpenSqlConsole ?? vi.fn()}
        onOpenConnectionManager={overrides.onOpenConnectionManager ?? vi.fn()}
        onOpenSettings={overrides.onOpenSettings ?? vi.fn()}
      />
    </TooltipProvider>,
  );
}
