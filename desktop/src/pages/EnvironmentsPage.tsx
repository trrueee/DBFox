import { useEffect, useState } from "react";
import { Activity, Database, FileText, Play, Plus, RefreshCw, Square, Trash2, AlertTriangle, CheckCircle } from "lucide-react";
import { api } from "../lib/api";
import type { DatabaseEnvironment, DataSource, Project } from "../lib/api";
import { StatusIndicator } from "../components/StatusIndicator";

interface EnvironmentsPageProps {
  activeProject: Project | null;
  onRefreshDatasources: () => Promise<void>;
  onSelectDataSource: (ds: DataSource | null) => void;
}

export const EnvironmentsPage = ({
  activeProject,
  onRefreshDatasources,
  onSelectDataSource,
}: EnvironmentsPageProps) => {
  const [environments, setEnvironments] = useState<DatabaseEnvironment[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [name, setName] = useState("Local MySQL Dev");
  const [logs, setLogs] = useState<{ environmentId: string; text: string } | null>(null);
  const [error, setError] = useState("");

  // Docker status & lifecycle states
  const [dockerAvailable, setDockerAvailable] = useState<boolean | null>(null);
  const [checkingDocker, setCheckingDocker] = useState(false);
  const [confirmDestroyEnv, setConfirmDestroyEnv] = useState<DatabaseEnvironment | null>(null);
  const [confirmRebuildEnv, setConfirmRebuildEnv] = useState<DatabaseEnvironment | null>(null);
  const [destroying, setDestroying] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [destroyError, setDestroyError] = useState("");
  const [rebuildError, setRebuildError] = useState("");

  useEffect(() => {
    void checkDocker();
    void refreshEnvironments();
  }, [activeProject?.id]);

  const checkDocker = async () => {
    setCheckingDocker(true);
    try {
      const res = await api.checkDockerStatus();
      setDockerAvailable(res.available);
    } catch {
      setDockerAvailable(false);
    } finally {
      setCheckingDocker(false);
    }
  };

  const refreshEnvironments = async () => {
    if (!activeProject) return;
    setLoading(true);
    try {
      setEnvironments(await api.listEnvironments(activeProject.id));
    } finally {
      setLoading(false);
    }
  };

  const updateEnvironment = (updated: DatabaseEnvironment) => {
    setEnvironments((items) => items.map((item) => (item.id === updated.id ? updated : item)));
  };

  const handleCreate = async () => {
    if (!activeProject) return;
    setCreating(true);
    setError("");
    try {
      const created = await api.createLocalMysqlEnvironment({
        project_id: activeProject.id,
        name: name.trim() || "Local MySQL Dev",
        mysql_version: "8.0",
        seed_demo: true,
      });
      await refreshEnvironments();
      await onRefreshDatasources();
      const sources = await api.listDatasources(activeProject.id);
      onSelectDataSource(sources.find((source) => source.id === created.datasource_id) ?? null);
    } catch (err: any) {
      setError(err.message ?? "Create local MySQL environment failed.");
    } finally {
      setCreating(false);
    }
  };

  const handleStart = async (environment: DatabaseEnvironment) => {
    setBusyId(environment.id);
    try {
      updateEnvironment(await api.startEnvironment(environment.id));
    } finally {
      setBusyId(null);
    }
  };

  const handleStop = async (environment: DatabaseEnvironment) => {
    setBusyId(environment.id);
    try {
      updateEnvironment(await api.stopEnvironment(environment.id));
    } finally {
      setBusyId(null);
    }
  };

  const handleHealth = async (environment: DatabaseEnvironment) => {
    setBusyId(environment.id);
    try {
      const result = await api.checkEnvironmentHealth(environment.id);
      updateEnvironment(result.environment);
    } finally {
      setBusyId(null);
    }
  };

  const handleLogs = async (environment: DatabaseEnvironment) => {
    setBusyId(environment.id);
    try {
      const result = await api.getEnvironmentLogs(environment.id);
      setLogs({ environmentId: environment.id, text: result.logs || "(no logs)" });
    } finally {
      setBusyId(null);
    }
  };

  const handleDestroy = async () => {
    if (!confirmDestroyEnv) return;
    setDestroying(true);
    setDestroyError("");
    try {
      await api.destroyEnvironment(confirmDestroyEnv.id);
      setConfirmDestroyEnv(null);
      await refreshEnvironments();
      await onRefreshDatasources();
    } catch (err: any) {
      setDestroyError(err.message ?? "Destroy environment failed.");
    } finally {
      setDestroying(false);
    }
  };

  const handleRebuild = async () => {
    if (!confirmRebuildEnv) return;
    setRebuilding(true);
    setRebuildError("");
    try {
      const updated = await api.rebuildEnvironment(confirmRebuildEnv.id);
      updateEnvironment(updated);
      setConfirmRebuildEnv(null);
      await refreshEnvironments();
      await onRefreshDatasources();
    } catch (err: any) {
      setRebuildError(err.message ?? "Rebuild environment failed.");
    } finally {
      setRebuilding(false);
    }
  };

  const statusType = (environment: DatabaseEnvironment) => {
    if (environment.last_health_status === "healthy" || environment.status === "running") return "success";
    if (environment.status === "stopped") return "idle";
    return "error";
  };

  return (
    <div className="animate-fade-in" style={{ display: "flex", flexDirection: "column", gap: 20, height: "100%", overflow: "auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h2 className="text-display" style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)" }}>
            Environment Lab
          </h2>
          <p style={{ color: "var(--text-secondary)", marginTop: 4, fontSize: "0.9rem" }}>
            Manage local Docker MySQL environments inside the current project.
          </p>
          {activeProject && (
            <p style={{ color: "var(--text-muted)", marginTop: 6, fontSize: "0.78rem" }}>
              Current project: {activeProject.name}
            </p>
          )}
        </div>
        <button className="btn-secondary" onClick={() => void refreshEnvironments()} disabled={loading || !activeProject}>
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* Docker daemon status banner */}
      {dockerAvailable === false && (
        <div className="lab-card animate-fade-in" style={{
          borderLeft: "4px solid var(--accent-red)",
          background: "rgba(239, 68, 68, 0.05)",
          padding: "16px 20px",
          borderRadius: "12px",
          display: "flex",
          alignItems: "center",
          gap: "14px",
          backdropFilter: "blur(8px)",
          boxShadow: "inset 0 1px 0 rgba(255, 255, 255, 0.05)"
        }}>
          <div style={{
            background: "rgba(239, 68, 68, 0.15)",
            color: "var(--accent-red)",
            width: "36px",
            height: "36px",
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0
          }}>
            <AlertTriangle size={18} className="animate-pulse" />
          </div>
          <div style={{ flex: 1 }}>
            <h4 style={{ fontWeight: 700, color: "var(--text-primary)", fontSize: "0.95rem" }}>
              Docker 运行环境未检测到 (Docker Daemon Offline)
            </h4>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.82rem", marginTop: 2 }}>
              请确保 Docker Desktop 已启动，且 `docker` 命令行已加入系统环境变量 PATH。未能连接到 Docker 服务将导致本地环境创建与销毁功能不可用。
            </p>
          </div>
          <button className="btn-secondary" style={{ padding: "6px 12px", fontSize: "0.8rem" }} onClick={checkDocker} disabled={checkingDocker}>
            {checkingDocker ? "Checking..." : "Re-Check"}
          </button>
        </div>
      )}

      {dockerAvailable === true && (
        <div className="lab-card animate-fade-in" style={{
          borderLeft: "4px solid var(--accent-green)",
          background: "rgba(34, 197, 94, 0.05)",
          padding: "12px 18px",
          borderRadius: "12px",
          display: "flex",
          alignItems: "center",
          gap: "12px",
          fontSize: "0.82rem"
        }}>
          <CheckCircle size={16} style={{ color: "var(--accent-green)" }} />
          <span style={{ color: "var(--text-secondary)" }}>
            Docker daemon is active and running. Ready to allocate on-demand local environments.
          </span>
        </div>
      )}

      <div className="lab-card" style={{ padding: 20 }}>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: 12, alignItems: "end" }}>
          <div>
            <label className="field-label">Local environment name</label>
            <input
              className="input-field"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Local MySQL Dev"
              disabled={dockerAvailable === false}
            />
          </div>
          <button className="btn-primary" onClick={handleCreate} disabled={creating || !activeProject || dockerAvailable === false}>
            {creating ? <RefreshCw size={14} className="animate-spin" /> : <Plus size={14} />}
            {creating ? "Creating..." : "Create Docker MySQL"}
          </button>
        </div>
        <p style={{ marginTop: 10, color: "var(--text-muted)", fontSize: "0.78rem" }}>
          Creates a MySQL 8.0 Docker container, seeds demo tables, and registers a DataBox datasource automatically.
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
            <div className="skeleton" style={{ height: 92, borderRadius: 12 }} />
            <div className="skeleton" style={{ height: 92, borderRadius: 12 }} />
          </>
        ) : environments.length === 0 ? (
          <div className="lab-card" style={{ padding: 48, textAlign: "center" }}>
            <Database size={38} style={{ color: "var(--text-muted)", opacity: 0.35, marginBottom: 12 }} />
            <div className="empty-state-title">No local environments yet</div>
            <div className="empty-state-desc" style={{ marginTop: 4 }}>
              Create a Docker MySQL environment to begin the full database lifecycle flow.
            </div>
          </div>
        ) : (
          environments.map((environment) => (
            <div key={environment.id} className="lab-card hover-lift" style={{ padding: 18 }}>
              <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: 16, alignItems: "center" }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, flexWrap: "wrap" }}>
                    <Database size={16} style={{ color: "var(--accent-indigo)" }} />
                    <h3 style={{ fontSize: "1rem", fontWeight: 700 }}>{environment.name}</h3>
                    <StatusIndicator type={statusType(environment)} label={environment.status} />
                    {environment.last_health_status && (
                      <span className="tag tag-green" style={{
                        background: environment.last_health_status === "healthy" ? "rgba(34, 197, 94, 0.1)" : "rgba(239, 68, 68, 0.1)",
                        color: environment.last_health_status === "healthy" ? "var(--accent-green)" : "var(--accent-red)",
                        border: "1px solid transparent"
                      }}>{environment.last_health_status}</span>
                    )}
                  </div>
                  <div style={{ display: "flex", gap: 16, color: "var(--text-muted)", fontSize: "0.78rem", fontFamily: "var(--font-mono)", flexWrap: "wrap" }}>
                    <span>{environment.image}</span>
                    <span>{environment.container_name}</span>
                    <span>{environment.host}:{environment.port}</span>
                    <span>{environment.database_name}</span>
                  </div>
                  {environment.last_error && (
                    <p style={{ marginTop: 8, color: "var(--accent-red)", fontSize: "0.78rem" }}>{environment.last_error}</p>
                  )}
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
                  <button className="btn-ghost" onClick={() => void handleHealth(environment)} disabled={busyId === environment.id}>
                    <Activity size={14} />
                    Health
                  </button>
                  <button className="btn-ghost" onClick={() => void handleLogs(environment)} disabled={busyId === environment.id}>
                    <FileText size={14} />
                    Logs
                  </button>
                  <button className="btn-ghost" style={{ color: "var(--accent-indigo)" }} onClick={() => setConfirmRebuildEnv(environment)} disabled={busyId === environment.id}>
                    <RefreshCw size={14} />
                    Rebuild
                  </button>
                  <button className="btn-ghost" style={{ color: "var(--accent-red)" }} onClick={() => setConfirmDestroyEnv(environment)} disabled={busyId === environment.id}>
                    <Trash2 size={14} />
                    Destroy
                  </button>
                  {environment.status === "running" ? (
                    <button className="btn-secondary" onClick={() => void handleStop(environment)} disabled={busyId === environment.id}>
                      <Square size={14} />
                      Stop
                    </button>
                  ) : (
                    <button className="btn-primary" onClick={() => void handleStart(environment)} disabled={busyId === environment.id}>
                      <Play size={14} />
                      Start
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {logs && (
        <div className="lab-card" style={{ padding: 18 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
            <h3 style={{ fontSize: "0.95rem", fontWeight: 700 }}>Container logs</h3>
            <button className="btn-ghost" onClick={() => setLogs(null)}>Close</button>
          </div>
          <pre style={{ maxHeight: 280, overflow: "auto", margin: 0, padding: 14, borderRadius: 10, background: "var(--bg-primary)", color: "var(--text-secondary)", fontSize: "0.75rem", whiteSpace: "pre-wrap" }}>
            {logs.text}
          </pre>
        </div>
      )}

      {/* Destroy Confirmation Modal */}
      {confirmDestroyEnv && (
        <div className="modal-backdrop" style={{
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: "rgba(0, 0, 0, 0.4)",
          backdropFilter: "blur(8px)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 1000,
        }}>
          <div className="modal-container" style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border-color)",
            borderRadius: "16px",
            width: "100%",
            maxWidth: "460px",
            padding: "24px",
            boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2)",
            position: "relative"
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px", color: "var(--accent-red)" }}>
              <AlertTriangle size={24} />
              <h3 style={{ fontSize: "1.2rem", fontWeight: 700, margin: 0 }}>销毁本地 Docker 环境？</h3>
            </div>
            
            <p style={{ fontSize: "0.9rem", color: "var(--text-secondary)", lineHeight: "1.5", marginBottom: "20px" }}>
              您确定要销毁环境 <strong style={{ color: "var(--text-primary)" }}>{confirmDestroyEnv.name}</strong> 吗？
              <br />
              <span style={{ color: "var(--accent-red)", fontWeight: 600 }}>警告：此操作不可逆！</span> 
              该环境关联的 Docker 容器 (<code style={{ fontSize: "0.8rem", background: "var(--bg-primary)", padding: "2px 4px", borderRadius: "4px" }}>{confirmDestroyEnv.container_name}</code>) 将被<strong>完全删除</strong>，其中的所有表结构、测试数据以及备份记录和 DataBox 关联数据源将被彻底清除。
            </p>

            {destroyError && (
              <div style={{ marginBottom: "16px" }}>
                <StatusIndicator type="error" label={destroyError} />
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px" }}>
              <button className="btn-secondary" onClick={() => setConfirmDestroyEnv(null)} disabled={destroying}>
                取消
              </button>
              <button className="btn-primary" style={{ background: "var(--accent-red)", color: "#fff" }} onClick={handleDestroy} disabled={destroying}>
                {destroying ? <RefreshCw size={14} className="animate-spin" /> : <Trash2 size={14} />}
                {destroying ? "正在销毁..." : "确认销毁"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Rebuild Confirmation Modal */}
      {confirmRebuildEnv && (
        <div className="modal-backdrop" style={{
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: "rgba(0, 0, 0, 0.4)",
          backdropFilter: "blur(8px)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 1000,
        }}>
          <div className="modal-container" style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border-color)",
            borderRadius: "16px",
            width: "100%",
            maxWidth: "460px",
            padding: "24px",
            boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2)",
            position: "relative"
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px", color: "var(--accent-indigo)" }}>
              <RefreshCw size={24} />
              <h3 style={{ fontSize: "1.2rem", fontWeight: 700, margin: 0 }}>重建本地 Docker 环境？</h3>
            </div>
            
            <p style={{ fontSize: "0.9rem", color: "var(--text-secondary)", lineHeight: "1.5", marginBottom: "20px" }}>
              您确定要重建环境 <strong style={{ color: "var(--text-primary)" }}>{confirmRebuildEnv.name}</strong> 吗？
              <br />
              重建操作将停止并删除当前的 Docker 容器，然后拉起一个全新的 MySQL 实例，并<strong>自动重新初始化并导入 Demo 基础测试数据</strong>。
              <br />
              <span style={{ color: "var(--accent-indigo)" }}>提示：此操作将清空该数据库当前的全部修改，并还原为初始演示状态。关联的数据源 ID 及配置将保持不变。</span>
            </p>

            {rebuildError && (
              <div style={{ marginBottom: "16px" }}>
                <StatusIndicator type="error" label={rebuildError} />
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px" }}>
              <button className="btn-secondary" onClick={() => setConfirmRebuildEnv(null)} disabled={rebuilding}>
                取消
              </button>
              <button className="btn-primary" onClick={handleRebuild} disabled={rebuilding}>
                {rebuilding ? <RefreshCw size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                {rebuilding ? "正在重建..." : "确认重建"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

