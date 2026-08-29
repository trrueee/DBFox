import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DataFrameFilter, DataFrameSort } from "../../../lib/api/types";
import type {
  DataFrameViewSource,
  DataFrameExportRequest,
  DataFrameLoadingMode,
  DataFramePageRequest,
  DataFramePageResponse,
  UseDataFrameViewOptions,
} from "./dataFrameViewTypes";

type SetPageValue = number | ((page: number) => number);

export interface DataFrameViewState {
  source: DataFrameViewSource;
  page: number;
  setPage: (value: SetPageValue) => void;
  pageSize: number;
  setPageSize: (value: number) => void;
  search: string;
  setSearch: (value: string) => void;
  sort: DataFrameSort[];
  setSort: (value: DataFrameSort[]) => void;
  filters: DataFrameFilter[];
  setFilters: (value: DataFrameFilter[]) => void;
  data: DataFramePageResponse | null;
  rows: unknown[][];
  columns: string[];
  columnTypes: Array<string | undefined>;
  rowCount: number | null | undefined;
  hasNextPage: boolean;
  latencyMs: number | undefined;
  consistency: "durable_snapshot" | "live_reexecution" | undefined;
  originalExecutedAt: string | null | undefined;
  viewExecutedAt: string | undefined;
  viewExecutionId: string | undefined;
  warnings: string[];
  notices: string[];
  error: unknown | null;
  loadingMode: DataFrameLoadingMode;
  isLoading: boolean;
  refresh: () => void;
  exportAll: () => Promise<Blob>;
}

export function useDataFrameView({
  source,
  fetchPage,
  exportAll: requestExportAll,
  enabled = true,
  initialPageSize = 20,
  countMode = "estimate",
}: UseDataFrameViewOptions): DataFrameViewState {
  const [page, setPageState] = useState(1);
  const [pageSize, setPageSizeState] = useState(initialPageSize);
  const [search, setSearchState] = useState("");
  const [sort, setSortState] = useState<DataFrameSort[]>([]);
  const [filters, setFiltersState] = useState<DataFrameFilter[]>([]);
  const [data, setData] = useState<DataFramePageResponse | null>(null);
  const [error, setError] = useState<unknown | null>(null);
  const [loadingMode, setLoadingMode] = useState<DataFrameLoadingMode>("idle");
  const requestSeqRef = useRef(0);
  const requestControllerRef = useRef<AbortController | null>(null);
  const nextLoadingModeRef = useRef<DataFrameLoadingMode>("initial");
  const dataRef = useRef<DataFramePageResponse | null>(null);

  const normalizedSearch = search.trim();

  const buildPageRequest = useCallback((): DataFramePageRequest => ({
    source,
    page,
    pageSize,
    sort: sort.length ? sort : undefined,
    filters: filters.length ? filters : undefined,
    search: normalizedSearch || undefined,
    countMode,
  }), [countMode, filters, normalizedSearch, page, pageSize, sort, source]);

  const load = useCallback(async (mode: DataFrameLoadingMode) => {
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
      setError(err);
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

  const setSort = useCallback((value: DataFrameSort[]) => {
    nextLoadingModeRef.current = "filter";
    setSortState(value);
    setPageState(1);
  }, []);

  const setFilters = useCallback((value: DataFrameFilter[]) => {
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
    if (!enabled) throw new Error("当前数据视图尚未就绪");
    const req: DataFrameExportRequest = {
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

  const columns = useMemo(() => data?.columns ?? [], [data?.columns]);
  const rows = useMemo(
    () => (data?.rows ?? []).map((row) => columns.map((column) => row[column])),
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
    columnTypes: data?.columnTypes ?? [],
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

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
