import type { ResultFilter, ResultSort } from "../../../lib/api/types";

export type SqlBackedLoadingMode = "idle" | "initial" | "refresh" | "page" | "filter" | "export";

export type SqlBackedDataViewSource =
  | {
      kind: "artifact-result";
      datasourceId: string;
      sourceSqlArtifactId: string;
      safeSql: string;
      columns: string[];
    }
  | {
      kind: "database-table";
      datasourceId: string;
      tableId?: string | null;
      tableName: string;
      columns: string[];
    };

export interface SqlBackedPageRequest {
  source: SqlBackedDataViewSource;
  page: number;
  pageSize: number;
  sort?: ResultSort[];
  filters?: ResultFilter[];
  search?: string;
  countMode?: "none" | "exact" | "estimate";
}

export interface SqlBackedExportRequest {
  source: SqlBackedDataViewSource;
  sort?: ResultSort[];
  filters?: ResultFilter[];
  search?: string;
}

export interface SqlBackedPageResponse {
  columns: string[];
  rows: Record<string, unknown>[];
  page: number;
  pageSize: number;
  rowCount?: number | null;
  hasNextPage: boolean;
  executedSql: string;
  latencyMs: number;
  warnings?: string[] | null;
  notices?: string[] | null;
}

export interface UseSqlBackedDataViewOptions {
  source: SqlBackedDataViewSource;
  fetchPage: (request: SqlBackedPageRequest) => Promise<SqlBackedPageResponse>;
  exportAll: (request: SqlBackedExportRequest) => Promise<Blob>;
  enabled?: boolean;
  initialPageSize?: number;
  countMode?: "none" | "exact" | "estimate";
}
