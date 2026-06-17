import { request } from "./client";
import type {
  DangerousOperationResult,
  DataSource,
  DataSourceCreateParams,
  DataSourceHealthResult,
  DataSourceTestParams,
  DataSourceTestResult,
  DataSourceUpdateParams,
  DeleteConfirm,
  SchemaSyncResult,
} from "./types";

export const datasourcesApi = {
  testConnection: (params: DataSourceTestParams) =>
    request<DataSourceTestResult>("/datasources/test", { method: "POST", body: JSON.stringify(params) }),

  createDatasource: (params: DataSourceCreateParams) =>
    request<DataSource>("/datasources", { method: "POST", body: JSON.stringify(params) }),

  listDatasources: (projectId?: string) =>
    request<DataSource[]>(projectId ? `/datasources?project_id=${encodeURIComponent(projectId)}` : "/datasources"),

  checkDatasourceHealth: (id: string) =>
    request<DataSourceHealthResult>(`/datasources/${id}/health`, { method: "POST" }),

  deleteDatasource: (id: string, confirm?: DeleteConfirm) => {
    const query = confirm ? `?confirm_token=${encodeURIComponent(confirm.token)}&confirm_text=${encodeURIComponent(confirm.text)}` : "";
    return request<DangerousOperationResult<{ success: boolean; message: string }>>(`/datasources/${id}${query}`, { method: "DELETE" });
  },

  updateDatasource: (id: string, params: DataSourceUpdateParams) =>
    request<DataSource>(`/datasources/${id}`, { method: "PUT", body: JSON.stringify(params) }),

  syncSchema: (id: string) =>
    request<SchemaSyncResult>(`/datasources/${id}/sync`, { method: "POST" }),

  releaseDatasource: (id: string) =>
    request<{ success: boolean; message: string }>(`/datasources/${id}/release`, { method: "POST" }),
};
