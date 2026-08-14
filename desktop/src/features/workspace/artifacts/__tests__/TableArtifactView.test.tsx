import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { agentApi } from "../../../../lib/api/agent";
import type { ResultViewArtifact, SqlArtifact } from "../../../../types/agentArtifact";
import { TableArtifactView } from "../TableArtifactView";

vi.mock("../../../../lib/api/agent", () => ({
  agentApi: {
    fetchArtifactPage: vi.fn(),
    exportArtifactCsv: vi.fn(),
  },
}));

const liveMetadata = {
  consistency: "live_reexecution" as const,
  originalExecutedAt: "2026-07-20T00:00:00Z",
  viewExecutedAt: "2026-07-20T00:00:01Z",
  viewExecutionId: "view-test",
  datasourceGeneration: 1,
  queryFingerprint: "query-test",
};

function makeArtifact(): ResultViewArtifact {
  return {
    id: "result-view-payload-1",
    type: "result_view",
    title: "查询结果",
    description: "订单按日聚合结果",
    sourceSqlArtifactId: "sql-artifact-payload-1",
    queryFingerprint: "query-payload-1",
    columns: ["day", "order_count", "note"],
    rowCount: 128,
    returnedRows: 12,
    latencyMs: 42,
    truncated: true,
  };
}

function makeSqlBackedArtifact(): ResultViewArtifact {
  return {
    id: "result-view-1",
    type: "result_view",
    title: "SQL-backed result",
    description: "Agent result view",
    sourceSqlArtifactId: "sql-artifact-1",
    queryFingerprint: "query-artifact-1",
    columns: ["day", "order_count"],
    rowCount: 128,
    returnedRows: 1,
    latencyMs: 42,
    truncated: false,
  };
}

function makeSourceSqlArtifact(): SqlArtifact {
  return {
    id: "sql-artifact-1",
    type: "sql",
    title: "来源 SQL",
    sql: "SELECT day, COUNT(*) AS order_count FROM orders GROUP BY day",
    dialect: "mysql",
    validationStatus: "passed",
    executionStatus: "completed",
  };
}

function makeTypedSqlBackedArtifact(): ResultViewArtifact {
  return {
    ...makeSqlBackedArtifact(),
    columns: [
      { name: "day", type: "date" },
      { name: "order_count", type: "integer" },
    ],
    queryFingerprint: "sql_test:typed",
  };
}

describe("TableArtifactView", () => {
  beforeEach(() => {
    cleanup();
    vi.mocked(agentApi.fetchArtifactPage).mockReset();
    vi.mocked(agentApi.exportArtifactCsv).mockReset();
    vi.mocked(agentApi.fetchArtifactPage).mockResolvedValue({
      columns: ["day", "order_count", "note"],
      rows: Array.from({ length: 10 }, (_, index) => ({
        day: `2026-06-${String(index + 1).padStart(2, "0")}`,
        order_count: (index + 1) * 10,
        note: index === 2 ? "row-3" : index === 4 ? null : `row-${index + 1}`,
      })),
      page: 1,
      pageSize: 10,
      rowCount: 128,
      hasNextPage: true,
      latencyMs: 38,
      ...liveMetadata,
      warnings: ["仅展示前 10 行"],
      notices: ["可继续筛选"],
    });
    vi.mocked(agentApi.exportArtifactCsv).mockResolvedValue(new Blob(["day,order_count\n2026-06-01,10\n"]));
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
    Object.assign(URL, {
      createObjectURL: vi.fn(() => "blob:csv"),
      revokeObjectURL: vi.fn(),
    });
  });

  it("loads a 10-row preview by artifact id and renders result metadata", async () => {
    render(<TableArtifactView artifact={makeArtifact()} onToast={vi.fn()} />);

    await screen.findByText("2026-06-10");
    expect(agentApi.fetchArtifactPage).toHaveBeenCalledWith(
      "result-view-payload-1",
      expect.objectContaining({ page: 1, pageSize: 10 }),
      expect.any(AbortSignal),
    );
    expect(screen.getByText("本页 10 / 共 128 行")).toBeTruthy();
    expect(screen.getByText("3 列")).toBeTruthy();
    expect(screen.getByText("38ms")).toBeTruthy();
    expect(screen.getByText("结果已截断")).toBeTruthy();
    expect(screen.getByText("仅展示前 10 行")).toBeTruthy();
    expect(screen.getByText("可继续筛选")).toBeTruthy();
    expect(screen.getByText(/分析取数/)).toBeTruthy();
    expect(screen.getByText(/当前重查/)).toBeTruthy();
    expect(screen.getByText("2026-06-10")).toBeTruthy();
    expect(screen.queryByText("2026-06-11")).toBeNull();
  });

  it("marks numeric cells and preserves SQL null as a distinct value", async () => {
    render(<TableArtifactView artifact={makeArtifact()} onToast={vi.fn()} />);

    await screen.findByText("2026-06-10");
    expect(screen.getByText("10").closest("td")?.className).toContain("is-numeric");
    const nullCell = screen.getByText("NULL").closest("td");
    expect(nullCell?.className).toContain("is-null");
    expect(nullCell?.querySelector(".dbfox-cell-null")).toBeTruthy();
  });

  it("switches one result artifact between its table and exact source SQL views", async () => {
    const onToast = vi.fn();
    const onOpenSqlConsole = vi.fn();
    render(
      <TableArtifactView
        artifact={makeSqlBackedArtifact()}
        sourceSqlArtifact={makeSourceSqlArtifact()}
        onOpenSqlConsole={onOpenSqlConsole}
        onToast={onToast}
      />,
    );

    await screen.findByText("2026-06-01");
    expect(screen.getByRole("tab", { name: "表格" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.queryByLabelText("SQL-backed result 来源 SQL")).toBeNull();

    fireEvent.mouseDown(screen.getByRole("tab", { name: "SQL" }), { button: 0, ctrlKey: false });

    const sql = screen.getByLabelText("SQL-backed result 来源 SQL");
    expect(sql.textContent).toContain("SELECT\n  day,\n  COUNT(*) AS order_count\nFROM\n  orders\nGROUP BY\n  day");
    expect(screen.queryByPlaceholderText("搜索结果")).toBeNull();
    expect(agentApi.fetchArtifactPage).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "复制 SQL" }));
    await waitFor(() => expect(onToast).toHaveBeenCalledWith("已复制 SQL"));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(makeSourceSqlArtifact().sql);
    fireEvent.click(screen.getByRole("button", { name: "在 SQL 控制台打开" }));
    expect(onOpenSqlConsole).toHaveBeenCalledWith(makeSourceSqlArtifact().sql);

    fireEvent.mouseDown(screen.getByRole("tab", { name: "表格" }), { button: 0, ctrlKey: false });
    expect(screen.getByPlaceholderText("搜索结果")).toBeTruthy();
  });

  it("does not offer a SQL view when the result source artifact is unavailable", async () => {
    render(<TableArtifactView artifact={makeSqlBackedArtifact()} onToast={vi.fn()} />);

    await screen.findByText("2026-06-01");
    expect(screen.queryByRole("tablist", { name: "查询结果显示方式" })).toBeNull();
    expect(screen.getByText("结果表")).toBeTruthy();
  });

  it("shows column type indicators for typed result columns", async () => {
    render(<TableArtifactView artifact={makeTypedSqlBackedArtifact()} onToast={vi.fn()} mode="workspace" />);

    await screen.findByText("2026-06-01");

    const dayHeader = screen.getByRole("columnheader", { name: /day date/ });
    const orderCountHeader = screen.getByRole("columnheader", { name: /order_count integer/ });
    expect(dayHeader.querySelector(".artifact-table-type-badge")?.textContent).toBe("date");
    expect(orderCountHeader.querySelector(".artifact-table-type-badge")?.textContent).toBe("integer");
  });

  it("keeps warnings and notices in the meta area", async () => {
    const { container } = render(<TableArtifactView artifact={makeArtifact()} onToast={vi.fn()} />);

    await screen.findByText("2026-06-10");
    const meta = container.querySelector(".artifact-table-meta");
    expect(meta?.textContent).toContain("仅展示前 10 行");
    expect(meta?.textContent).toContain("可继续筛选");
  });

  it("copies an individual cell value", async () => {
    const onToast = vi.fn();
    render(<TableArtifactView artifact={makeArtifact()} onToast={onToast} />);

    await screen.findByText("2026-06-10");
    const cell = screen.getByText("row-3").closest("td");
    if (!cell) throw new Error("Expected result cell");
    fireEvent.click(cell);
    fireEvent.keyDown(cell, { key: "c", ctrlKey: true });

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("row-3");
    await waitFor(() => expect(onToast).toHaveBeenCalledWith("已复制单元格"));
  });

  it("uses the shared long-cell viewer and copies through its explicit action", async () => {
    const longValue = "payload=" + "segment-".repeat(14);
    vi.mocked(agentApi.fetchArtifactPage).mockResolvedValueOnce({
      columns: ["note"], rows: [{ note: longValue }], page: 1, pageSize: 10,
      rowCount: 1, hasNextPage: false, latencyMs: 1, ...liveMetadata,
    });
    const artifact = {
      ...makeArtifact(),
      columns: ["note"],
      rowCount: 1,
      returnedRows: 1,
      warnings: [],
      notices: [],
      truncated: false,
    };

    render(<TableArtifactView artifact={artifact} onToast={vi.fn()} />);

    const trigger = (await screen.findByText(/payload=segment/)).closest(".dbfox-cell-preview-trigger");
    if (!trigger) throw new Error("Expected long-cell preview trigger");
    expect(trigger.className).toContain("dbfox-cell-preview-trigger");
    expect(screen.getByText("键值").className).toContain("dbfox-cell-preview-kind");

    fireEvent.click(trigger);
    fireEvent.click(await screen.findByRole("button", { name: "复制值" }));

    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith(longValue));
  });

  it("marks the clicked artifact table cell as selected", async () => {
    render(<TableArtifactView artifact={makeArtifact()} onToast={vi.fn()} />);

    const firstCell = (await screen.findByText("2026-06-01")).closest("td");
    const secondCell = screen.getByText("row-3").closest("td");
    if (!firstCell || !secondCell) throw new Error("Expected table cells to be rendered");

    fireEvent.click(firstCell);
    expect(firstCell.className).toContain("is-selected");
    expect(firstCell.getAttribute("aria-selected")).toBe("true");

    fireEvent.click(secondCell);
    expect(secondCell.className).toContain("is-selected");
    expect(firstCell.className).not.toContain("is-selected");
  });

  it("sends inline search to the artifact result endpoint", async () => {
    render(<TableArtifactView artifact={makeArtifact()} onToast={vi.fn()} />);

    await screen.findByText("2026-06-01");
    vi.mocked(agentApi.fetchArtifactPage).mockResolvedValueOnce({
      columns: ["day", "order_count", "note"],
      rows: [{ day: "2026-06-12", order_count: 120, note: "row-12" }],
      page: 1, pageSize: 10, rowCount: 1, hasNextPage: false,
      latencyMs: 1, ...liveMetadata,
    });
    fireEvent.change(screen.getByPlaceholderText("搜索结果"), { target: { value: "row-12" } });

    await waitFor(() => expect(agentApi.fetchArtifactPage).toHaveBeenLastCalledWith(
      "result-view-payload-1",
      expect.objectContaining({ search: "row-12" }),
      expect.any(AbortSignal),
    ));
    expect(await screen.findByText("2026-06-12")).toBeTruthy();
  });

  it("sends inline sorting to the artifact result endpoint", async () => {
    render(<TableArtifactView artifact={makeArtifact()} onToast={vi.fn()} />);

    await screen.findByText("2026-06-01");
    fireEvent.click(screen.getByRole("button", { name: "order_count" }));

    await waitFor(() => expect(agentApi.fetchArtifactPage).toHaveBeenLastCalledWith(
      "result-view-payload-1",
      expect.objectContaining({ sort: [{ column: "order_count", direction: "desc" }] }),
      expect.any(AbortSignal),
    ));
  });

  it("opens the loaded result as a workspace tab", () => {
    const artifact = makeArtifact();
    const onOpenResultTab = vi.fn();
    render(<TableArtifactView artifact={artifact} onToast={vi.fn()} onOpenResultTab={onOpenResultTab} />);

    fireEvent.click(screen.getByRole("button", { name: "打开为 Tab" }));

    expect(onOpenResultTab).toHaveBeenCalledWith(artifact);
  });

  it("exports sql-backed workspace results through the result export API", async () => {
    const artifact = makeSqlBackedArtifact();
    const onToast = vi.fn();

    render(<TableArtifactView artifact={artifact} onToast={onToast} mode="workspace" />);

    await screen.findByText("2026-06-01");
    fireEvent.change(screen.getByPlaceholderText("搜索 SQL 结果..."), { target: { value: "daily" } });
    fireEvent.click(screen.getByRole("button", { name: "order_count" }));

    await waitFor(() =>
      expect(agentApi.fetchArtifactPage).toHaveBeenLastCalledWith(
        "result-view-1",
        expect.objectContaining({
          search: "daily",
          sort: [{ column: "order_count", direction: "desc" }],
        }),
        expect.any(AbortSignal),
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: "导出" }));

    await waitFor(() =>
      expect(agentApi.exportArtifactCsv).toHaveBeenCalledWith("result-view-1", {
        search: "daily",
        sort: [{ column: "order_count", direction: "desc" }],
      }),
    );
    await waitFor(() => expect(onToast).toHaveBeenCalledWith("已导出 CSV"));
  });

  it("uses only the result artifact id for sql-backed pagination", async () => {
    render(<TableArtifactView artifact={makeSqlBackedArtifact()} onToast={vi.fn()} mode="workspace" />);

    await waitFor(() =>
      expect(agentApi.fetchArtifactPage).toHaveBeenCalledWith(
        "result-view-1",
        expect.objectContaining({
          page: 1,
          pageSize: 50,
        }),
        expect.any(AbortSignal),
      ),
    );
  });

  it("keeps the workspace result search inside the main toolbar group", async () => {
    const { container } = render(<TableArtifactView artifact={makeSqlBackedArtifact()} onToast={vi.fn()} mode="workspace" />);

    await screen.findByText("2026-06-01");
    const search = container.querySelector(".artifact-table-search-shell .artifact-table-search");
    if (!search) throw new Error("Result search input was not rendered");

    expect(container.querySelector(".artifact-table-toolbar-main")?.contains(search)).toBe(true);
    expect(container.querySelector(".hifi-toolbar-right .artifact-table-search")).toBeNull();
  });

  it("applies sql-backed toolbar filters through the result page API", async () => {
    render(<TableArtifactView artifact={makeSqlBackedArtifact()} onToast={vi.fn()} mode="workspace" />);

    await screen.findByText("2026-06-01");
    fireEvent.click(screen.getByRole("button", { name: "筛选" }));
    chooseSelectOption("筛选列", "day");
    chooseSelectOption("筛选条件", "包含");
    fireEvent.change(screen.getByLabelText("筛选值"), { target: { value: "2026-06" } });
    fireEvent.click(screen.getByRole("button", { name: "应用筛选" }));

    await waitFor(() =>
      expect(agentApi.fetchArtifactPage).toHaveBeenLastCalledWith(
        "result-view-1",
        expect.objectContaining({
          filters: [{ column: "day", operator: "contains", value: "2026-06" }],
        }),
        expect.any(AbortSignal),
      ),
    );
  });

  it("applies sql-backed toolbar sort through the result page API", async () => {
    render(<TableArtifactView artifact={makeSqlBackedArtifact()} onToast={vi.fn()} mode="workspace" />);

    await screen.findByText("2026-06-01");
    fireEvent.click(screen.getByRole("button", { name: "排序" }));
    chooseSelectOption("排序列", "order_count");
    chooseSelectOption("排序方向", "升序");
    fireEvent.click(screen.getByRole("button", { name: "应用排序" }));

    await waitFor(() =>
      expect(agentApi.fetchArtifactPage).toHaveBeenLastCalledWith(
        "result-view-1",
        expect.objectContaining({
          sort: [{ column: "order_count", direction: "asc" }],
        }),
        expect.any(AbortSignal),
      ),
    );
  });

  it("normalizes typed sql-backed columns before sorting and fetching", async () => {
    render(<TableArtifactView artifact={makeTypedSqlBackedArtifact()} onToast={vi.fn()} mode="workspace" />);

    await screen.findByText("2026-06-01");
    fireEvent.click(screen.getByRole("button", { name: "order_count" }));

    await waitFor(() =>
      expect(agentApi.fetchArtifactPage).toHaveBeenLastCalledWith(
        "result-view-1",
        expect.objectContaining({
          sort: [{ column: "order_count", direction: "desc" }],
        }),
        expect.any(AbortSignal),
      ),
    );
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
