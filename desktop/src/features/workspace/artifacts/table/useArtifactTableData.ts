import { useEffect, useMemo, useState } from "react";
import { agentApi } from "../../../../lib/api/agent";
import type { ResultPageRequest, ResultPageResponse } from "../../../../lib/api/types";
import type { ResultViewArtifact, TableArtifact } from "../../../../types/agentArtifact";
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
  search: string;
  setSearch: (value: string) => void;
  sort: SortState | null;
  setSortColumn: (columnIndex: number) => void;
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
  const [backendData, setBackendData] = useState<ResultPageResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [debouncedSearch, setDebouncedSearch] = useState(search);
  const [expanded, setExpanded] = useState(false);

  const isSqlBackedWorkspace = mode === "workspace" && artifact.type === "result_view" && artifact.storageMode === "sql_backed";

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    if (!isSqlBackedWorkspace) return;
    let active = true;
    const fetchPage = async () => {
      setIsLoading(true);
      setFetchError(null);
      try {
        const resultView = artifact as ResultViewArtifact;
        const req: ResultPageRequest = {
          datasourceId: resultView.datasourceId,
          sourceSqlArtifactId: resultView.sourceSqlSemanticId,
          safeSql: resultView.safeSql,
          page,
          pageSize,
          sort: sort ? [{ column: artifact.columns[sort.columnIndex], direction: sort.direction }] : undefined,
          search: debouncedSearch.trim() || undefined,
          countMode: "estimate",
        };
        const res = await agentApi.fetchResultPage(req);
        if (active) setBackendData(res);
      } catch (err) {
        if (active) setFetchError(err instanceof Error ? err.message : String(err));
      } finally {
        if (active) setIsLoading(false);
      }
    };
    void fetchPage();
    return () => {
      active = false;
    };
  }, [isSqlBackedWorkspace, artifact, page, pageSize, sort, debouncedSearch]);

  const rowsToUse = artifact.type === "result_view" ? (artifact.rows ?? artifact.previewRows) : artifact.rows;

  const backendRows = useMemo(() => {
    if (!backendData) return [];
    return backendData.rows.map((row) =>
      backendData.columns.map((col) => {
        const val = row[col];
        return typeof val === "object" && val !== null ? JSON.stringify(val) : String(val ?? "");
      }),
    );
  }, [backendData]);

  const csv = useMemo(
    () => toCsv(artifact.columns, isSqlBackedWorkspace ? backendRows : rowsToUse),
    [artifact.columns, backendRows, isSqlBackedWorkspace, rowsToUse],
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

  const setSortColumn = (columnIndex: number) => {
    setSort((current) => {
      if (current?.columnIndex !== columnIndex) return { columnIndex, direction: "desc" };
      return { columnIndex, direction: current.direction === "desc" ? "asc" : "desc" };
    });
    setPage(1);
  };

  return {
    search,
    setSearch,
    sort,
    setSortColumn,
    page,
    setPage,
    pageSize,
    setPageSize,
    visibleRows,
    filteredAndSortedRows,
    totalRows: isSqlBackedWorkspace ? (backendData?.rowCount ?? undefined) : (artifact.rowCount ?? rowsToUse.length),
    returnedRows: isSqlBackedWorkspace ? backendRows.length : (artifact.returnedRows ?? rowsToUse.length),
    previewCount: visibleRows.length,
    warnings: isSqlBackedWorkspace ? (backendData?.warnings ?? []) : (artifact.warnings ?? []),
    notices: isSqlBackedWorkspace ? (backendData?.notices ?? []) : (artifact.notices ?? []),
    latencyMs: isSqlBackedWorkspace ? backendData?.latencyMs : artifact.latencyMs,
    isLoading,
    fetchError,
    isSqlBackedWorkspace,
    shouldUseWindow,
    expanded,
    setExpanded,
    csv,
    rowsToUseLength: rowsToUse.length,
    isSearching,
    hasNextPage: Boolean(backendData?.hasNextPage),
  };
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
