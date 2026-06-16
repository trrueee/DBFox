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

  syncEmbeddings: (datasourceId: string, apiKey?: string, apiBase?: string, modelName?: string) => {
    let url = `/semantic/aliases/sync-embeddings?datasource_id=${encodeURIComponent(datasourceId)}`;
    if (apiKey) {
      url += `&api_key=${encodeURIComponent(apiKey)}`;
    }
    if (apiBase) {
      url += `&api_base=${encodeURIComponent(apiBase)}`;
    }
    if (modelName) {
      url += `&model_name=${encodeURIComponent(modelName)}`;
    }
    return request<{ success: boolean; synced_count: number; message: string }>(url, { method: "POST" });
  },

  getSyncStatus: (datasourceId: string) =>
    request<SemanticSyncStatus>(
      `/semantic/aliases/sync-status?datasource_id=${encodeURIComponent(datasourceId)}`
    ),
};
