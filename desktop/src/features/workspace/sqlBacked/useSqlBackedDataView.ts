import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ResultFilter, ResultSort } from "../../../lib/api/types";
import type {
  SqlBackedDataViewSource,
  SqlBackedExportRequest,
  SqlBackedLoadingMode,
  SqlBackedPageRequest,
  SqlBackedPageResponse,
  UseSqlBackedDataViewOptions,
} from "./sqlBackedTypes";

type SetPageValue = number | ((page: number) => number);

export interface SqlBackedDataViewState {
  source: SqlBackedDataViewSource;
  page: number;
  setPage: (value: SetPageValue) => void;
  pageSize: number;
  setPageSize: (value: number) => void;
  search: string;
  setSearch: (value: string) => void;
  sort: ResultSort[];
  setSort: (value: ResultSort[]) => void;
  filters: ResultFilter[];
  setFilters: (value: ResultFilter[]) => void;
  data: SqlBackedPageResponse | null;
  rows: string[][];
  columns: string[];
  rowCount: number | null | undefined;
  hasNextPage: boolean;
  executedSql: string;
  latencyMs: number | undefined;
  warnings: string[];
  notices: string[];
  error: string | null;
  loadingMode: SqlBackedLoadingMode;
  isLoading: boolean;
  refresh: () => void;
  exportAll: () => Promise<Blob>;
}

export function useSqlBackedDataView({
  source,
  fetchPage,
  exportAll: requestExportAll,
  initialPageSize = 20,
  countMode = "estimate",
}: UseSqlBackedDataViewOptions): SqlBackedDataViewState {
  const [page, setPageState] = useState(1);
  const [pageSize, setPageSizeState] = useState(initialPageSize);
  const [search, setSearchState] = useState("");
  const [sort, setSortState] = useState<ResultSort[]>([]);
  const [filters, setFiltersState] = useState<ResultFilter[]>([]);
  const [data, setData] = useState<SqlBackedPageResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingMode, setLoadingMode] = useState<SqlBackedLoadingMode>("idle");
  const requestSeqRef = useRef(0);
  const nextLoadingModeRef = useRef<SqlBackedLoadingMode>("initial");
  const dataRef = useRef<SqlBackedPageResponse | null>(null);

  const normalizedSearch = search.trim();

  const buildPageRequest = useCallback((): SqlBackedPageRequest => ({
    source,
    page,
    pageSize,
    sort: sort.length ? sort : undefined,
    filters: filters.length ? filters : undefined,
    search: normalizedSearch || undefined,
    countMode,
  }), [countMode, filters, normalizedSearch, page, pageSize, sort, source]);

  const load = useCallback(async (mode: SqlBackedLoadingMode) => {
    const seq = ++requestSeqRef.current;
    setLoadingMode(dataRef.current ? mode : "initial");
    try {
      const response = await fetchPage(buildPageRequest());
      if (seq !== requestSeqRef.current) return;
      dataRef.current = response;
      setData(response);
      setError(null);
    } catch (err) {
      if (seq !== requestSeqRef.current) return;
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (seq === requestSeqRef.current) setLoadingMode("idle");
    }
  }, [buildPageRequest, fetchPage]);

  useEffect(() => {
    const mode = nextLoadingModeRef.current;
    nextLoadingModeRef.current = data ? "refresh" : "initial";
    void load(mode);
  }, [load]);

  const setPage = useCallback((value: SetPageValue) => {
    nextLoadingModeRef.current = "page";
    setPageState(value);
  }, []);

  const setPageSize = useCallback((value: number) => {
    nextLoadingModeRef.current = "page";
    setPageSizeState(value);
    setPageState(1);
  }, []);

  const setSearch = useCallback((value: string) => {
    nextLoadingModeRef.current = "filter";
    setSearchState(value);
    setPageState(1);
  }, []);

  const setSort = useCallback((value: ResultSort[]) => {
    nextLoadingModeRef.current = "filter";
    setSortState(value);
    setPageState(1);
  }, []);

  const setFilters = useCallback((value: ResultFilter[]) => {
    nextLoadingModeRef.current = "filter";
    setFiltersState(value);
    setPageState(1);
  }, []);

  const refresh = useCallback(() => {
    nextLoadingModeRef.current = "refresh";
    void load("refresh");
  }, [load]);

  const handleExportAll = useCallback(async () => {
    const req: SqlBackedExportRequest = {
      source,
      sort: sort.length ? sort : undefined,
      filters: filters.length ? filters : undefined,
      search: normalizedSearch || undefined,
    };
    setLoadingMode("export");
    try {
      return await requestExportAll(req);
    } finally {
      setLoadingMode("idle");
    }
  }, [filters, normalizedSearch, requestExportAll, sort, source]);

  const columns = data?.columns ?? source.columns;
  const rows = useMemo(
    () => (data?.rows ?? []).map((row) => columns.map((column) => stringifyCell(row[column]))),
    [columns, data?.rows],
  );

  return {
    source,
    page,
    setPage,
    pageSize,
    setPageSize,
    search,
    setSearch,
    sort,
    setSort,
    filters,
    setFilters,
    data,
    rows,
    columns,
    rowCount: data?.rowCount,
    hasNextPage: Boolean(data?.hasNextPage),
    executedSql: data?.executedSql ?? "",
    latencyMs: data?.latencyMs,
    warnings: data?.warnings ?? [],
    notices: data?.notices ?? [],
    error,
    loadingMode,
    isLoading: loadingMode !== "idle",
    refresh,
    exportAll: handleExportAll,
  };
}

function stringifyCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
