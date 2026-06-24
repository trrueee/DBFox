import { useCallback, useMemo, useState } from "react";
import { agentApi } from "../../../../lib/api/agent";
import type { ResultFilter } from "../../../../lib/api/types";
import type { ResultViewArtifact, TableArtifact } from "../../../../types/agentArtifact";
import type {
  SqlBackedDataViewSource,
  SqlBackedExportRequest,
  SqlBackedPageRequest,
} from "../../sqlBacked/sqlBackedTypes";
import { useSqlBackedDataView } from "../../sqlBacked/useSqlBackedDataView";
import { toCsv } from "../artifactActions";

const PREVIEW_ROW_LIMIT = 10;
const LARGE_RESULT_THRESHOLD = 500;
const WINDOW_ROW_LIMIT = 200;

export type SortDirection = "asc" | "desc";

export interface SortState {
  columnIndex: number;
  direction: SortDirection;
}

export interface ArtifactTableData {
  columns: string[];
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
  filteredAndSortedRows: string[][];
  totalRows: number | undefined;
  returnedRows: number;
  previewCount: number;
  warnings: string[];
  notices: string[];
  latencyMs: number | undefined;
  isLoading: boolean;
  fetchError: string | null;
  isSqlBackedWorkspace: boolean;
  shouldUseWindow: boolean;
  expanded: boolean;
  setExpanded: (value: boolean | ((current: boolean) => boolean)) => void;
  csv: string;
  exportAll?: () => Promise<Blob>;
  refresh: () => void;
  rowsToUseLength: number;
  isSearching: boolean;
  hasNextPage: boolean;
}

export function useArtifactTableData(
  artifact: TableArtifact | ResultViewArtifact,
  mode: "inline" | "workspace",
): ArtifactTableData {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortState | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [expanded, setExpanded] = useState(false);

  const isSqlBackedWorkspace = mode === "workspace" && artifact.type === "result_view" && artifact.storageMode === "sql_backed";
  const columns = useMemo(() => artifact.columns.map(columnName).filter(Boolean), [artifact.columns]);

  const sqlBackedSource = useMemo<SqlBackedDataViewSource>(() => {
    if (artifact.type === "result_view") {
      return {
        kind: "artifact-result",
        datasourceId: artifact.datasourceId,
        sourceSqlArtifactId: artifact.sourceSqlSemanticId,
        safeSql: artifact.safeSql,
        columns,
      };
    }
    return {
      kind: "artifact-result",
      datasourceId: "",
      sourceSqlArtifactId: artifact.id,
      safeSql: artifact.sql ?? "",
      columns,
    };
  }, [artifact, columns]);

  const fetchSqlBackedPage = useCallback(async (request: SqlBackedPageRequest) => {
    if (request.source.kind !== "artifact-result") throw new Error("Unsupported SQL-backed artifact source");
    return agentApi.fetchResultPage({
      datasourceId: request.source.datasourceId,
      sourceSqlArtifactId: request.source.sourceSqlArtifactId,
      safeSql: request.source.safeSql,
      page: request.page,
      pageSize: request.pageSize,
      sort: request.sort,
      filters: request.filters,
      search: request.search,
      countMode: request.countMode ?? "estimate",
    });
  }, []);

  const exportSqlBackedRows = useCallback(async (request: SqlBackedExportRequest) => {
    if (request.source.kind !== "artifact-result") throw new Error("Unsupported SQL-backed artifact source");
    return agentApi.exportResultCsv({
      datasourceId: request.source.datasourceId,
      sourceSqlArtifactId: request.source.sourceSqlArtifactId,
      safeSql: request.source.safeSql,
      sort: request.sort,
      filters: request.filters,
      search: request.search,
    });
  }, []);

  const sqlBacked = useSqlBackedDataView({
    source: sqlBackedSource,
    fetchPage: fetchSqlBackedPage,
    exportAll: exportSqlBackedRows,
    enabled: isSqlBackedWorkspace,
    initialPageSize: 50,
    countMode: "estimate",
  });

  const rowsToUse = artifact.type === "result_view" ? (artifact.rows ?? artifact.previewRows) : artifact.rows;

  const backendRows = sqlBacked.rows;

  const csv = useMemo(
    () => toCsv(columns, isSqlBackedWorkspace ? backendRows : rowsToUse),
    [columns, backendRows, isSqlBackedWorkspace, rowsToUse],
  );
  const normalizedSearch = search.trim().toLowerCase();

  const filteredAndSortedRows = useMemo(() => {
    if (isSqlBackedWorkspace) return backendRows;
    const filteredRows =
      normalizedSearch.length > 0
        ? rowsToUse.filter((row) => row.some((cell) => cell.toLowerCase().includes(normalizedSearch)))
        : rowsToUse;

    if (!sort) return filteredRows;
    return [...filteredRows].sort((left, right) =>
      compareCells(left[sort.columnIndex] ?? "", right[sort.columnIndex] ?? "", sort.direction),
    );
  }, [backendRows, isSqlBackedWorkspace, normalizedSearch, rowsToUse, sort]);

  const isSearching = normalizedSearch.length > 0;
  const shouldUseWindow =
    !isSqlBackedWorkspace && (expanded || isSearching) && filteredAndSortedRows.length > LARGE_RESULT_THRESHOLD;
  const visibleRows = isSqlBackedWorkspace
    ? filteredAndSortedRows
    : expanded || isSearching
      ? filteredAndSortedRows.slice(0, shouldUseWindow ? WINDOW_ROW_LIMIT : filteredAndSortedRows.length)
      : filteredAndSortedRows.slice(0, PREVIEW_ROW_LIMIT);

  const activeSort = useMemo<SortState | null>(() => {
    if (!isSqlBackedWorkspace) return sort;
    const current = sqlBacked.sort[0];
    if (!current) return null;
    const columnIndex = columns.indexOf(current.column);
    if (columnIndex < 0) return null;
    return { columnIndex, direction: current.direction };
  }, [columns, isSqlBackedWorkspace, sort, sqlBacked.sort]);

  const setSortColumn = (columnIndex: number) => {
    if (isSqlBackedWorkspace) {
      const column = columns[columnIndex];
      if (!column) return;
      const current = sqlBacked.sort[0];
      const direction = current?.column === column && current.direction === "desc" ? "asc" : "desc";
      sqlBacked.setSort([{ column, direction }]);
      return;
    }
    setSort((current) => {
      if (current?.columnIndex !== columnIndex) return { columnIndex, direction: "desc" };
      return { columnIndex, direction: current.direction === "desc" ? "asc" : "desc" };
    });
    setPage(1);
  };

  const setSortState = (columnIndex: number, direction: SortDirection) => {
    const column = columns[columnIndex];
    if (!column) return;
    if (isSqlBackedWorkspace) {
      sqlBacked.setSort([{ column, direction }]);
      return;
    }
    setSort({ columnIndex, direction });
    setPage(1);
  };

  const clearSort = () => {
    if (isSqlBackedWorkspace) {
      sqlBacked.setSort([]);
      return;
    }
    setSort(null);
    setPage(1);
  };

  return {
    columns,
    search: isSqlBackedWorkspace ? sqlBacked.search : search,
    setSearch: isSqlBackedWorkspace ? sqlBacked.setSearch : setSearch,
    sort: activeSort,
    setSortColumn,
    setSortState,
    clearSort,
    filters: isSqlBackedWorkspace ? sqlBacked.filters : [],
    setFilters: isSqlBackedWorkspace ? sqlBacked.setFilters : () => undefined,
    page: isSqlBackedWorkspace ? sqlBacked.page : page,
    setPage: isSqlBackedWorkspace ? sqlBacked.setPage : setPage,
    pageSize: isSqlBackedWorkspace ? sqlBacked.pageSize : pageSize,
    setPageSize: isSqlBackedWorkspace ? sqlBacked.setPageSize : setPageSize,
    visibleRows,
    filteredAndSortedRows,
    totalRows: isSqlBackedWorkspace ? (sqlBacked.rowCount ?? undefined) : (artifact.rowCount ?? rowsToUse.length),
    returnedRows: isSqlBackedWorkspace ? backendRows.length : (artifact.returnedRows ?? rowsToUse.length),
    previewCount: visibleRows.length,
    warnings: isSqlBackedWorkspace ? sqlBacked.warnings : (artifact.warnings ?? []),
    notices: isSqlBackedWorkspace ? sqlBacked.notices : (artifact.notices ?? []),
    latencyMs: isSqlBackedWorkspace ? sqlBacked.latencyMs : artifact.latencyMs,
    isLoading: isSqlBackedWorkspace ? sqlBacked.isLoading : false,
    fetchError: isSqlBackedWorkspace ? sqlBacked.error : null,
    isSqlBackedWorkspace,
    shouldUseWindow,
    expanded,
    setExpanded,
    csv,
    exportAll: isSqlBackedWorkspace ? sqlBacked.exportAll : undefined,
    refresh: isSqlBackedWorkspace ? sqlBacked.refresh : () => undefined,
    rowsToUseLength: rowsToUse.length,
    isSearching,
    hasNextPage: isSqlBackedWorkspace ? sqlBacked.hasNextPage : false,
  };
}

function columnName(column: TableArtifact["columns"][number] | ResultViewArtifact["columns"][number]): string {
  if (typeof column === "string") return column;
  return column.name;
}

function compareCells(left: string, right: string, direction: SortDirection): number {
  const leftNumber = Number(left);
  const rightNumber = Number(right);
  const bothNumeric =
    left.trim() !== "" && right.trim() !== "" && Number.isFinite(leftNumber) && Number.isFinite(rightNumber);
  const result = bothNumeric
    ? leftNumber - rightNumber
    : left.localeCompare(right, undefined, { numeric: true, sensitivity: "base" });
  return direction === "asc" ? result : -result;
}
