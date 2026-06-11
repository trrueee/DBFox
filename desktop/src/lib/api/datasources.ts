import { request } from "./client";
import type { DangerousOperationResult, DataSource, DataSourceHealthResult, DataSourceTestResult, SchemaSyncResult } from "./types";

export const datasourcesApi = {
  testConnection: (params: unknown) =>
    request<DataSourceTestResult>("/datasources/test", { method: "POST", body: JSON.stringify(params) }),

  createDatasource: (params: unknown) =>
    request<DataSource>("/datasources", { method: "POST", body: JSON.stringify(params) }),

  listDatasources: (projectId?: string) =>
    request<DataSource[]>(projectId ? `/datasources?project_id=${encodeURIComponent(projectId)}` : "/datasources"),

  checkDatasourceHealth: (id: string) =>
    request<DataSourceHealthResult>(`/datasources/${id}/health`, { method: "POST" }),

  deleteDatasource: (id: string, confirm?: { token: string; text: string }) => {
    const query = confirm ? `?confirm_token=${encodeURIComponent(confirm.token)}&confirm_text=${encodeURIComponent(confirm.text)}` : "";
    return request<DangerousOperationResult<{ success: boolean; message: string }>>(`/datasources/${id}${query}`, { method: "DELETE" });
  },

  syncSchema: (id: string) =>
    request<SchemaSyncResult>(`/datasources/${id}/sync`, { method: "POST" }),
};
