import { request } from "./client";

export interface DiagnosticLogSource {
  name: string;
  path: string;
  exists: boolean;
  size_bytes: number;
  modified_at: string | null;
  content: string;
}

export interface DiagnosticLogsResponse {
  generated_at: string;
  policy: {
    redacted: boolean;
    max_lines_per_source: number;
    omitted: string[];
  };
  environment: Record<string, unknown>;
  sources: DiagnosticLogSource[];
}

export const diagnosticsApi = {
  getLogs: (maxLines = 300) =>
    request<DiagnosticLogsResponse>(
      `/diagnostics/logs?max_lines=${encodeURIComponent(String(maxLines))}`,
    ),

  clearLogs: () =>
    request<{ cleared: boolean; sources_cleared: string[] }>("/diagnostics/logs", {
      method: "DELETE",
    }),
};
