import {
  clearDiagnosticLogsApiV1DiagnosticsLogsClearPost,
  clearSecurityAuditApiV1DiagnosticsSecurityAuditClearPost,
  getDiagnosticLogsApiV1DiagnosticsLogsGet,
} from "./generated/sdk.gen";
import type {
  DiagnosticLogsResponse,
  DiagnosticLogSourceResponse,
} from "./generated/types.gen";

export type DiagnosticLogSource = DiagnosticLogSourceResponse;
export type { DiagnosticLogsResponse };

export const diagnosticsApi = {
  async getLogs(maxLines = 300) {
    const { data } = await getDiagnosticLogsApiV1DiagnosticsLogsGet({
      query: { max_lines: maxLines },
      throwOnError: true,
    });
    return data;
  },

  async clearLogs() {
    const { data } = await clearDiagnosticLogsApiV1DiagnosticsLogsClearPost({
      throwOnError: true,
    });
    return data;
  },

  async clearSecurityAudit(confirmText: string) {
    const { data } = await clearSecurityAuditApiV1DiagnosticsSecurityAuditClearPost({
      body: { confirm_text: confirmText },
      throwOnError: true,
    });
    return data;
  },
};
