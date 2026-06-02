import { useCallback, useEffect, useState } from "react";
import { X, Plus, Trash2, Save } from "lucide-react";
import { api } from "../../lib/api";
import type {
  DataSource,
  SchemaTable,
  SemanticAlias,
  SemanticDimension,
  SemanticMetric,
  WorkspaceTableScope,
} from "../../lib/api";

interface Props {
  datasource: DataSource;
  projectId: string;
  onClose: () => void;
}

type PanelTab = "aliases" | "metrics" | "dimensions" | "table-scope";

export function SemanticSettingsPanel({ datasource, projectId, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<PanelTab>("aliases");
  const [tables, setTables] = useState<SchemaTable[]>([]);

  useEffect(() => {
    api.listTables(datasource.id).then(setTables).catch(() => setTables([]));
  }, [datasource.id]);

  const tabs: { key: PanelTab; label: string }[] = [
    { key: "aliases", label: "Aliases" },
    { key: "metrics", label: "Metrics" },
    { key: "dimensions", label: "Dimensions" },
    { key: "table-scope", label: "Table Scope" },
  ];

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center",
      background: "rgba(0,0,0,0.35)",
    }}>
      <div style={{
        background: "var(--bg-primary)", borderRadius: 8, border: "1px solid var(--border-light)",
        width: 720, maxHeight: "80vh", display: "flex", flexDirection: "column",
        boxShadow: "0 8px 32px rgba(0,0,0,0.18)",
      }}>
        {/* Header */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "10px 14px", borderBottom: "1px solid var(--border-light)",
        }}>
          <span style={{ fontSize: "0.85rem", fontWeight: 700 }}>
            Semantic Settings &mdash; {datasource.name}
          </span>
          <button onClick={onClose} style={iconBtnStyle}>
            <X size={15} />
          </button>
        </div>

        {/* Tab bar */}
        <div style={{ display: "flex", gap: 0, borderBottom: "1px solid var(--border-light)", padding: "0 14px" }}>
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              style={{
                ...tabBtnStyle,
                borderBottom: activeTab === t.key ? "2px solid var(--accent-indigo)" : "2px solid transparent",
                color: activeTab === t.key ? "var(--accent-indigo)" : "var(--text-secondary)",
              }}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflow: "auto", padding: "12px 14px" }}>
          {activeTab === "aliases" && <AliasesEditor datasourceId={datasource.id} />}
          {activeTab === "metrics" && <MetricsEditor datasourceId={datasource.id} />}
          {activeTab === "dimensions" && <DimensionsEditor datasourceId={datasource.id} />}
          {activeTab === "table-scope" && (
            <TableScopeEditor datasourceId={datasource.id} projectId={projectId} tables={tables} />
          )}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Aliases Editor                                                      */
/* ------------------------------------------------------------------ */

function AliasesEditor({ datasourceId }: { datasourceId: string }) {
  const [items, setItems] = useState<SemanticAlias[]>([]);
  const [loading, setLoading] = useState(true);

  const [alias, setAlias] = useState("");
  const [targetType, setTargetType] = useState("column");
  const [target, setTarget] = useState("");
  const [description, setDescription] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try { setItems(await api.listSemanticAliases(datasourceId)); } catch { setItems([]); }
    finally { setLoading(false); }
  }, [datasourceId]);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    if (!alias.trim() || !target.trim()) return;
    await api.createSemanticAlias({ data_source_id: datasourceId, alias: alias.trim(), target_type: targetType, target: target.trim(), description: description || null });
    setAlias(""); setTarget(""); setDescription("");
    await load();
  };

  const handleDelete = async (id: string) => {
    await api.deleteSemanticAlias(id);
    await load();
  };

  if (loading) return <div style={{ color: "var(--text-muted)" }}>Loading...</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "flex-end" }}>
        <Field label="Alias">
          <input className="input-field input-field-sm" style={{ width: 120 }} value={alias} onChange={(e) => setAlias(e.target.value)} placeholder="e.g. GMV" />
        </Field>
        <Field label="Type">
          <select className="input-field input-field-sm" style={{ width: 100 }} value={targetType} onChange={(e) => setTargetType(e.target.value)}>
            <option value="column">column</option>
            <option value="table">table</option>
          </select>
        </Field>
        <Field label="Target">
          <input className="input-field input-field-sm" style={{ width: 180 }} value={target} onChange={(e) => setTarget(e.target.value)} placeholder="e.g. orders.total_amount" />
        </Field>
        <Field label="Desc">
          <input className="input-field input-field-sm" style={{ width: 100 }} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="optional" />
        </Field>
        <button onClick={handleCreate} style={smallPrimaryBtn}><Plus size={13} /> Add</button>
      </div>
      {items.length === 0 && <div style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>No aliases defined.</div>}
      {items.map((item) => (
        <div key={item.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 6px", background: "var(--bg-secondary)", borderRadius: 4 }}>
          <code style={{ fontSize: "0.72rem" }}>{item.alias}</code>
          <span style={{ color: "var(--text-muted)", fontSize: "0.68rem" }}>&rarr; {item.target_type}:{item.target}</span>
          {item.description && <span style={{ color: "var(--text-muted)", fontSize: "0.65rem" }}>({item.description})</span>}
          <div style={{ flex: 1 }} />
          <button onClick={() => handleDelete(item.id)} style={iconBtnStyle}><Trash2 size={12} /></button>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Metrics Editor                                                      */
/* ------------------------------------------------------------------ */

function MetricsEditor({ datasourceId }: { datasourceId: string }) {
  const [items, setItems] = useState<SemanticMetric[]>([]);
  const [loading, setLoading] = useState(true);

  const [name, setName] = useState("");
  const [expression, setExpression] = useState("");
  const [sourceColumns, setSourceColumns] = useState("");
  const [description, setDescription] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try { setItems(await api.listSemanticMetrics(datasourceId)); } catch { setItems([]); }
    finally { setLoading(false); }
  }, [datasourceId]);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    if (!name.trim() || !expression.trim()) return;
    const cols = sourceColumns.trim() ? JSON.stringify(sourceColumns.split(",").map((s) => s.trim())) : null;
    await api.createSemanticMetric({ data_source_id: datasourceId, name: name.trim(), expression: expression.trim(), source_columns_json: cols, description: description || null });
    setName(""); setExpression(""); setSourceColumns(""); setDescription("");
    await load();
  };

  const handleDelete = async (id: string) => {
    await api.deleteSemanticMetric(id);
    await load();
  };

  if (loading) return <div style={{ color: "var(--text-muted)" }}>Loading...</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "flex-end" }}>
        <Field label="Name">
          <input className="input-field input-field-sm" style={{ width: 120 }} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. GMV" />
        </Field>
        <Field label="Expression">
          <input className="input-field input-field-sm" style={{ width: 200 }} value={expression} onChange={(e) => setExpression(e.target.value)} placeholder="e.g. SUM(orders.total_amount)" />
        </Field>
        <Field label="Source Columns">
          <input className="input-field input-field-sm" style={{ width: 160 }} value={sourceColumns} onChange={(e) => setSourceColumns(e.target.value)} placeholder="orders.total_amount" />
        </Field>
        <Field label="Desc">
          <input className="input-field input-field-sm" style={{ width: 100 }} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="optional" />
        </Field>
        <button onClick={handleCreate} style={smallPrimaryBtn}><Plus size={13} /> Add</button>
      </div>
      {items.length === 0 && <div style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>No metrics defined.</div>}
      {items.map((item) => (
        <div key={item.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 6px", background: "var(--bg-secondary)", borderRadius: 4 }}>
          <code style={{ fontSize: "0.72rem", fontWeight: 600 }}>{item.name}</code>
          <code style={{ fontSize: "0.68rem", color: "var(--text-secondary)" }}>{item.expression}</code>
          {item.description && <span style={{ color: "var(--text-muted)", fontSize: "0.65rem" }}>({item.description})</span>}
          <div style={{ flex: 1 }} />
          <button onClick={() => handleDelete(item.id)} style={iconBtnStyle}><Trash2 size={12} /></button>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Dimensions Editor                                                   */
/* ------------------------------------------------------------------ */

function DimensionsEditor({ datasourceId }: { datasourceId: string }) {
  const [items, setItems] = useState<SemanticDimension[]>([]);
  const [loading, setLoading] = useState(true);

  const [name, setName] = useState("");
  const [columnRef, setColumnRef] = useState("");
  const [transform, setTransform] = useState("");
  const [description, setDescription] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try { setItems(await api.listSemanticDimensions(datasourceId)); } catch { setItems([]); }
    finally { setLoading(false); }
  }, [datasourceId]);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    if (!name.trim() || !columnRef.trim()) return;
    await api.createSemanticDimension({ data_source_id: datasourceId, name: name.trim(), column_ref: columnRef.trim(), transform: transform.trim() || null, description: description || null });
    setName(""); setColumnRef(""); setTransform(""); setDescription("");
    await load();
  };

  const handleDelete = async (id: string) => {
    await api.deleteSemanticDimension(id);
    await load();
  };

  if (loading) return <div style={{ color: "var(--text-muted)" }}>Loading...</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "flex-end" }}>
        <Field label="Name">
          <input className="input-field input-field-sm" style={{ width: 120 }} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. 下单日期" />
        </Field>
        <Field label="Column Ref">
          <input className="input-field input-field-sm" style={{ width: 180 }} value={columnRef} onChange={(e) => setColumnRef(e.target.value)} placeholder="e.g. orders.created_at" />
        </Field>
        <Field label="Transform">
          <select className="input-field input-field-sm" style={{ width: 100 }} value={transform} onChange={(e) => setTransform(e.target.value)}>
            <option value="">(none)</option>
            <option value="DATE">DATE</option>
            <option value="MONTH">MONTH</option>
            <option value="YEAR">YEAR</option>
          </select>
        </Field>
        <Field label="Desc">
          <input className="input-field input-field-sm" style={{ width: 100 }} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="optional" />
        </Field>
        <button onClick={handleCreate} style={smallPrimaryBtn}><Plus size={13} /> Add</button>
      </div>
      {items.length === 0 && <div style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>No dimensions defined.</div>}
      {items.map((item) => (
        <div key={item.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 6px", background: "var(--bg-secondary)", borderRadius: 4 }}>
          <code style={{ fontSize: "0.72rem", fontWeight: 600 }}>{item.name}</code>
          <code style={{ fontSize: "0.68rem", color: "var(--text-secondary)" }}>{item.column_ref}{item.transform ? ` [${item.transform}]` : ""}</code>
          <div style={{ flex: 1 }} />
          <button onClick={() => handleDelete(item.id)} style={iconBtnStyle}><Trash2 size={12} /></button>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Table Scope Editor                                                  */
/* ------------------------------------------------------------------ */

function TableScopeEditor({ datasourceId, projectId, tables }: { datasourceId: string; projectId: string; tables: SchemaTable[] }) {
  const [scopeIds, setScopeIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const scopes: WorkspaceTableScope[] = await api.getWorkspaceTableScope(projectId, datasourceId);
      setScopeIds(new Set(scopes.filter((s) => s.enabled).map((s) => s.table_id)));
    } catch { setScopeIds(new Set()); }
    finally { setLoading(false); }
  }, [projectId, datasourceId]);

  useEffect(() => { load(); }, [load]);

  const toggle = (tableId: string) => {
    setScopeIds((prev) => {
      const next = new Set(prev);
      if (next.has(tableId)) next.delete(tableId); else next.add(tableId);
      return next;
    });
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateWorkspaceTableScope({ project_id: projectId, datasource_id: datasourceId, enabled_table_ids: [...scopeIds] });
      await load();
    } finally { setSaving(false); }
  };

  if (loading) return <div style={{ color: "var(--text-muted)" }}>Loading...</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
          {scopeIds.size} of {tables.length} tables enabled for querying
        </span>
        <button onClick={handleSave} disabled={saving} style={smallPrimaryBtn}>
          <Save size={13} /> {saving ? "Saving..." : "Save"}
        </button>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 2, maxHeight: 400, overflow: "auto" }}>
        {tables.map((table) => (
          <label key={table.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "3px 6px", cursor: "pointer", borderRadius: 3, background: scopeIds.has(table.id) ? "var(--bg-active)" : "transparent" }}>
            <input type="checkbox" checked={scopeIds.has(table.id)} onChange={() => toggle(table.id)} />
            <span style={{ fontSize: "0.72rem" }}>{table.table_name}</span>
            {table.table_comment && <span style={{ color: "var(--text-muted)", fontSize: "0.65rem" }}>&mdash; {table.table_comment}</span>}
          </label>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Shared styles                                                       */
/* ------------------------------------------------------------------ */

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: "0.65rem", color: "var(--text-muted)" }}>
      {label}
      {children}
    </label>
  );
}

const iconBtnStyle: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", justifyContent: "center",
  width: 26, height: 26, border: "none", borderRadius: 4,
  background: "transparent", color: "var(--text-secondary)", cursor: "pointer",
};

const tabBtnStyle: React.CSSProperties = {
  padding: "6px 12px", border: "none", background: "transparent",
  fontSize: "0.72rem", fontWeight: 600, cursor: "pointer",
};

const smallPrimaryBtn: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: 4,
  padding: "4px 10px", height: 26, border: "none", borderRadius: 4,
  background: "var(--accent-indigo)", color: "#fff", fontSize: "0.7rem",
  fontWeight: 600, cursor: "pointer",
};
