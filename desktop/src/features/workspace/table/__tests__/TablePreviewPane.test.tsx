import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TablePreviewPane } from "../TablePreviewPane";

const engineMocks = vi.hoisted(() => ({
  executeSql: vi.fn(),
  quoteIdentifier: vi.fn((identifier: string) => `\`${identifier}\``),
}));

vi.mock("../../../engine/engineApi", () => engineMocks);

const schemaMocks = vi.hoisted(() => ({
  findTableByName: vi.fn(),
  listColumns: vi.fn(),
}));

vi.mock("../../../../lib/api/schema", () => schemaMocks);

function sqlResult(rows: Array<Record<string, unknown>>, latencyMs = 5, columns = ["id", "name"]) {
  return {
    success: true,
    columns,
    rows,
    rowCount: rows.length,
    latencyMs,
    warnings: [],
    notices: [],
  };
}

describe("TablePreviewPane", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    Object.assign(URL, {
      createObjectURL: vi.fn(() => "blob:table-csv"),
      revokeObjectURL: vi.fn(),
    });
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
    schemaMocks.findTableByName.mockResolvedValue({ id: "table-1", table_name: "users" });
    schemaMocks.listColumns.mockResolvedValue([
      { column_name: "id", data_type: "bigint" },
      { column_name: "name", data_type: "varchar" },
    ]);
  });

  it("keeps the current page visible while loading the next page", async () => {
    const firstPageRows = Array.from({ length: 21 }, (_, index) => ({
      id: String(index + 1),
      name: `user-${index + 1}`,
    }));
    engineMocks.executeSql
      .mockResolvedValueOnce(sqlResult(firstPageRows))
      .mockReturnValueOnce(new Promise(() => {}));

    const { container } = render(
      <TablePreviewPane tableId="users" datasourceId="ds-1" datasourceDbType="mysql" onOpenSqlConsole={vi.fn()} onToast={vi.fn()} />,
    );

    expect(await screen.findByText("user-1")).toBeTruthy();
    expect(schemaMocks.findTableByName).toHaveBeenCalledWith("ds-1", "users");

    fireEvent.click(screen.getByText(">"));

    await waitFor(() => expect(engineMocks.executeSql).toHaveBeenCalledTimes(2));
    expect(screen.getByText("user-1")).toBeTruthy();
    expect(container.querySelector(".hifi-preview-skeleton")).toBeNull();
    expect(container.querySelector(".hifi-page-num.active")?.textContent).toBe("1");
    expect(container.querySelector(".hifi-table-footer")?.textContent).toContain("第 1 页");
    expect(container.querySelector(".hifi-table-footer")?.textContent).toContain("正在加载第 2 页");
  });

  it("formats datetime preview cells for readable table scanning", async () => {
    schemaMocks.listColumns.mockResolvedValueOnce([
      { column_name: "id", data_type: "bigint" },
      { column_name: "name", data_type: "varchar" },
      { column_name: "created_at", data_type: "datetime" },
    ]);
    engineMocks.executeSql.mockResolvedValue(
      sqlResult(
        [{ id: "1", name: "monthly_basic", created_at: "2026-05-09T10:22:57.506000" }],
        5,
        ["id", "name", "created_at"],
      ),
    );

    render(
      <TablePreviewPane tableId="billing_plans" datasourceId="ds-1" datasourceDbType="mysql" onOpenSqlConsole={vi.fn()} onToast={vi.fn()} />,
    );

    expect(await screen.findByText("2026-05-09 10:22:57.506")).toBeTruthy();
    expect(screen.queryByText("2026-05-09T10:22:57.506000")).toBeNull();
  });

  it("pushes search, filter, and sort into the preview SQL", async () => {
    engineMocks.executeSql.mockResolvedValue(sqlResult([{ id: "1", name: "amy" }]));

    render(<TablePreviewPane tableId="users" datasourceId="ds-1" datasourceDbType="mysql" onOpenSqlConsole={vi.fn()} onToast={vi.fn()} />);

    expect(await screen.findByText("amy")).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText("搜索表数据..."), { target: { value: "amy" } });
    fireEvent.click(screen.getByRole("button", { name: "筛选" }));
    chooseSelectOption("筛选列", "name");
    chooseSelectOption("筛选条件", "等于");
    fireEvent.change(screen.getByLabelText("筛选值"), { target: { value: "amy" } });
    fireEvent.click(screen.getByRole("button", { name: "应用筛选" }));
    fireEvent.click(screen.getByRole("button", { name: "排序" }));
    chooseSelectOption("排序列", "name");
    chooseSelectOption("排序方向", "升序");
    fireEvent.click(screen.getByRole("button", { name: "应用排序" }));

    await waitFor(() => {
      const sql = engineMocks.executeSql.mock.calls.at(-1)?.[1] as string;
      expect(sql).toContain("`name` = 'amy'");
      expect(sql).toContain("`name` LIKE '%amy%'");
      expect(sql).toContain("ORDER BY `name` ASC");
    });
  });

  it("uses UI primitives for the table preview toolbar controls", async () => {
    engineMocks.executeSql.mockResolvedValue(sqlResult([{ id: "1", name: "amy" }]));

    const { container } = render(
      <TablePreviewPane tableId="toolbar_users" datasourceId="ds-1" datasourceDbType="mysql" onOpenSqlConsole={vi.fn()} onToast={vi.fn()} />,
    );

    expect(await screen.findByText("amy")).toBeTruthy();

    const toolbar = screen.getByRole("toolbar", { name: "表数据工具栏" });
    expect(toolbar.querySelector(".hifi-toolbar-btn")).toBeNull();
    expect(screen.getByRole("button", { name: "刷新" }).className).toContain("dbfox-button");
    expect(screen.getByPlaceholderText("搜索表数据...").className).toContain("hifi-preview-search");

    fireEvent.click(screen.getByRole("button", { name: "筛选" }));

    const controlSurface = container.querySelector(".hifi-table-toolbar-stack");
    expect(controlSurface?.querySelector(".hifi-toolbar-btn")).toBeNull();
    expect(screen.getByRole("combobox", { name: "筛选列" }).className).toContain("dbfox-select-trigger");
    expect(screen.getByRole("combobox", { name: "筛选列" }).className).toContain("hifi-preview-control-select");
    expect(screen.getByLabelText("筛选值").className).toContain("hifi-preview-control-input");

    fireEvent.click(screen.getByRole("button", { name: "排序" }));

    expect(screen.getByRole("combobox", { name: "排序方向" }).className).toContain("dbfox-select-trigger");
    expect(screen.getByRole("combobox", { name: "排序方向" }).className).toContain("hifi-preview-control-select");
  });

  it("uses UI primitives for preview pagination and empty actions", async () => {
    engineMocks.executeSql.mockResolvedValue(sqlResult([]));

    const { container } = render(
      <TablePreviewPane tableId="empty_users" datasourceId="ds-1" datasourceDbType="mysql" onOpenSqlConsole={vi.fn()} onToast={vi.fn()} />,
    );

    expect(await screen.findByText("这张表还没有数据")).toBeTruthy();

    const footer = container.querySelector(".hifi-table-footer");
    expect(footer?.querySelector(".hifi-toolbar-btn")).toBeNull();
    expect(screen.getByRole("button", { name: "<" }).className).toContain("dbfox-button");
    expect(screen.getByRole("combobox").className).toContain("dbfox-select-trigger");

    const emptyActions = container.querySelector(".hifi-preview-empty-actions");
    expect(emptyActions?.querySelector(".hifi-toolbar-btn")).toBeNull();
    const emptyButtons = Array.from(emptyActions?.querySelectorAll("button") ?? []);
    expect(emptyButtons).toHaveLength(2);
    expect(emptyButtons[0].className).toContain("dbfox-button");
    expect(emptyButtons[1].className).toContain("dbfox-button");
  });

  it("exports the current matching table result without page limits", async () => {
    engineMocks.executeSql.mockResolvedValue(sqlResult([{ id: "1", name: "amy" }]));
    const onToast = vi.fn();

    render(<TablePreviewPane tableId="users" datasourceId="ds-1" datasourceDbType="mysql" onOpenSqlConsole={vi.fn()} onToast={onToast} />);

    expect(await screen.findByText("amy")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "导出" }));

    await waitFor(() => {
      const [, sql, purpose] = engineMocks.executeSql.mock.calls.at(-1) ?? [];
      expect(purpose).toBe("export table users");
      expect(String(sql)).not.toContain("LIMIT");
    });
    await waitFor(() => expect(onToast).toHaveBeenCalledWith("已导出 CSV"));
  });

  it("copies and marks the clicked preview cell as selected", async () => {
    const onToast = vi.fn();
    engineMocks.executeSql.mockResolvedValue(sqlResult([{ id: "1", name: "amy" }]));

    render(
      <TablePreviewPane tableId="copyable_users" datasourceId="ds-1" datasourceDbType="mysql" onOpenSqlConsole={vi.fn()} onToast={onToast} />,
    );

    const cell = (await screen.findByText("amy")).closest("td");
    if (!cell) throw new Error("Expected preview cell to be rendered");

    fireEvent.click(cell);

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("amy");
    expect(cell.className).toContain("is-selected");
    expect(cell.getAttribute("aria-selected")).toBe("true");
    await waitFor(() => expect(onToast).toHaveBeenCalledWith("已复制单元格"));
  });

  it("renders null preview cells as a stable NULL pill and copies NULL", async () => {
    const onToast = vi.fn();
    engineMocks.executeSql.mockResolvedValue(sqlResult([{ id: "1", name: null }]));

    render(
      <TablePreviewPane tableId="nullable_users" datasourceId="ds-1" datasourceDbType="mysql" onOpenSqlConsole={vi.fn()} onToast={onToast} />,
    );

    const nullPill = await screen.findByText("NULL");
    const cell = nullPill.closest("td");
    if (!cell) throw new Error("Expected null preview cell to be rendered");

    expect(nullPill.className).toContain("table-preview-null-pill");
    expect(cell.className).toContain("is-null");

    fireEvent.click(cell);

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("NULL");
    await waitFor(() => expect(onToast).toHaveBeenCalledWith("已复制单元格"));
  });
});

function chooseSelectOption(label: string, optionName: string) {
  fireEvent.pointerDown(screen.getByRole("combobox", { name: label }), {
    button: 0,
    ctrlKey: false,
    pointerId: 1,
    pointerType: "mouse",
  });
  fireEvent.click(screen.getByRole("option", { name: optionName }));
}
