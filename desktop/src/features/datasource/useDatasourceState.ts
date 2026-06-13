import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  listColumns,
  listDatasources,
  listTables,
  type EngineColumn,
  type EngineDataSource,
  type EngineSchemaTable,
} from "../engine/engineApi";
import type { DataSource } from "../../lib/api/types";

type UseDatasourceStateOptions = {
  onToast: (message: string) => void;
};

export function useDatasourceState({ onToast }: UseDatasourceStateOptions) {
  const [datasources, setDatasources] = useState<EngineDataSource[]>([]);
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
  const activeDatasourceForSettings = useMemo<DataSource | null>(() => {
    if (!activeDatasource) return null;
    return {
      id: activeDatasource.id,
      name: activeDatasource.name,
      db_type: activeDatasource.db_type,
      host: activeDatasource.host,
      port: activeDatasource.port,
      database_name: activeDatasource.database_name,
      username: "",
      connection_mode: "direct",
      status: activeDatasource.status,
      last_test_status: activeDatasource.last_test_status ?? undefined,
      last_test_latency_ms: activeDatasource.last_test_latency_ms ?? null,
      last_sync_status: activeDatasource.last_sync_status ?? undefined,
      created_at: "",
    };
  }, [activeDatasource]);

  // ---- Initial load (mount once) ----

  const loadDatasources = useCallback(async () => {
    setLoadingSchema(true);
    setSchemaError("");
    try {
      const nextDatasources = await listDatasources();
      setDatasources(nextDatasources);
      // Pick the first available datasource (or keep current if still valid)
      setActiveDatasourceId((prev) => {
        if (prev && nextDatasources.some((item) => item.id === prev)) {
          return prev;
        }
        return nextDatasources[0]?.id || "";
      });
    } catch (err) {
      setSchemaError(err instanceof Error ? err.message : "读取本地 Engine 数据源失败");
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
      onToast("没有活动数据源");
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
  }, [activeDatasourceId, onToast]);

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
  };
}
