import { act } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useDatasourceStore } from "../../../stores/datasourceStore";
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
    releaseDatasource: vi.fn(),
    createDatasource: vi.fn(),
    updateDatasource: vi.fn(),
    deleteDatasource: vi.fn(),
    syncSchema: vi.fn(),
    checkDatasourceHealth: vi.fn(),
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

describe("datasourceStore", () => {
  beforeEach(() => {
    vi.useRealTimers();
    vi.mocked(datasourcesApi.listDatasources).mockReset();
    vi.mocked(listTables).mockReset();
    vi.mocked(listTables).mockResolvedValue([]);
    useDatasourceStore.setState({
      datasources: [],
      activeDatasourceId: "",
      activeDatasourceForSettings: null,
      tables: [],
      loadingSchema: false,
      schemaError: "",
      tableColumns: {},
    });
  });

  it("retries an initial transient engine fetch failure", async () => {
    vi.useFakeTimers();
    vi.mocked(datasourcesApi.listDatasources)
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce([datasource]);

    const promise = useDatasourceStore.getState().loadDatasources();

    await act(async () => {
      await Promise.resolve();
    });
    expect(vi.mocked(datasourcesApi.listDatasources)).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });

    await promise;
    const state = useDatasourceStore.getState();
    expect(vi.mocked(datasourcesApi.listDatasources)).toHaveBeenCalledTimes(2);
    expect(state.datasources).toEqual([datasource]);
    expect(state.schemaError).toBe("");
  });

  it("reloads datasources when refreshing without an active datasource", async () => {
    vi.mocked(datasourcesApi.listDatasources)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([datasource]);

    await act(async () => {
      await useDatasourceStore.getState().loadDatasources();
    });

    expect(vi.mocked(datasourcesApi.listDatasources)).toHaveBeenCalledTimes(1);

    await act(async () => {
      await useDatasourceStore.getState().refreshSchema();
    });

    // refreshSchema calls loadDatasources when no active datasource
    expect(vi.mocked(datasourcesApi.listDatasources)).toHaveBeenCalledTimes(2);
    expect(useDatasourceStore.getState().datasources).toEqual([datasource]);
  });
});
