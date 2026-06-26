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
  const results: Array<{ name: string; columns: EngineColumn[] }> = new Array(tables.length);
  let nextIndex = 0;

  async function worker() {
    while (nextIndex < tables.length) {
      const index = nextIndex;
      nextIndex += 1;
      const table = tables[index];
      try {
        const columns = await listColumns(table.id);
        results[index] = { name: table.table_name, columns };
      } catch {
        results[index] = { name: table.table_name, columns: [] };
      }
    }
  }

  const workerCount = Math.min(COLUMN_LOAD_CONCURRENCY, tables.length);
  await Promise.all(Array.from({ length: workerCount }, () => worker()));
  return results;
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
      set({ schemaError: err instanceof Error ? err.message : "读取数据源失败", datasources: [] });
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
    set({ loadingSchema: true });
    try {
      set({ tables: await listTables(activeDatasourceId), tableColumns: {} });
    } catch {
      // Schema refresh is best-effort
    } finally {
      set({ loadingSchema: false });
    }
  },

  loadTableColumns: async (tableId: string) => {
    const table = get().tables.find((item) => item.id === tableId);
    if (!table) return [];
    const cached = get().tableColumns[table.table_name];
    if (cached) return cached;

    const columns = await listColumns(table.id);
    set((state) => ({
      tableColumns: {
        ...state.tableColumns,
        [table.table_name]: columns,
      },
    }));
    return columns;
  },

  loadColumnsForTables: async (tableIds: string[]) => {
    const requested = new Set(tableIds);
    const targetTables = get().tables.filter((table) => requested.has(table.id));
    const missingTables = targetTables.filter((table) => !get().tableColumns[table.table_name]);
    const results = await loadColumnsWithLimit(missingTables);
    const nextColumns: Record<string, EngineColumn[]> = { ...get().tableColumns };
    for (const { name, columns } of results) {
      nextColumns[name] = columns;
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

let activeTablesFetchId: string | null = null;

// Side-effect: fetch tables when active datasource changes
useDatasourceStore.subscribe((state, prev) => {
  if (state.activeDatasourceId === prev.activeDatasourceId) return;
  if (!state.activeDatasourceId) {
    useDatasourceStore.setState({ tables: [], tableColumns: {} });
    return;
  }
  const targetId = state.activeDatasourceId;
  activeTablesFetchId = targetId;

  useDatasourceStore.setState({ loadingSchema: true, schemaError: "", tableColumns: {} });

  listTables(targetId)
    .then((result) => {
      if (activeTablesFetchId === targetId) {
        useDatasourceStore.setState({ tables: result, tableColumns: {}, schemaError: "" });
      }
    })
    .catch((err) => {
      if (activeTablesFetchId === targetId) {
        useDatasourceStore.setState({
          schemaError: err instanceof Error ? err.message : "读取数据库结构失败",
        });
      }
    })
    .finally(() => {
      if (activeTablesFetchId === targetId) {
        useDatasourceStore.setState({ loadingSchema: false });
      }
    });
});
