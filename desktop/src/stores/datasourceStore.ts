import { create } from "zustand";
import {
  listColumns,
  listTables,
  type EngineColumn,
  type EngineSchemaTable,
} from "../lib/api/schema";
import { datasourcesApi } from "../lib/api/datasources";
import type { DataSource, DataSourceCreateParams, DataSourceHealthResult, DataSourceUpdateParams, DeleteConfirm, SchemaSyncOptions } from "../lib/api/types";

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
  createDatasource: (params: DataSourceCreateParams) => Promise<DataSource>;
  updateDatasource: (id: string, params: DataSourceUpdateParams) => Promise<DataSource>;
  deleteDatasource: (id: string, confirm?: DeleteConfirm) => Promise<unknown>;
  syncSchema: (id: string, options?: SchemaSyncOptions) => Promise<unknown>;
  checkHealth: (id: string) => Promise<DataSourceHealthResult>;
}

export type DatasourceStore = DatasourceState & DatasourceActions;

const DATASOURCE_LOAD_RETRY_DELAYS_MS = [300, 900, 1500, 3000, 5000];

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function isTransientEngineFetchError(error: unknown) {
  if (error instanceof TypeError) return true;
  if (!(error instanceof Error)) return false;
  const message = error.message.toLowerCase();
  return message.includes("failed to fetch") || message.includes("networkerror") || message.includes("load failed");
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
      set({ tables: await listTables(activeDatasourceId) });
    } catch {
      // Schema refresh is best-effort
    } finally {
      set({ loadingSchema: false });
    }
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
        set({ tables: await listTables(id) });
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

  useDatasourceStore.setState({ loadingSchema: true, schemaError: "" });

  listTables(targetId)
    .then((result) => {
      if (activeTablesFetchId === targetId) {
        useDatasourceStore.setState({ tables: result, schemaError: "" });
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

let activeColumnsFetchTables: EngineSchemaTable[] | null = null;

// Side-effect: fetch columns when tables change
useDatasourceStore.subscribe((state, prev) => {
  if (state.tables === prev.tables) return;
  if (state.tables.length === 0) {
    useDatasourceStore.setState({ tableColumns: {} });
    return;
  }
  const currentTables = state.tables;
  activeColumnsFetchTables = currentTables;

  const fetchColumns = async () => {
    const results = await Promise.all(
      currentTables.map(async (table) => {
        try {
          const columns = await listColumns(table.id);
          return { name: table.table_name, columns };
        } catch {
          return { name: table.table_name, columns: [] as EngineColumn[] };
        }
      }),
    );
    if (activeColumnsFetchTables !== currentTables) return;
    const cols: Record<string, EngineColumn[]> = {};
    for (const { name, columns } of results) {
      cols[name] = columns;
    }
    useDatasourceStore.setState({ tableColumns: cols });
  };
  fetchColumns();
});
