import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { agentApi } from "../../../../lib/api/agent";
import type { ArtifactRepresentationResult } from "../../../../lib/api/generated/types.gen";
import { DATAFRAME_REPRESENTATION_TYPE } from "../../../../lib/api/representation";
import { ApiError } from "../../../../lib/api/client";
import { TableArtifactView } from "../TableArtifactView";

vi.mock("../../../../lib/api/agent", () => ({
  agentApi: {
    readArtifactRepresentation: vi.fn(),
    streamArtifactRepresentation: vi.fn(),
  },
}));

const liveMetadata = {
  consistency: "durable_snapshot" as const,
  originalExecutedAt: "2026-07-20T00:00:00Z",
  viewExecutedAt: "2026-07-20T00:00:01Z",
  viewExecutionId: "view-test",
  resourceVersion: 1,
  sourceFingerprint: "query-test",
};

type LegacyPage = typeof liveMetadata & {
  columns: string[];
  rows: Array<Record<string, unknown>>;
  page: number;
  pageSize: number;
  rowCount: number | null;
  hasNextPage: boolean;
  latencyMs: number;
  columnTypes?: string[];
  sourceTruncated?: boolean;
  warnings?: string[];
  notices?: string[];
};

function dataframeResult(value: LegacyPage): ArtifactRepresentationResult {
  return {
    representation_type: DATAFRAME_REPRESENTATION_TYPE,
    representation_version: 1,
    operation: "page",
    payload: {
      fields: value.columns.map((name, index) => ({
        key: `field_${index}`,
        name,
        type: value.columnTypes?.[index] ?? "string",
        nullable: true,
        semantic_type: null,
        unit: null,
        values: value.rows.map((row) => row[name] ?? null),
      })),
      page: value.page,
      page_size: value.pageSize,
      row_count: value.rowCount,
      has_next_page: value.hasNextPage,
      latency_ms: value.latencyMs,
      source_truncated: value.sourceTruncated ?? false,
    },
    consistency: value.consistency,
    original_observed_at: value.originalExecutedAt,
    read_at: value.viewExecutedAt,
    read_id: value.viewExecutionId,
    source_version: String(value.resourceVersion),
    source_fingerprint: value.sourceFingerprint,
    warnings: value.warnings ?? [],
    notices: value.notices ?? [],
  };
}

function makeArtifact() {
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

function makeSqlBackedArtifact() {
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

function makeTypedSqlBackedArtifact() {
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
    vi.mocked(agentApi.readArtifactRepresentation).mockReset();
    vi.mocked(agentApi.streamArtifactRepresentation).mockReset();
    vi.mocked(agentApi.readArtifactRepresentation).mockResolvedValue(dataframeResult({
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
      columnTypes: ["date", "integer", "string"],
      sourceTruncated: true,
      ...liveMetadata,
      warnings: ["仅展示前 10 行"],
      notices: ["可继续筛选"],
    }));
    vi.mocked(agentApi.streamArtifactRepresentation).mockResolvedValue(new Blob(["day,order_count\n2026-06-01,10\n"]));
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
    expect(agentApi.readArtifactRepresentation).toHaveBeenCalledWith(
      "result-view-payload-1",
      DATAFRAME_REPRESENTATION_TYPE,
      expect.objectContaining({ parameters: expect.objectContaining({ page: 1, page_size: 10 }) }),
      expect.any(AbortSignal),
    );
    expect(screen.getByText("本页 10 / 共 128 行")).toBeTruthy();
    expect(screen.getByText("3 列")).toBeTruthy();
    expect(screen.getByText("38ms")).toBeTruthy();
    expect(screen.getByText("结果已截断")).toBeTruthy();
    expect(screen.getByText("仅展示前 10 行")).toBeTruthy();
    expect(screen.getByText("可继续筛选")).toBeTruthy();
    expect(screen.getByText("耐久快照")).toBeTruthy();
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
    vi.mocked(agentApi.readArtifactRepresentation).mockResolvedValueOnce(dataframeResult({
      columns: ["note"], rows: [{ note: longValue }], page: 1, pageSize: 10,
      rowCount: 1, hasNextPage: false, latencyMs: 1, ...liveMetadata,
    }));
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
    vi.mocked(agentApi.readArtifactRepresentation).mockResolvedValueOnce(dataframeResult({
      columns: ["day", "order_count", "note"],
      rows: [{ day: "2026-06-12", order_count: 120, note: "row-12" }],
      page: 1, pageSize: 10, rowCount: 1, hasNextPage: false,
      latencyMs: 1, ...liveMetadata,
    }));
    fireEvent.change(screen.getByPlaceholderText("搜索结果"), { target: { value: "row-12" } });

    await waitFor(() => expect(agentApi.readArtifactRepresentation).toHaveBeenLastCalledWith(
      "result-view-payload-1",
      DATAFRAME_REPRESENTATION_TYPE,
      expect.objectContaining({ parameters: expect.objectContaining({ search: "row-12" }) }),
      expect.any(AbortSignal),
    ));
    expect(await screen.findByText("2026-06-12")).toBeTruthy();
  });

  it("sends inline sorting to the artifact result endpoint", async () => {
    render(<TableArtifactView artifact={makeArtifact()} onToast={vi.fn()} />);

    await screen.findByText("2026-06-01");
    fireEvent.click(screen.getByRole("button", { name: "order_count" }));

    await waitFor(() => expect(agentApi.readArtifactRepresentation).toHaveBeenLastCalledWith(
      "result-view-payload-1",
      DATAFRAME_REPRESENTATION_TYPE,
      expect.objectContaining({ parameters: expect.objectContaining({ sort: [{ field: "order_count", direction: "desc" }] }) }),
      expect.any(AbortSignal),
    ));
    expect(screen.getByRole("columnheader", { name: /order_count integer/ }).getAttribute("aria-sort")).toBe("descending");
  });

  it("preserves old table content and discloses safe Problem Details metadata after a page failure", async () => {
    vi.mocked(agentApi.readArtifactRepresentation)
      .mockResolvedValueOnce(dataframeResult({
        columns: ["day"],
        rows: [{ day: "2026-06-01" }],
        page: 1,
        pageSize: 10,
        rowCount: 2,
        hasNextPage: true,
        latencyMs: 4,
        ...liveMetadata,
      }))
      .mockRejectedValueOnce(new ApiError(
        "private database message",
        503,
        "RESULT_VIEW_UNAVAILABLE",
        [],
        { request_id: "result-request-3", password: "must-not-render" },
      ));

    render(
      <TableArtifactView
        artifact={makeArtifact()}
        onToast={vi.fn()}
        mode="workspace"
      />,
    );
    expect(await screen.findByText("2026-06-01")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "下一页" }));

    expect(await screen.findByText("分页数据未更新")).toBeTruthy();
    expect(screen.getByText("2026-06-01")).toBeTruthy();
    fireEvent.click(screen.getByText("技术详情"));
    expect(screen.getByText("RESULT_VIEW_UNAVAILABLE")).toBeTruthy();
    expect(screen.getByText("result-request-3")).toBeTruthy();
    expect(document.body.textContent).not.toContain("private database message");
    expect(document.body.textContent).not.toContain("must-not-render");
  });

  it("exposes the TanStack table as a counted keyboard grid", async () => {
    render(<TableArtifactView artifact={makeArtifact()} onToast={vi.fn()} />);

    await screen.findByText("2026-06-10");
    const grid = screen.getByRole("grid", { name: "查询结果" });
    expect(grid.getAttribute("aria-colcount")).toBe("3");
    expect(grid.getAttribute("aria-rowcount")).toBe("11");

    const firstCell = screen.getByText("2026-06-01").closest("td");
    if (!firstCell) throw new Error("Expected first result cell");
    firstCell.focus();
    fireEvent.keyDown(firstCell, { key: "ArrowRight" });
    expect(document.activeElement).toBe(screen.getByText("10").closest("td"));
  });

  it("opens the loaded result as a workspace tab", () => {
    const artifact = makeArtifact();
    const onOpenArtifact = vi.fn();
    render(<TableArtifactView artifact={artifact} onToast={vi.fn()} onOpenArtifact={onOpenArtifact} />);

    fireEvent.click(screen.getByRole("button", { name: "打开为 Tab" }));

    expect(onOpenArtifact).toHaveBeenCalledWith(artifact);
  });

  it("exports sql-backed workspace results through the result export API", async () => {
    const artifact = makeSqlBackedArtifact();
    const onToast = vi.fn();

    render(<TableArtifactView artifact={artifact} onToast={onToast} mode="workspace" />);

    await screen.findByText("2026-06-01");
    fireEvent.change(screen.getByPlaceholderText("搜索 SQL 结果..."), { target: { value: "daily" } });
    fireEvent.click(screen.getByRole("button", { name: "order_count" }));

    await waitFor(() =>
      expect(agentApi.readArtifactRepresentation).toHaveBeenLastCalledWith(
        "result-view-1",
        DATAFRAME_REPRESENTATION_TYPE,
        expect.objectContaining({ parameters: expect.objectContaining({
          search: "daily",
          sort: [{ field: "order_count", direction: "desc" }],
        })
        }),
        expect.any(AbortSignal),
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: "导出" }));

    await waitFor(() =>
      expect(agentApi.streamArtifactRepresentation).toHaveBeenCalledWith(
        "result-view-1",
        DATAFRAME_REPRESENTATION_TYPE,
        expect.objectContaining({ parameters: expect.objectContaining({
          search: "daily",
          sort: [{ field: "order_count", direction: "desc" }],
        }) }),
      ),
    );
    await waitFor(() => expect(onToast).toHaveBeenCalledWith("已导出 CSV"));
  });

  it("uses only the result artifact id for sql-backed pagination", async () => {
    render(<TableArtifactView artifact={makeSqlBackedArtifact()} onToast={vi.fn()} mode="workspace" />);

    await waitFor(() =>
      expect(agentApi.readArtifactRepresentation).toHaveBeenCalledWith(
        "result-view-1",
        DATAFRAME_REPRESENTATION_TYPE,
        expect.objectContaining({ parameters: expect.objectContaining({
          page: 1,
          page_size: 50,
        }) }),
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
      expect(agentApi.readArtifactRepresentation).toHaveBeenLastCalledWith(
        "result-view-1",
        DATAFRAME_REPRESENTATION_TYPE,
        expect.objectContaining({ parameters: expect.objectContaining({
          filters: [{ field: "day", operator: "contains", value: "2026-06" }],
        }) }),
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
      expect(agentApi.readArtifactRepresentation).toHaveBeenLastCalledWith(
        "result-view-1",
        DATAFRAME_REPRESENTATION_TYPE,
        expect.objectContaining({ parameters: expect.objectContaining({
          sort: [{ field: "order_count", direction: "asc" }],
        }) }),
        expect.any(AbortSignal),
      ),
    );
  });

  it("normalizes typed sql-backed columns before sorting and fetching", async () => {
    render(<TableArtifactView artifact={makeTypedSqlBackedArtifact()} onToast={vi.fn()} mode="workspace" />);

    await screen.findByText("2026-06-01");
    fireEvent.click(screen.getByRole("button", { name: "order_count" }));

    await waitFor(() =>
      expect(agentApi.readArtifactRepresentation).toHaveBeenLastCalledWith(
        "result-view-1",
        DATAFRAME_REPRESENTATION_TYPE,
        expect.objectContaining({ parameters: expect.objectContaining({
          sort: [{ field: "order_count", direction: "desc" }],
        }) }),
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
