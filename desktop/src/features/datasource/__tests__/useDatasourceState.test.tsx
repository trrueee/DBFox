import type { PropsWithChildren } from "react";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { datasourcesApi } from "../../../lib/api/datasources";
import { schemaApi } from "../../../lib/api/schema";
import type { DataSource } from "../../../lib/api/types";
import { useDatasourceSelectionStore } from "../../../stores/datasourceSelectionStore";
import { useDatasourceState } from "../useDatasourceState";

vi.mock("../../../lib/api/schema", () => ({
  schemaApi: {
    listTables: vi.fn(),
  },
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
  env: "dev",
  host: "127.0.0.1",
  port: 3306,
  database_name: "demo",
  username: "admin",
  connection_mode: "direct",
  is_read_only: false,
  status: "active",
  created_at: "2026-01-01T00:00:00Z",
  connection_generation: 1,
};

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

describe("useDatasourceState", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    useDatasourceSelectionStore.setState({ activeDatasourceId: "" });
    vi.mocked(datasourcesApi.listDatasources).mockResolvedValue([datasource]);
    vi.mocked(datasourcesApi.releaseDatasource).mockResolvedValue({ message: "released" });
    vi.mocked(schemaApi.listTables).mockResolvedValue([]);
  });

  it("loads datasources, selects a valid default, and loads its schema", async () => {
    const { result } = renderHook(() => useDatasourceState(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.activeDatasource?.id).toBe("ds-1"));
    await waitFor(() => expect(schemaApi.listTables).toHaveBeenCalledWith("ds-1"));

    expect(result.current.datasources).toEqual([datasource]);
    expect(result.current.schemaError).toBe("");
  });

  it("releases the previous datasource when the active selection changes", async () => {
    const second = { ...datasource, id: "ds-2", name: "Analytics" };
    vi.mocked(datasourcesApi.listDatasources).mockResolvedValue([datasource, second]);
    const { result } = renderHook(() => useDatasourceState(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.activeDatasourceId).toBe("ds-1"));

    act(() => result.current.setActiveDatasourceId("ds-2"));

    expect(datasourcesApi.releaseDatasource).toHaveBeenCalledWith("ds-1");
    await waitFor(() => expect(result.current.activeDatasourceId).toBe("ds-2"));
  });

  it("invalidates the datasource list and schema after synchronization", async () => {
    vi.mocked(datasourcesApi.syncSchema).mockResolvedValue({
      ok: true,
      message: "synced",
      tablesSynced: 0,
      tablesDropped: 0,
      columnsCreated: 0,
      columnsUpdated: 0,
      columnsRemoved: 0,
      aiEnrich: null,
    });
    const { result } = renderHook(() => useDatasourceState(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.activeDatasourceId).toBe("ds-1"));
    await waitFor(() => expect(schemaApi.listTables).toHaveBeenCalledTimes(1));
    const datasourceCallsBeforeSync = vi.mocked(datasourcesApi.listDatasources).mock.calls.length;
    const tableCallsBeforeSync = vi.mocked(schemaApi.listTables).mock.calls.length;

    await act(() => result.current.syncSchema("ds-1"));

    await waitFor(() =>
      expect(vi.mocked(datasourcesApi.listDatasources).mock.calls.length)
        .toBeGreaterThan(datasourceCallsBeforeSync),
    );
    await waitFor(() =>
      expect(vi.mocked(schemaApi.listTables).mock.calls.length)
        .toBeGreaterThan(tableCallsBeforeSync),
    );
  });
});
