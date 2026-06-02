import { request } from "./client";
import type { BackupRecord, DangerousOperationResult } from "./types";

export const backupApi = {
  listBackups: (projectId: string, datasourceId?: string) =>
    request<BackupRecord[]>(
      `/projects/${encodeURIComponent(projectId)}/backups${
        datasourceId ? `?datasource_id=${encodeURIComponent(datasourceId)}` : ""
      }`,
    ),

  createBackup: (datasourceId: string, label?: string) =>
    request<BackupRecord>("/backups", {
      method: "POST",
      body: JSON.stringify({ datasource_id: datasourceId, label }),
    }),

  restorePrecheck: (backupId: string) =>
    request<{
      ok: boolean;
      warnings: string[];
      errors: string[];
      filePath: string;
      fileSizeBytes: number;
      checksumSha256?: string;
    }>(`/backups/${backupId}/restore-precheck`, { method: "POST" }),

  restoreBackup: (backupId: string, confirm?: { token: string; text: string }) => {
    const query = confirm ? `?confirm_token=${encodeURIComponent(confirm.token)}&confirm_text=${encodeURIComponent(confirm.text)}` : "";
    return request<DangerousOperationResult<{
      success: boolean;
      backup_id: string;
      datasource_id: string;
      database_name: string;
      message: string;
    }>>(`/backups/${backupId}/restore${query}`, { method: "POST" });
  },
};
