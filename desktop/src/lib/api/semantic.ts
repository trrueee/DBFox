import { request } from "./client";
import type {
  SemanticAlias,
  SemanticAliasCreateParams,
  SemanticAliasUpdateParams,
  SemanticDimension,
  SemanticDimensionCreateParams,
  SemanticDimensionUpdateParams,
  SemanticMetric,
  SemanticMetricCreateParams,
  SemanticMetricUpdateParams,
  WorkspaceTableScope,
  WorkspaceTableScopeUpdateParams,
} from "./types";

export const semanticApi = {
  // Aliases
  listSemanticAliases: (datasourceId: string) =>
    request<SemanticAlias[]>(`/semantic/aliases?datasource_id=${encodeURIComponent(datasourceId)}`),

  createSemanticAlias: (params: SemanticAliasCreateParams) =>
    request<SemanticAlias>("/semantic/aliases", { method: "POST", body: JSON.stringify(params) }),

  updateSemanticAlias: (id: string, params: SemanticAliasUpdateParams) =>
    request<SemanticAlias>(`/semantic/aliases/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(params) }),

  deleteSemanticAlias: (id: string) =>
    request<{ success: boolean; message: string }>(`/semantic/aliases/${encodeURIComponent(id)}`, { method: "DELETE" }),

  // Metrics
  listSemanticMetrics: (datasourceId: string) =>
    request<SemanticMetric[]>(`/semantic/metrics?datasource_id=${encodeURIComponent(datasourceId)}`),

  createSemanticMetric: (params: SemanticMetricCreateParams) =>
    request<SemanticMetric>("/semantic/metrics", { method: "POST", body: JSON.stringify(params) }),

  updateSemanticMetric: (id: string, params: SemanticMetricUpdateParams) =>
    request<SemanticMetric>(`/semantic/metrics/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(params) }),

  deleteSemanticMetric: (id: string) =>
    request<{ success: boolean; message: string }>(`/semantic/metrics/${encodeURIComponent(id)}`, { method: "DELETE" }),

  // Dimensions
  listSemanticDimensions: (datasourceId: string) =>
    request<SemanticDimension[]>(`/semantic/dimensions?datasource_id=${encodeURIComponent(datasourceId)}`),

  createSemanticDimension: (params: SemanticDimensionCreateParams) =>
    request<SemanticDimension>("/semantic/dimensions", { method: "POST", body: JSON.stringify(params) }),

  updateSemanticDimension: (id: string, params: SemanticDimensionUpdateParams) =>
    request<SemanticDimension>(`/semantic/dimensions/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(params) }),

  deleteSemanticDimension: (id: string) =>
    request<{ success: boolean; message: string }>(`/semantic/dimensions/${encodeURIComponent(id)}`, { method: "DELETE" }),

  // Table Scope
  getWorkspaceTableScope: (projectId: string, datasourceId: string) =>
    request<WorkspaceTableScope[]>(
      `/semantic/table-scope?project_id=${encodeURIComponent(projectId)}&datasource_id=${encodeURIComponent(datasourceId)}`
    ),

  updateWorkspaceTableScope: (params: WorkspaceTableScopeUpdateParams) =>
    request<{ success: boolean; message: string }>("/semantic/table-scope", { method: "POST", body: JSON.stringify(params) }),
};
