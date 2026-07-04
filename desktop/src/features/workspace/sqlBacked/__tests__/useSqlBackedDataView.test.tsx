import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { SqlBackedPageResponse } from "../sqlBackedTypes";
import { useSqlBackedDataView } from "../useSqlBackedDataView";

const source = {
  kind: "artifact-result" as const,
  datasourceId: "ds-1",
  sourceSqlArtifactId: "sql-artifact-1",
  safeSql: "SELECT id FROM users",
  columns: ["id"],
};

function pageResponse(rows: Array<Record<string, unknown>>, page: number): SqlBackedPageResponse {
  return {
    columns: ["id"],
    rows,
    page,
    pageSize: 20,
    hasNextPage: page < 3,
    executedSql: `SELECT id FROM users LIMIT 20 OFFSET ${(page - 1) * 20}`,
    latencyMs: 5,
    warnings: [],
    notices: [],
  };
}

describe("useSqlBackedDataView", () => {
  it("keeps last stable data while loading the next page", async () => {
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce(pageResponse([{ id: "1" }], 1))
      .mockReturnValueOnce(new Promise(() => {}));
    const exportAll = vi.fn();

    const { result } = renderHook(() => useSqlBackedDataView({ source, fetchPage, exportAll }));

    await waitFor(() => expect(result.current.rows).toEqual([["1"]]));

    act(() => result.current.setPage(2));

    await waitFor(() => expect(fetchPage).toHaveBeenCalledTimes(2));
    expect(result.current.rows).toEqual([["1"]]);
    expect(result.current.loadingMode).toBe("page");
  });

  it("does not let an older response overwrite a newer response", async () => {
    const resolvers: Array<(value: SqlBackedPageResponse) => void> = [];
    const fetchPage = vi.fn(() => new Promise<SqlBackedPageResponse>((resolve) => resolvers.push(resolve)));
    const exportAll = vi.fn();

    const { result } = renderHook(() => useSqlBackedDataView({ source, fetchPage, exportAll }));

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

  it("resets to page one when search, sort, or filters change", async () => {
    const fetchPage = vi.fn().mockResolvedValue(pageResponse([{ id: "1" }], 1));
    const exportAll = vi.fn();
    const { result } = renderHook(() => useSqlBackedDataView({ source, fetchPage, exportAll }));

    await waitFor(() => expect(result.current.rows).toEqual([["1"]]));
    act(() => result.current.setPage(2));
    await waitFor(() => expect(result.current.page).toBe(2));

    act(() => result.current.setSearch("active"));
    expect(result.current.page).toBe(1);

    act(() => result.current.setSort([{ column: "id", direction: "desc" }]));
    expect(result.current.page).toBe(1);

    act(() => result.current.setFilters([{ column: "id", operator: "equals", value: "1" }]));
    expect(result.current.page).toBe(1);
  });

  it("exports all rows with the current search, filters, and sort", async () => {
    const fetchPage = vi.fn().mockResolvedValue(pageResponse([{ id: "1" }], 1));
    const exportAll = vi.fn().mockResolvedValue(new Blob(["id\n1\n"], { type: "text/csv" }));
    const { result } = renderHook(() => useSqlBackedDataView({ source, fetchPage, exportAll }));

    await waitFor(() => expect(result.current.rows).toEqual([["1"]]));
    act(() => result.current.setSearch("active"));
    act(() => result.current.setSort([{ column: "id", direction: "desc" }]));
    act(() => result.current.setFilters([{ column: "id", operator: "equals", value: "1" }]));

    await result.current.exportAll();

    expect(exportAll).toHaveBeenCalledWith({
      source,
      sort: [{ column: "id", direction: "desc" }],
      filters: [{ column: "id", operator: "equals", value: "1" }],
      search: "active",
    });
  });
});

