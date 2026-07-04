import { request } from "./client";
import type { GuardrailCheckResult } from "./types";

export const queryApi = {
  validateSql: (sql: string, options?: { datasourceId?: string; signal?: AbortSignal }) =>
    request<GuardrailCheckResult>("/query/validate", {
      method: "POST",
      body: JSON.stringify({ sql, datasource_id: options?.datasourceId }),
      signal: options?.signal,
    }),

  cancelQuery: (executionId: string) =>
    request<{ success: boolean; cancelled: boolean; executionId: string; message: string }>("/query/cancel", {
      method: "POST",
      body: JSON.stringify({ execution_id: executionId }),
    }),
};
