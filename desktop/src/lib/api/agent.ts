import { request, requestBlob } from "./client";
import type {
  ConsoleExecuteRequest,
  ConsoleExecuteResponse,
  ChartDataResponse,
  ResultExportRequest,
  ResultPageRequest,
  ResultPageResponse,
  TableResultExportRequest,
  TableResultPageRequest,
} from "./types";


export const agentApi = {
  executeSqlConsole: (value: ConsoleExecuteRequest) =>
    request<ConsoleExecuteResponse>("/agent/console/execute", {
      method: "POST",
      body: JSON.stringify(value),
    }),

  fetchArtifactPage: (artifactId: string, value: ResultPageRequest, signal?: AbortSignal) =>
    request<ResultPageResponse>(`/artifacts/${encodeURIComponent(artifactId)}/page`, {
      method: "POST",
      body: JSON.stringify(value),
      signal,
    }),

  fetchArtifactChartData: (artifactId: string) =>
    request<ChartDataResponse>(`/artifacts/${encodeURIComponent(artifactId)}/chart-data`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  exportArtifactCsv: (artifactId: string, value: ResultExportRequest) =>
    requestBlob(`/artifacts/${encodeURIComponent(artifactId)}/export`, {
      method: "POST",
      body: JSON.stringify(value),
    }),

  fetchTableResultPage: (value: TableResultPageRequest) =>
    request<ResultPageResponse>("/agent/results/table/page", {
      method: "POST",
      body: JSON.stringify(value),
    }),

  exportTableResultCsv: (value: TableResultExportRequest) =>
    requestBlob("/agent/results/table/export", {
      method: "POST",
      body: JSON.stringify(value),
    }),
};


export interface LlmTestResponse {
  ok: boolean;
  model: string;
  api_base: string;
  latency_ms: number;
  error_code: string | null;
  error_message: string | null;
}


export function testLlmConnection(
  llmCredentialId: string,
  apiBase: string,
  modelName: string,
): Promise<LlmTestResponse> {
  return request<LlmTestResponse>("/agent/llm/test", {
    method: "POST",
    body: JSON.stringify({
      llm_credential_id: llmCredentialId,
      api_base: apiBase,
      model_name: modelName,
    }),
  });
}
