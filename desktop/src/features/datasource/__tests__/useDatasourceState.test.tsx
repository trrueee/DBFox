import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useDatasourceState } from "../useDatasourceState";
import { listDatasources, listTables } from "../../engine/engineApi";
import type { EngineDataSource } from "../../engine/engineApi";

vi.mock("../../engine/engineApi", () => ({
  listDatasources: vi.fn(),
  listTables: vi.fn(),
  listColumns: vi.fn(),
}));

const datasource: EngineDataSource = {
  id: "ds-1",
  name: "Local MySQL",
  db_type: "mysql",
  host: "127.0.0.1",
  port: 3306,
  database_name: "demo",
  status: "active",
};

describe("useDatasourceState", () => {
  beforeEach(() => {
    vi.useRealTimers();
    vi.mocked(listDatasources).mockReset();
    vi.mocked(listTables).mockReset();
    vi.mocked(listTables).mockResolvedValue([]);
  });

  it("retries an initial transient engine fetch failure", async () => {
    vi.useFakeTimers();
    vi.mocked(listDatasources)
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce([datasource]);

    const { result } = renderHook(() => useDatasourceState({ onToast: vi.fn() }));

    await act(async () => {
      await Promise.resolve();
    });
    expect(vi.mocked(listDatasources)).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });

    expect(vi.mocked(listDatasources)).toHaveBeenCalledTimes(2);
    expect(result.current.datasources).toEqual([datasource]);
    expect(result.current.schemaError).toBe("");
  });

  it("reloads datasources when refreshing without an active datasource", async () => {
    vi.mocked(listDatasources)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([datasource]);
    const onToast = vi.fn();

    const { result } = renderHook(() => useDatasourceState({ onToast }));

    await waitFor(() => expect(vi.mocked(listDatasources)).toHaveBeenCalledTimes(1));

    await act(async () => {
      await result.current.refreshSchema();
    });

    expect(vi.mocked(listDatasources)).toHaveBeenCalledTimes(2);
    expect(result.current.datasources).toEqual([datasource]);
    expect(onToast).not.toHaveBeenCalledWith(expect.stringContaining("没有活动数据源"));
  });
});
