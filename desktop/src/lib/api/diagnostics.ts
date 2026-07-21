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
  security_audit: {
    retention_days: number;
    export_window_days: number;
    max_records: number;
    records: Array<{
      id: string;
      action: string;
      outcome: string;
      actorType: string;
      resourceType: string;
      resourceId: string | null;
      sessionId: string | null;
      runId: string | null;
      correlationId: string;
      details: Record<string, unknown>;
      createdAt: string;
    }>;
  };
}

export const diagnosticsApi = {
  getLogs: (maxLines = 300) =>
    request<DiagnosticLogsResponse>(
      `/diagnostics/logs?max_lines=${encodeURIComponent(String(maxLines))}`,
    ),

  clearLogs: () =>
    request<{ cleared: boolean; sources_cleared: string[] }>("/diagnostics/logs/clear", {
      method: "POST",
    }),

  clearSecurityAudit: (confirmText: string) =>
    request<{ cleared: boolean; records_deleted: number }>("/diagnostics/security-audit/clear", {
      method: "POST",
      body: JSON.stringify({ confirm_text: confirmText }),
    }),
};
