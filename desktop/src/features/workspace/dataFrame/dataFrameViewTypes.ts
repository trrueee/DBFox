import type { DataFrameFilter, DataFrameSort } from "../../../lib/api/types";

export type DataFrameLoadingMode = "idle" | "initial" | "refresh" | "page" | "filter" | "export";

export interface DataFrameViewSource {
  kind: "artifact-representation";
  artifactId: string;
  representationType: string;
}

export interface DataFramePageRequest {
  source: DataFrameViewSource;
  page: number;
  pageSize: number;
  sort?: DataFrameSort[];
  filters?: DataFrameFilter[];
  search?: string;
  countMode?: "none" | "exact" | "estimate";
}

export interface DataFrameExportRequest {
  source: DataFrameViewSource;
  sort?: DataFrameSort[];
  filters?: DataFrameFilter[];
  search?: string;
}

export interface DataFramePageResponse {
  columns: string[];
  columnTypes: Array<string | undefined>;
  rows: Record<string, unknown>[];
  page: number;
  pageSize: number;
  rowCount?: number | null;
  hasNextPage: boolean;
  latencyMs: number;
  sourceTruncated: boolean;
  consistency: "durable_snapshot" | "live_reexecution";
  originalExecutedAt?: string | null;
  viewExecutedAt: string;
  viewExecutionId: string;
  resourceVersion: string | number;
  sourceFingerprint: string;
  warnings?: string[] | null;
  notices?: string[] | null;
}

export interface UseDataFrameViewOptions {
  source: DataFrameViewSource;
  fetchPage: (request: DataFramePageRequest, signal: AbortSignal) => Promise<DataFramePageResponse>;
  exportAll: (request: DataFrameExportRequest) => Promise<Blob>;
  enabled?: boolean;
  initialPageSize?: number;
  countMode?: "none" | "exact" | "estimate";
}
