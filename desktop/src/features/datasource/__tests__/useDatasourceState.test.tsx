import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useDatasourceState } from "../useDatasourceState";
import { listTables } from "../../engine/engineApi";
import { datasourcesApi } from "../../../lib/api/datasources";
import type { DataSource } from "../../../lib/api/types";

vi.mock("../../engine/engineApi", () => ({
  listTables: vi.fn(),
  listColumns: vi.fn(),
}));

vi.mock("../../../lib/api/datasources", () => ({
  datasourcesApi: {
    listDatasources: vi.fn(),
  },
}));

const datasource: DataSource = {
  id: "ds-1",
  name: "Local MySQL",
  db_type: "mysql",
  host: "127.0.0.1",
  port: 3306,
  database_name: "demo",
  username: "admin",
  connection_mode: "direct",
  is_read_only: false,
  status: "active",
  created_at: "2026-01-01T00:00:00Z",
};

describe("useDatasourceState", () => {
  beforeEach(() => {
    vi.useRealTimers();
    vi.mocked(datasourcesApi.listDatasources).mockReset();
    vi.mocked(listTables).mockReset();
    vi.mocked(listTables).mockResolvedValue([]);
  });

  it("retries an initial transient engine fetch failure", async () => {
    vi.useFakeTimers();
    vi.mocked(datasourcesApi.listDatasources)
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce([datasource]);

    const { result } = renderHook(() => useDatasourceState({ onToast: vi.fn() }));

    await act(async () => {
      await Promise.resolve();
    });
    expect(vi.mocked(datasourcesApi.listDatasources)).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });

    expect(vi.mocked(datasourcesApi.listDatasources)).toHaveBeenCalledTimes(2);
    expect(result.current.datasources).toEqual([datasource]);
    expect(result.current.schemaError).toBe("");
  });

  it("reloads datasources when refreshing without an active datasource", async () => {
    vi.mocked(datasourcesApi.listDatasources)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([datasource]);
    const onToast = vi.fn();

    const { result } = renderHook(() => useDatasourceState({ onToast }));

    await waitFor(() => expect(vi.mocked(datasourcesApi.listDatasources)).toHaveBeenCalledTimes(1));

    await act(async () => {
      await result.current.refreshSchema();
    });

    expect(vi.mocked(datasourcesApi.listDatasources)).toHaveBeenCalledTimes(2);
    expect(result.current.datasources).toEqual([datasource]);
    expect(onToast).not.toHaveBeenCalledWith(expect.stringContaining("没有活动数据源"));
  });
});
