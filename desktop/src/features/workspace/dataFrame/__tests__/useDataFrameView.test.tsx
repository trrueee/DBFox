import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../../lib/api/client";
import type { DataFramePageResponse } from "../dataFrameViewTypes";
import { useDataFrameView } from "../useDataFrameView";

const source = {
  kind: "artifact-representation" as const,
  artifactId: "result-artifact-1",
  representationType: "dbfox.dataframe.v1",
};

function pageResponse(rows: Array<Record<string, unknown>>, page: number): DataFramePageResponse {
  return {
    columns: ["id"],
    columnTypes: ["integer"],
    rows,
    page,
    pageSize: 20,
    hasNextPage: page < 3,
    latencyMs: 5,
    sourceTruncated: false,
    consistency: "live_reexecution",
    originalExecutedAt: "2026-07-20T00:00:00Z",
    viewExecutedAt: "2026-07-20T00:00:01Z",
    viewExecutionId: `view-${page}`,
    resourceVersion: 1,
    sourceFingerprint: "source-1",
    warnings: [],
    notices: [],
  };
}

describe("useDataFrameView", () => {
  it("keeps last stable data while loading the next page", async () => {
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce(pageResponse([{ id: "1" }], 1))
      .mockReturnValueOnce(new Promise(() => {}));
    const exportAll = vi.fn();

    const { result } = renderHook(() => useDataFrameView({ source, fetchPage, exportAll }));

    await waitFor(() => expect(result.current.rows).toEqual([["1"]]));

    act(() => result.current.setPage(2));

    await waitFor(() => expect(fetchPage).toHaveBeenCalledTimes(2));
    expect(result.current.rows).toEqual([["1"]]);
    expect(result.current.loadingMode).toBe("page");
  });

  it("preserves null, empty text, booleans, numbers, and objects without string sentinels", async () => {
    const typedSource = { ...source, columns: ["null_value", "empty_value", "label", "enabled", "count", "payload"] };
    const fetchPage = vi.fn().mockResolvedValue({
      ...pageResponse([], 1),
      columns: typedSource.columns,
      rows: [{
        null_value: null,
        empty_value: "",
        label: "NULL",
        enabled: false,
        count: 0,
        payload: { ok: true },
      }],
    });

    const { result } = renderHook(() => useDataFrameView({ source: typedSource, fetchPage, exportAll: vi.fn() }));

    await waitFor(() => expect(result.current.rows).toEqual([[
      null,
      "",
      "NULL",
      false,
      0,
      { ok: true },
    ]]));
  });

  it("does not let an older response overwrite a newer response", async () => {
    const resolvers: Array<(value: DataFramePageResponse) => void> = [];
    const fetchPage = vi.fn(() => new Promise<DataFramePageResponse>((resolve) => resolvers.push(resolve)));
    const exportAll = vi.fn();

    const { result } = renderHook(() => useDataFrameView({ source, fetchPage, exportAll }));

    await waitFor(() => expect(fetchPage).toHaveBeenCalledTimes(1));
    act(() => result.current.setPage(2));
    await waitFor(() => expect(fetchPage).toHaveBeenCalledTimes(2));
    act(() => result.current.setPage(3));
    await waitFor(() => expect(fetchPage).toHaveBeenCalledTimes(3));

    act(() => resolvers[2](pageResponse([{ id: "3" }], 3)));
    await waitFor(() => expect(result.current.rows).toEqual([["3"]]));

    act(() => resolvers[1](pageResponse([{ id: "2" }], 2)));
    await new Promise((resolve) => window.setTimeout(resolve, 0));

    expect(result.current.rows).toEqual([["3"]]);
    expect(result.current.page).toBe(3);
  });

  it("retains the structured API error instead of flattening raw provider text", async () => {
    const failure = new ApiError(
      "private provider failure",
      503,
      "RESULT_VIEW_UNAVAILABLE",
      [],
      { request_id: "result-request-9" },
    );
    const { result } = renderHook(() => useDataFrameView({
      source,
      fetchPage: vi.fn().mockRejectedValue(failure),
      exportAll: vi.fn(),
    }));

    await waitFor(() => expect(result.current.error).toBe(failure));
  });

  it("resets to page one when search, sort, or filters change", async () => {
    const fetchPage = vi.fn().mockResolvedValue(pageResponse([{ id: "1" }], 1));
    const exportAll = vi.fn();
    const { result } = renderHook(() => useDataFrameView({ source, fetchPage, exportAll }));

    await waitFor(() => expect(result.current.rows).toEqual([["1"]]));
    act(() => result.current.setPage(2));
    await waitFor(() => expect(result.current.page).toBe(2));

    act(() => result.current.setSearch("active"));
    expect(result.current.page).toBe(1);

    act(() => result.current.setSort([{ field: "id", direction: "desc" }]));
    expect(result.current.page).toBe(1);

    act(() => result.current.setFilters([{ field: "id", operator: "equals", value: "1" }]));
    expect(result.current.page).toBe(1);
  });

  it("exports all rows with the current search, filters, and sort", async () => {
    const fetchPage = vi.fn().mockResolvedValue(pageResponse([{ id: "1" }], 1));
    const exportAll = vi.fn().mockResolvedValue(new Blob(["id\n1\n"], { type: "text/csv" }));
    const { result } = renderHook(() => useDataFrameView({ source, fetchPage, exportAll }));

    await waitFor(() => expect(result.current.rows).toEqual([["1"]]));
    act(() => result.current.setSearch("active"));
    act(() => result.current.setSort([{ field: "id", direction: "desc" }]));
    act(() => result.current.setFilters([{ field: "id", operator: "equals", value: "1" }]));

    await result.current.exportAll();

    expect(exportAll).toHaveBeenCalledWith({
      source,
      sort: [{ field: "id", direction: "desc" }],
      filters: [{ field: "id", operator: "equals", value: "1" }],
      search: "active",
    });
  });
});

