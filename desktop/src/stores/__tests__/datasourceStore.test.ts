import { beforeEach, describe, expect, it, vi } from "vitest";
import { useDatasourceStore } from "../datasourceStore";

vi.mock("../../features/engine/engineApi", () => ({
  listTables: vi.fn().mockResolvedValue([]),
  listColumns: vi.fn().mockResolvedValue([]),
}));

vi.mock("../../lib/api/datasources", () => ({
  datasourcesApi: {
    listDatasources: vi.fn().mockResolvedValue([]),
    createDatasource: vi.fn(),
    updateDatasource: vi.fn(),
    deleteDatasource: vi.fn(),
    syncSchema: vi.fn(),
    checkDatasourceHealth: vi.fn(),
    releaseDatasource: vi.fn().mockResolvedValue(undefined),
  },
}));

const { datasourcesApi } = await import("../../lib/api/datasources");
const { listTables, listColumns } = await import("../../features/engine/engineApi");

const DS1 = { id: "ds-1", name: "Test DB", db_type: "mysql" as const, host: "localhost", port: 3306, database_name: "test", username: "root", is_read_only: false, env: "dev" };
const DS2 = { id: "ds-2", name: "Prod DB", db_type: "postgresql" as const, host: "prod.db", port: 5432, database_name: "prod", username: "admin", is_read_only: true, env: "prod" };

function resetAll() {
  vi.clearAllMocks();
  vi.mocked(datasourcesApi.listDatasources).mockResolvedValue([]);
  vi.mocked(listTables).mockResolvedValue([]);
  vi.mocked(listColumns).mockResolvedValue([]);
  useDatasourceStore.setState({
    datasources: [],
    activeDatasourceId: "",
    activeDatasourceForSettings: null,
    tables: [],
    loadingSchema: false,
    schemaError: "",
    tableColumns: {},
  });
}

describe("datasourceStore — loadDatasources", () => {
  beforeEach(resetAll);

  it("loads datasources and sets active to first one", async () => {
    vi.mocked(datasourcesApi.listDatasources).mockResolvedValue([DS1, DS2] as never);

    await useDatasourceStore.getState().loadDatasources();

    const s = useDatasourceStore.getState();
    expect(s.datasources).toHaveLength(2);
    expect(s.activeDatasourceId).toBe("ds-1");
    expect(s.loadingSchema).toBe(false);
  });

  it("preserves activeDatasourceId if still present in new list", async () => {
    useDatasourceStore.setState({ activeDatasourceId: "ds-2" });
    vi.mocked(datasourcesApi.listDatasources).mockResolvedValue([DS1, DS2] as never);

    await useDatasourceStore.getState().loadDatasources();

    expect(useDatasourceStore.getState().activeDatasourceId).toBe("ds-2");
  });

  it("sets schemaError on non-transient failure", async () => {
    vi.mocked(datasourcesApi.listDatasources).mockRejectedValue(new Error("auth failed"));

    await useDatasourceStore.getState().loadDatasources();

    expect(useDatasourceStore.getState().schemaError).toBe("auth failed");
    expect(useDatasourceStore.getState().datasources).toEqual([]);
  });
});

describe("datasourceStore — setActiveDatasourceId", () => {
  beforeEach(resetAll);

  it("sets activeDatasourceId and activeDatasourceForSettings", () => {
    useDatasourceStore.setState({ datasources: [DS1, DS2] as never });

    useDatasourceStore.getState().setActiveDatasourceId("ds-2");

    const s = useDatasourceStore.getState();
    expect(s.activeDatasourceId).toBe("ds-2");
    expect(s.activeDatasourceForSettings?.id).toBe("ds-2");
  });

  it("releases previous datasource pool on switch", () => {
    useDatasourceStore.setState({ datasources: [DS1, DS2] as never, activeDatasourceId: "ds-1" });

    useDatasourceStore.getState().setActiveDatasourceId("ds-2");

    expect(datasourcesApi.releaseDatasource).toHaveBeenCalledWith("ds-1");
  });
});

describe("datasourceStore — refreshSchema", () => {
  beforeEach(resetAll);

  it("fetches tables for active datasource", async () => {
    const mockTables = [{ id: "t1", table_name: "users", table_schema: "public", table_comment: "", table_type: "BASE TABLE", row_count_estimate: 100, engine_name: "mysql", created_at: "", updated_at: "" }];
    vi.mocked(listTables).mockResolvedValue(mockTables as never);
    useDatasourceStore.setState({ activeDatasourceId: "ds-1" });

    await useDatasourceStore.getState().refreshSchema();

    expect(useDatasourceStore.getState().tables).toEqual(mockTables);
    expect(listTables).toHaveBeenCalledWith("ds-1");
  });

  it("falls back to loadDatasources when no active id", async () => {
    vi.mocked(datasourcesApi.listDatasources).mockResolvedValue([DS1] as never);
    useDatasourceStore.setState({ activeDatasourceId: "" });

    await useDatasourceStore.getState().refreshSchema();

    expect(datasourcesApi.listDatasources).toHaveBeenCalled();
  });
});

describe("datasourceStore — CRUD operations", () => {
  beforeEach(resetAll);

  it("createDatasource calls API and reloads", async () => {
    vi.mocked(datasourcesApi.createDatasource).mockResolvedValue(DS1 as never);
    vi.mocked(datasourcesApi.listDatasources).mockResolvedValue([DS1] as never);

    const result = await useDatasourceStore.getState().createDatasource({} as never);

    expect(datasourcesApi.createDatasource).toHaveBeenCalled();
    expect(result.id).toBe("ds-1");
  });

  it("deleteDatasource reloads and clears active when confirmed", async () => {
    vi.mocked(datasourcesApi.deleteDatasource).mockResolvedValue(null);
    vi.mocked(datasourcesApi.listDatasources).mockResolvedValue([]);
    useDatasourceStore.setState({ activeDatasourceId: "ds-1", datasources: [DS1] as never });

    await useDatasourceStore.getState().deleteDatasource("ds-1");

    expect(useDatasourceStore.getState().activeDatasourceId).toBe("");
  });

  it("deleteDatasource does not clear active when confirmation required", async () => {
    vi.mocked(datasourcesApi.deleteDatasource).mockResolvedValue({
      requires_confirmation: true,
      confirm_token: "abc",
    });
    useDatasourceStore.setState({ activeDatasourceId: "ds-1" });

    await useDatasourceStore.getState().deleteDatasource("ds-1");

    expect(useDatasourceStore.getState().activeDatasourceId).toBe("ds-1");
    expect(datasourcesApi.listDatasources).not.toHaveBeenCalled();
  });
});
