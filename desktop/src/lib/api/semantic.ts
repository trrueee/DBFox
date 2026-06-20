import { request } from "./client";
import type {
  SemanticAlias,
  SemanticAliasCreateParams,
  SemanticAliasUpdateParams,
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

  // NOTE: syncEmbeddings and getSyncStatus were removed in MVP simplification (2026-06-20).
  // AI enrichment is now triggered via datasource sync with ai_enrich: true.
};
