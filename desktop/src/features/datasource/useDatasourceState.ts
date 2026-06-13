import { useCallback, useEffect, useMemo, useState } from "react";
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

  const loadDatasources = useCallback(async () => {
    setLoadingSchema(true);
    setSchemaError("");
    try {
      const nextDatasources = await listDatasources();
      setDatasources(nextDatasources);
      const nextActive = activeDatasourceId && nextDatasources.some((item) => item.id === activeDatasourceId)
        ? activeDatasourceId
        : nextDatasources[0]?.id || "";
      setActiveDatasourceId(nextActive);
      setTables(nextActive ? await listTables(nextActive) : []);
    } catch (err) {
      setSchemaError(err instanceof Error ? err.message : "读取本地 Engine 数据源失败");
      setDatasources([]);
      setTables([]);
    } finally {
      setLoadingSchema(false);
    }
  }, [activeDatasourceId]);

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

  useEffect(() => {
    void loadDatasources();
  }, [loadDatasources]);

  useEffect(() => {
    if (!activeDatasourceId) return;
    const fetchTables = async () => {
      try {
        setTables(await listTables(activeDatasourceId));
      } catch (err) {
        setSchemaError(err instanceof Error ? err.message : "读取表结构失败");
      }
    };
    void fetchTables();
  }, [activeDatasourceId]);

  useEffect(() => {
    if (tables.length === 0) {
      setTableColumns({});
      return;
    }
    const fetchColumns = async () => {
      const cols: Record<string, EngineColumn[]> = {};
      for (const table of tables) {
        try {
          cols[table.table_name] = await listColumns(table.id);
        } catch {
          // Column search is an enhancement; keep the table list usable if a column request fails.
        }
      }
      setTableColumns(cols);
    };
    void fetchColumns();
  }, [tables]);

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
