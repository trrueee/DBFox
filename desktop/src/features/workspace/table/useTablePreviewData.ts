import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { agentApi } from "../../../lib/api/agent";
import type { ResultFilterOperator } from "../../../lib/api/types";
import { findTableByName, listColumns, type EngineColumn } from "../../../lib/api/schema";
import type {
  SqlBackedDataViewSource,
  SqlBackedExportRequest,
  SqlBackedPageRequest,
} from "../sqlBacked/sqlBackedTypes";
import { useSqlBackedDataView } from "../sqlBacked/useSqlBackedDataView";
import { databaseTypeLabel } from "../databaseTypeLabel";

interface TableMetadata {
  tableId: string;
  columns: string[];
  columnTypes: Map<string, string>;
  columnDetails: Map<string, TableColumnDetail>;
}

export interface TableColumnDetail {
  isPrimaryKey: boolean;
  isForeignKey: boolean;
  isNullable: boolean;
  comment: string;
}

interface UseTablePreviewDataOptions {
  datasourceId: string;
  datasourceDbType?: string | null;
  tableName: string;
}

interface MetadataState {
  scopeKey: string;
  value: TableMetadata | null;
  error: string;
}

export function useTablePreviewData({
  datasourceId,
  datasourceDbType,
  tableName,
}: UseTablePreviewDataOptions) {
  const scopeKey = `${datasourceId}|${tableName}`;
  const [metadataState, setMetadataState] = useState<MetadataState>({
    scopeKey,
    value: null,
    error: "",
  });
  const metadataRequest = useRef(0);
  const metadata = metadataState.scopeKey === scopeKey ? metadataState.value : null;
  const metadataError = !datasourceId
    ? "没有可用的数据源，无法预览表数据。"
    : metadataState.scopeKey === scopeKey
      ? metadataState.error
      : "";

  useEffect(() => {
    const request = ++metadataRequest.current;
    if (!datasourceId) return undefined;

    void (async () => {
      try {
        const table = await findTableByName(datasourceId, tableName);
        if (!table) {
          throw new Error("未找到该表的数据源或字段信息，请先同步表结构。");
        }
        const columns = await listColumns(table.id);
        if (request !== metadataRequest.current) return;
        const columnTypes = new Map<string, string>();
        const columnDetails = new Map<string, TableColumnDetail>();
        columns.forEach((column: EngineColumn) => {
          columnTypes.set(column.column_name, databaseTypeLabel(column.data_type || column.column_type));
          columnDetails.set(column.column_name, {
            isPrimaryKey: column.is_primary_key,
            isForeignKey: column.is_foreign_key,
            isNullable: column.is_nullable,
            comment: column.column_comment || "",
          });
        });
        setMetadataState({
          scopeKey,
          value: {
            tableId: table.id,
            columns: columns.map((column: EngineColumn) => column.column_name),
            columnTypes,
            columnDetails,
          },
          error: "",
        });
      } catch (caught) {
        if (request === metadataRequest.current) {
          setMetadataState({
            scopeKey,
            value: null,
            error: caught instanceof Error ? caught.message : "读取表结构失败",
          });
        }
      }
    })();

    return () => {
      metadataRequest.current += 1;
    };
  }, [datasourceDbType, datasourceId, scopeKey, tableName]);

  const source = useMemo<SqlBackedDataViewSource>(() => ({
    kind: "database-table",
    datasourceId,
    tableId: metadata?.tableId,
    tableName,
    columns: metadata?.columns ?? [],
  }), [datasourceId, metadata, tableName]);

  const fetchPage = useCallback(async (request: SqlBackedPageRequest) => {
    if (request.source.kind !== "database-table" || !request.source.tableId) {
      throw new Error("表结构尚未就绪，请先同步表结构。");
    }
    return agentApi.fetchTableResultPage({
      datasourceId: request.source.datasourceId,
      tableId: request.source.tableId,
      tableName: request.source.tableName,
      page: request.page,
      pageSize: request.pageSize,
      filters: request.filters,
      sort: request.sort,
      search: request.search,
      countMode: request.countMode,
    });
  }, []);

  const exportAll = useCallback(async (request: SqlBackedExportRequest) => {
    if (request.source.kind !== "database-table" || !request.source.tableId) {
      throw new Error("表结构尚未就绪，请先同步表结构。");
    }
    return agentApi.exportTableResultCsv({
      datasourceId: request.source.datasourceId,
      tableId: request.source.tableId,
      tableName: request.source.tableName,
      filters: request.filters,
      sort: request.sort,
      search: request.search,
    });
  }, []);

  const gateway = useSqlBackedDataView({
    source,
    fetchPage,
    exportAll,
    enabled: Boolean(metadata),
    initialPageSize: 20,
    countMode: "estimate",
  });

  return {
    ...gateway,
    columnTypes: metadata?.columnTypes ?? EMPTY_COLUMN_TYPES,
    columnDetails: metadata?.columnDetails ?? EMPTY_COLUMN_DETAILS,
    error: metadataError || gateway.error || "",
  };
}

const EMPTY_COLUMN_TYPES = new Map<string, string>();
const EMPTY_COLUMN_DETAILS = new Map<string, TableColumnDetail>();

export type TableFilterOperator = ResultFilterOperator;
