import { useEffect, useState } from "react";
import {
  Activity,
  BookOpen,
  ChevronDown,
  ChevronRight,
  Database,
  Eye,
  HardDrive,
  RefreshCw,
  Table2,
  Terminal,
} from "lucide-react";
import { api } from "./lib/api";
import type { DataSource, SchemaTable } from "./lib/api";
import { DataSourcesPage } from "./pages/DataSourcesPage";
import { QueryPage } from "./pages/QueryPage";
import { SchemaPage } from "./pages/SchemaPage";
import { DashboardPage } from "./pages/DashboardPage";

type AppTab = "datasources" | "schema" | "query" | "dashboard";

export default function App() {
  const [activeTab, setActiveTab] = useState<AppTab>("datasources");
  const [activeDataSource, setActiveDataSource] = useState<DataSource | null>(null);
  const [datasources, setDatasources] = useState<DataSource[]>([]);
  const [schemaTables, setSchemaTables] = useState<SchemaTable[]>([]);
  const [loadingTree, setLoadingTree] = useState(true);
  const [loadingObjects, setLoadingObjects] = useState(false);
  const [connectionsOpen, setConnectionsOpen] = useState(true);
  const [objectsOpen, setObjectsOpen] = useState(true);
  const [selectedTableName, setSelectedTableName] = useState<string | null>(null);
  const [schemaInitialView, setSchemaInitialView] = useState<"fields" | "er" | "data" | null>(null);

  useEffect(() => {
    void refreshDatasources();
  }, []);

  useEffect(() => {
    if (!activeDataSource) {
      setSchemaTables([]);
      setSelectedTableName(null);
      return;
    }
    void refreshSchemaTables(activeDataSource.id);
  }, [activeDataSource?.id]);

  useEffect(() => {
    if (activeTab !== "schema") setSchemaInitialView(null);
  }, [activeTab]);

  const refreshDatasources = async () => {
    try {
      setLoadingTree(true);
      const items = await api.listDatasources();
      setDatasources(items);
      setActiveDataSource((current) => {
        if (!current) return items[0] ?? null;
        return items.find((item) => item.id === current.id) ?? items[0] ?? null;
      });
    } finally {
      setLoadingTree(false);
    }
  };

  const refreshSchemaTables = async (datasourceId: string) => {
    try {
      setLoadingObjects(true);
      const items = await api.listTables(datasourceId);
      setSchemaTables(items);
      setSelectedTableName((current) =>
        current && items.some((item) => item.table_name === current) ? current : items[0]?.table_name ?? null,
      );
    } finally {
      setLoadingObjects(false);
    }
  };

  const handleSelectDataSource = (ds: DataSource | null) => {
    setActiveDataSource(ds);
    setSelectedTableName(null);
    if (!ds) {
      setActiveTab("datasources");
      return;
    }
    if (ds.database_name === "databox_demo" || ds.name.includes("Demo")) {
      setActiveTab("query");
    } else if (activeTab === "datasources") {
      setActiveTab("schema");
    }
  };

  const handleSelectTable = (tableName: string, showPreview = false) => {
    setSelectedTableName(tableName);
    setActiveTab("schema");
    setSchemaInitialView(showPreview ? "data" : null);
  };

  const workspaceTitle =
    activeTab === "datasources"
      ? "数据源管理"
      : activeTab === "schema"
      ? "Schema 浏览"
      : activeTab === "query"
      ? "SQL 工作台"
      : "AI 监控审计";

  const navItems: { id: AppTab; label: string; icon: typeof Database }[] = [
    { id: "datasources", label: "数据源", icon: Database },
    { id: "schema", label: "Schema", icon: BookOpen },
    { id: "query", label: "工作台", icon: Terminal },
    { id: "dashboard", label: "监控审计", icon: Activity },
  ];

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "280px minmax(0, 1fr)",
        height: "100vh",
        width: "100vw",
        background: "var(--bg-primary)",
        overflow: "hidden",
      }}
    >
      {/* ═══ SIDEBAR ═══ */}
      <aside
        className="select-none"
        style={{
          display: "grid",
          gridTemplateRows: "auto auto minmax(0, 1fr) auto",
          background: "var(--bg-surface)",
          borderRight: "1px solid var(--border-light)",
          overflow: "hidden",
        }}
      >
        {/* Logo */}
        <div style={{ padding: "24px 20px 16px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <div
              style={{
                width: 34,
                height: 34,
                borderRadius: 8,
                background: "var(--accent-indigo)",
                display: "grid",
                placeItems: "center",
              }}
            >
              <HardDrive size={17} color="#fff" />
            </div>
            <div>
              <h1
                className="text-display"
                style={{ fontSize: "1.25rem", fontWeight: 700, lineHeight: 1.2, color: "var(--text-primary)" }}
              >
                DataBox
              </h1>
              <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: 1 }}>
                数据库探索实验室
              </p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav style={{ padding: "0 14px 12px", display: "flex", flexDirection: "column", gap: 4 }}>
          {navItems.map(({ id, label, icon: Icon }) => {
            const isActive = activeTab === id;
            return (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                disabled={id !== "datasources" && !activeDataSource}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  width: "100%",
                  padding: "9px 14px",
                  border: "none",
                  borderRadius: 8,
                  background: isActive ? "var(--bg-active)" : "transparent",
                  color: isActive ? "var(--accent-indigo)" : "var(--text-secondary)",
                  fontWeight: isActive ? 600 : 500,
                  fontSize: "0.88rem",
                  cursor: id !== "datasources" && !activeDataSource ? "not-allowed" : "pointer",
                  opacity: id !== "datasources" && !activeDataSource ? 0.45 : 1,
                  transition: "background 0.15s, color 0.15s",
                }}
              >
                <Icon size={16} />
                {label}
              </button>
            );
          })}
        </nav>

        {/* Tree */}
        <div style={{ padding: "0 14px", overflow: "auto" }}>
          <div
            style={{
              border: "1px solid var(--border-light)",
              borderRadius: 10,
              overflow: "hidden",
            }}
          >
            {/* Connections */}
            <button
              onClick={() => setConnectionsOpen((v) => !v)}
              style={{
                width: "100%",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "10px 14px",
                border: "none",
                background: "var(--bg-secondary)",
                color: "var(--text-secondary)",
                fontSize: "0.78rem",
                fontWeight: 600,
                cursor: "pointer",
                letterSpacing: "0.02em",
              }}
            >
              连接列表
              {connectionsOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </button>

            {connectionsOpen && (
              <div style={{ padding: "10px 12px" }}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: 8,
                  }}
                >
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    已保存 ({datasources.length})
                  </span>
                  <button
                    className="btn-ghost"
                    onClick={() => void refreshDatasources()}
                    disabled={loadingTree}
                    style={{ fontSize: "0.72rem" }}
                  >
                    <RefreshCw size={11} className={loadingTree ? "animate-spin" : ""} />
                  </button>
                </div>

                {loadingTree ? (
                  <div style={{ padding: "14px 8px" }}>
                    <div className="skeleton" style={{ height: 36, marginBottom: 6, borderRadius: 6 }} />
                    <div className="skeleton" style={{ height: 36, borderRadius: 6 }} />
                  </div>
                ) : datasources.length === 0 ? (
                  <div style={{ padding: "16px 8px", fontSize: "0.8rem", color: "var(--text-muted)", textAlign: "center" }}>
                    暂无连接
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    {datasources.map((ds) => {
                      const selected = activeDataSource?.id === ds.id;
                      return (
                        <button
                          key={ds.id}
                          onClick={() => handleSelectDataSource(ds)}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                            width: "100%",
                            padding: "8px 10px",
                            border: "none",
                            borderRadius: 6,
                            background: selected ? "var(--bg-active)" : "transparent",
                            color: selected ? "var(--accent-indigo)" : "var(--text-secondary)",
                            cursor: "pointer",
                            textAlign: "left",
                            transition: "background 0.12s",
                          }}
                        >
                          <Database size={13} style={{ flexShrink: 0, opacity: selected ? 1 : 0.5 }} />
                          <div style={{ minWidth: 0 }}>
                            <div
                              style={{
                                fontSize: "0.82rem",
                                fontWeight: selected ? 600 : 500,
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                              }}
                            >
                              {ds.name}
                            </div>
                            <div
                              style={{
                                fontSize: "0.7rem",
                                color: "var(--text-muted)",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                                marginTop: 1,
                              }}
                            >
                              {ds.host}:{ds.port}
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {/* Objects */}
            <button
              onClick={() => setObjectsOpen((v) => !v)}
              style={{
                width: "100%",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "10px 14px",
                border: "none",
                borderTop: "1px solid var(--border-light)",
                background: "var(--bg-secondary)",
                color: "var(--text-secondary)",
                fontSize: "0.78rem",
                fontWeight: 600,
                cursor: "pointer",
                letterSpacing: "0.02em",
              }}
            >
              数据对象
              {objectsOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </button>

            {objectsOpen && (
              <div style={{ padding: "10px 12px" }}>
                {!activeDataSource ? (
                  <div style={{ padding: "16px 8px", fontSize: "0.8rem", color: "var(--text-muted)", textAlign: "center" }}>
                    请先选择连接
                  </div>
                ) : (
                  <>
                    <div style={{ marginBottom: 10 }}>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>当前数据库</div>
                      <div style={{ fontSize: "0.85rem", fontWeight: 600, marginTop: 2 }}>
                        {activeDataSource.database_name}
                      </div>
                    </div>

                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        padding: "4px 0 8px",
                      }}
                    >
                      <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                        表 ({schemaTables.length})
                      </span>
                      <button
                        className="btn-ghost"
                        onClick={() => void refreshSchemaTables(activeDataSource.id)}
                        disabled={loadingObjects}
                        style={{ fontSize: "0.72rem" }}
                      >
                        <RefreshCw size={11} className={loadingObjects ? "animate-spin" : ""} />
                      </button>
                    </div>

                    {loadingObjects ? (
                      <div style={{ padding: "8px 0" }}>
                        {[1, 2, 3].map((i) => (
                          <div key={i} className="skeleton" style={{ height: 32, marginBottom: 4, borderRadius: 4 }} />
                        ))}
                      </div>
                    ) : schemaTables.length === 0 ? (
                      <div style={{ padding: "16px 8px", fontSize: "0.8rem", color: "var(--text-muted)", textAlign: "center" }}>
                        尚未同步
                      </div>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                        {schemaTables.map((table) => {
                          const selected = selectedTableName === table.table_name;
                          return (
                            <div
                              key={table.id}
                              style={{ display: "flex", alignItems: "center", gap: 2 }}
                            >
                              <button
                                onClick={() => handleSelectTable(table.table_name)}
                                style={{
                                  flex: 1,
                                  display: "flex",
                                  alignItems: "center",
                                  gap: 8,
                                  padding: "6px 10px",
                                  border: "none",
                                  borderRadius: 5,
                                  background: selected ? "var(--bg-active)" : "transparent",
                                  color: selected ? "var(--accent-indigo)" : "var(--text-secondary)",
                                  cursor: "pointer",
                                  textAlign: "left",
                                  transition: "background 0.12s",
                                  minWidth: 0,
                                }}
                              >
                                <Table2 size={12} style={{ flexShrink: 0, opacity: selected ? 1 : 0.4 }} />
                                <span
                                  style={{
                                    fontSize: "0.81rem",
                                    fontWeight: selected ? 600 : 400,
                                    overflow: "hidden",
                                    textOverflow: "ellipsis",
                                    whiteSpace: "nowrap",
                                  }}
                                >
                                  {table.table_name}
                                </span>
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleSelectTable(table.table_name, true);
                                }}
                                title="预览"
                                className="btn-ghost"
                                style={{ padding: 4, flexShrink: 0 }}
                              >
                                <Eye size={12} />
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div
          style={{
            padding: "10px 18px",
            borderTop: "1px solid var(--border-light)",
            display: "flex",
            alignItems: "center",
            gap: 6,
            fontSize: "0.72rem",
            color: "var(--text-muted)",
          }}
        >
          <Activity size={11} />
          <span>Engine :18625</span>
        </div>
      </aside>

      {/* ═══ MAIN CONTENT ═══ */}
      <section
        style={{
          display: "grid",
          gridTemplateRows: "auto minmax(0, 1fr) auto",
          minWidth: 0,
          height: "100%",
          overflow: "hidden",
        }}
      >
        {/* Header / Breadcrumb */}
        <header
          className="select-none"
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "16px 24px",
            borderBottom: "1px solid var(--border-light)",
            background: "var(--bg-surface)",
            borderTop: activeDataSource?.env === "prod" ? "3px solid var(--accent-red)" : undefined,
          }}
        >
          <div className="breadcrumb">
            <span style={{ color: "var(--text-muted)" }}>工作区</span>
            <span className="breadcrumb-sep">/</span>
            <span className="breadcrumb-current">{workspaceTitle}</span>
            {activeDataSource && (
              <>
                <span className="breadcrumb-sep">/</span>
                <span>{activeDataSource.name}</span>
              </>
            )}
            {activeTab === "schema" && selectedTableName && (
              <>
                <span className="breadcrumb-sep">/</span>
                <span style={{ color: "var(--text-secondary)" }}>{selectedTableName}</span>
              </>
            )}
          </div>
          {activeDataSource ? (
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {activeDataSource.env === "prod" && (
                <span className="status-badge" style={{ background: "rgba(220, 38, 38, 0.12)", color: "var(--accent-red)", border: "1px solid rgba(220, 38, 38, 0.3)", fontWeight: 700, display: "flex", alignItems: "center", gap: 4 }}>
                  🚨 生产环境 PROD
                </span>
              )}
              {activeDataSource.env === "test" && (
                <span className="status-badge" style={{ background: "rgba(217, 119, 6, 0.12)", color: "var(--accent-amber)", border: "1px solid rgba(217, 119, 6, 0.3)", fontWeight: 600 }}>
                  🔬 测试环境 TEST
                </span>
              )}
              {activeDataSource.env === "dev" && (
                <span className="status-badge" style={{ background: "var(--bg-active)", color: "var(--text-secondary)", border: "1px solid var(--border-light)" }}>
                  💻 开发环境 DEV
                </span>
              )}
              {activeDataSource.is_read_only && (
                <span className="status-badge" style={{ background: "rgba(74, 91, 192, 0.12)", color: "var(--accent-indigo)", border: "1px solid rgba(74, 91, 192, 0.3)", fontWeight: 600 }}>
                  🔒 只读保护
                </span>
              )}
              <span className="status-badge status-badge-success">{activeDataSource.database_name}</span>
            </div>
          ) : (
            <span className="status-badge status-badge-neutral">未连接</span>
          )}
        </header>

        {/* Page Content */}
        <main
          style={{
            padding: 20,
            overflow: "hidden",
            minWidth: 0,
            height: "100%",
            display: "flex",
            flexDirection: "column",
          }}
        >
          {activeTab === "datasources" && (
            <DataSourcesPage
              onSelectDataSource={handleSelectDataSource}
              activeDataSource={activeDataSource}
              onRefreshDatasources={refreshDatasources}
            />
          )}
          {activeTab === "schema" && activeDataSource && (
            <SchemaPage
              datasource={activeDataSource}
              initialViewTab={schemaInitialView ?? undefined}
            />
          )}
          {activeTab === "query" && activeDataSource && (
            <QueryPage datasource={activeDataSource} />
          )}
          {activeTab === "dashboard" && activeDataSource && (
            <DashboardPage datasource={activeDataSource} />
          )}
        </main>

        {/* Footer */}
        <footer
          className="select-none"
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "6px 24px",
            borderTop: "1px solid var(--border-light)",
            background: "var(--bg-surface)",
            fontSize: "0.72rem",
            color: "var(--text-muted)",
          }}
        >
          <span>DataBox V1.0 — 本地数据库探索实验室</span>
          <span>Desktop-first · MySQL Client</span>
        </footer>
      </section>
    </div>
  );
}
