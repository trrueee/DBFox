import { beforeEach, describe, expect, it, vi } from "vitest";
import { useDatasourceStore } from "../datasourceStore";
import type { EngineColumn, EngineSchemaTable } from "../../lib/api/schema";

vi.mock("../../lib/api/schema", () => ({
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
const { listTables, listColumns } = await import("../../lib/api/schema");

const DS1 = { id: "ds-1", name: "Test DB", db_type: "mysql" as const, host: "localhost", port: 3306, database_name: "test", username: "root", connection_generation: 1, is_read_only: false, env: "dev" };
const DS2 = { id: "ds-2", name: "Prod DB", db_type: "postgresql" as const, host: "prod.db", port: 5432, database_name: "prod", username: "admin", connection_generation: 1, is_read_only: true, env: "prod" };

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

  it("clears and reloads schema when the active datasource generation changes", async () => {
    const nextTables = [{ id: "table-new", table_name: "new_orders", table_comment: "" }];
    let resolveTables!: (tables: typeof nextTables) => void;
    useDatasourceStore.setState({
      datasources: [DS1] as never,
      activeDatasourceId: DS1.id,
      tables: [{ id: "table-old", table_name: "old_orders", table_comment: "" }],
      tableColumns: { "table-old": [] },
    });
    vi.mocked(listTables).mockImplementation(
      () => new Promise((resolve) => { resolveTables = resolve as typeof resolveTables; }),
    );
    vi.mocked(datasourcesApi.listDatasources).mockResolvedValue([
      { ...DS1, host: "new-host", connection_generation: 2 },
    ] as never);

    await useDatasourceStore.getState().loadDatasources();

    expect(useDatasourceStore.getState().tables).toEqual([]);
    expect(useDatasourceStore.getState().tableColumns).toEqual({});
    resolveTables(nextTables);
    await vi.waitFor(() => expect(useDatasourceStore.getState().tables).toEqual(nextTables));
    expect(listTables).toHaveBeenCalledWith(DS1.id);
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

describe("datasourceStore — schema column loading", () => {
  beforeEach(resetAll);

  it("does not fetch every table's columns just because the table list changed", async () => {
    const tables: EngineSchemaTable[] = [
      { id: "table-1", table_name: "users", table_comment: "" },
      { id: "table-2", table_name: "orders", table_comment: "" },
    ];

    useDatasourceStore.setState({ tables });

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(listColumns).not.toHaveBeenCalled();
    expect(useDatasourceStore.getState().tableColumns).toEqual({});
  });

  it("loads a single table's columns on demand and caches them by table id", async () => {
    const tables: EngineSchemaTable[] = [
      { id: "table-users", table_name: "users", table_comment: "" },
      { id: "table-orders", table_name: "orders", table_comment: "" },
    ];
    const columns: EngineColumn[] = [
      {
        id: "col-users-id",
        column_name: "id",
        data_type: "INTEGER",
        column_type: "INTEGER",
        is_nullable: false,
        column_default: "",
        column_comment: "",
        is_primary_key: true,
        is_foreign_key: false,
      },
    ];
    vi.mocked(listColumns).mockResolvedValue(columns);
    useDatasourceStore.setState({ tables });

    const result = await useDatasourceStore.getState().loadTableColumns("table-users");

    expect(result).toEqual(columns);
    expect(listColumns).toHaveBeenCalledWith("table-users");
    expect(useDatasourceStore.getState().tableColumns).toEqual({ "table-users": columns });
  });

  it("does not reuse cached columns for duplicate table names in different schemas", async () => {
    const tables: EngineSchemaTable[] = [
      { id: "table-public-users", table_schema: "public", table_name: "users", table_comment: "" },
      { id: "table-audit-users", table_schema: "audit", table_name: "users", table_comment: "" },
    ];
    const publicColumns: EngineColumn[] = [
      {
        id: "col-public-id",
        column_name: "id",
        data_type: "INTEGER",
        column_type: "INTEGER",
        is_nullable: false,
        column_default: "",
        column_comment: "",
        is_primary_key: true,
        is_foreign_key: false,
      },
    ];
    const auditColumns: EngineColumn[] = [
      {
        id: "col-audit-event-id",
        column_name: "event_id",
        data_type: "INTEGER",
        column_type: "INTEGER",
        is_nullable: false,
        column_default: "",
        column_comment: "",
        is_primary_key: true,
        is_foreign_key: false,
      },
    ];
    vi.mocked(listColumns).mockImplementation((tableId: string) =>
      Promise.resolve(tableId === "table-public-users" ? publicColumns : auditColumns),
    );
    useDatasourceStore.setState({ tables });

    const firstResult = await useDatasourceStore.getState().loadTableColumns("table-public-users");
    const secondResult = await useDatasourceStore.getState().loadTableColumns("table-audit-users");

    expect(firstResult).toEqual(publicColumns);
    expect(secondResult).toEqual(auditColumns);
    expect(listColumns).toHaveBeenCalledTimes(2);
    expect(useDatasourceStore.getState().tableColumns).toEqual({
      "table-public-users": publicColumns,
      "table-audit-users": auditColumns,
    });
  });

  it("keeps concurrency limited for explicit batch column loads", async () => {
    const tables: EngineSchemaTable[] = Array.from({ length: 10 }, (_, index) => ({
      id: `table-${index}`,
      table_name: `table_${index}`,
      table_comment: "",
    }));
    let activeRequests = 0;
    let maxActiveRequests = 0;
    const pending: Array<() => void> = [];

    vi.mocked(listColumns).mockImplementation(
      (tableId: string) =>
        new Promise<EngineColumn[]>((resolve) => {
          activeRequests += 1;
          maxActiveRequests = Math.max(maxActiveRequests, activeRequests);
          pending.push(() => {
            activeRequests -= 1;
            resolve([
              {
                id: `${tableId}-column`,
                column_name: "id",
                data_type: "INTEGER",
                column_type: "INTEGER",
                is_nullable: false,
                column_default: "",
                column_comment: "",
                is_primary_key: true,
                is_foreign_key: false,
              },
            ]);
          });
        }),
    );

    useDatasourceStore.setState({ tables });
    const loadPromise = useDatasourceStore.getState().loadColumnsForTables(tables.map((table) => table.id));

    await vi.waitFor(() => expect(listColumns).toHaveBeenCalledTimes(4));
    expect(maxActiveRequests).toBeLessThanOrEqual(4);

    while (pending.length > 0) {
      pending.shift()?.();
      await vi.waitFor(() => expect(activeRequests).toBeLessThanOrEqual(4));
    }

    await loadPromise;

    expect(Object.keys(useDatasourceStore.getState().tableColumns)).toHaveLength(10);
    expect(listColumns).toHaveBeenCalledTimes(10);
    expect(maxActiveRequests).toBeLessThanOrEqual(4);
  });

  it("does not cache a failed batch column load as an empty schema", async () => {
    const tables: EngineSchemaTable[] = [
      { id: "table-retry", table_name: "retry_me", table_comment: "" },
    ];
    const columns: EngineColumn[] = [
      {
        id: "column-retry",
        column_name: "id",
        data_type: "INTEGER",
        column_type: "INTEGER",
        is_nullable: false,
        column_default: "",
        column_comment: "",
        is_primary_key: true,
        is_foreign_key: false,
      },
    ];
    useDatasourceStore.setState({
      datasources: [DS1] as never,
      activeDatasourceId: DS1.id,
    });
    await vi.waitFor(() => expect(useDatasourceStore.getState().loadingSchema).toBe(false));
    useDatasourceStore.setState({ tables });
    vi.mocked(listColumns)
      .mockRejectedValueOnce(new Error("temporary failure"))
      .mockResolvedValueOnce(columns);

    await useDatasourceStore.getState().loadColumnsForTables(["table-retry"]);
    expect(useDatasourceStore.getState().tableColumns).toEqual({});

    await useDatasourceStore.getState().loadColumnsForTables(["table-retry"]);
    expect(listColumns).toHaveBeenCalledTimes(2);
    expect(useDatasourceStore.getState().tableColumns).toEqual({ "table-retry": columns });
  });
});
