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
  latencyMs: number | undefined;
  consistency: "live_reexecution" | "live_query" | undefined;
  originalExecutedAt: string | null | undefined;
  viewExecutedAt: string | undefined;
  viewExecutionId: string | undefined;
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
  enabled = true,
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
  const requestControllerRef = useRef<AbortController | null>(null);
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
    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    setLoadingMode(dataRef.current ? mode : "initial");
    try {
      const response = await fetchPage(buildPageRequest(), controller.signal);
      if (seq !== requestSeqRef.current) return;
      dataRef.current = response;
      setData(response);
      setError(null);
    } catch (err) {
      if (seq !== requestSeqRef.current) return;
      if (isAbortError(err)) return;
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (requestControllerRef.current === controller) requestControllerRef.current = null;
      if (seq === requestSeqRef.current) setLoadingMode("idle");
    }
  }, [buildPageRequest, fetchPage]);

  useEffect(() => {
    if (!enabled) {
      requestControllerRef.current?.abort();
      requestControllerRef.current = null;
      requestSeqRef.current += 1;
      dataRef.current = null;
      nextLoadingModeRef.current = "initial";
      return undefined;
    }
    const mode = nextLoadingModeRef.current;
    nextLoadingModeRef.current = dataRef.current ? "refresh" : "initial";
    void load(mode);
    return () => {
      requestSeqRef.current += 1;
      requestControllerRef.current?.abort();
      requestControllerRef.current = null;
    };
  }, [enabled, load]);

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
    if (!enabled) return;
    nextLoadingModeRef.current = "refresh";
    void load("refresh");
  }, [enabled, load]);

  const handleExportAll = useCallback(async () => {
    if (!enabled) throw new Error("SQL-backed data view is disabled");
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
  }, [enabled, filters, normalizedSearch, requestExportAll, sort, source]);

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
    latencyMs: data?.latencyMs,
    consistency: data?.consistency,
    originalExecutedAt: data?.originalExecutedAt,
    viewExecutedAt: data?.viewExecutedAt,
    viewExecutionId: data?.viewExecutionId,
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

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
