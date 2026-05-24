import type { MouseEvent } from "react";
import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  Plus,
  RefreshCw,
  Trash2,
  X,
  Sparkles,
} from "lucide-react";
import { api } from "../lib/api";
import type { DataSource, Project } from "../lib/api";
import { StatusIndicator } from "../components/StatusIndicator";
import { DangerConfirmDialog, type ConfirmationDetails } from "../components/DangerConfirmDialog";

interface DataSourcesPageProps {
  onSelectDataSource: (ds: DataSource | null) => void;
  activeDataSource: DataSource | null;
  activeProject: Project | null;
  onRefreshDatasources: () => Promise<void>;
}

const DEMO_STEPS = [
  "正在检测本地 Docker 运行环境...",
  "正在拉取并启动 MySQL 8.0 容器 (映射本地 3309 端口)...",
  "正在等待数据库实例就绪并测试 TCP 连接握手...",
  "正在创建电子商务表结构并建立物理外键关联 (20 张表)...",
  "正在生成高度逼真的商品、订单、支付、退款等多表电商演练数据集...",
  "正在自动保存数据源连接配置并深度同步 Schema 元数据缓存...",
  "Demo 数据库启动成功！正在为您切换至 AI SQL 工作台..."
];

export const DataSourcesPage = ({
  onSelectDataSource,
  activeDataSource,
  activeProject,
  onRefreshDatasources,
}: DataSourcesPageProps) => {
  const [dataSources, setDataSources] = useState<DataSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirmDetails, setConfirmDetails] = useState<ConfirmationDetails | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const [demoStarting, setDemoStarting] = useState(false);
  const [demoStep, setDemoStep] = useState(0);
  const [demoError, setDemoError] = useState("");
  const [testResult, setTestResult] = useState<{
    status: "idle" | "testing" | "success" | "error";
    message: string;
    details?: { serverVersion?: string; readonly?: boolean; tablesCount?: number };
  }>({ status: "idle", message: "" });
  const [form, setForm] = useState({
    db_type: "mysql",
    name: "",
    host: "",
    port: 3306,
    database_name: "",
    username: "",
    password: "",
    is_read_only: false,
    env: "dev",
    ssh_enabled: false,
    ssh_host: "",
    ssh_port: 22,
    ssh_username: "",
    ssh_password: "",
    ssh_pkey_path: "",
    ssh_pkey_passphrase: "",
    ssl_enabled: false,
    ssl_ca_path: "",
    ssl_cert_path: "",
    ssl_key_path: "",
    ssl_verify_identity: true,
  });

  useEffect(() => {
    void fetchDataSources();
  }, [activeProject?.id]);

  const fetchDataSources = async () => {
    try {
      setLoading(true);
      setDataSources(await api.listDatasources(activeProject?.id));
    } finally {
      setLoading(false);
    }
  };

  const syncLists = async () => {
    await fetchDataSources();
    await onRefreshDatasources();
  };

  const handleStartDemoDb = async () => {
    setDemoStarting(true);
    setDemoStep(0);
    setDemoError("");

    let currentStep = 0;
    const interval = window.setInterval(() => {
      if (currentStep < DEMO_STEPS.length - 2) {
        currentStep++;
        setDemoStep(currentStep);
      }
    }, 2800);

    try {
      const created = await api.startDemoMysql(activeProject?.id);
      window.clearInterval(interval);
      setDemoStep(DEMO_STEPS.length - 2);
      await new Promise(r => setTimeout(r, 1200));
      setDemoStep(DEMO_STEPS.length - 1);
      await new Promise(r => setTimeout(r, 800));

      await syncLists();
      onSelectDataSource(created);
    } catch (err: any) {
      window.clearInterval(interval);
      setDemoError(err.message ?? "未知错误。请确保 Docker Desktop 已启动且能以管理员权限在后台运行。");
    } finally {
      setDemoStarting(false);
    }
  };

  const updateForm = (key: keyof typeof form, value: string | number | boolean) => {
    setForm((c) => ({ ...c, [key]: value }));
  };

  const handleTestConnection = async () => {
    if (form.db_type === "sqlite") {
      if (!form.database_name) {
        setTestResult({ status: "error", message: "请先填写 SQLite 数据库文件路径。" });
        return;
      }
    } else {
      if (!form.host || !form.database_name || !form.username) {
        setTestResult({ status: "error", message: "请先填写主机、数据库名和用户名。" });
        return;
      }
    }
    setTestResult({ status: "testing", message: "正在测试连接..." });
    try {
      const result = await api.testConnection(form);
      setTestResult({ status: "success", message: result.message ?? "连接成功。", details: result });
    } catch (error: any) {
      setTestResult({ status: "error", message: error.message ?? "连接测试失败。" });
    }
  };

  const resetForm = () => {
    setForm({
      db_type: "mysql",
      name: "",
      host: "",
      port: 3306,
      database_name: "",
      username: "",
      password: "",
      is_read_only: false,
      env: "dev",
      ssh_enabled: false,
      ssh_host: "",
      ssh_port: 22,
      ssh_username: "",
      ssh_password: "",
      ssh_pkey_path: "",
      ssh_pkey_passphrase: "",
      ssl_enabled: false,
      ssl_ca_path: "",
      ssl_cert_path: "",
      ssl_key_path: "",
      ssl_verify_identity: true,
    });
    setFormError("");
    setTestResult({ status: "idle", message: "" });
  };

  const handleCreateDataSource = async () => {
    if (form.db_type === "sqlite") {
      if (!form.name || !form.database_name) {
        setFormError("请完整填写连接名称和数据库路径。");
        return;
      }
    } else {
      if (!form.name || !form.host || !form.database_name || !form.username) {
        setFormError("请完整填写必填项。");
        return;
      }
    }
    try {
      setSubmitting(true);
      setFormError("");
      const created = await api.createDatasource({ ...form, project_id: activeProject?.id });
      setSyncingId(created.id);
      await api.syncSchema(created.id);
      await syncLists();
      resetForm();
      setShowAddForm(false);
      const refreshed = await api.listDatasources(activeProject?.id);
      setDataSources(refreshed);
      onSelectDataSource(refreshed.find((item) => item.id === created.id) ?? null);
    } catch (error: any) {
      setFormError(error.message ?? "保存失败。");
    } finally {
      setSubmitting(false);
      setSyncingId(null);
    }
  };

  const handleSyncSchema = async (id: string, event: MouseEvent) => {
    event.stopPropagation();
    try {
      setSyncingId(id);
      await api.syncSchema(id);
      await syncLists();
    } finally {
      setSyncingId(null);
    }
  };

  const handleDeleteDataSource = async (id: string, event: MouseEvent) => {
    event.stopPropagation();
    if (!window.confirm("确认删除此数据源？")) return;
    try {
      const res = await api.deleteDatasource(id);
      if (res && typeof res === "object" && "requires_confirmation" in res && res.requires_confirmation) {
        setConfirmDetails({
          confirm_token: res.confirm_token,
          impact_summary: res.impact_summary,
          expected_confirm_text: res.expected_confirm_text,
          onConfirm: async (text) => {
            await api.deleteDatasource(id, { token: res.confirm_token, text });
            setConfirmDetails(null);
            await syncLists();
            if (activeDataSource?.id === id) onSelectDataSource(null);
          },
          onCancel: () => setConfirmDetails(null)
        });
        return;
      }
      await syncLists();
      if (activeDataSource?.id === id) onSelectDataSource(null);
    } catch (err: any) {
      alert(err.message || "删除数据源失败");
    }
  };

  const statusType = (ds: DataSource) =>
    ds.last_sync_status === "success" ? "success" : ds.last_sync_status === "failed" ? "error" : "idle";

  return (
    <div
      className="animate-fade-in"
      style={{ display: "flex", flexDirection: "column", gap: 20, height: "100%", overflow: "auto" }}
    >
      {/* Page Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h2 className="text-display" style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)" }}>
            连接管理器
          </h2>
          <p style={{ color: "var(--text-secondary)", marginTop: 4, fontSize: "0.9rem" }}>
            管理远程 MySQL 连接，测试可用性，同步本地 Schema 缓存
          </p>
          {activeProject && (
            <p style={{ color: "var(--text-muted)", marginTop: 6, fontSize: "0.78rem" }}>
              Current project: {activeProject.name}
            </p>
          )}
        </div>
        <button className="btn-primary" onClick={() => setShowAddForm((v) => !v)}>
          {showAddForm ? <X size={15} /> : <Plus size={15} />}
          {showAddForm ? "收起" : "添加连接"}
        </button>
      </div>

      {/* Add Form */}
      {showAddForm && (
        <div className="lab-card animate-slide-down" style={{ padding: 24 }}>
          <h3 className="text-display" style={{ fontSize: "1.1rem", fontWeight: 600, marginBottom: 20 }}>
            新增数据源
          </h3>

          <div style={{ marginBottom: 20 }}>
            <label className="field-label">数据库类型</label>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginTop: 6 }}>
              {[
                { id: "mysql", label: "MySQL", icon: "🐬" },
                { id: "postgresql", label: "PostgreSQL", icon: "🐘" },
                { id: "sqlite", label: "SQLite", icon: "📁" },
              ].map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    updateForm("db_type", item.id);
                    if (item.id === "mysql") updateForm("port", 3306);
                    else if (item.id === "postgresql") updateForm("port", 5432);
                    else updateForm("port", 0);
                  }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: 8,
                    padding: "10px 16px",
                    borderRadius: 8,
                    border: form.db_type === item.id ? "2px solid var(--accent-indigo)" : "1px solid var(--border-light)",
                    background: form.db_type === item.id ? "rgba(79, 70, 229, 0.08)" : "var(--bg-secondary)",
                    color: form.db_type === item.id ? "var(--accent-indigo)" : "var(--text-secondary)",
                    fontWeight: form.db_type === item.id ? 600 : 500,
                    cursor: "pointer",
                    transition: "all 0.2s ease",
                  }}
                >
                  <span>{item.icon}</span>
                  <span>{item.label}</span>
                </button>
              ))}
            </div>
          </div>

          {form.db_type === "sqlite" ? (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              <div>
                <label className="field-label">连接名称</label>
                <input
                  className="input-field"
                  value={form.name}
                  onChange={(e) => updateForm("name", e.target.value)}
                  placeholder="例：本地 SQLite 数据库"
                />
              </div>
              <div>
                <label className="field-label">SQLite 数据库文件绝对路径</label>
                <input
                  className="input-field"
                  value={form.database_name}
                  onChange={(e) => updateForm("database_name", e.target.value)}
                  placeholder="C:\Users\username\databases\mydb.sqlite"
                />
                <p style={{ marginTop: 4, fontSize: "0.78rem", color: "var(--text-muted)" }}>
                  请输入本地 .db 或 .sqlite 文件的完整绝对路径。若该文件不存在，系统连接测试时将自动创建。
                </p>
              </div>
            </div>
          ) : (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <div>
                  <label className="field-label">连接名称</label>
                  <input
                    className="input-field"
                    value={form.name}
                    onChange={(e) => updateForm("name", e.target.value)}
                    placeholder={form.db_type === "postgresql" ? "例：测试 PG 数据库" : "例：生产只读库"}
                  />
                </div>
                <div>
                  <label className="field-label">主机地址</label>
                  <input
                    className="input-field"
                    value={form.host}
                    onChange={(e) => updateForm("host", e.target.value)}
                    placeholder="db.example.com"
                  />
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "120px 1fr 1fr", gap: 16, marginTop: 16 }}>
                <div>
                  <label className="field-label">端口</label>
                  <input
                    className="input-field"
                    type="number"
                    value={form.port}
                    onChange={(e) => updateForm("port", Number(e.target.value) || (form.db_type === "postgresql" ? 5432 : 3306))}
                  />
                </div>
                <div>
                  <label className="field-label">数据库名</label>
                  <input
                    className="input-field"
                    value={form.database_name}
                    onChange={(e) => updateForm("database_name", e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label">用户名</label>
                  <input
                    className="input-field"
                    value={form.username}
                    onChange={(e) => updateForm("username", e.target.value)}
                  />
                </div>
              </div>

              <div style={{ marginTop: 16 }}>
                <label className="field-label">密码</label>
                <input
                  className="input-field"
                  type="password"
                  value={form.password}
                  onChange={(e) => updateForm("password", e.target.value)}
                  placeholder="若无密码请留空"
                />
              </div>
            </>
          )}

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginTop: 16 }}>
            <div>
              <label className="field-label">环境标签</label>
              <select
                className="input-field"
                value={form.env}
                onChange={(e) => updateForm("env", e.target.value)}
                style={{ width: "100%", background: "var(--bg-primary)", color: "var(--text-primary)" }}
              >
                <option value="dev">💻 开发环境 (DEV)</option>
                <option value="test">🔬 测试环境 (TEST)</option>
                <option value="prod">🚨 生产环境 (PROD)</option>
              </select>
            </div>
            <div>
              <label className="field-label">连接保护模式</label>
              <div style={{ display: "flex", alignItems: "center", height: 38 }}>
                <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: "0.82rem", color: "var(--text-secondary)", fontWeight: 500 }}>
                  <input
                    type="checkbox"
                    checked={form.is_read_only}
                    onChange={(e) => updateForm("is_read_only", e.target.checked)}
                    style={{ width: 16, height: 16, accentColor: "var(--accent-indigo)", cursor: "pointer" }}
                  />
                  启用只读模式 (限制危险 SQL)
                </label>
              </div>
            </div>
          </div>

          {/* SSH Tunnel Toggle (Non-SQLite only) */}
          {form.db_type !== "sqlite" && (
            <div style={{ marginTop: 20, borderTop: "1px solid var(--border-light)", paddingTop: 16 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontWeight: 600, fontSize: "0.88rem", color: "var(--text-primary)" }}>
                <input
                  type="checkbox"
                  checked={form.ssh_enabled}
                  onChange={(e) => updateForm("ssh_enabled", e.target.checked)}
                  style={{ width: 15, height: 15, accentColor: "var(--accent-indigo)", cursor: "pointer" }}
                />
                启用 SSH 隧道连接 (堡垒机 / 跳板机)
              </label>
            </div>
          )}

          {form.db_type !== "sqlite" && form.ssh_enabled && (
            <div className="animate-slide-down shadow-sm" style={{ marginTop: 16, padding: 18, background: "var(--bg-primary)", borderRadius: 10, border: "1px dashed var(--border-light)", display: "flex", flexDirection: "column", gap: 14 }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 120px 1fr", gap: 14 }}>
                <div>
                  <label className="field-label">SSH 主机地址</label>
                  <input
                    className="input-field"
                    value={form.ssh_host}
                    onChange={(e) => updateForm("ssh_host", e.target.value)}
                    placeholder="ssh.example.com"
                  />
                </div>
                <div>
                  <label className="field-label">SSH 端口</label>
                  <input
                    className="input-field"
                    type="number"
                    value={form.ssh_port}
                    onChange={(e) => updateForm("ssh_port", Number(e.target.value) || 22)}
                  />
                </div>
                <div>
                  <label className="field-label">SSH 用户名</label>
                  <input
                    className="input-field"
                    value={form.ssh_username}
                    onChange={(e) => updateForm("ssh_username", e.target.value)}
                    placeholder="username"
                  />
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                <div>
                  <label className="field-label">SSH 密码 (密码认证)</label>
                  <input
                    className="input-field"
                    type="password"
                    value={form.ssh_password}
                    onChange={(e) => updateForm("ssh_password", e.target.value)}
                    placeholder="如使用密码认证，请填写"
                  />
                </div>
                <div>
                  <label className="field-label">SSH 私钥绝对路径 (密钥认证)</label>
                  <input
                    className="input-field"
                    value={form.ssh_pkey_path}
                    onChange={(e) => updateForm("ssh_pkey_path", e.target.value)}
                    placeholder="例：C:\Users\username\.ssh\id_rsa"
                  />
                </div>
              </div>

              {form.ssh_pkey_path && (
                <div className="animate-slide-down">
                  <label className="field-label">私钥密码 (Passphrase)</label>
                  <input
                    className="input-field"
                    type="password"
                    value={form.ssh_pkey_passphrase}
                    onChange={(e) => updateForm("ssh_pkey_passphrase", e.target.value)}
                    placeholder="若私钥有密码保护，请填写"
                  />
                </div>
              )}
            </div>
          )}

          {/* MySQL SSL/TLS Toggle (MySQL only) */}
          {form.db_type === "mysql" && (
            <div style={{ marginTop: 20, borderTop: "1px solid var(--border-light)", paddingTop: 16 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontWeight: 600, fontSize: "0.88rem", color: "var(--text-primary)" }}>
                <input
                  type="checkbox"
                  checked={form.ssl_enabled}
                  onChange={(e) => updateForm("ssl_enabled", e.target.checked)}
                  style={{ width: 15, height: 15, accentColor: "var(--accent-indigo)", cursor: "pointer" }}
                />
                启用 MySQL SSL/TLS 证书校验
              </label>
              <p style={{ marginTop: 6, fontSize: "0.78rem", color: "var(--text-muted)" }}>
                建议远程数据库开启 TLS；默认校验服务端证书 and 主机名，避免把连接降级成“只加密不验身份”。
              </p>
            </div>
          )}

          {form.db_type === "mysql" && form.ssl_enabled && (
            <div className="animate-slide-down shadow-sm" style={{ marginTop: 16, padding: 18, background: "var(--bg-primary)", borderRadius: 10, border: "1px dashed var(--border-light)", display: "flex", flexDirection: "column", gap: 14 }}>
              <div>
                <label className="field-label">CA 证书路径</label>
                <input
                  className="input-field"
                  value={form.ssl_ca_path}
                  onChange={(e) => updateForm("ssl_ca_path", e.target.value)}
                  placeholder="例如：C:\\certs\\mysql-ca.pem"
                />
                <p style={{ marginTop: 5, fontSize: "0.76rem", color: "var(--text-muted)" }}>
                  开启主机名校验时必须提供 CA 证书路径。
                </p>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                <div>
                  <label className="field-label">客户端证书路径（可选）</label>
                  <input
                    className="input-field"
                    value={form.ssl_cert_path}
                    onChange={(e) => updateForm("ssl_cert_path", e.target.value)}
                    placeholder="例如：C:\\certs\\client-cert.pem"
                  />
                </div>
                <div>
                  <label className="field-label">客户端私钥路径（可选）</label>
                  <input
                    className="input-field"
                    value={form.ssl_key_path}
                    onChange={(e) => updateForm("ssl_key_path", e.target.value)}
                    placeholder="例如：C:\\certs\\client-key.pem"
                  />
                </div>
              </div>

              <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: "0.82rem", color: "var(--text-secondary)", fontWeight: 500 }}>
                <input
                  type="checkbox"
                  checked={form.ssl_verify_identity}
                  onChange={(e) => updateForm("ssl_verify_identity", e.target.checked)}
                  style={{ width: 16, height: 16, accentColor: "var(--accent-indigo)", cursor: "pointer" }}
                />
                校验证书主机名（推荐开启）
              </label>
            </div>
          )}


          {formError && (
            <div style={{ marginTop: 12 }}>
              <StatusIndicator type="error" label={formError} />
            </div>
          )}

          {/* Test Result */}
          {testResult.status !== "idle" && (
            <div
              className="lab-card-accent animate-slide-down"
              style={{
                marginTop: 16,
                padding: 14,
                borderLeftColor:
                  testResult.status === "success"
                    ? "var(--accent-green)"
                    : testResult.status === "error"
                      ? "var(--accent-red)"
                      : "var(--accent-amber)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  fontWeight: 600,
                  fontSize: "0.88rem",
                  color:
                    testResult.status === "success"
                      ? "var(--accent-green)"
                      : testResult.status === "error"
                        ? "var(--accent-red)"
                        : "var(--text-secondary)",
                }}
              >
                {testResult.status === "success" ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
                {testResult.message}
              </div>
              {testResult.details && (
                <div
                  style={{
                    marginTop: 8,
                    display: "flex",
                    gap: 20,
                    fontSize: "0.82rem",
                    color: "var(--text-secondary)",
                    fontFamily: "var(--font-mono)",
                  }}
                >
                  <span>Server: {testResult.details.serverVersion ?? "-"}</span>
                  <span>Tables: {testResult.details.tablesCount ?? "-"}</span>
                  <span>ReadOnly: {testResult.details.readonly ? "Yes" : "No"}</span>
                </div>
              )}
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 20 }}>
            <button className="btn-secondary" onClick={handleTestConnection} disabled={submitting}>
              测试连接
            </button>
            <button className="btn-primary" onClick={handleCreateDataSource} disabled={submitting}>
              {submitting ? "保存中..." : "保存并同步 Schema"}
            </button>
          </div>
        </div>
      )}

      {/* Connection List */}
      <div style={{ flex: 1 }}>
        <h3 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: 12, display: "flex", alignItems: "center", gap: 8 }}>
          已保存连接
          <span style={{ fontWeight: 400, color: "var(--text-muted)", fontSize: "0.85rem" }}>
            ({dataSources.length})
          </span>
        </h3>

        {loading ? (
          <div className="stagger" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {[1, 2, 3].map((i) => (
              <div key={i} className="skeleton" style={{ height: 80, borderRadius: 10 }} />
            ))}
          </div>
        ) : demoStarting ? (
          <div 
            className="lab-card animate-fade-in" 
            style={{ 
              padding: "48px 32px", 
              textAlign: "center", 
              background: "linear-gradient(135deg, rgba(30, 41, 59, 0.4), rgba(15, 23, 42, 0.6))", 
              border: "1px solid rgba(255, 255, 255, 0.08)",
              backdropFilter: "blur(12px)",
              borderRadius: 16,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 24,
              minHeight: 380,
              boxShadow: "0 20px 40px rgba(0, 0, 0, 0.3)"
            }}
          >
            <div style={{ position: "relative", width: 80, height: 80 }}>
              <div 
                style={{ 
                  position: "absolute", 
                  top: 0, 
                  left: 0, 
                  right: 0, 
                  bottom: 0, 
                  borderRadius: "50%", 
                  background: "radial-gradient(circle, var(--accent-indigo) 0%, transparent 70%)", 
                  opacity: 0.4,
                  animation: "pulse 2s infinite" 
                }} 
              />
              <RefreshCw 
                size={48} 
                className="animate-spin" 
                style={{ 
                  color: "var(--accent-indigo)", 
                  position: "absolute", 
                  top: 16, 
                  left: 16 
                }} 
              />
            </div>

            <div style={{ maxWidth: 500 }}>
              <h3 style={{ fontSize: "1.25rem", fontWeight: 700, color: "#fff", marginBottom: 8 }}>
                正在一键整备 Demo 演示环境
              </h3>
              <p style={{ fontSize: "0.88rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
                DataBox 正在自动化下载、编排 Docker 容器，并构建一套标准的电子商业务只读数据库以进行完整的 AI 问数功能端到端体验。这通常需要 10-15 秒，请稍候。
              </p>
            </div>

            <div 
              style={{ 
                width: "100%", 
                maxWidth: 460, 
                background: "rgba(0, 0, 0, 0.2)", 
                borderRadius: 10, 
                padding: 16, 
                border: "1px solid rgba(255, 255, 255, 0.05)",
                textAlign: "left"
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
                <span style={{ fontSize: "0.78rem", fontWeight: 600, color: "var(--accent-indigo)", background: "rgba(74, 91, 192, 0.15)", padding: "2px 8px", borderRadius: 4 }}>
                  运行进度
                </span>
                <span style={{ fontSize: "0.78rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                  {Math.min(Math.round(((demoStep + 1) / DEMO_STEPS.length) * 100), 100)}%
                </span>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {DEMO_STEPS.map((s, idx) => {
                  const isPassed = idx < demoStep;
                  const isCurrent = idx === demoStep;
                  return (
                    <div 
                      key={s} 
                      style={{ 
                        display: "flex", 
                        alignItems: "center", 
                        gap: 8, 
                        fontSize: "0.82rem",
                        color: isPassed ? "var(--text-muted)" : isCurrent ? "#fff" : "rgba(255, 255, 255, 0.25)",
                        transition: "color 0.3s",
                        fontWeight: isCurrent ? 600 : 400
                      }}
                    >
                      <div 
                        style={{ 
                          width: 6, 
                          height: 6, 
                          borderRadius: "50%", 
                          background: isPassed ? "var(--accent-green)" : isCurrent ? "var(--accent-indigo)" : "rgba(255, 255, 255, 0.15)",
                          boxShadow: isCurrent ? "0 0 8px var(--accent-indigo)" : undefined
                        }} 
                      />
                      <span>{s}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        ) : demoError ? (
          <div 
            className="lab-card animate-fade-in" 
            style={{ 
              padding: "48px 32px", 
              textAlign: "center", 
              background: "linear-gradient(135deg, rgba(30, 41, 59, 0.4), rgba(15, 23, 42, 0.6))", 
              border: "1px solid rgba(255, 255, 255, 0.08)",
              backdropFilter: "blur(12px)",
              borderRadius: 16,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 20,
              minHeight: 380
            }}
          >
            <AlertTriangle size={48} style={{ color: "var(--accent-red)" }} />
            <div style={{ maxWidth: 500 }}>
              <h3 style={{ fontSize: "1.25rem", fontWeight: 700, color: "#fff", marginBottom: 8 }}>
                启动 Demo 数据库失败
              </h3>
              <p style={{ fontSize: "0.88rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
                {demoError}
              </p>
            </div>
            <div style={{ display: "flex", gap: 12 }}>
              <button className="btn-secondary" onClick={() => setDemoError("")}>
                返回列表
              </button>
              <button className="btn-primary" onClick={handleStartDemoDb} style={{ background: "linear-gradient(135deg, #2D3B8C, #4A5BC0)" }}>
                重新尝试启动
              </button>
            </div>
          </div>
        ) : dataSources.length === 0 ? (
          <div 
            className="lab-card animate-fade-in" 
            style={{ 
              padding: "56px 40px", 
              textAlign: "center", 
              background: "linear-gradient(135deg, rgba(20, 25, 45, 0.4), rgba(15, 17, 30, 0.6))",
              borderColor: "rgba(74, 91, 192, 0.2)",
              borderWidth: 1.5,
              borderRadius: 16,
              boxShadow: "0 12px 30px rgba(0, 0, 0, 0.15)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 24
            }}
          >
            <div 
              style={{ 
                width: 68, 
                height: 68, 
                borderRadius: "50%", 
                background: "rgba(74, 91, 192, 0.1)", 
                display: "grid", 
                placeItems: "center",
                border: "1px solid rgba(74, 91, 192, 0.2)"
              }}
            >
              <Database size={32} style={{ color: "var(--accent-indigo)" }} />
            </div>

            <div style={{ maxWidth: 500 }}>
              <h3 style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-primary)" }}>
                快速开启您的数据探索之旅
              </h3>
              <p style={{ fontSize: "0.9rem", color: "var(--text-secondary)", marginTop: 8, lineHeight: 1.6 }}>
                DataBox 自动化下载、编排 Docker 容器，并构建一套标准的电子商业务只读数据库以进行完整的 AI 问数功能端到端体验。您可以通过下方快速接入您已有的 MySQL 数据库，或者使用 Docker 一键生成高仿真演示库。
              </p>
            </div>

            <div style={{ display: "flex", gap: 16, marginTop: 8 }}>
              <button 
                className="btn-secondary" 
                onClick={() => {
                  setShowAddForm(true);
                  setTimeout(() => {
                    document.querySelector(".lab-card")?.scrollIntoView({ behavior: "smooth" });
                  }, 100);
                }}
                style={{ padding: "12px 24px", fontSize: "0.92rem", borderRadius: 10 }}
              >
                连接已有 MySQL
              </button>
              <button 
                className="btn-primary" 
                onClick={handleStartDemoDb}
                style={{ 
                  padding: "12px 24px", 
                  fontSize: "0.92rem", 
                  borderRadius: 10,
                  background: "linear-gradient(135deg, #2D3B8C, #4A5BC0)",
                  border: "none",
                  boxShadow: "0 4px 15px rgba(74, 91, 192, 0.4)",
                  display: "flex",
                  alignItems: "center",
                  gap: 8
                }}
              >
                <Sparkles size={16} />
                一键启动 Demo 数据库
              </button>
            </div>
          </div>
        ) : (
          <div className="stagger" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {dataSources.map((ds) => {
              const isActive = activeDataSource?.id === ds.id;
              const st = statusType(ds);

              return (
                <div
                  key={ds.id}
                  className="lab-card hover-lift"
                  style={{
                    padding: "16px 20px",
                    borderColor: isActive ? "var(--accent-indigo)" : undefined,
                    borderWidth: isActive ? 1.5 : 1,
                    cursor: "pointer",
                  }}
                  onClick={() => onSelectDataSource(ds)}
                >
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "minmax(0, 1.5fr) 120px 170px 100px auto",
                      gap: 16,
                      alignItems: "center",
                    }}
                  >
                    <div style={{ minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <Database size={15} style={{ color: isActive ? "var(--accent-indigo)" : "var(--text-muted)" }} />
                        <h4
                          style={{
                            fontSize: "0.94rem",
                            fontWeight: 600,
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {ds.name}
                        </h4>
                        {isActive && <span className="tag tag-indigo">当前</span>}
                        {ds.db_type === "postgresql" && <span className="tag tag-indigo" style={{ background: "rgba(99, 102, 241, 0.1)", color: "#818CF8", border: "1px solid rgba(99, 102, 241, 0.2)", fontWeight: 600 }}>PostgreSQL</span>}
                        {ds.db_type === "sqlite" && <span className="tag tag-neutral" style={{ background: "rgba(100, 116, 139, 0.1)", color: "#94A3B8", border: "1px solid rgba(100, 116, 139, 0.2)", fontWeight: 600 }}>SQLite</span>}
                        {(ds.db_type === "mysql" || !ds.db_type) && <span className="tag tag-indigo" style={{ background: "rgba(59, 130, 246, 0.1)", color: "#60A5FA", border: "1px solid rgba(59, 130, 246, 0.2)", fontWeight: 600 }}>MySQL</span>}
                        {ds.env === "prod" && <span className="tag tag-error" style={{ background: "rgba(220, 38, 38, 0.1)", color: "var(--accent-red)", border: "1px solid rgba(220, 38, 38, 0.2)", fontWeight: 600 }}>PROD</span>}
                        {ds.env === "test" && <span className="tag tag-warning" style={{ background: "rgba(217, 119, 6, 0.1)", color: "var(--accent-amber)", border: "1px solid rgba(217, 119, 6, 0.2)" }}>测试</span>}
                        {ds.env === "dev" && <span className="tag tag-neutral" style={{ background: "var(--bg-active)", color: "var(--text-secondary)", border: "1px solid var(--border-light)" }}>开发</span>}
                        {ds.is_read_only && <span className="tag tag-indigo" style={{ background: "rgba(74, 91, 192, 0.1)", color: "var(--accent-indigo)", border: "1px solid rgba(74, 91, 192, 0.2)" }}>只读</span>}
                        {ds.ssh_enabled && <span className="tag tag-amber" style={{ background: "rgba(180, 83, 9, 0.1)", color: "var(--accent-amber)", border: "1px solid rgba(180, 83, 9, 0.2)" }}>SSH 隧道</span>}
                        {ds.ssl_enabled && <span className="tag tag-green" style={{ background: "rgba(22, 163, 74, 0.1)", color: "var(--accent-green)", border: "1px solid rgba(22, 163, 74, 0.2)" }}>TLS</span>}
                      </div>
                      <p
                        style={{
                          marginTop: 3,
                          fontSize: "0.8rem",
                          color: "var(--text-muted)",
                          fontFamily: "var(--font-mono)",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {ds.db_type === "sqlite" ? ds.database_name : `${ds.host}:${ds.port} / ${ds.database_name}`}
                      </p>
                    </div>

                    <div style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>
                      {ds.db_type === "sqlite" ? "-" : ds.username}
                    </div>

                    <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                      {ds.last_sync_at ? new Date(ds.last_sync_at).toLocaleString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "未同步"}
                    </div>

                    <StatusIndicator type={st} label={st === "success" ? "已同步" : st === "error" ? "失败" : "待同步"} />

                    <div style={{ display: "flex", justifyContent: "flex-end", gap: 6 }}>
                      <button
                        className="btn-ghost"
                        onClick={(e) => handleSyncSchema(ds.id, e)}
                        disabled={syncingId === ds.id}
                        style={{ color: "var(--accent-indigo)" }}
                      >
                        <RefreshCw size={14} className={syncingId === ds.id ? "animate-spin" : ""} />
                        {syncingId === ds.id ? "同步中" : "同步"}
                      </button>
                      <button
                        className="btn-ghost"
                        onClick={(e) => handleDeleteDataSource(ds.id, e)}
                        style={{ color: "var(--accent-red)" }}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
      <DangerConfirmDialog details={confirmDetails} />
    </div>
  );
};
