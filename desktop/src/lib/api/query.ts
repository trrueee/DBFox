import { request } from "./client";
import type { GuardrailCheckResult, QueryHistory, QueryResult } from "./types";

export const queryApi = {
  validateSql: (sql: string, options?: { datasourceId?: string; signal?: AbortSignal }) =>
    request<GuardrailCheckResult>("/query/validate", {
      method: "POST",
      body: JSON.stringify({ sql, datasource_id: options?.datasourceId }),
      signal: options?.signal,
    }),

  executeSql: (datasourceId: string, sql: string, question?: string, executionId?: string, signal?: AbortSignal) =>
    request<QueryResult>("/query/execute", {
      method: "POST",
      body: JSON.stringify({ datasource_id: datasourceId, sql, question, execution_id: executionId }),
      signal,
    }),

  cancelQuery: (executionId: string) =>
    request<{ success: boolean; cancelled: boolean; executionId: string; message: string }>("/query/cancel", {
      method: "POST",
      body: JSON.stringify({ execution_id: executionId }),
    }),

  listHistory: (datasourceId?: string, filters?: { search?: string; status?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (datasourceId) params.set("datasource_id", datasourceId);
    if (filters?.search) params.set("search", filters.search);
    if (filters?.status && filters.status !== "all") params.set("status", filters.status);
    if (filters?.limit) params.set("limit", String(filters.limit));
    const query = params.toString();
    return request<QueryHistory[]>(`/query/history${query ? `?${query}` : ""}`);
  },

  deleteHistory: (historyId: string) =>
    request<{ success: boolean; deleted: number }>(`/query/history/${encodeURIComponent(historyId)}`, {
      method: "DELETE",
    }),

  clearHistory: (datasourceId: string) =>
    request<{ success: boolean; deleted: number }>(
      `/query/history?datasource_id=${encodeURIComponent(datasourceId)}`,
      { method: "DELETE" },
    ),
};
