import { useEffect, useState } from "react";
import {
  Activity,
  Database,
  HardDrive,
  FolderKanban,
  Settings,
  Layout
} from "lucide-react";
import { api } from "./lib/api";
import type { DataSource, Project, SchemaTable } from "./lib/api";
import { BackupsPage } from "./pages/BackupsPage";
import { DataSourcesPage } from "./pages/DataSourcesPage";
import { EnvironmentsPage } from "./pages/EnvironmentsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { WorkbenchPage } from "./pages/WorkbenchPage";
import { DemoTourGuide } from "./components/DemoTourGuide";
import { PromptDialog } from "./components/PromptDialog";

type AppTab = "workbench" | "environments" | "backups" | "dashboard" | "datasources";

export default function App() {
  const [activeTab, setActiveTab] = useState<AppTab>("workbench");
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [activeDataSource, setActiveDataSource] = useState<DataSource | null>(null);
  const [datasources, setDatasources] = useState<DataSource[]>([]);
  const [schemaTables, setSchemaTables] = useState<SchemaTable[]>([]);

  const [loadingTree, setLoadingTree] = useState(true);
  const [loadingObjects, setLoadingObjects] = useState(false);
  const [showCreateProject, setShowCreateProject] = useState(false);

  useEffect(() => {
    void refreshProjects();
  }, []);

  useEffect(() => {
    void refreshDatasources();
  }, [activeProject?.id]);

  useEffect(() => {
    if (!activeDataSource) {
      setSchemaTables([]);
      return;
    }
    void refreshSchemaTables(activeDataSource.id);
  }, [activeDataSource?.id]);

  // Global keyboard shortcuts for tab navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      if (!mod) return;
      if (e.key === "1") { e.preventDefault(); setActiveTab("workbench"); }
      if (e.key === "2") { e.preventDefault(); setActiveTab("environments"); }
      if (e.key === "3") { e.preventDefault(); setActiveTab("backups"); }
      if (e.key === "4") { e.preventDefault(); setActiveTab("dashboard"); }
      if (e.key === "5") { e.preventDefault(); setActiveTab("datasources"); }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const refreshProjects = async () => {
    const items = await api.listProjects();
    setProjects(items);
    setActiveProject((current) => {
      if (!current) return items[0] ?? null;
      return items.find((item) => item.id === current.id) ?? items[0] ?? null;
    });
  };

  const refreshDatasources = async () => {
    try {
      setLoadingTree(true);
      const items = await api.listDatasources(activeProject?.id);
      setDatasources(items);
      setActiveDataSource((current) => {
        if (!current) return items[0] ?? null;
        return items.find((item) => item.id === current.id) ?? items[0] ?? null;
      });
    } finally {
      setLoadingTree(false);
    }
  };

  const handleCreateProject = async (name: string) => {
    const created = await api.createProject({ name });
    await refreshProjects();
    setActiveProject(created);
    setActiveDataSource(null);
    setSchemaTables([]);
    setActiveTab("workbench");
  };

  const refreshSchemaTables = async (datasourceId: string) => {
    try {
      setLoadingObjects(true);
      const items = await api.listTables(datasourceId);
      setSchemaTables(items);
    } finally {
      setLoadingObjects(false);
    }
  };

  const handleSelectDataSource = (ds: DataSource | null) => {
    setActiveDataSource(ds);
    if (!ds) {
      setActiveTab("datasources");
      return;
    }
    setActiveTab("workbench");
  };

  // Nav Item structures
  const navItems: { id: AppTab; label: string; icon: typeof Database }[] = [
    { id: "workbench", label: "工作台", icon: Layout },
    { id: "environments", label: "环境", icon: HardDrive },
    { id: "backups", label: "备份", icon: FolderKanban },
    { id: "dashboard", label: "监控", icon: Activity },
    { id: "datasources", label: "设置", icon: Settings },
  ];

  // Environment badge glowing indicators
  const getEnvBadgeColor = () => {
    if (!activeDataSource) return "rgba(148, 163, 184, 0.4)";
    if (activeDataSource.env === "prod") return "var(--accent-red)";
    if (activeDataSource.env === "test") return "var(--accent-amber)";
    return "var(--accent-green)";
  };

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "44px minmax(0, 1fr)",
        height: "100vh",
        width: "100vw",
        background: "var(--bg-primary)",
        overflow: "hidden",
      }}
    >
      {/* ═══ 1. HIGH-FIDELITY LEFT NAVIGATION RAIL (44px) ═══ */}
      <aside
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "space-between",
          background: "var(--bg-surface)",
          borderRight: "1px solid var(--border-light)",
          padding: "16px 0 12px",
          zIndex: 10,
          boxShadow: "2px 0 8px rgba(0,0,0,0.02)",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
          {/* Logo Brand Icon */}
          <div
            className="hover-lift"
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              background: "linear-gradient(135deg, var(--accent-indigo), #6366F1)",
              display: "grid",
              placeItems: "center",
              boxShadow: "0 4px 10px rgba(74, 91, 192, 0.25)",
              cursor: "pointer",
            }}
            onClick={() => setActiveTab("workbench")}
            title="DataBox - 物理智能数据库工作台"
          >
            <HardDrive size={16} color="#fff" />
          </div>

          <div style={{ width: 20, height: "1px", background: "var(--border-light)" }} />

          {/* Navigation tabs */}
          <div style={{ display: "flex", flexDirection: "column", gap: 6, width: "100%" }}>
            {navItems.map(({ id, label, icon: Icon }) => {
              const isActive = activeTab === id;
              const isLocked = id === "workbench" && !activeDataSource;

              return (
                <button
                  key={id}
                  onClick={() => setActiveTab(id)}
                  disabled={isLocked && datasources.length > 0} // lock only if they have data sources but none connected
                  style={{
                    position: "relative",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: 32,
                    height: 32,
                    margin: "0 auto",
                    border: "none",
                    borderRadius: 8,
                    background: isActive ? "rgba(74, 91, 192, 0.08)" : "transparent",
                    color: isActive ? "var(--accent-indigo)" : "var(--text-secondary)",
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                  }}
                  title={label}
                >
                  <Icon size={16} style={{ color: isActive ? "var(--accent-indigo)" : "inherit" }} />
                  
                  {isActive && (
                    <div
                      style={{
                        position: "absolute",
                        left: 0,
                        top: 8,
                        bottom: 8,
                        width: 3,
                        borderRadius: "0 4px 4px 0",
                        background: "var(--accent-indigo)",
                      }}
                    />
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Bottom Rail Controls */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
          {/* Active Connection Breathing light indicator */}
          {activeDataSource && (
            <div 
              style={{
                width: 10,
                height: 10,
                borderRadius: "50%",
                background: getEnvBadgeColor(),
                boxShadow: `0 0 8px ${getEnvBadgeColor()}`,
                animation: "pulse 2s infinite"
              }}
              title={`已连接: ${activeDataSource.name} (${activeDataSource.env})`}
            />
          )}

          <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", fontWeight: 600 }}>
            :18625
          </div>
        </div>
      </aside>

      {/* ═══ 2. MAIN WORKSPACE VIEWPORT ═══ */}
      <section
        style={{
          display: "grid",
          gridTemplateRows: activeTab === "workbench" ? "minmax(0, 1fr) auto" : "auto minmax(0, 1fr) auto",
          minWidth: 0,
          height: "100%",
          overflow: "hidden",
        }}
      >
        {/* Top Breadcrumb Header */}
        {activeTab !== "workbench" && (
          <header
            className="select-none"
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "10px 24px",
              borderBottom: "1px solid var(--border-light)",
              background: "var(--bg-surface)",
              borderTop: activeDataSource?.env === "prod" ? "3px solid var(--accent-red)" : undefined,
            }}
          >
            <div className="breadcrumb" style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "0.82rem" }}>
              <span style={{ color: "var(--text-muted)" }}>{activeProject?.name || "DataBox"}</span>
              <span className="breadcrumb-sep" style={{ color: "var(--text-muted)" }}>/</span>
              <span className="breadcrumb-current" style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                {navItems.find(n => n.id === activeTab)?.label}
              </span>
              {activeDataSource && (
                <>
                  <span className="breadcrumb-sep" style={{ color: "var(--text-muted)" }}>/</span>
                  <span style={{ color: "var(--text-secondary)" }}>{activeDataSource.name}</span>
                </>
              )}
            </div>
            
            {activeDataSource ? (
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                {activeDataSource.env === "prod" && (
                  <span className="status-badge" style={{ background: "rgba(220, 38, 38, 0.12)", color: "var(--accent-red)", border: "1px solid rgba(220, 38, 38, 0.3)", fontWeight: 700 }}>
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
              <span className="status-badge status-badge-neutral">无激活连接</span>
            )}
          </header>
        )}

        {/* Page rendering */}
        <main
          style={{
            padding: activeTab === "workbench" ? 0 : 20, // Workbench gets absolute full-bleed spacing
            overflow: "hidden",
            minWidth: 0,
            height: "100%",
            display: "flex",
            flexDirection: "column",
          }}
        >
          {activeTab === "workbench" && (
            <WorkbenchPage
              projects={projects}
              activeProject={activeProject}
              setActiveProject={setActiveProject}
              datasources={datasources}
              activeDataSource={activeDataSource}
              setActiveDataSource={handleSelectDataSource}
              schemaTables={schemaTables}
              loadingObjects={loadingObjects}
              loadingTree={loadingTree}
              onRefreshSchemaTables={refreshSchemaTables}
            />
          )}
          {activeTab === "environments" && (
            <EnvironmentsPage
              activeProject={activeProject}
              onRefreshDatasources={refreshDatasources}
              onSelectDataSource={handleSelectDataSource}
            />
          )}
          {activeTab === "backups" && (
            <BackupsPage
              activeProject={activeProject}
              datasources={datasources}
              activeDataSource={activeDataSource}
            />
          )}
          {activeTab === "dashboard" && activeDataSource && (
            <DashboardPage datasource={activeDataSource} />
          )}
          {activeTab === "datasources" && (
            <DataSourcesPage
              onSelectDataSource={handleSelectDataSource}
              activeDataSource={activeDataSource}
              activeProject={activeProject}
              onRefreshDatasources={refreshDatasources}
            />
          )}
        </main>

        {/* System Footer Bar */}
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
          <span>DataBox Studio v1.2 · MySQL / PostgreSQL / SQLite</span>
          <span>Security Exec Layer Active</span>
        </footer>
      </section>

      <PromptDialog
        open={showCreateProject}
        title="创建新项目"
        placeholder="输入项目名称"
        onConfirm={(name) => {
          setShowCreateProject(false);
          void handleCreateProject(name);
        }}
        onCancel={() => setShowCreateProject(false)}
      />

      <DemoTourGuide
        activeTab={activeTab === "workbench" ? "datasources" : activeTab}
        setActiveTab={(t) => setActiveTab(t === "datasources" ? "workbench" : (t as any))}
        activeProject={activeProject}
        projects={projects}
        activeDataSource={activeDataSource}
        datasources={datasources}
        schemaTables={schemaTables}
        handleCreateProject={async (name?: string) => {
          await handleCreateProject(name || "新项目");
        }}
      />
    </div>
  );
}
