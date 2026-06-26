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
  SchemaSyncOptions,
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
    return request<DangerousOperationResult<{ success: boolean; message: string }>>(`/datasources/${id}`, {
      method: "DELETE",
      body: confirm ? JSON.stringify({ confirm_token: confirm.token, confirm_text: confirm.text }) : undefined,
    });
  },

  updateDatasource: (id: string, params: DataSourceUpdateParams) =>
    request<DataSource>(`/datasources/${id}`, { method: "PUT", body: JSON.stringify(params) }),

  syncSchema: (id: string, options?: SchemaSyncOptions) =>
    request<SchemaSyncResult>(`/datasources/${id}/sync`, {
      method: "POST",
      body: options ? JSON.stringify(options) : undefined,
    }),

  releaseDatasource: (id: string) =>
    request<{ success: boolean; message: string }>(`/datasources/${id}/release`, { method: "POST" }),
};
