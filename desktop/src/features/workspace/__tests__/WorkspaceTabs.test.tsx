import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "../../../components/ui";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import { WorkspaceTabs } from "../WorkspaceTabs";

describe("WorkspaceTabs interactions", () => {
  beforeEach(() => {
    cleanup();
    useWorkspaceStore.setState({
      tabs: [
        { id: "smart-query", title: "智能问数", type: "smart-query" },
        { id: "table-ds-1-orders", title: "orders", type: "table", tableId: "orders" },
        { id: "sql-1", title: "SQL 控制台", type: "sql" },
      ],
      activeTabId: "smart-query",
      sqlConsoleState: {
        "sql-1": { draftSql: "SELECT 1", entries: [], running: false },
      },
      selectedTables: [],
      contextTables: [],
      tableSubTabs: {},
      _tabSeq: { sql: 2, multiTable: 1, queryResult: 1, message: 1 },
    });
  });

  it("activates table tabs and syncs selected table context", () => {
    renderWorkspaceTabs();

    fireEvent.click(screen.getByRole("tab", { name: "orders" }));

    expect(useWorkspaceStore.getState().activeTabId).toBe("table-ds-1-orders");
    expect(useWorkspaceStore.getState().selectedTables).toEqual(["orders"]);
  });

  it("closes a tab without activating it", () => {
    renderWorkspaceTabs();

    fireEvent.click(screen.getByRole("button", { name: "关闭 SQL 控制台" }));

    expect(useWorkspaceStore.getState().activeTabId).toBe("smart-query");
    expect(useWorkspaceStore.getState().tabs.some((tab) => tab.id === "sql-1")).toBe(false);
    expect(useWorkspaceStore.getState().sqlConsoleState["sql-1"]).toBeUndefined();
  });

  it("opens a new SQL console from the add button", () => {
    const onOpenSqlConsole = vi.fn();
    renderWorkspaceTabs(onOpenSqlConsole);

    fireEvent.click(screen.getByRole("button", { name: "新建 SQL 查询" }));

    expect(onOpenSqlConsole).toHaveBeenCalledTimes(1);
  });
});

function renderWorkspaceTabs(onOpenSqlConsole = vi.fn()) {
  return render(
    <TooltipProvider>
      <WorkspaceTabs onOpenSqlConsole={onOpenSqlConsole} />
    </TooltipProvider>,
  );
}
