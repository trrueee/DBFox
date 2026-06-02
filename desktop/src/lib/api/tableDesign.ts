import { request } from "./client";
import type {
  DangerousOperationResult,
  DeleteResponse,
  TableDesignAiResponse,
  TableDesignColumn,
  TableDesignDraft,
  TableDesignExecutionResult,
  TableDesignIndex,
} from "./types";

export const tableDesignApi = {
  generateSchemaAlteration: (params: {
    datasource_id: string;
    instruction: string;
    api_key?: string;
    api_base?: string;
    model?: string;
  }) =>
    request<{ ddl: string; model: string; mode: string }>("/schema/design/ai-modify", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  executeTableDesignDDL: (datasourceId: string, ddl: string, confirm?: { token: string; text: string }) =>
    request<DangerousOperationResult<TableDesignExecutionResult>>("/schema/design/execute-ddl", {
      method: "POST",
      body: JSON.stringify({
        datasource_id: datasourceId,
        ddl,
        confirm_token: confirm?.token,
        confirm_text: confirm?.text,
      }),
    }),

  generateTestData: (params: { datasource_id: string; table_name: string; row_count?: number; language?: string }, confirm?: { token: string; text: string }) =>
    request<DangerousOperationResult<{ success: boolean; tableName: string; insertedRows: number; latencyMs: number; message: string }>>("/schema/generate-test-data", {
      method: "POST",
      body: JSON.stringify({
        ...params,
        confirm_token: confirm?.token,
        confirm_text: confirm?.text,
      }),
    }),

  listTableDesignDrafts: (projectId: string) =>
    request<TableDesignDraft[]>(`/schema/design/drafts?project_id=${projectId}`),

  getTableDesignDraft: (draftId: string) =>
    request<TableDesignDraft>(`/schema/design/drafts/${draftId}`),

  saveTableDesignDraft: (req: {
    project_id: string;
    draft_id?: string;
    table_name: string;
    table_comment?: string;
    columns: TableDesignColumn[];
    indexes: TableDesignIndex[];
  }) =>
    request<TableDesignDraft>("/schema/design/drafts/save", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  deleteTableDesignDraft: (draftId: string) =>
    request<DeleteResponse>(`/schema/design/drafts/${draftId}`, { method: "DELETE" }),

  generateTableDesignAi: (prompt: string, config?: { apiKey?: string; apiBase?: string; model?: string }) =>
    request<TableDesignAiResponse>("/schema/design/ai-generate", {
      method: "POST",
      body: JSON.stringify({
        prompt,
        api_key: config?.apiKey,
        api_base: config?.apiBase,
        model_name: config?.model,
      }),
    }),
};
