import { useCallback, useMemo } from "react";
import { agentApi } from "../../../../lib/api/agent";
import {
  DATAFRAME_REPRESENTATION_TYPE,
  parseDataFrameRead,
} from "../../../../lib/api/representation";
import type { DataFrameFilter } from "../../../../lib/api/types";
import type { ArtifactEnvelope } from "../types";
import type {
  DataFrameViewSource,
  DataFrameExportRequest,
  DataFramePageRequest,
} from "../../dataFrame/dataFrameViewTypes";
import { useDataFrameView } from "../../dataFrame/useDataFrameView";
import { toCsv } from "../artifactActions";

export type SortDirection = "asc" | "desc";

export interface SortState {
  columnIndex: number;
  direction: SortDirection;
}

export interface ArtifactTableData {
  columns: string[];
  columnTypes: Array<string | undefined>;
  search: string;
  setSearch: (value: string) => void;
  sort: SortState | null;
  setSortColumn: (columnIndex: number) => void;
  setSortState: (columnIndex: number, direction: SortDirection) => void;
  clearSort: () => void;
  filters: DataFrameFilter[];
  setFilters: (value: DataFrameFilter[]) => void;
  page: number;
  setPage: (updater: number | ((page: number) => number)) => void;
  pageSize: number;
  setPageSize: (value: number) => void;
  visibleRows: unknown[][];
  totalRows: number | undefined;
  returnedRows: number;
  warnings: string[];
  notices: string[];
  latencyMs: number | undefined;
  consistency: "durable_snapshot" | "live_reexecution" | undefined;
  originalExecutedAt: string | null | undefined;
  viewExecutedAt: string | undefined;
  isLoading: boolean;
  fetchError: unknown | null;
  csv: string;
  exportAll: () => Promise<Blob>;
  refresh: () => void;
  hasNextPage: boolean;
  sourceTruncated: boolean;
}

export function useArtifactTableData(
  artifact: Pick<ArtifactEnvelope<unknown>, "id">,
  mode: "inline" | "workspace",
): ArtifactTableData {
  const source = useMemo<DataFrameViewSource>(() => ({
    kind: "artifact-representation",
    artifactId: artifact.id,
    representationType: DATAFRAME_REPRESENTATION_TYPE,
  }), [artifact.id]);

  const fetchPage = useCallback(async (request: DataFramePageRequest, signal: AbortSignal) => {
    const represented = await agentApi.readArtifactRepresentation(
      request.source.artifactId,
      request.source.representationType,
      {
        operation: "page",
        parameters: {
          page: request.page,
          page_size: request.pageSize,
          sort: request.sort,
          filters: request.filters,
          search: request.search,
          count_mode: request.countMode ?? "none",
        },
      },
      signal,
    );
    const read = parseDataFrameRead(represented);
    return {
      columns: read.page.fields.map((field) => field.name),
      columnTypes: read.page.fields.map((field) => field.type),
      rows: read.rows,
      page: read.page.page,
      pageSize: read.page.page_size,
      rowCount: read.page.row_count,
      hasNextPage: read.page.has_next_page,
      latencyMs: read.page.latency_ms,
      sourceTruncated: read.page.source_truncated,
      consistency: read.consistency,
      originalExecutedAt: read.originalObservedAt,
      viewExecutedAt: read.readAt,
      viewExecutionId: read.readId,
      resourceVersion: read.sourceVersion,
      sourceFingerprint: read.sourceFingerprint,
      warnings: read.warnings,
      notices: read.notices,
    };
  }, []);

  const exportAll = useCallback(async (request: DataFrameExportRequest) => {
    return agentApi.streamArtifactRepresentation(
      request.source.artifactId,
      request.source.representationType,
      {
        operation: "export.csv",
        parameters: {
          sort: request.sort,
          filters: request.filters,
          search: request.search,
        },
      },
    );
  }, []);

  const gateway = useDataFrameView({
    source,
    fetchPage,
    exportAll,
    initialPageSize: mode === "inline" ? 10 : 50,
    countMode: mode === "workspace" ? "exact" : "none",
  });
  const columns = gateway.columns;
  const csv = useMemo(() => toCsv(columns, gateway.rows), [columns, gateway.rows]);
  const activeSort = useMemo<SortState | null>(() => {
    const current = gateway.sort[0];
    if (!current) return null;
    const columnIndex = columns.indexOf(current.field);
    return columnIndex < 0 ? null : { columnIndex, direction: current.direction };
  }, [columns, gateway.sort]);

  const setSortColumn = (columnIndex: number) => {
    const column = columns[columnIndex];
    if (!column) return;
    const current = gateway.sort[0];
    const direction = current?.field === column && current.direction === "desc" ? "asc" : "desc";
    gateway.setSort([{ field: column, direction }]);
  };
  const setSortState = (columnIndex: number, direction: SortDirection) => {
    const column = columns[columnIndex];
    if (column) gateway.setSort([{ field: column, direction }]);
  };

  return {
    columns,
    columnTypes: gateway.columnTypes,
    search: gateway.search,
    setSearch: gateway.setSearch,
    sort: activeSort,
    setSortColumn,
    setSortState,
    clearSort: () => gateway.setSort([]),
    filters: gateway.filters,
    setFilters: gateway.setFilters,
    page: gateway.page,
    setPage: gateway.setPage,
    pageSize: gateway.pageSize,
    setPageSize: gateway.setPageSize,
    visibleRows: gateway.rows,
    totalRows: gateway.rowCount ?? undefined,
    returnedRows: gateway.rows.length,
    warnings: gateway.warnings,
    notices: gateway.notices,
    latencyMs: gateway.latencyMs,
    consistency: gateway.consistency,
    originalExecutedAt: gateway.originalExecutedAt,
    viewExecutedAt: gateway.viewExecutedAt,
    isLoading: gateway.isLoading,
    fetchError: gateway.error,
    csv,
    exportAll: gateway.exportAll,
    refresh: gateway.refresh,
    hasNextPage: gateway.hasNextPage,
    sourceTruncated: Boolean(gateway.data?.sourceTruncated),
  };
}
