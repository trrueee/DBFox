import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  Activity,
} from "lucide-react";
import { api } from "../lib/api";
import type { DataSource, Project } from "../lib/api";
import {
  buildDatasourceCreatePayload,
  buildDatasourceTestPayload,
  buildDatasourceUpdatePayload,
  type DatasourceFormShape,
} from "../lib/datasourcePayload";
import { StatusIndicator } from "../components/StatusIndicator";
import { DangerConfirmDialog, type ConfirmationDetails } from "../components/DangerConfirmDialog";
import { useToast } from "../components/Toast";

type PageMode = "detail" | "create" | "edit";
type ActionState = "idle" | "testing" | "saving" | "syncing" | "deleting";

interface DataSourcesPageProps {
  onSelectDataSource: (ds: DataSource | null) => void;
  activeDataSource: DataSource | null;
  activeProject: Project | null;
  onRefreshDatasources: () => Promise<void>;
  initialShowAddForm?: boolean;
}

const emptyForm = () => ({
  db_type: "mysql" as string,
  name: "",
  host: "",
  port: 3306 as number,
  database_name: "",
  username: "",
  password: "",
  is_read_only: false,
  env: "dev" as string,
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

const formFromDataSource = (ds: DataSource) => ({
  db_type: ds.db_type || "mysql",
  name: ds.name || "",
  host: ds.host || "",
  port: ds.port || (ds.db_type === "postgresql" ? 5432 : ds.db_type === "sqlite" ? 0 : 3306),
  database_name: ds.database_name || "",
  username: ds.username || "",
  password: "",
  is_read_only: Boolean(ds.is_read_only),
  env: ds.env || "dev",
  ssh_enabled: Boolean(ds.ssh_enabled),
  ssh_host: ds.ssh_host || "",
  ssh_port: ds.ssh_port || 22,
  ssh_username: ds.ssh_username || "",
  ssh_password: "",
  ssh_pkey_path: ds.ssh_pkey_path || "",
  ssh_pkey_passphrase: "",
  ssl_enabled: Boolean(ds.ssl_enabled),
  ssl_ca_path: ds.ssl_ca_path || "",
  ssl_cert_path: ds.ssl_cert_path || "",
  ssl_key_path: ds.ssl_key_path || "",
  ssl_verify_identity: ds.ssl_verify_identity !== false,
});

export const DataSourcesPage = ({
  onSelectDataSource,
  activeDataSource,
  activeProject,
  onRefreshDatasources,
  initialShowAddForm,
}: DataSourcesPageProps) => {
  const toast = useToast();
  const [datasources, setDatasources] = useState<DataSource[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [mode, setMode] = useState<PageMode>("detail");
  const [form, setForm] = useState(emptyForm());
  const [search, setSearch] = useState("");
  const [formError, setFormError] = useState("");
  const [actionState, setActionState] = useState<ActionState>("idle");
  const [testResult, setTestResult] = useState<{
    status: "idle" | "testing" | "success" | "error";
    message: string;
    details?: { serverVersion?: string; readonly?: boolean; tablesCount?: number };
  }>({ status: "idle", message: "" });
  const [confirmDetails, setConfirmDetails] = useState<ConfirmationDetails | null>(null);

  const selected = datasources.find((d) => d.id === selectedId) || null;

  const loadDatasources = async (preferredId?: string) => {
    const next = await api.listDatasources(activeProject?.id);
    setDatasources(next);
    setSelectedId((current) => {
      if (preferredId && next.some((item) => item.id === preferredId)) return preferredId;
      if (current && next.some((item) => item.id === current)) return current;
      if (activeDataSource && next.some((item) => item.id === activeDataSource.id)) return activeDataSource.id;
      return next[0]?.id || "";
    });
    return next;
  };

  useEffect(() => {
    void loadDatasources();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProject?.id]);

  useEffect(() => {
    if (initialShowAddForm) startCreate();
    else setMode("detail");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialShowAddForm]);

  const startCreate = () => {
    setMode("create");
    setForm(emptyForm());
    setFormError("");
    setTestResult({ status: "idle", message: "" });
  };

  const startEdit = (ds: DataSource) => {
    setMode("edit");
    setForm(formFromDataSource(ds));
    setFormError("");
    setTestResult({ status: "idle", message: "" });
  };

  const updateForm = (key: string, value: string | number | boolean) => {
    setForm((c) => ({ ...c, [key]: value }));
  };

  const handleTestConnection = async () => {
    if (form.db_type === "sqlite" && !form.database_name) {
      setTestResult({ status: "error", message: "请先填写 SQLite 数据库文件路径。" });
      return;
    }
    if (form.db_type !== "sqlite" && (!form.host || !form.database_name || !form.username)) {
      setTestResult({ status: "error", message: "请先填写主机、数据库名和用户名。" });
      return;
    }
    setTestResult({ status: "testing", message: "正在测试连接..." });
    try {
      const result = await api.testConnection(buildDatasourceTestPayload(form as DatasourceFormShape));
      setTestResult({ status: "success", message: result.message ?? "连接成功。", details: result });
    } catch (error: unknown) {
      setTestResult({ status: "error", message: (error as Error).message ?? "连接测试失败。" });
    }
  };

  const handleCreate = async () => {
    if (!validateForm()) return;
    try {
      setActionState("saving");
      setFormError("");
      const created = await api.createDatasource(
        buildDatasourceCreatePayload(form as DatasourceFormShape, activeProject?.id),
      );
      await api.syncSchema(created.id);
      setMode("detail");
      await loadDatasources(created.id);
      await onRefreshDatasources();
      onSelectDataSource(created);
      toast.toast("数据源创建成功", "success");
    } catch (error: unknown) {
      setFormError((error as Error).message ?? "保存失败。");
    } finally {
      setActionState("idle");
    }
  };

  const handleUpdate = async () => {
    if (!validateForm()) return;
    if (!selected) return;
    try {
      setActionState("saving");
      setFormError("");
      const updated = await api.updateDatasource(selected.id, buildDatasourceUpdatePayload(form as DatasourceFormShape));
      setDatasources((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
      setMode("detail");
      await onRefreshDatasources();
      toast.toast("数据源已更新", "success");
    } catch (error: unknown) {
      setFormError((error as Error).message ?? "更新失败。");
    } finally {
      setActionState("idle");
    }
  };

  const validateForm = () => {
    if (form.db_type === "sqlite") {
      if (!form.name || !form.database_name) { setFormError("请完整填写连接名称和数据库路径。"); return false; }
    } else {
      if (!form.name || !form.host || !form.database_name || !form.username) { setFormError("请完整填写必填项。"); return false; }
    }
    return true;
  };

  const handleSync = async () => {
    if (!selected) return;
    try {
      setActionState("syncing");
      await api.syncSchema(selected.id);
      await loadDatasources(selected.id);
      await onRefreshDatasources();
      toast.toast("Schema 同步完成", "success");
    } catch (error: unknown) {
      toast.toast((error as Error).message || "同步失败", "error");
    } finally {
      setActionState("idle");
    }
  };

  const handleHealthCheck = async () => {
    if (!selected) return;
    try {
      setActionState("testing");
      const result = await api.checkDatasourceHealth(selected.id);
      if (!result.ok) {
        toast.toast(result.message || "连接健康检查失败", "error");
      } else {
        toast.toast("连接健康检查通过", "success");
      }
      await loadDatasources(selected.id);
    } finally {
      setActionState("idle");
    }
  };

  const handleDelete = async () => {
    if (!selected) return;
    try {
      setActionState("deleting");
      const res = await api.deleteDatasource(selected.id);
      const raw = res as unknown as Record<string, unknown> | null;
      if (raw && raw.requires_confirmation) {
        const confirmation = raw;
        setConfirmDetails({
          confirm_token: confirmation.confirm_token as string,
          impact_summary: confirmation.impact_summary as string,
          expected_confirm_text: confirmation.expected_confirm_text as string,
          onConfirm: async (text: string) => {
            await api.deleteDatasource(selected.id, { token: confirmation.confirm_token as string, text });
            setConfirmDetails(null);
            await loadDatasources();
            await onRefreshDatasources();
            if (activeDataSource?.id === selected.id) onSelectDataSource(null);
            toast.toast("数据源已删除", "success");
          },
          onCancel: () => setConfirmDetails(null),
        });
        return;
      }
      await loadDatasources();
      await onRefreshDatasources();
      if (activeDataSource?.id === selected.id) onSelectDataSource(null);
      toast.toast("数据源已删除", "success");
    } catch (err: unknown) {
      toast.toast((err as Error).message || "删除数据源失败", "error");
    } finally {
      setActionState("idle");
    }
  };

  const filtered = search
    ? datasources.filter((d) => d.name.toLowerCase().includes(search.toLowerCase()) || d.host.toLowerCase().includes(search.toLowerCase()))
    : datasources;

  const healthType = (ds: DataSource) =>
    ds.last_test_status === "success" ? "success" : ds.last_test_status === "failed" ? "error" : "idle";

  const fmtDate = (v?: string) =>
    v ? new Date(v).toLocaleString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "-";

  const dbBadge = (ds: DataSource) =>
    ds.db_type === "postgresql" ? { label: "PG", color: "#818CF8" }
    : ds.db_type === "sqlite" ? { label: "Lite", color: "#94A3B8" }
    : { label: "MySQL", color: "#60A5FA" };

  const envBadge = (env?: string) =>
    env === "prod" ? { label: "生产", color: "var(--accent-red)" }
    : env === "test" ? { label: "测试", color: "var(--accent-amber)" }
    : { label: "开发", color: "var(--text-secondary)" };

  // ---- Render modes ----

  const renderForm = (title: string, submitLabel: string, onSubmit: () => void) => (
    <form onSubmit={(e) => e.preventDefault()} className="hifi-card hifi-datasource-form">
      <h3 className="hifi-card-title">{title}</h3>
      {/* DB type selector */}
      <div style={{ marginBottom: 20 }}>
        <label className="field-label">数据库类型</label>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginTop: 6 }}>
          {[{ id: "mysql", label: "MySQL", icon: "🐬" }, { id: "postgresql", label: "PostgreSQL", icon: "🐘" }, { id: "sqlite", label: "SQLite", icon: "📁" }].map((item) => (
            <button key={item.id} type="button" onClick={() => { updateForm("db_type", item.id); if (item.id === "mysql") updateForm("port", 3306); else if (item.id === "postgresql") updateForm("port", 5432); else updateForm("port", 0); }}
              style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, padding: "10px 16px", borderRadius: 8,
                border: form.db_type === item.id ? "2px solid var(--accent-indigo)" : "1px solid var(--border-light)",
                background: form.db_type === item.id ? "rgba(79,70,229,0.08)" : "var(--bg-secondary)",
                color: form.db_type === item.id ? "var(--accent-indigo)" : "var(--text-secondary)", fontWeight: form.db_type === item.id ? 600 : 500, cursor: "pointer" }}
            ><span>{item.icon}</span><span>{item.label}</span></button>
          ))}
        </div>
      </div>
      {/* Basic fields */}
      {form.db_type === "sqlite" ? (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <div><label className="field-label" htmlFor="ds-name">连接名称</label><input id="ds-name" className="hifi-input" value={form.name} onChange={(e) => updateForm("name", e.target.value)} placeholder="例：本地 SQLite 数据库" /></div>
          <div><label className="field-label">SQLite 数据库文件绝对路径</label><input className="hifi-input" value={form.database_name} onChange={(e) => updateForm("database_name", e.target.value)} placeholder="C:\Users\...\mydb.sqlite" /></div>
        </div>
      ) : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div><label className="field-label" htmlFor="ds-name">连接名称</label><input id="ds-name" className="hifi-input" value={form.name} onChange={(e) => updateForm("name", e.target.value)} placeholder="例：生产只读库" /></div>
            <div><label className="field-label">主机地址</label><input className="hifi-input" value={form.host} onChange={(e) => updateForm("host", e.target.value)} placeholder="db.example.com" /></div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "120px 1fr 1fr", gap: 16, marginTop: 16 }}>
            <div><label className="field-label">端口</label><input className="hifi-input" type="number" value={form.port} onChange={(e) => updateForm("port", Number(e.target.value) || 3306)} /></div>
            <div><label className="field-label">数据库名</label><input className="hifi-input" value={form.database_name} onChange={(e) => updateForm("database_name", e.target.value)} /></div>
            <div><label className="field-label">用户名</label><input className="hifi-input" value={form.username} onChange={(e) => updateForm("username", e.target.value)} /></div>
          </div>
          <div style={{ marginTop: 16 }}><label className="field-label">密码</label><input className="hifi-input" type="password" value={form.password} onChange={(e) => updateForm("password", e.target.value)} placeholder="留空则不修改" /></div>
        </>
      )}
      {/* Env + read-only */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginTop: 16 }}>
        <div>
          <label className="field-label">环境标签</label>
          <select className="hifi-select" value={form.env} onChange={(e) => updateForm("env", e.target.value)}>
            <option value="dev">💻 开发环境 (DEV)</option>
            <option value="test">🔬 测试环境 (TEST)</option>
            <option value="prod">🚨 生产环境 (PROD)</option>
          </select>
        </div>
        <div><label className="field-label" style={{ display: "flex", alignItems: "center", gap: 8, height: 38, cursor: "pointer" }}><input type="checkbox" checked={form.is_read_only} onChange={(e) => updateForm("is_read_only", e.target.checked)} /> 启用只读模式</label></div>
      </div>
      {/* SSH */}
      {form.db_type !== "sqlite" && (
        <div style={{ marginTop: 20, borderTop: "1px solid var(--border-light)", paddingTop: 16 }}>
          <label className="field-label" style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}><input type="checkbox" checked={form.ssh_enabled} onChange={(e) => updateForm("ssh_enabled", e.target.checked)} /> 启用 SSH 隧道连接</label>
        </div>
      )}
      {form.db_type !== "sqlite" && form.ssh_enabled && (
        <div style={{ marginTop: 16, padding: 18, background: "var(--bg-primary)", borderRadius: 10, border: "1px dashed var(--border-light)", display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 120px 1fr", gap: 14 }}>
            <div><label className="field-label">SSH 主机</label><input className="hifi-input" value={form.ssh_host} onChange={(e) => updateForm("ssh_host", e.target.value)} /></div>
            <div><label className="field-label">SSH 端口</label><input className="hifi-input" type="number" value={form.ssh_port} onChange={(e) => updateForm("ssh_port", Number(e.target.value) || 22)} /></div>
            <div><label className="field-label">SSH 用户名</label><input className="hifi-input" value={form.ssh_username} onChange={(e) => updateForm("ssh_username", e.target.value)} /></div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            <div><label className="field-label">SSH 密码</label><input className="hifi-input" type="password" value={form.ssh_password} onChange={(e) => updateForm("ssh_password", e.target.value)} /></div>
            <div><label className="field-label">SSH 私钥路径</label><input className="hifi-input" value={form.ssh_pkey_path} onChange={(e) => updateForm("ssh_pkey_path", e.target.value)} /></div>
          </div>
          {form.ssh_pkey_path && <div><label className="field-label">私钥密码</label><input className="hifi-input" type="password" value={form.ssh_pkey_passphrase} onChange={(e) => updateForm("ssh_pkey_passphrase", e.target.value)} /></div>}
        </div>
      )}
      {/* SSL */}
      {form.db_type === "mysql" && (
        <div style={{ marginTop: 20, borderTop: "1px solid var(--border-light)", paddingTop: 16 }}>
          <label className="field-label" style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}><input type="checkbox" checked={form.ssl_enabled} onChange={(e) => updateForm("ssl_enabled", e.target.checked)} /> 启用 MySQL SSL/TLS</label>
        </div>
      )}
      {form.db_type === "mysql" && form.ssl_enabled && (
        <div style={{ marginTop: 16, padding: 18, background: "var(--bg-primary)", borderRadius: 10, border: "1px dashed var(--border-light)", display: "flex", flexDirection: "column", gap: 14 }}>
          <div><label className="field-label">CA 证书路径</label><input className="hifi-input" value={form.ssl_ca_path} onChange={(e) => updateForm("ssl_ca_path", e.target.value)} /></div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            <div><label className="field-label">客户端证书</label><input className="hifi-input" value={form.ssl_cert_path} onChange={(e) => updateForm("ssl_cert_path", e.target.value)} /></div>
            <div><label className="field-label">客户端私钥</label><input className="hifi-input" value={form.ssl_key_path} onChange={(e) => updateForm("ssl_key_path", e.target.value)} /></div>
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}><input type="checkbox" checked={form.ssl_verify_identity} onChange={(e) => updateForm("ssl_verify_identity", e.target.checked)} /> 校验证书主机名</label>
        </div>
      )}
      {/* Error / Test result */}
      {formError && <div style={{ marginTop: 12 }}><StatusIndicator type="error" label={formError} /></div>}
      {testResult.status !== "idle" && (
        <div style={{ marginTop: 16, padding: 14, borderRadius: 8, borderLeft: "3px solid", borderLeftColor: testResult.status === "success" ? "var(--accent-green)" : testResult.status === "error" ? "var(--accent-red)" : "var(--accent-amber)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 600, fontSize: "0.88rem" }}>
            {testResult.status === "success" ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}{testResult.message}
          </div>
        </div>
      )}
      <div className="hifi-form-actions">
        <button type="button" className="hifi-btn hifi-btn-outline" onClick={handleTestConnection} disabled={actionState !== "idle"}>测试连接</button>
        <button type="button" className="hifi-btn hifi-btn-primary" onClick={onSubmit} disabled={actionState !== "idle"}>{actionState === "saving" ? "保存中..." : submitLabel}</button>
      </div>
    </form>
  );

  const renderDetail = () => {
    if (!selected) return <div className="hifi-empty-state"><Database size={28} /><p>选择一个数据源查看详情</p></div>;
    const h = healthType(selected);
    return (
      <div className="hifi-datasource-detail" style={{ padding: 20, overflow: "auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
          <div>
            <h3 style={{ fontSize: "1.1rem", fontWeight: 700 }}>{selected.name}</h3>
            <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", fontFamily: "monospace" }}>
              {selected.db_type === "sqlite" ? selected.database_name : `${selected.host}:${selected.port} / ${selected.database_name}`}
            </div>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <button className="hifi-btn hifi-btn-outline" style={{ padding: "4px 12px", fontSize: "0.72rem" }} onClick={() => { onSelectDataSource(selected); toast.toast(`已激活: ${selected.name}`, "success"); }}>设为当前</button>
            <button className="hifi-btn hifi-btn-outline" style={{ padding: "4px 12px", fontSize: "0.72rem" }} onClick={() => startEdit(selected)}>编辑</button>
            <button className="hifi-btn hifi-btn-outline" style={{ padding: "4px 12px", fontSize: "0.72rem" }} onClick={handleSync} disabled={actionState === "syncing"}><RefreshCw size={12} className={actionState === "syncing" ? "animate-spin" : ""} /> 同步</button>
            <button className="hifi-btn hifi-btn-outline" style={{ padding: "4px 12px", fontSize: "0.72rem" }} onClick={handleHealthCheck} disabled={actionState === "testing"}><Activity size={12} /> 检测</button>
            <button className="hifi-btn hifi-btn-outline" style={{ padding: "4px 12px", fontSize: "0.72rem", color: "var(--accent-red)" }} onClick={handleDelete} disabled={actionState === "deleting"}><Trash2 size={12} /> 删除</button>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
          <span style={{ fontSize: "0.7rem", fontWeight: 500, color: dbBadge(selected).color, background: "rgba(59,130,246,0.08)", padding: "2px 8px", borderRadius: 4 }}>{dbBadge(selected).label}</span>
          <span style={{ fontSize: "0.7rem", fontWeight: 500, color: envBadge(selected.env).color, background: "rgba(100,116,139,0.06)", padding: "2px 8px", borderRadius: 4 }}>{envBadge(selected.env).label}</span>
          {selected.is_read_only && <span style={{ fontSize: "0.7rem", color: "var(--accent-indigo)", background: "rgba(91,92,240,0.06)", padding: "2px 8px", borderRadius: 4 }}>只读</span>}
        </div>
        <h4 className="field-label" style={{ marginBottom: 8 }}>连接配置摘要</h4>
        <div className="hifi-datasource-metrics" style={{ marginBottom: 16 }}>
          <div><span className="field-label">主机</span><div style={{ fontSize: "0.82rem" }}>{selected.db_type === "sqlite" ? "N/A" : selected.host || "-"}</div></div>
          <div><span className="field-label">端口</span><div style={{ fontSize: "0.82rem" }}>{selected.port || "-"}</div></div>
          <div><span className="field-label">数据库</span><div style={{ fontSize: "0.82rem" }}>{selected.database_name || "-"}</div></div>
          <div><span className="field-label">用户名</span><div style={{ fontSize: "0.82rem" }}>{selected.username || "-"}</div></div>
          <div><span className="field-label">环境</span><div style={{ fontSize: "0.82rem" }}>{envBadge(selected.env).label}</div></div>
          <div><span className="field-label">只读</span><div style={{ fontSize: "0.82rem" }}>{selected.is_read_only ? "是" : "否"}</div></div>
        </div>
        <h4 className="field-label" style={{ marginBottom: 8 }}>状态</h4>
        <div className="hifi-datasource-metrics">
          <div><span className="field-label">连接</span><span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: h === "success" ? "var(--accent-green)" : h === "error" ? "var(--accent-red)" : "#cbd5e1", marginRight: 4 }} />{h === "success" ? "正常" : h === "error" ? "失败" : "未检测"}{selected.last_test_latency_ms ? <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}> {selected.last_test_latency_ms}ms</span> : null}</div>
          <div><span className="field-label">上次同步</span><div style={{ fontSize: "0.82rem" }}>{fmtDate(selected.last_sync_at)}</div></div>
          <div><span className="field-label">表数量</span><div style={{ fontSize: "0.82rem" }}>{selected.last_test_tables_count ?? "-"}</div></div>
        </div>
        {selected.last_test_error && <div style={{ marginTop: 8, fontSize: "0.75rem", color: "var(--accent-red)" }}>{selected.last_test_error}</div>}
      </div>
    );
  };

  return (
    <div className="hifi-tab-pane hifi-datasource-page">
      <div className="hifi-page-header">
        <div><h2 className="hifi-page-title">数据源管理</h2></div>
        <button type="button" className="hifi-btn hifi-btn-primary" onClick={startCreate}><Plus size={13} />新建连接</button>
      </div>

      {datasources.length === 0 && mode !== "create" ? (
        <div className="hifi-empty-state"><Database size={28} /><h3>暂无数据源连接</h3><p>添加一个数据库连接以开始使用</p><button className="hifi-btn hifi-btn-primary" onClick={startCreate}><Plus size={13} />新建连接</button></div>
      ) : (
        <div className="hifi-datasource-console">
          {/* Left list */}
          <div className="hifi-datasource-list">
            <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--hairline)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, background: "var(--bg-secondary)", borderRadius: 6, padding: "4px 8px" }}>
                <Search size={12} style={{ color: "var(--text-muted)" }} />
                <input className="hifi-input" style={{ border: "none", background: "transparent", padding: "2px 0", fontSize: "0.78rem" }} placeholder="搜索..." value={search} onChange={(e) => setSearch(e.target.value)} />
              </div>
            </div>
            <div style={{ flex: 1, overflow: "auto", padding: "4px 6px" }}>
              {filtered.map((ds) => (
                <button key={ds.id} className={`hifi-datasource-list-item${ds.id === selectedId ? " active" : ""}`} onClick={() => { setMode("detail"); setSelectedId(ds.id); }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <Database size={12} style={{ color: ds.id === selectedId ? "var(--accent-indigo)" : "var(--text-muted)", flexShrink: 0 }} />
                    <span style={{ fontSize: "0.8rem", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{ds.name}</span>
                  </div>
                  <div style={{ display: "flex", gap: 4, marginTop: 2 }}>
                    <span style={{ fontSize: "0.6rem", color: dbBadge(ds).color }}>{dbBadge(ds).label}</span>
                    <span style={{ fontSize: "0.6rem", color: envBadge(ds.env).color }}>{envBadge(ds.env).label}</span>
                    <span style={{ width: 5, height: 5, borderRadius: "50%", background: healthType(ds) === "success" ? "var(--accent-green)" : healthType(ds) === "error" ? "var(--accent-red)" : "#cbd5e1", marginLeft: "auto" }} />
                  </div>
                </button>
              ))}
            </div>
          </div>
          {/* Right panel */}
          <div className="hifi-datasource-detail" style={{ minHeight: 0 }}>
            {mode === "detail" && renderDetail()}
            {mode === "create" && renderForm("新增数据源", "保存并同步 Schema", handleCreate)}
            {mode === "edit" && renderForm("编辑数据源", "保存修改", handleUpdate)}
          </div>
        </div>
      )}

      <DangerConfirmDialog details={confirmDetails} />
    </div>
  );
};
