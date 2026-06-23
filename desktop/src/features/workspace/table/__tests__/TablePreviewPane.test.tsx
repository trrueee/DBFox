import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TablePreviewPane } from "../TablePreviewPane";

const engineMocks = vi.hoisted(() => ({
  executeSql: vi.fn(),
  listColumns: vi.fn(),
  quoteIdentifier: vi.fn((identifier: string) => `\`${identifier}\``),
  resolveTableByName: vi.fn(),
}));

vi.mock("../../../engine/engineApi", () => engineMocks);

function sqlResult(rows: Array<Record<string, unknown>>, latencyMs = 5) {
  return {
    success: true,
    columns: ["id", "name"],
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
    engineMocks.resolveTableByName.mockResolvedValue({
      datasource: { id: "ds-1", db_type: "mysql" },
      table: { id: "table-1", table_name: "users" },
    });
    engineMocks.listColumns.mockResolvedValue([
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
      <TablePreviewPane tableId="users" onOpenSqlConsole={vi.fn()} onToast={vi.fn()} />,
    );

    expect(await screen.findByText("user-1")).toBeTruthy();

    fireEvent.click(screen.getByText(">"));

    await waitFor(() => expect(engineMocks.executeSql).toHaveBeenCalledTimes(2));
    expect(screen.getByText("user-1")).toBeTruthy();
    expect(container.querySelector(".hifi-preview-skeleton")).toBeNull();
  });

  it("pushes search, filter, and sort into the preview SQL", async () => {
    engineMocks.executeSql.mockResolvedValue(sqlResult([{ id: "1", name: "amy" }]));

    render(<TablePreviewPane tableId="users" onOpenSqlConsole={vi.fn()} onToast={vi.fn()} />);

    expect(await screen.findByText("amy")).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText("搜索表数据..."), { target: { value: "amy" } });
    fireEvent.click(screen.getByRole("button", { name: "筛选" }));
    fireEvent.change(screen.getByLabelText("筛选列"), { target: { value: "name" } });
    fireEvent.change(screen.getByLabelText("筛选条件"), { target: { value: "equals" } });
    fireEvent.change(screen.getByLabelText("筛选值"), { target: { value: "amy" } });
    fireEvent.click(screen.getByRole("button", { name: "应用筛选" }));
    fireEvent.click(screen.getByRole("button", { name: "排序" }));
    fireEvent.change(screen.getByLabelText("排序列"), { target: { value: "name" } });
    fireEvent.change(screen.getByLabelText("排序方向"), { target: { value: "asc" } });
    fireEvent.click(screen.getByRole("button", { name: "应用排序" }));

    await waitFor(() => {
      const sql = engineMocks.executeSql.mock.calls.at(-1)?.[1] as string;
      expect(sql).toContain("`name` = 'amy'");
      expect(sql).toContain("`name` LIKE '%amy%'");
      expect(sql).toContain("ORDER BY `name` ASC");
    });
  });

  it("exports the current matching table result without page limits", async () => {
    engineMocks.executeSql.mockResolvedValue(sqlResult([{ id: "1", name: "amy" }]));
    const onToast = vi.fn();

    render(<TablePreviewPane tableId="users" onOpenSqlConsole={vi.fn()} onToast={onToast} />);

    expect(await screen.findByText("amy")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "导出" }));

    await waitFor(() => {
      const [, sql, purpose] = engineMocks.executeSql.mock.calls.at(-1) ?? [];
      expect(purpose).toBe("export table users");
      expect(String(sql)).not.toContain("LIMIT");
    });
    await waitFor(() => expect(onToast).toHaveBeenCalledWith("已导出 CSV"));
  });
});
