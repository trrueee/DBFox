import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { agentApi } from "../../../../lib/api/agent";
import type { ResultViewArtifact } from "../../../../types/agentArtifact";
import { TableArtifactView } from "../TableArtifactView";

vi.mock("../../../../lib/api/agent", () => ({
  agentApi: {
    fetchResultPage: vi.fn(),
    exportResultCsv: vi.fn(),
  },
}));

function makeArtifact(): ResultViewArtifact {
  return {
    id: "result-view-payload-1",
    type: "result_view",
    title: "查询结果",
    description: "订单按日聚合结果",
    storageMode: "payload",
    datasourceId: "ds-1",
    sourceSqlSemanticId: "sql-artifact-payload-1",
    sourceSql: "SELECT day, COUNT(*) AS order_count FROM orders GROUP BY day",
    safeSql: "SELECT day, COUNT(*) AS order_count FROM orders GROUP BY day",
    columns: ["day", "order_count", "note"],
    previewRows: Array.from({ length: 10 }, (_, index) => [
      `2026-06-${String(index + 1).padStart(2, "0")}`,
      String((index + 1) * 10),
      index === 1 ? "NULL" : `row-${index + 1}`,
    ]),
    previewRowCount: 10,
    rows: Array.from({ length: 12 }, (_, index) => [
      `2026-06-${String(index + 1).padStart(2, "0")}`,
      String((index + 1) * 10),
      index === 1 ? "NULL" : `row-${index + 1}`,
    ]),
    rowCount: 128,
    returnedRows: 12,
    latencyMs: 42,
    truncated: true,
    warnings: ["仅展示前 10 行"],
    notices: ["可继续筛选"],
  };
}

function makeLargeArtifact(): ResultViewArtifact {
  return {
    ...makeArtifact(),
    previewRows: Array.from({ length: 10 }, (_, index) => [
      `2026-07-${String(index + 1).padStart(3, "0")}`,
      String(index + 1),
      `large-row-${index + 1}`,
    ]),
    previewRowCount: 10,
    rows: Array.from({ length: 620 }, (_, index) => [
      `2026-07-${String(index + 1).padStart(3, "0")}`,
      String(index + 1),
      `large-row-${index + 1}`,
    ]),
    rowCount: 620,
    returnedRows: 620,
    truncated: false,
    warnings: [],
  };
}

function makeSqlBackedArtifact(): ResultViewArtifact {
  return {
    id: "result-view-1",
    type: "result_view",
    title: "SQL-backed result",
    description: "Agent result view",
    storageMode: "sql_backed",
    datasourceId: "ds-1",
    sourceSqlSemanticId: "sql-artifact-1",
    sourceSql: "SELECT day, order_count FROM daily_orders",
    safeSql: "SELECT day, order_count FROM daily_orders",
    columns: ["day", "order_count"],
    previewRows: [["2026-06-01", "10"]],
    previewRowCount: 1,
    rowCount: 128,
    returnedRows: 1,
    latencyMs: 42,
    truncated: false,
  };
}

function makeLegacySqlBackedArtifact(): ResultViewArtifact {
  return {
    ...makeSqlBackedArtifact(),
    id: "result-view-legacy",
    sourceSqlSemanticId: "sql_candidate",
  };
}

function makeTypedSqlBackedArtifact(): ResultViewArtifact {
  return {
    ...makeSqlBackedArtifact(),
    columns: [
      { name: "day", type: "date" },
      { name: "order_count", type: "integer" },
    ],
    dialect: "sqlite",
    fingerprint: "sql_test:typed",
    sqlFingerprint: "sql_test:typed",
  };
}

describe("TableArtifactView", () => {
  beforeEach(() => {
    cleanup();
    vi.mocked(agentApi.fetchResultPage).mockReset();
    vi.mocked(agentApi.exportResultCsv).mockReset();
    vi.mocked(agentApi.fetchResultPage).mockResolvedValue({
      columns: ["day", "order_count"],
      rows: [{ day: "2026-06-01", order_count: 10 }],
      page: 1,
      pageSize: 50,
      rowCount: 128,
      hasNextPage: true,
      executedSql: "SELECT day, order_count FROM daily_orders LIMIT 50 OFFSET 0",
      latencyMs: 38,
      warnings: [],
      notices: [],
    });
    vi.mocked(agentApi.exportResultCsv).mockResolvedValue(new Blob(["day,order_count\n2026-06-01,10\n"]));
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

  it("renders result metadata, warnings, and a 10-row preview", () => {
    render(<TableArtifactView artifact={makeArtifact()} onToast={vi.fn()} />);

    expect(screen.getByText("预览 10 / 共 128 行")).toBeTruthy();
    expect(screen.getByText("3 列")).toBeTruthy();
    expect(screen.getByText("42ms")).toBeTruthy();
    expect(screen.getByText("结果已截断")).toBeTruthy();
    expect(screen.getByText("仅展示前 10 行")).toBeTruthy();
    expect(screen.getByText("可继续筛选")).toBeTruthy();
    expect(screen.getByText("NULL")).toBeTruthy();
    expect(screen.getByText("2026-06-10")).toBeTruthy();
    expect(screen.queryByText("2026-06-11")).toBeNull();
  });

  it("marks numeric and null cells with data-grid classes", () => {
    render(<TableArtifactView artifact={makeArtifact()} onToast={vi.fn()} />);

    expect(screen.getByText("10").closest("td")?.className).toContain("is-numeric");
    expect(screen.getByText("NULL").closest("td")?.className).toContain("is-null");
  });

  it("keeps warnings and notices in the meta area", () => {
    const { container } = render(<TableArtifactView artifact={makeArtifact()} onToast={vi.fn()} />);

    const meta = container.querySelector(".artifact-table-meta");
    expect(meta?.textContent).toContain("仅展示前 10 行");
    expect(meta?.textContent).toContain("可继续筛选");
  });

  it("copies an individual cell value", async () => {
    const onToast = vi.fn();
    render(<TableArtifactView artifact={makeArtifact()} onToast={onToast} />);

    fireEvent.click(screen.getByText("NULL"));

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("NULL");
    await waitFor(() => expect(onToast).toHaveBeenCalledWith("已复制单元格"));
  });

  it("searches across all loaded rows, not only the preview", () => {
    render(<TableArtifactView artifact={makeArtifact()} onToast={vi.fn()} />);

    fireEvent.change(screen.getByPlaceholderText("搜索结果"), { target: { value: "row-12" } });

    expect(screen.getByText("2026-06-12")).toBeTruthy();
    expect(screen.queryByText("2026-06-01")).toBeNull();
  });

  it("sorts by a clicked column header", () => {
    render(<TableArtifactView artifact={makeArtifact()} onToast={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "order_count" }));

    expect(screen.getByText("2026-06-12")).toBeTruthy();
    expect(screen.queryByText("2026-06-01")).toBeNull();
  });

  it("can reveal all loaded rows", () => {
    render(<TableArtifactView artifact={makeArtifact()} onToast={vi.fn()} />);

    fireEvent.click(screen.getByText("查看全部已载入 12 行"));

    expect(screen.getByText("2026-06-11")).toBeTruthy();
    expect(screen.getByText("收起预览")).toBeTruthy();
  });

  it("opens the loaded result as a workspace tab", () => {
    const artifact = makeArtifact();
    const onOpenResultTab = vi.fn();
    render(<TableArtifactView artifact={artifact} onToast={vi.fn()} onOpenResultTab={onOpenResultTab} />);

    fireEvent.click(screen.getByRole("button", { name: "打开为 Tab" }));

    expect(onOpenResultTab).toHaveBeenCalledWith(artifact);
  });

  it("uses a bounded render window for large loaded results", () => {
    render(<TableArtifactView artifact={makeLargeArtifact()} onToast={vi.fn()} />);

    fireEvent.click(screen.getByText("查看全部已载入 620 行"));

    expect(screen.getByText("窗口 1-200 / 620")).toBeTruthy();
    expect(screen.getByText("2026-07-200")).toBeTruthy();
    expect(screen.queryByText("2026-07-201")).toBeNull();
  });

  it("exports sql-backed workspace results through the result export API", async () => {
    const artifact = makeSqlBackedArtifact();
    const onToast = vi.fn();

    render(<TableArtifactView artifact={artifact} onToast={onToast} mode="workspace" />);

    await screen.findByText("2026-06-01");
    fireEvent.change(screen.getByPlaceholderText("搜索 SQL 结果..."), { target: { value: "daily" } });
    fireEvent.click(screen.getByRole("button", { name: "order_count" }));

    await waitFor(() =>
      expect(agentApi.fetchResultPage).toHaveBeenLastCalledWith(
        expect.objectContaining({
          search: "daily",
          sort: [{ column: "order_count", direction: "desc" }],
        }),
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: "导出" }));

    await waitFor(() =>
      expect(agentApi.exportResultCsv).toHaveBeenCalledWith({
        datasourceId: "ds-1",
        sourceSqlArtifactId: "result-view-1",
        safeSql: "SELECT day, order_count FROM daily_orders",
        search: "daily",
        sort: [{ column: "order_count", direction: "desc" }],
      }),
    );
    await waitFor(() => expect(onToast).toHaveBeenCalledWith("已导出 CSV"));
  });

  it("uses the result view artifact as source for sql-backed pagination", async () => {
    render(<TableArtifactView artifact={makeSqlBackedArtifact()} onToast={vi.fn()} mode="workspace" />);

    await waitFor(() =>
      expect(agentApi.fetchResultPage).toHaveBeenCalledWith(
        expect.objectContaining({
          sourceSqlArtifactId: "result-view-1",
          safeSql: "SELECT day, order_count FROM daily_orders",
        }),
      ),
    );
  });

  it("uses the result view artifact as source for legacy generic sql ids", async () => {
    render(<TableArtifactView artifact={makeLegacySqlBackedArtifact()} onToast={vi.fn()} mode="workspace" />);

    await waitFor(() =>
      expect(agentApi.fetchResultPage).toHaveBeenCalledWith(
        expect.objectContaining({
          sourceSqlArtifactId: "result-view-legacy",
          safeSql: "SELECT day, order_count FROM daily_orders",
        }),
      ),
    );
  });

  it("keeps the workspace result search inside the main toolbar group", async () => {
    const { container } = render(<TableArtifactView artifact={makeSqlBackedArtifact()} onToast={vi.fn()} mode="workspace" />);

    await screen.findByText("2026-06-01");
    const search = container.querySelector(".hifi-result-search-shell .hifi-result-search");
    if (!search) throw new Error("Result search input was not rendered");

    expect(container.querySelector(".hifi-result-toolbar-main")?.contains(search)).toBe(true);
    expect(container.querySelector(".hifi-toolbar-right .hifi-result-search")).toBeNull();
  });

  it("applies sql-backed toolbar filters through the result page API", async () => {
    render(<TableArtifactView artifact={makeSqlBackedArtifact()} onToast={vi.fn()} mode="workspace" />);

    await screen.findByText("2026-06-01");
    fireEvent.click(screen.getByRole("button", { name: "筛选" }));
    fireEvent.change(screen.getByLabelText("筛选列"), { target: { value: "day" } });
    fireEvent.change(screen.getByLabelText("筛选条件"), { target: { value: "contains" } });
    fireEvent.change(screen.getByLabelText("筛选值"), { target: { value: "2026-06" } });
    fireEvent.click(screen.getByRole("button", { name: "应用筛选" }));

    await waitFor(() =>
      expect(agentApi.fetchResultPage).toHaveBeenLastCalledWith(
        expect.objectContaining({
          filters: [{ column: "day", operator: "contains", value: "2026-06" }],
        }),
      ),
    );
  });

  it("applies sql-backed toolbar sort through the result page API", async () => {
    render(<TableArtifactView artifact={makeSqlBackedArtifact()} onToast={vi.fn()} mode="workspace" />);

    await screen.findByText("2026-06-01");
    fireEvent.click(screen.getByRole("button", { name: "排序" }));
    fireEvent.change(screen.getByLabelText("排序列"), { target: { value: "order_count" } });
    fireEvent.change(screen.getByLabelText("排序方向"), { target: { value: "asc" } });
    fireEvent.click(screen.getByRole("button", { name: "应用排序" }));

    await waitFor(() =>
      expect(agentApi.fetchResultPage).toHaveBeenLastCalledWith(
        expect.objectContaining({
          sort: [{ column: "order_count", direction: "asc" }],
        }),
      ),
    );
  });

  it("normalizes typed sql-backed columns before sorting and fetching", async () => {
    render(<TableArtifactView artifact={makeTypedSqlBackedArtifact()} onToast={vi.fn()} mode="workspace" />);

    await screen.findByText("2026-06-01");
    fireEvent.click(screen.getByRole("button", { name: "order_count" }));

    await waitFor(() =>
      expect(agentApi.fetchResultPage).toHaveBeenLastCalledWith(
        expect.objectContaining({
          sort: [{ column: "order_count", direction: "desc" }],
        }),
      ),
    );
  });
});
