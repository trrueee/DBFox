import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { agentApi } from "../../../../lib/api/agent";
import type { ResultViewArtifact, TableArtifact } from "../../../../types/agentArtifact";
import { TableArtifactView } from "../TableArtifactView";

vi.mock("../../../../lib/api/agent", () => ({
  agentApi: {
    fetchResultPage: vi.fn(),
    exportResultCsv: vi.fn(),
  },
}));

function makeArtifact(): TableArtifact {
  return {
    id: "result-table-1",
    type: "table",
    title: "查询结果",
    description: "订单按日聚合结果",
    columns: ["day", "order_count", "note"],
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
    sql: "SELECT day, COUNT(*) AS order_count FROM orders GROUP BY day",
  };
}

function makeLargeArtifact(): TableArtifact {
  return {
    ...makeArtifact(),
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
        sourceSqlArtifactId: "sql-artifact-1",
        safeSql: "SELECT day, order_count FROM daily_orders",
        search: "daily",
        sort: [{ column: "order_count", direction: "desc" }],
      }),
    );
    await waitFor(() => expect(onToast).toHaveBeenCalledWith("已导出 CSV"));
  });
});
