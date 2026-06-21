import { request } from "./client";

export interface WorkspaceTableScopeResponse {
  id: string;
  project_id: string;
  data_source_id: string;
  table_id: string;
  enabled: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface WorkspaceTableScopeUpdateRequest {
  project_id: string;
  datasource_id: string;
  enabled_table_ids: string[];
}

export const semanticApi = {
  getTableScope: (projectId: string, datasourceId: string) =>
    request<WorkspaceTableScopeResponse[]>(`/semantic/table-scope?project_id=${encodeURIComponent(projectId)}&datasource_id=${encodeURIComponent(datasourceId)}`),

  updateTableScope: (params: WorkspaceTableScopeUpdateRequest) =>
    request<{ success: boolean; message: string }>("/semantic/table-scope", {
      method: "POST",
      body: JSON.stringify(params),
    }),
};
