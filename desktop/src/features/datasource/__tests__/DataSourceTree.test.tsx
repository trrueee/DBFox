import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "../../../components/ui";
import { useDatasourceStore } from "../../../stores/datasourceStore";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import type { DataSource } from "../../../lib/api/types";
import { DataSourceTree } from "../DataSourceTree";

const datasources = [
  { id: "ds-1", name: "primary", db_type: "mysql", status: "active", database_name: "creatorhub" },
  { id: "ds-2", name: "analytics", db_type: "postgres", status: "active", database_name: "analytics" },
] as DataSource[];

describe("DataSourceTree", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    useDatasourceStore.setState({
      datasources,
      activeDatasourceId: "ds-1",
      activeDatasourceForSettings: datasources[0],
      tables: [
        { id: "table-1", table_name: "orders", table_comment: "Orders", module_tag: "billing" },
      ],
      loadingSchema: false,
      schemaError: "",
      tableColumns: {},
    });
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

    expect(useDatasourceStore.getState().activeDatasourceId).toBe("ds-2");
  });

  it("keeps the table tree inside a DBFox scroll area", () => {
    const { container } = renderTree();

    expect(container.querySelector(".ds-tree-scroll-area")).toBeTruthy();
    expect(container.querySelector(".dbfox-scroll-area-viewport")?.textContent).toContain("orders");
  });
});

function renderTree() {
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
      />
    </TooltipProvider>,
  );
}
