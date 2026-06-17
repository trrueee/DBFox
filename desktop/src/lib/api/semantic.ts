import { request } from "./client";
import type {
  SemanticAlias,
  SemanticAliasCreateParams,
  SemanticAliasUpdateParams,
  SemanticSyncStatus,
} from "./types";

export const semanticApi = {
  listAliases: (datasourceId: string) =>
    request<SemanticAlias[]>(`/semantic/aliases?datasource_id=${encodeURIComponent(datasourceId)}`),

  createAlias: (params: SemanticAliasCreateParams) =>
    request<SemanticAlias>("/semantic/aliases", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  updateAlias: (id: string, params: SemanticAliasUpdateParams) =>
    request<SemanticAlias>(`/semantic/aliases/${id}`, {
      method: "PUT",
      body: JSON.stringify(params),
    }),

  deleteAlias: (id: string) =>
    request<{ success: boolean; message: string }>(`/semantic/aliases/${id}`, {
      method: "DELETE",
    }),

  syncEmbeddings: (datasourceId: string, apiKey?: string, apiBase?: string, modelName?: string) =>
    request<{ success: boolean; synced_count: number; message: string }>(
      `/semantic/aliases/sync-embeddings?datasource_id=${encodeURIComponent(datasourceId)}`,
      {
        method: "POST",
        body: JSON.stringify({
          api_key: apiKey || undefined,
          api_base: apiBase || undefined,
          model_name: modelName || undefined,
        }),
      },
    ),

  getSyncStatus: (datasourceId: string) =>
    request<SemanticSyncStatus>(
      `/semantic/aliases/sync-status?datasource_id=${encodeURIComponent(datasourceId)}`
    ),
};
