import { request } from "./client";
import type { BenchmarkResult, DeleteResponse, GeneratedSqlResult, GoldenSqlRecord, LlmStats } from "./types";

export const aiApi = {
  generateSql: (datasourceId: string, question: string, config?: { apiKey?: string; apiBase?: string; model?: string; optimizeRag?: boolean }, signal?: AbortSignal) =>
    request<GeneratedSqlResult>("/query/generate", {
      method: "POST",
      body: JSON.stringify({
        datasource_id: datasourceId,
        question,
        api_key: config?.apiKey,
        api_base: config?.apiBase,
        model_name: config?.model,
        optimize_rag: config?.optimizeRag ?? false,
      }),
      signal,
    }),

  listGoldenSql: (datasourceId: string) =>
    request<GoldenSqlRecord[]>(`/golden-sql?datasource_id=${datasourceId}`),

  createGoldenSql: (datasourceId: string, question: string, goldenSql: string) =>
    request<GoldenSqlRecord>("/golden-sql", {
      method: "POST",
      body: JSON.stringify({ datasource_id: datasourceId, question, golden_sql: goldenSql }),
    }),

  deleteGoldenSql: (id: string) =>
    request<DeleteResponse>(`/golden-sql/${id}`, { method: "DELETE" }),

  runBenchmark: (datasourceId: string, config?: { apiKey?: string; apiBase?: string; model?: string; optimizeRag?: boolean }) =>
    request<BenchmarkResult>("/golden-sql/run-benchmark", {
      method: "POST",
      body: JSON.stringify({
        datasource_id: datasourceId,
        api_key: config?.apiKey,
        api_base: config?.apiBase,
        model_name: config?.model,
        optimize_rag: config?.optimizeRag ?? false,
      }),
    }),

  getLlmStats: (datasourceId: string) =>
    request<LlmStats>(`/llm-logs/stats?datasource_id=${datasourceId}`),
};
