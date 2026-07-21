import { useCallback, useMemo } from "react";
import { agentApi } from "../../../../lib/api/agent";
import type { ResultFilter } from "../../../../lib/api/types";
import type { ResultViewArtifact } from "../../../../types/agentArtifact";
import type {
  SqlBackedDataViewSource,
  SqlBackedExportRequest,
  SqlBackedPageRequest,
} from "../../sqlBacked/sqlBackedTypes";
import { useSqlBackedDataView } from "../../sqlBacked/useSqlBackedDataView";
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
  filters: ResultFilter[];
  setFilters: (value: ResultFilter[]) => void;
  page: number;
  setPage: (updater: number | ((page: number) => number)) => void;
  pageSize: number;
  setPageSize: (value: number) => void;
  visibleRows: string[][];
  totalRows: number | undefined;
  returnedRows: number;
  warnings: string[];
  notices: string[];
  latencyMs: number | undefined;
  consistency: "live_reexecution" | "live_query" | undefined;
  originalExecutedAt: string | null | undefined;
  viewExecutedAt: string | undefined;
  isLoading: boolean;
  fetchError: string | null;
  csv: string;
  exportAll: () => Promise<Blob>;
  refresh: () => void;
  hasNextPage: boolean;
}

export function useArtifactTableData(
  artifact: ResultViewArtifact,
  mode: "inline" | "workspace",
): ArtifactTableData {
  const columnMetadata = useMemo(
    () => artifact.columns
      .map((column) => ({ name: columnName(column), type: columnType(column) }))
      .filter((column) => Boolean(column.name)),
    [artifact.columns],
  );
  const descriptorColumns = useMemo(() => columnMetadata.map((column) => column.name), [columnMetadata]);
  const columnTypes = useMemo(() => columnMetadata.map((column) => column.type), [columnMetadata]);
  const source = useMemo<SqlBackedDataViewSource>(() => ({
    kind: "artifact-result",
    artifactId: artifact.id,
    columns: descriptorColumns,
  }), [artifact.id, descriptorColumns]);

  const fetchPage = useCallback(async (request: SqlBackedPageRequest, signal: AbortSignal) => {
    if (request.source.kind !== "artifact-result") throw new Error("Unsupported Result Gateway source");
    return agentApi.fetchArtifactPage(request.source.artifactId, {
      page: request.page,
      pageSize: request.pageSize,
      sort: request.sort,
      filters: request.filters,
      search: request.search,
      countMode: request.countMode ?? "estimate",
    }, signal);
  }, []);

  const exportAll = useCallback(async (request: SqlBackedExportRequest) => {
    if (request.source.kind !== "artifact-result") throw new Error("Unsupported Result Gateway source");
    return agentApi.exportArtifactCsv(request.source.artifactId, {
      sort: request.sort,
      filters: request.filters,
      search: request.search,
    });
  }, []);

  const gateway = useSqlBackedDataView({
    source,
    fetchPage,
    exportAll,
    initialPageSize: mode === "inline" ? 10 : 50,
    countMode: "estimate",
  });
  const columns = gateway.columns;
  const csv = useMemo(() => toCsv(columns, gateway.rows), [columns, gateway.rows]);
  const activeSort = useMemo<SortState | null>(() => {
    const current = gateway.sort[0];
    if (!current) return null;
    const columnIndex = columns.indexOf(current.column);
    return columnIndex < 0 ? null : { columnIndex, direction: current.direction };
  }, [columns, gateway.sort]);

  const setSortColumn = (columnIndex: number) => {
    const column = columns[columnIndex];
    if (!column) return;
    const current = gateway.sort[0];
    const direction = current?.column === column && current.direction === "desc" ? "asc" : "desc";
    gateway.setSort([{ column, direction }]);
  };
  const setSortState = (columnIndex: number, direction: SortDirection) => {
    const column = columns[columnIndex];
    if (column) gateway.setSort([{ column, direction }]);
  };

  return {
    columns,
    columnTypes,
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
    totalRows: gateway.rowCount ?? artifact.rowCount,
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
  };
}

function columnName(column: ResultViewArtifact["columns"][number]): string {
  return typeof column === "string" ? column : column.name;
}

function columnType(column: ResultViewArtifact["columns"][number]): string | undefined {
  return typeof column === "string" ? undefined : column.type;
}
