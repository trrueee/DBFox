import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  listColumns,
  listTables,
  type EngineColumn,
  type EngineSchemaTable,
} from "../engine/engineApi";
import { datasourcesApi } from "../../lib/api/datasources";
import type { DataSource, DataSourceCreateParams, DataSourceUpdateParams, DeleteConfirm } from "../../lib/api/types";

import { useToast } from "../../components/Toast";

type UseDatasourceStateOptions = {
  onToast?: (message: string) => void;
};

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

export function useDatasourceState(options?: UseDatasourceStateOptions) {
  const { toast } = useToast();
  const onToast = options?.onToast || toast;
  const [datasources, setDatasources] = useState<DataSource[]>([]);
  const [activeDatasourceId, setActiveDatasourceId] = useState("");
  const [tables, setTables] = useState<EngineSchemaTable[]>([]);
  const [loadingSchema, setLoadingSchema] = useState(false);
  const [schemaError, setSchemaError] = useState("");
  const [tableColumns, setTableColumns] = useState<Record<string, EngineColumn[]>>({});

  // Guard against double-fetch on mount in React Strict Mode
  const mountedRef = useRef(false);

  const activeDatasource = useMemo(
    () => datasources.find((item) => item.id === activeDatasourceId) || null,
    [activeDatasourceId, datasources],
  );
  const activeDatasourceForSettings = activeDatasource;

  // ---- Initial load (mount once) ----

  const loadDatasources = useCallback(async () => {
    setLoadingSchema(true);
    setSchemaError("");
    try {
      for (let attempt = 0; ; attempt++) {
        try {
          const nextDatasources = await datasourcesApi.listDatasources();
          setDatasources(nextDatasources);
          // Pick the first available datasource (or keep current if still valid)
          setActiveDatasourceId((prev) => {
            if (prev && nextDatasources.some((item) => item.id === prev)) {
              return prev;
            }
            return nextDatasources[0]?.id || "";
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
      setSchemaError(err instanceof Error ? err.message : "读取数据源失败");
      setDatasources([]);
    } finally {
      setLoadingSchema(false);
    }
  }, []);

  useEffect(() => {
    if (mountedRef.current) return;
    mountedRef.current = true;
    void loadDatasources();
  }, [loadDatasources]);

  // ---- Fetch tables when active datasource changes ----

  useEffect(() => {
    let cancelled = false;
    const fetchTables = async () => {
      if (!activeDatasourceId) {
        if (!cancelled) setTables([]);
        return;
      }
      try {
        const result = await listTables(activeDatasourceId);
        if (!cancelled) setTables(result);
      } catch (err) {
        if (!cancelled) {
          setSchemaError(err instanceof Error ? err.message : "读取表结构失败");
        }
      }
    };
    void fetchTables();
    return () => {
      cancelled = true;
    };
  }, [activeDatasourceId]);

  // ---- Fetch columns when table list is ready ----

  useEffect(() => {
    let cancelled = false;
    const fetchColumns = async () => {
      if (tables.length === 0) {
        if (!cancelled) setTableColumns({});
        return;
      }
      const cols: Record<string, EngineColumn[]> = {};
      for (const table of tables) {
        if (cancelled) return;
        try {
          cols[table.table_name] = await listColumns(table.id);
        } catch {
          // Column search is an enhancement; keep the table list usable
        }
      }
      if (!cancelled) setTableColumns(cols);
    };
    void fetchColumns();
    return () => {
      cancelled = true;
    };
  }, [tables]);

  // ---- Manual refresh ----

  const refreshSchema = useCallback(async () => {
    if (!activeDatasourceId) {
      await loadDatasources();
      return;
    }
    setLoadingSchema(true);
    try {
      setTables(await listTables(activeDatasourceId));
      onToast("已刷新 Schema 元数据");
    } catch (err) {
      onToast(err instanceof Error ? err.message : "刷新 Schema 失败");
    } finally {
      setLoadingSchema(false);
    }
  }, [activeDatasourceId, loadDatasources, onToast]);

  const refreshDatasources = loadDatasources;

  const syncSchema = useCallback(async (id: string) => {
    const result = await datasourcesApi.syncSchema(id);
    await loadDatasources();
    if (id === activeDatasourceId) {
      setLoadingSchema(true);
      try {
        setTables(await listTables(id));
      } catch (err) {
        setSchemaError(err instanceof Error ? err.message : "读取表结构失败");
      } finally {
        setLoadingSchema(false);
      }
    }
    return result;
  }, [activeDatasourceId, loadDatasources]);

  const checkHealth = useCallback(async (id: string) => {
    const result = await datasourcesApi.checkDatasourceHealth(id);
    await loadDatasources();
    return result;
  }, [loadDatasources]);

  const createDatasource = useCallback(async (params: DataSourceCreateParams) => {
    const result = await datasourcesApi.createDatasource(params);
    await loadDatasources();
    return result;
  }, [loadDatasources]);

  const updateDatasource = useCallback(async (id: string, params: DataSourceUpdateParams) => {
    const result = await datasourcesApi.updateDatasource(id, params);
    await loadDatasources();
    return result;
  }, [loadDatasources]);

  const deleteDatasource = useCallback(async (id: string, confirm?: DeleteConfirm) => {
    const result = await datasourcesApi.deleteDatasource(id, confirm);
    const raw = result as unknown as Record<string, unknown> | null;
    if (!raw || !raw.requires_confirmation) {
      await loadDatasources();
      if (activeDatasourceId === id) {
        setActiveDatasourceId("");
      }
    }
    return result;
  }, [loadDatasources, activeDatasourceId]);

  return {
    datasources,
    activeDatasource,
    activeDatasourceForSettings,
    activeDatasourceId,
    setActiveDatasourceId,
    tables,
    loadingSchema,
    schemaError,
    tableColumns,
    loadDatasources,
    refreshSchema,
    refreshDatasources,
    syncSchema,
    checkHealth,
    createDatasource,
    updateDatasource,
    deleteDatasource,
  };
}
