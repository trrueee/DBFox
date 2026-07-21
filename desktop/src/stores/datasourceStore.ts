import { create } from "zustand";
import {
  listColumns,
  listTables,
  type EngineColumn,
  type EngineSchemaTable,
} from "../lib/api/schema";
import { datasourcesApi } from "../lib/api/datasources";
import type { DataSource, DataSourceCreateParams, DataSourceHealthResult, DataSourceUpdateParams, DeleteConfirm, SchemaSyncOptions, SchemaSyncResult } from "../lib/api/types";

interface DatasourceState {
  datasources: DataSource[];
  activeDatasourceId: string;
  activeDatasourceForSettings: DataSource | null;
  tables: EngineSchemaTable[];
  loadingSchema: boolean;
  schemaError: string;
  tableColumns: Record<string, EngineColumn[]>;
}

interface DatasourceActions {
  setActiveDatasourceId: (id: string) => void;
  loadDatasources: () => Promise<void>;
  refreshSchema: () => Promise<void>;
  loadTableColumns: (tableId: string) => Promise<EngineColumn[]>;
  loadColumnsForTables: (tableIds: string[]) => Promise<Record<string, EngineColumn[]>>;
  createDatasource: (params: DataSourceCreateParams) => Promise<DataSource>;
  updateDatasource: (id: string, params: DataSourceUpdateParams) => Promise<DataSource>;
  deleteDatasource: (id: string, confirm?: DeleteConfirm) => Promise<unknown>;
  syncSchema: (id: string, options?: SchemaSyncOptions) => Promise<SchemaSyncResult>;
  checkHealth: (id: string) => Promise<DataSourceHealthResult>;
}

export type DatasourceStore = DatasourceState & DatasourceActions;

const DATASOURCE_LOAD_RETRY_DELAYS_MS = [300, 900, 1500, 3000, 5000];
const COLUMN_LOAD_CONCURRENCY = 4;

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function isTransientEngineFetchError(error: unknown) {
  if (error instanceof TypeError) return true;
  if (!(error instanceof Error)) return false;
  const message = error.message.toLowerCase();
  return message.includes("failed to fetch") || message.includes("networkerror") || message.includes("load failed");
}

async function loadColumnsWithLimit(tables: EngineSchemaTable[]) {
  const results: Array<{ id: string; columns: EngineColumn[] } | undefined> = new Array(tables.length);
  let nextIndex = 0;

  async function worker() {
    while (nextIndex < tables.length) {
      const index = nextIndex;
      nextIndex += 1;
      const table = tables[index];
      try {
        const columns = await listColumns(table.id);
        results[index] = { id: table.id, columns };
      } catch {
        // A failed request is not an empty schema and must remain retryable.
        results[index] = undefined;
      }
    }
  }

  const workerCount = Math.min(COLUMN_LOAD_CONCURRENCY, tables.length);
  await Promise.all(Array.from({ length: workerCount }, () => worker()));
  return results.filter(
    (result): result is { id: string; columns: EngineColumn[] } => result !== undefined,
  );
}

function datasourceCacheKey(state: Pick<DatasourceState, "activeDatasourceId" | "datasources">) {
  if (!state.activeDatasourceId) return "";
  const datasource = state.datasources.find((item) => item.id === state.activeDatasourceId);
  return `${state.activeDatasourceId}:${datasource?.connection_generation ?? 0}`;
}

export const useDatasourceStore = create<DatasourceStore>()((set, get) => ({
  datasources: [],
  activeDatasourceId: "",
  activeDatasourceForSettings: null,
  tables: [],
  loadingSchema: false,
  schemaError: "",
  tableColumns: {},

  setActiveDatasourceId: (id: string) => {
    const prev = get().activeDatasourceId;
    set({
      activeDatasourceId: id,
      activeDatasourceForSettings: get().datasources.find((ds) => ds.id === id) || null,
    });
    if (prev && prev !== id) {
      datasourcesApi.releaseDatasource(prev).catch((err) => {
        console.warn("Failed to release datasource pool on switch:", err);
      });
    }
  },

  loadDatasources: async () => {
    set({ loadingSchema: true, schemaError: "" });
    try {
      for (let attempt = 0; ; attempt++) {
        try {
          const nextDatasources = await datasourcesApi.listDatasources();
          const currentId = get().activeDatasourceId;
          const activeId =
            currentId && nextDatasources.some((item) => item.id === currentId)
              ? currentId
              : nextDatasources[0]?.id || "";
          set({
            datasources: nextDatasources,
            activeDatasourceId: activeId,
            activeDatasourceForSettings: nextDatasources.find((ds) => ds.id === activeId) || null,
          });
          return;
        } catch (err) {
          const retryDelay = DATASOURCE_LOAD_RETRY_DELAYS_MS[attempt];
          if (retryDelay !== undefined && isTransientEngineFetchError(err)) {
            await delay(retryDelay);
            continue;
          }
          throw err;
        }
      }
    } catch (err) {
      set({
        schemaError: err instanceof Error ? err.message : "读取数据源失败",
        datasources: [],
        activeDatasourceId: "",
        activeDatasourceForSettings: null,
        tables: [],
        tableColumns: {},
      });
    } finally {
      set({ loadingSchema: false });
    }
  },

  refreshSchema: async () => {
    const { activeDatasourceId, loadDatasources } = get();
    if (!activeDatasourceId) {
      await loadDatasources();
      return;
    }
    const cacheKey = datasourceCacheKey(get());
    set({ loadingSchema: true, tables: [], tableColumns: {}, schemaError: "" });
    try {
      const tables = await listTables(activeDatasourceId);
      if (datasourceCacheKey(get()) === cacheKey) {
        set({ tables, tableColumns: {} });
      }
    } catch (err) {
      if (datasourceCacheKey(get()) === cacheKey) {
        set({ schemaError: err instanceof Error ? err.message : "读取数据库结构失败" });
      }
    } finally {
      if (datasourceCacheKey(get()) === cacheKey) {
        set({ loadingSchema: false });
      }
    }
  },

  loadTableColumns: async (tableId: string) => {
    const table = get().tables.find((item) => item.id === tableId);
    if (!table) return [];
    const cached = get().tableColumns[table.id];
    if (cached) return cached;

    const cacheKey = datasourceCacheKey(get());
    const columns = await listColumns(table.id);
    if (datasourceCacheKey(get()) !== cacheKey || !get().tables.some((item) => item.id === table.id)) {
      return [];
    }
    set((state) => ({
      tableColumns: {
        ...state.tableColumns,
        [table.id]: columns,
      },
    }));
    return columns;
  },

  loadColumnsForTables: async (tableIds: string[]) => {
    const cacheKey = datasourceCacheKey(get());
    const requested = new Set(tableIds);
    const targetTables = get().tables.filter((table) => requested.has(table.id));
    const missingTables = targetTables.filter((table) => !get().tableColumns[table.id]);
    const results = await loadColumnsWithLimit(missingTables);
    if (datasourceCacheKey(get()) !== cacheKey) {
      return get().tableColumns;
    }
    const nextColumns: Record<string, EngineColumn[]> = { ...get().tableColumns };
    for (const { id, columns } of results) {
      nextColumns[id] = columns;
    }
    set({ tableColumns: nextColumns });
    return nextColumns;
  },

  createDatasource: async (params) => {
    const result = await datasourcesApi.createDatasource(params);
    await get().loadDatasources();
    return result;
  },

  updateDatasource: async (id, params) => {
    const result = await datasourcesApi.updateDatasource(id, params);
    await get().loadDatasources();
    return result;
  },

  deleteDatasource: async (id, confirm) => {
    const result = await datasourcesApi.deleteDatasource(id, confirm);
    const raw = result as unknown as Record<string, unknown> | null;
    if (!raw || !raw.requires_confirmation) {
      await get().loadDatasources();
      if (get().activeDatasourceId === id) {
        set({ activeDatasourceId: "", activeDatasourceForSettings: null });
      }
    }
    return result;
  },

  syncSchema: async (id, options) => {
    const result = await datasourcesApi.syncSchema(id, options);
    await get().loadDatasources();
    if (id === get().activeDatasourceId) {
      set({ loadingSchema: true });
      try {
        set({ tables: await listTables(id), tableColumns: {} });
      } catch {
        // Best-effort
      } finally {
        set({ loadingSchema: false });
      }
    }
    return result;
  },

  checkHealth: async (id) => {
    const result = await datasourcesApi.checkDatasourceHealth(id);
    await get().loadDatasources();
    return result;
  },
}));

let activeTablesFetchKey: string | null = null;

// Side-effect: fetch tables when active datasource changes
useDatasourceStore.subscribe((state, prev) => {
  const nextKey = datasourceCacheKey(state);
  const previousKey = datasourceCacheKey(prev);
  if (nextKey === previousKey) return;
  if (!state.activeDatasourceId) {
    activeTablesFetchKey = null;
    useDatasourceStore.setState({ tables: [], tableColumns: {} });
    return;
  }
  const targetId = state.activeDatasourceId;
  activeTablesFetchKey = nextKey;

  useDatasourceStore.setState({ loadingSchema: true, schemaError: "", tables: [], tableColumns: {} });

  listTables(targetId)
    .then((result) => {
      if (activeTablesFetchKey === nextKey && datasourceCacheKey(useDatasourceStore.getState()) === nextKey) {
        useDatasourceStore.setState({ tables: result, tableColumns: {}, schemaError: "" });
      }
    })
    .catch((err) => {
      if (activeTablesFetchKey === nextKey && datasourceCacheKey(useDatasourceStore.getState()) === nextKey) {
        useDatasourceStore.setState({
          tables: [],
          tableColumns: {},
          schemaError: err instanceof Error ? err.message : "读取数据库结构失败",
        });
      }
    })
    .finally(() => {
      if (activeTablesFetchKey === nextKey && datasourceCacheKey(useDatasourceStore.getState()) === nextKey) {
        useDatasourceStore.setState({ loadingSchema: false });
      }
    });
});
