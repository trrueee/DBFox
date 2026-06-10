import { request } from "./client";
import type { DangerousOperationResult } from "./types";

export const tableDesignApi = {
  generateTestData: (params: { datasource_id: string; table_name: string; row_count?: number; language?: string }, confirm?: { token: string; text: string }) =>
    request<DangerousOperationResult<{ success: boolean; tableName: string; insertedRows: number; latencyMs: number; message: string }>>("/schema/generate-test-data", {
      method: "POST",
      body: JSON.stringify({
        ...params,
        confirm_token: confirm?.token,
        confirm_text: confirm?.text,
      }),
    }),
};
