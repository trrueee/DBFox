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
});

