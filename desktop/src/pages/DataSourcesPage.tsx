import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Plus,
} from "lucide-react";
import { api } from "../lib/api";
import type { DataSource, Project } from "../lib/api";
import {
  buildDatasourceCreatePayload,
  buildDatasourceTestPayload,
  type DatasourceFormShape,
} from "../lib/datasourcePayload";
import { StatusIndicator } from "../components/StatusIndicator";

interface DataSourcesPageProps {
  onSelectDataSource: (ds: DataSource | null) => void;
  activeDataSource: DataSource | null;
  activeProject: Project | null;
  onRefreshDatasources: () => Promise<void>;
  initialShowAddForm?: boolean;
}

export const DataSourcesPage = ({
  onSelectDataSource,
  activeDataSource: _activeDataSource,
  activeProject,
  onRefreshDatasources,
  initialShowAddForm,
}: DataSourcesPageProps) => {
  void _activeDataSource; // kept for caller compat, unused in simplified form
  const [submitting, setSubmitting] = useState(false);
  const [showAddForm, setShowAddForm] = useState(initialShowAddForm ?? false);
  const [formError, setFormError] = useState("");
  const [testResult, setTestResult] = useState<{
    status: "idle" | "testing" | "success" | "error";
    message: string;
    details?: { serverVersion?: string; readonly?: boolean; tablesCount?: number };
  }>({ status: "idle", message: "" });
  const [form, setForm] = useState({
    db_type: "mysql" as string,
    name: "",
    host: "",
    port: 3306 as number,
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
    setShowAddForm(initialShowAddForm ?? false);
  }, [initialShowAddForm]);

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
      const result = await api.testConnection(buildDatasourceTestPayload(form as DatasourceFormShape));
      setTestResult({ status: "success", message: result.message ?? "连接成功。", details: result });
    } catch (error: unknown) {
      setTestResult({ status: "error", message: (error as Error).message ?? "连接测试失败。" });
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
      const created = await api.createDatasource(
        buildDatasourceCreatePayload(form as DatasourceFormShape, activeProject?.id),
      );
      await api.syncSchema(created.id);
      resetForm();
      setShowAddForm(false);
      await onRefreshDatasources();
      const refreshed = await api.listDatasources(activeProject?.id);
      onSelectDataSource(refreshed.find((item) => item.id === created.id) ?? null);
    } catch (error: unknown) {
      setFormError((error as Error).message ?? "保存失败。");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="hifi-tab-pane hifi-datasource-page">
      <div className="hifi-page-header">
        <div>
          <h2 className="hifi-page-title">连接管理</h2>
          <p className="hifi-page-desc">管理本地保存的数据源连接，测试可用性，同步 Schema 缓存</p>
        </div>
        <button type="button" className="hifi-btn hifi-btn-primary" onClick={() => setShowAddForm((v) => !v)}>
          <Plus size={13} />
          {showAddForm ? "收起" : "新建连接"}
        </button>
      </div>

      {showAddForm && (
        <form
          onSubmit={(e) => e.preventDefault()}
          className="hifi-card hifi-datasource-form"
        >
          <h3 className="hifi-card-title">新增数据源</h3>

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
                  className="hifi-input"
                  value={form.name}
                  onChange={(e) => updateForm("name", e.target.value)}
                  placeholder="例：本地 SQLite 数据库"
                />
              </div>
              <div>
                <label className="field-label">SQLite 数据库文件绝对路径</label>
                <input
                  className="hifi-input"
                  value={form.database_name}
                  onChange={(e) => updateForm("database_name", e.target.value)}
                  placeholder="C:\Users\username\databases\mydb.sqlite"
                />
                <p style={{ marginTop: 4, fontSize: "0.78rem", color: "var(--text-muted)" }}>
                  请输入本地 .db 或 .sqlite 文件的完整绝对路径。
                </p>
              </div>
            </div>
          ) : (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <div>
                  <label className="field-label">连接名称</label>
                  <input
                    className="hifi-input"
                    value={form.name}
                    onChange={(e) => updateForm("name", e.target.value)}
                    placeholder={form.db_type === "postgresql" ? "例：测试 PG 数据库" : "例：生产只读库"}
                  />
                </div>
                <div>
                  <label className="field-label">主机地址</label>
                  <input
                    className="hifi-input"
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
                    className="hifi-input"
                    type="number"
                    value={form.port}
                    onChange={(e) => updateForm("port", Number(e.target.value) || (form.db_type === "postgresql" ? 5432 : 3306))}
                  />
                </div>
                <div>
                  <label className="field-label">数据库名</label>
                  <input
                    className="hifi-input"
                    value={form.database_name}
                    onChange={(e) => updateForm("database_name", e.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label">用户名</label>
                  <input
                    className="hifi-input"
                    value={form.username}
                    onChange={(e) => updateForm("username", e.target.value)}
                  />
                </div>
              </div>

              <div style={{ marginTop: 16 }}>
                <label className="field-label">密码</label>
                <input
                  className="hifi-input"
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
                className="hifi-select"
                value={form.env}
                onChange={(e) => updateForm("env", e.target.value)}
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

          {/* SSH Tunnel */}
          {form.db_type !== "sqlite" && (
            <div style={{ marginTop: 20, borderTop: "1px solid var(--border-light)", paddingTop: 16 }}>
              <label className="field-label" style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
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
            <div style={{ marginTop: 16, padding: 18, background: "var(--bg-primary)", borderRadius: 10, border: "1px dashed var(--border-light)", display: "flex", flexDirection: "column", gap: 14 }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 120px 1fr", gap: 14 }}>
                <div>
                  <label className="field-label">SSH 主机地址</label>
                  <input className="hifi-input" value={form.ssh_host} onChange={(e) => updateForm("ssh_host", e.target.value)} placeholder="ssh.example.com" />
                </div>
                <div>
                  <label className="field-label">SSH 端口</label>
                  <input className="hifi-input" type="number" value={form.ssh_port} onChange={(e) => updateForm("ssh_port", Number(e.target.value) || 22)} />
                </div>
                <div>
                  <label className="field-label">SSH 用户名</label>
                  <input className="hifi-input" value={form.ssh_username} onChange={(e) => updateForm("ssh_username", e.target.value)} placeholder="username" />
                </div>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                <div>
                  <label className="field-label">SSH 密码 (密码认证)</label>
                  <input className="hifi-input" type="password" value={form.ssh_password} onChange={(e) => updateForm("ssh_password", e.target.value)} placeholder="如使用密码认证，请填写" />
                </div>
                <div>
                  <label className="field-label">SSH 私钥绝对路径 (密钥认证)</label>
                  <input className="hifi-input" value={form.ssh_pkey_path} onChange={(e) => updateForm("ssh_pkey_path", e.target.value)} placeholder="例：C:\Users\username\.ssh\id_rsa" />
                </div>
              </div>
              {form.ssh_pkey_path && (
                <div>
                  <label className="field-label">私钥密码 (Passphrase)</label>
                  <input className="hifi-input" type="password" value={form.ssh_pkey_passphrase} onChange={(e) => updateForm("ssh_pkey_passphrase", e.target.value)} placeholder="若私钥有密码保护，请填写" />
                </div>
              )}
            </div>
          )}

          {/* MySQL SSL */}
          {form.db_type === "mysql" && (
            <div style={{ marginTop: 20, borderTop: "1px solid var(--border-light)", paddingTop: 16 }}>
              <label className="field-label" style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={form.ssl_enabled}
                  onChange={(e) => updateForm("ssl_enabled", e.target.checked)}
                  style={{ width: 15, height: 15, accentColor: "var(--accent-indigo)", cursor: "pointer" }}
                />
                启用 MySQL SSL/TLS 证书校验
              </label>
              <p style={{ marginTop: 6, fontSize: "0.78rem", color: "var(--text-muted)" }}>
                建议远程数据库开启 TLS；默认校验服务端证书和主机名。
              </p>
            </div>
          )}

          {form.db_type === "mysql" && form.ssl_enabled && (
            <div style={{ marginTop: 16, padding: 18, background: "var(--bg-primary)", borderRadius: 10, border: "1px dashed var(--border-light)", display: "flex", flexDirection: "column", gap: 14 }}>
              <div>
                <label className="field-label">CA 证书路径</label>
                <input className="hifi-input" value={form.ssl_ca_path} onChange={(e) => updateForm("ssl_ca_path", e.target.value)} placeholder="例如：C:\certs\mysql-ca.pem" />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                <div>
                  <label className="field-label">客户端证书路径（可选）</label>
                  <input className="hifi-input" value={form.ssl_cert_path} onChange={(e) => updateForm("ssl_cert_path", e.target.value)} placeholder="例如：C:\certs\client-cert.pem" />
                </div>
                <div>
                  <label className="field-label">客户端私钥路径（可选）</label>
                  <input className="hifi-input" value={form.ssl_key_path} onChange={(e) => updateForm("ssl_key_path", e.target.value)} placeholder="例如：C:\certs\client-key.pem" />
                </div>
              </div>
              <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: "0.82rem", color: "var(--text-secondary)", fontWeight: 500 }}>
                <input type="checkbox" checked={form.ssl_verify_identity} onChange={(e) => updateForm("ssl_verify_identity", e.target.checked)} style={{ width: 16, height: 16, accentColor: "var(--accent-indigo)", cursor: "pointer" }} />
                校验证书主机名（推荐开启）
              </label>
            </div>
          )}

          {formError && (
            <div style={{ marginTop: 12 }}>
              <StatusIndicator type="error" label={formError} />
            </div>
          )}

          {testResult.status !== "idle" && (
            <div
              style={{
                marginTop: 16, padding: 14, borderRadius: 8,
                borderLeft: "3px solid",
                borderLeftColor: testResult.status === "success" ? "var(--accent-green)" : testResult.status === "error" ? "var(--accent-red)" : "var(--accent-amber)",
                background: "var(--bg-card, #fff)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 600, fontSize: "0.88rem", color: testResult.status === "success" ? "var(--accent-green)" : testResult.status === "error" ? "var(--accent-red)" : "var(--text-secondary)" }}>
                {testResult.status === "success" ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
                {testResult.message}
              </div>
              {testResult.details && (
                <div style={{ marginTop: 8, display: "flex", gap: 20, fontSize: "0.82rem", color: "var(--text-secondary)", fontFamily: "var(--font-mono)" }}>
                  <span>Server: {testResult.details.serverVersion ?? "-"}</span>
                  <span>Tables: {testResult.details.tablesCount ?? "-"}</span>
                  <span>ReadOnly: {testResult.details.readonly ? "Yes" : "No"}</span>
                </div>
              )}
            </div>
          )}

          <div className="hifi-form-actions">
            <button type="button" className="hifi-btn hifi-btn-outline" onClick={handleTestConnection} disabled={submitting}>
              测试连接
            </button>
            <button type="button" className="hifi-btn hifi-btn-primary" onClick={handleCreateDataSource} disabled={submitting}>
              {submitting ? "保存中..." : "保存并同步 Schema"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
};
