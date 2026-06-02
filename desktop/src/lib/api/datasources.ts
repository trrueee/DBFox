import { request } from "./client";
import type { DangerousOperationResult, DataSource, DataSourceHealthResult, DataSourceTestResult, DatabaseEnvironment, SchemaSyncResult } from "./types";

export const datasourcesApi = {
  listEnvironments: (projectId: string) =>
    request<DatabaseEnvironment[]>(`/projects/${encodeURIComponent(projectId)}/environments`),

  createLocalMysqlEnvironment: (params: { project_id: string; name: string; mysql_version?: string; seed_demo?: boolean }) =>
    request<DatabaseEnvironment>("/environments/local-mysql", { method: "POST", body: JSON.stringify(params) }),

  startEnvironment: (environmentId: string) =>
    request<DatabaseEnvironment>(`/environments/${environmentId}/start`, { method: "POST" }),

  stopEnvironment: (environmentId: string) =>
    request<DatabaseEnvironment>(`/environments/${environmentId}/stop`, { method: "POST" }),

  checkEnvironmentHealth: (environmentId: string) =>
    request<{ environment: DatabaseEnvironment; health: Record<string, unknown> }>(`/environments/${environmentId}/health`),

  getEnvironmentLogs: (environmentId: string, tail = 200) =>
    request<{ environmentId: string; logs: string }>(`/environments/${environmentId}/logs?tail=${tail}`),

  checkDockerStatus: () =>
    request<{ available: boolean }>("/environments/docker-status"),

  destroyEnvironment: (environmentId: string) =>
    request<{ ok: boolean; message: string }>(`/environments/${environmentId}`, { method: "DELETE" }),

  rebuildEnvironment: (environmentId: string) =>
    request<DatabaseEnvironment>(`/environments/${environmentId}/rebuild`, { method: "POST" }),

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

  startDemoMysql: (projectId?: string) =>
    request<DataSource>("/demo/start", { method: "POST", body: JSON.stringify({ project_id: projectId }) }),
};
