import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Database, FileArchive, Plus, RefreshCw, ShieldCheck, ShieldAlert, X, Loader2, Play } from "lucide-react";
import { api } from "../lib/api";
import type { BackupRecord, DataSource, Project } from "../lib/api";
import { StatusIndicator } from "../components/StatusIndicator";
import { DangerConfirmDialog, type ConfirmationDetails } from "../components/DangerConfirmDialog";

interface BackupsPageProps {
  activeProject: Project | null;
  datasources: DataSource[];
  activeDataSource: DataSource | null;
}

export const BackupsPage = ({ activeProject, datasources, activeDataSource }: BackupsPageProps) => {
  const [backups, setBackups] = useState<BackupRecord[]>([]);
  const [selectedDatasourceId, setSelectedDatasourceId] = useState(activeDataSource?.id ?? "");
  const [label, setLabel] = useState("");
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [precheck, setPrecheck] = useState<{
    backupId: string;
    ok: boolean;
    warnings: string[];
    errors: string[];
    fileSizeBytes?: number;
    filePath?: string;
  } | null>(null);
  const [error, setError] = useState("");

  // Restore state
  const [restoringBackup, setRestoringBackup] = useState<BackupRecord | null>(null);
  const [restoreConfirmed, setRestoreConfirmed] = useState(false);
  const [restoreConfirmDbName, setRestoreConfirmDbName] = useState("");
  const [restoring, setRestoring] = useState(false);
  const [restoreError, setRestoreError] = useState("");
  const [restoreSuccess, setRestoreSuccess] = useState(false);
  const [confirmDetails, setConfirmDetails] = useState<ConfirmationDetails | null>(null);

  useEffect(() => {
    setSelectedDatasourceId(activeDataSource?.id ?? datasources[0]?.id ?? "");
  }, [activeDataSource?.id, datasources]);

  useEffect(() => {
    void refreshBackups();
  }, [activeProject?.id, selectedDatasourceId]);

  const refreshBackups = async () => {
    if (!activeProject) return;
    setLoading(true);
    try {
      setBackups(await api.listBackups(activeProject.id, selectedDatasourceId || undefined));
    } finally {
      setLoading(false);
    }
  };

  const handleCreateBackup = async () => {
    if (!selectedDatasourceId) {
      setError("Please select a datasource before creating a backup.");
      return;
    }
    setCreating(true);
    setError("");
    try {
      const created = await api.createBackup(selectedDatasourceId, label);
      setBackups((items) => [created, ...items]);
      setLabel("");
    } catch (err: any) {
      setError(err.message ?? "Backup failed.");
    } finally {
      setCreating(false);
    }
  };

  const handlePrecheck = async (backup: BackupRecord) => {
    setError("");
    try {
      const result = await api.restorePrecheck(backup.id);
      setPrecheck({
        backupId: backup.id,
        ok: result.ok,
        warnings: result.warnings,
        errors: result.errors,
        fileSizeBytes: result.fileSizeBytes,
        filePath: result.filePath,
      });
    } catch (err: any) {
      setError(err.message ?? "Restore precheck failed.");
    }
  };

  const handleOpenRestoreModal = async (backup: BackupRecord) => {
    setRestoringBackup(backup);
    setRestoreConfirmed(false);
    setRestoreConfirmDbName("");
    setRestoreError("");
    setRestoreSuccess(false);
    
    // Automatically run precheck
    try {
      const result = await api.restorePrecheck(backup.id);
      setPrecheck({
        backupId: backup.id,
        ok: result.ok,
        warnings: result.warnings,
        errors: result.errors,
        fileSizeBytes: result.fileSizeBytes,
        filePath: result.filePath,
      });
    } catch (err: any) {
      setRestoreError(err.message ?? "Restore precheck failed.");
    }
  };

  const handleExecuteRestore = async () => {
    if (!restoringBackup) return;
    const ds = datasources.find((item) => item.id === restoringBackup.datasource_id);
    if (!ds) return;

    if (ds.env === "prod" && restoreConfirmDbName !== ds.database_name) {
      setRestoreError("数据库名称输入错误，请重新确认！");
      return;
    }
    if (!restoreConfirmed) {
      setRestoreError("您必须勾选确认选项以执行恢复！");
      return;
    }

    setRestoring(true);
    setRestoreError("");
    try {
      const res = await api.restoreBackup(restoringBackup.id);
      if (res && typeof res === "object" && "requires_confirmation" in res && res.requires_confirmation) {
        setConfirmDetails({
          confirm_token: res.confirm_token,
          impact_summary: res.impact_summary,
          expected_confirm_text: res.expected_confirm_text,
          onConfirm: async (text) => {
            await api.restoreBackup(restoringBackup.id, { token: res.confirm_token, text });
            setConfirmDetails(null);
            setRestoreSuccess(true);
            void refreshBackups();
          },
          onCancel: () => setConfirmDetails(null),
        });
        return;
      }
      setRestoreSuccess(true);
      void refreshBackups();
    } catch (err: any) {
      setRestoreError(err.message ?? "Database restore failed.");
    } finally {
      setRestoring(false);
    }
  };

  const datasourceName = (id: string) => datasources.find((item) => item.id === id)?.name ?? id;

  const statusType = (backup: BackupRecord) => {
    if (backup.status === "success") return "success";
    if (backup.status === "failed") return "error";
    return "idle";
  };

  const formatBytes = (bytes?: number) => {
    if (!bytes) return "-";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  };

  return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", gap: 20, height: "100%", overflow: "auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h2 className="text-display" style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)" }}>
            Backup Vault
          </h2>
          <p style={{ color: "var(--text-secondary)", marginTop: 4, fontSize: "0.9rem" }}>
            Create auditable MySQL dumps and run restore prechecks before risky operations.
          </p>
          {activeProject && (
            <p style={{ color: "var(--text-muted)", marginTop: 6, fontSize: "0.78rem" }}>
              Current project: {activeProject.name}
            </p>
          )}
        </div>
        <button className="btn-secondary" onClick={() => void refreshBackups()} disabled={loading || !activeProject}>
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      <div className="lab-card" style={{ padding: 20 }}>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(220px, 0.8fr) minmax(0, 1fr) auto", gap: 12, alignItems: "end" }}>
          <div>
            <label className="field-label">Datasource</label>
            <select
              className="input-field"
              value={selectedDatasourceId}
              onChange={(event) => setSelectedDatasourceId(event.target.value)}
              style={{ background: "var(--bg-primary)", color: "var(--text-primary)" }}
            >
              <option value="">Select datasource</option>
              {datasources.map((datasource) => (
                <option key={datasource.id} value={datasource.id}>
                  {datasource.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="field-label">Backup label</label>
            <input
              className="input-field"
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              placeholder="Before migration, release snapshot, etc."
            />
          </div>
          <button className="btn-primary" onClick={handleCreateBackup} disabled={creating || !selectedDatasourceId}>
            {creating ? <RefreshCw size={14} className="animate-spin" /> : <Plus size={14} />}
            {creating ? "Backing up..." : "Create backup"}
          </button>
        </div>
        <p style={{ marginTop: 10, color: "var(--text-muted)", fontSize: "0.78rem" }}>
          Uses local `mysqldump`; passwords are not placed on the command line. Built-in mock demo datasources are not dumpable.
        </p>
        {error && (
          <div style={{ marginTop: 12 }}>
            <StatusIndicator type="error" label={error} />
          </div>
        )}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {loading ? (
          <>
            <div className="skeleton" style={{ height: 96, borderRadius: 12 }} />
            <div className="skeleton" style={{ height: 96, borderRadius: 12 }} />
          </>
        ) : backups.length === 0 ? (
          <div className="lab-card" style={{ padding: 48, textAlign: "center" }}>
            <FileArchive size={38} style={{ color: "var(--text-muted)", opacity: 0.35, marginBottom: 12 }} />
            <div className="empty-state-title">No backups yet</div>
            <div className="empty-state-desc" style={{ marginTop: 4 }}>
              Create a backup before migrations, imports, or destructive schema changes.
            </div>
          </div>
        ) : (
          backups.map((backup) => {
            const currentPrecheck = precheck?.backupId === backup.id ? precheck : null;
            return (
              <div key={backup.id} className="lab-card hover-lift" style={{ padding: 18 }}>
                <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: 16, alignItems: "center" }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                      <FileArchive size={16} style={{ color: "var(--accent-indigo)" }} />
                      <h3 style={{ fontSize: "1rem", fontWeight: 700 }}>{backup.label || "Untitled backup"}</h3>
                      <StatusIndicator type={statusType(backup)} label={backup.status} />
                      {currentPrecheck && (
                        <span className={currentPrecheck.ok ? "tag tag-green" : "tag tag-error"}>
                          {currentPrecheck.ok ? "precheck ok" : "precheck failed"}
                        </span>
                      )}
                    </div>
                    <div style={{ display: "flex", gap: 16, color: "var(--text-muted)", fontSize: "0.78rem", fontFamily: "var(--font-mono)", flexWrap: "wrap" }}>
                      <span>{datasourceName(backup.datasource_id)}</span>
                      <span>{backup.backup_type}</span>
                      <span>{formatBytes(backup.file_size_bytes)}</span>
                      <span>{backup.duration_ms ?? "-"} ms</span>
                    </div>
                    <p style={{ marginTop: 8, color: "var(--text-muted)", fontSize: "0.76rem", fontFamily: "var(--font-mono)", overflowWrap: "anywhere" }}>
                      {backup.file_path || "No file path recorded"}
                    </p>
                    {backup.error_message && (
                      <p style={{ marginTop: 8, color: "var(--accent-red)", fontSize: "0.78rem" }}>{backup.error_message}</p>
                    )}
                    {currentPrecheck && (currentPrecheck.errors.length > 0 || currentPrecheck.warnings.length > 0) && (
                      <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 4, fontSize: "0.78rem" }}>
                        {currentPrecheck.errors.map((item) => (
                          <span key={item} style={{ color: "var(--accent-red)", display: "flex", alignItems: "center", gap: 5 }}>
                            <AlertTriangle size={13} /> {item}
                          </span>
                        ))}
                        {currentPrecheck.warnings.map((item) => (
                          <span key={item} style={{ color: "var(--accent-amber)", display: "flex", alignItems: "center", gap: 5 }}>
                            <AlertTriangle size={13} /> {item}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", flexWrap: "wrap" }}>
                    <button className="btn-ghost" onClick={() => void handlePrecheck(backup)}>
                      {currentPrecheck?.ok ? <CheckCircle2 size={14} /> : <ShieldCheck size={14} />}
                      Restore precheck
                    </button>
                    {backup.status === "success" && (
                      <button className="btn-secondary" style={{ borderColor: "var(--accent-indigo)", color: "var(--accent-indigo)" }} onClick={() => void handleOpenRestoreModal(backup)}>
                        <Play size={14} />
                        Restore database
                      </button>
                    )}
                    {backup.datasource_id && (
                      <button
                        className="btn-ghost"
                        onClick={() => {
                          const datasource = datasources.find((item) => item.id === backup.datasource_id);
                          if (datasource) setSelectedDatasourceId(datasource.id);
                        }}
                      >
                        <Database size={14} />
                        Select source
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {restoringBackup && (() => {
        const ds = datasources.find(item => item.id === restoringBackup.datasource_id);
        const isProd = ds?.env === "prod";
        const dbName = ds?.database_name ?? "";
        const currentPrecheck = precheck?.backupId === restoringBackup.id ? precheck : null;
        const hasErrors = currentPrecheck ? currentPrecheck.errors.length > 0 : false;
        
        return (
          <div
            style={{
              position: "fixed",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: "rgba(15, 17, 23, 0.75)",
              backdropFilter: "blur(6px)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 9999,
              padding: 24,
              animation: "fadeIn 0.2s ease",
            }}
          >
            <div
              className="lab-card lab-card-elevated"
              style={{
                width: "100%",
                maxWidth: 580,
                maxHeight: "90vh",
                display: "flex",
                flexDirection: "column",
                overflow: "hidden",
                border: "1px solid var(--border-light)",
                boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2)",
              }}
            >
              {/* Header */}
              <div
                style={{
                  padding: "16px 20px",
                  borderBottom: "1px solid var(--border-light)",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  background: isProd ? "rgba(239, 68, 68, 0.08)" : "var(--bg-secondary)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  {isProd ? (
                    <ShieldAlert size={20} style={{ color: "var(--accent-red)" }} />
                  ) : (
                    <Play size={18} style={{ color: "var(--accent-indigo)" }} />
                  )}
                  <h4 style={{ margin: 0, fontSize: "1.05rem", fontWeight: 700 }}>
                    {restoreSuccess ? "数据库恢复成功" : "确认恢复数据库数据"}
                  </h4>
                </div>
                <button
                  style={{
                    border: "none",
                    background: "transparent",
                    color: "var(--text-muted)",
                    cursor: "pointer",
                    padding: 4,
                    display: "flex",
                    alignItems: "center",
                    borderRadius: "50%",
                  }}
                  onClick={() => setRestoringBackup(null)}
                  disabled={restoring}
                >
                  <X size={16} />
                </button>
              </div>

              {/* Scrollable Content */}
              <div style={{ padding: 20, overflow: "auto", display: "flex", flexDirection: "column", gap: 16 }}>
                {restoreSuccess ? (
                  <div style={{ textAlign: "center", padding: "20px 0" }}>
                    <div style={{ display: "inline-flex", padding: 12, borderRadius: "50%", background: "rgba(16, 185, 129, 0.15)", color: "var(--accent-green)", marginBottom: 12 }}>
                      <CheckCircle2 size={40} />
                    </div>
                    <h4 style={{ fontSize: "1.2rem", fontWeight: 700, marginBottom: 8, color: "var(--text-primary)" }}>
                      数据库恢复执行成功！
                    </h4>
                    <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", maxWidth: 400, margin: "0 auto 20px" }}>
                      已成功将备份文件导入到目标数据库 <strong>{dbName}</strong>，并且后台已自动触发 Schema Sync 以刷新表结构元数据。
                    </p>
                    <button className="btn-primary" style={{ margin: "0 auto" }} onClick={() => setRestoringBackup(null)}>
                      我知道了
                    </button>
                  </div>
                ) : (
                  <>
                    {/* Backup File Info */}
                    <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: 12, borderRadius: 8, background: "var(--bg-secondary)", border: "1px solid var(--border-light)", fontSize: "0.85rem" }}>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span style={{ color: "var(--text-muted)" }}>备份标签:</span>
                        <strong style={{ color: "var(--text-primary)" }}>{restoringBackup.label || "未命名备份"}</strong>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span style={{ color: "var(--text-muted)" }}>目标数据库:</span>
                        <strong style={{ color: "var(--text-primary)" }}>{datasourceName(restoringBackup.datasource_id)} ({ds?.host})</strong>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span style={{ color: "var(--text-muted)" }}>备份文件路径:</span>
                        <span style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: "0.78rem", wordBreak: "break-all", textAlign: "right" }}>{restoringBackup.file_path}</span>
                      </div>
                    </div>

                    {/* Precheck display */}
                    <div>
                      <h5 style={{ fontSize: "0.85rem", fontWeight: 700, marginBottom: 8 }}>预检查报告：</h5>
                      {!currentPrecheck ? (
                        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.85rem", color: "var(--text-muted)" }}>
                          <Loader2 size={14} className="animate-spin" />
                          正在运行恢复前预检查...
                        </div>
                      ) : (
                        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <span className={currentPrecheck.ok ? "tag tag-green" : "tag tag-error"}>
                              {currentPrecheck.ok ? "Precheck OK" : "Precheck Failed"}
                            </span>
                            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                              文件大小：{formatBytes(currentPrecheck.fileSizeBytes)}
                            </span>
                          </div>

                          {currentPrecheck.errors.length > 0 && (
                            <div style={{ padding: 12, borderRadius: 8, background: "rgba(239, 68, 68, 0.08)", border: "1px solid rgba(239, 68, 68, 0.2)", display: "flex", flexDirection: "column", gap: 4 }}>
                              {currentPrecheck.errors.map(err => (
                                <div key={err} style={{ color: "var(--accent-red)", fontSize: "0.8rem", display: "flex", alignItems: "center", gap: 6 }}>
                                  <AlertTriangle size={14} /> {err}
                                </div>
                              ))}
                            </div>
                          )}

                          {currentPrecheck.warnings.length > 0 && (
                            <div style={{ padding: 12, borderRadius: 8, background: "rgba(245, 158, 11, 0.08)", border: "1px solid rgba(245, 158, 11, 0.2)", display: "flex", flexDirection: "column", gap: 4 }}>
                              {currentPrecheck.warnings.map(warn => (
                                <div key={warn} style={{ color: "var(--accent-amber)", fontSize: "0.8rem", display: "flex", alignItems: "center", gap: 6 }}>
                                  <AlertTriangle size={14} /> {warn}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Safety Sandbox warning */}
                    {isProd && (
                      <div className="animate-pulse" style={{ padding: 14, borderRadius: 8, background: "rgba(239, 68, 68, 0.12)", border: "1px solid var(--accent-red)", color: "var(--accent-red)", fontSize: "0.85rem", fontWeight: 600, display: "flex", gap: 8, alignItems: "flex-start" }}>
                        <ShieldAlert size={18} style={{ flexShrink: 0, marginTop: 2 }} />
                        <div>
                          <strong>警告：当前目标数据源为生产环境 (PROD)！</strong>
                          <p style={{ fontSize: "0.78rem", fontWeight: 400, marginTop: 4, color: "rgba(239, 68, 68, 0.9)" }}>
                            数据库恢复操作会覆盖或清除目标库中原有的所有数据。请极度小心！该操作完全不可逆。
                          </p>
                        </div>
                      </div>
                    )}

                    {/* Double confirmations */}
                    <div style={{ display: "flex", flexDirection: "column", gap: 12, borderTop: "1px solid var(--border-light)", paddingTop: 16 }}>
                      <label style={{ display: "flex", gap: 8, cursor: "pointer", fontSize: "0.85rem", color: "var(--text-primary)" }}>
                        <input
                          type="checkbox"
                          checked={restoreConfirmed}
                          onChange={(e) => setRestoreConfirmed(e.target.checked)}
                          disabled={hasErrors || restoring}
                          style={{ marginTop: 3 }}
                        />
                        <span>我已知晓并理解：此数据库恢复操作将会强行覆盖目标库 <strong>{dbName}</strong> 的所有已有数据和表。</span>
                      </label>

                      {isProd && (
                        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                          <label className="field-label" style={{ fontSize: "0.8rem", color: "var(--accent-red)", fontWeight: 600 }}>
                            请输入目标数据库名（<strong>{dbName}</strong>）以确认：
                          </label>
                          <input
                            className="input-field"
                            value={restoreConfirmDbName}
                            onChange={(e) => setRestoreConfirmDbName(e.target.value)}
                            placeholder={dbName}
                            disabled={hasErrors || restoring}
                            style={{ borderColor: restoreConfirmDbName === dbName ? "var(--accent-green)" : "var(--accent-red)" }}
                          />
                        </div>
                      )}
                    </div>

                    {restoreError && (
                      <StatusIndicator type="error" label={restoreError} />
                    )}

                    {/* Actions */}
                    <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 8 }}>
                      <button className="btn-secondary" onClick={() => setRestoringBackup(null)} disabled={restoring}>
                        取消
                      </button>
                      <button
                        className="btn-primary"
                        onClick={() => void handleExecuteRestore()}
                        disabled={
                          restoring ||
                          hasErrors ||
                          !restoreConfirmed ||
                          (isProd && restoreConfirmDbName !== dbName)
                        }
                        style={{
                          background: isProd ? "var(--accent-red)" : "var(--accent-indigo)",
                          borderColor: isProd ? "var(--accent-red)" : "var(--accent-indigo)",
                          color: "#ffffff"
                        }}
                      >
                        {restoring && <Loader2 size={14} className="animate-spin" />}
                        {restoring ? "正在恢复数据..." : "执行导入恢复"}
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        );
      })()}
      <DangerConfirmDialog details={confirmDetails} />
    </div>
  );
};
