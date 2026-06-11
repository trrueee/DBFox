import { request } from "./client";
import type { GuardrailCheckResult, QueryResult } from "./types";

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
};
