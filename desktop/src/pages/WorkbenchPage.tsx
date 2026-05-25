import { useState, useMemo, useEffect } from "react";
import { 
  Database, 
  Table2, 
  Terminal, 
  ChevronDown, 
  ChevronRight, 
  Plus, 
  X, 
  Eye, 
  Sparkles, 
  ShieldCheck, 
  Keyboard, 
  Play, 
  Search, 
  RefreshCw,
  Code2,
  HardDrive
} from "lucide-react";
import { api } from "../lib/api";
import type { DataSource, Project, SchemaTable } from "../lib/api";
import { QueryPage } from "./QueryPage";
import { SchemaPage } from "./SchemaPage";
import { DataPage } from "./DataPage";
import { ErrorBoundary } from "../components/ErrorBoundary";

// Tab structure for the workspace
export interface WorkbenchTab {
  id: string; // e.g. "query_123" or "table:users"
  type: "query" | "table" | "ai_bench";
  title: string;
  tableName?: string;
  activeSubTab?: "data" | "schema" | "er" | "design";
  sqlDraft?: string;
}

interface WorkbenchPageProps {
  // Connections and metadata states
  projects: Project[];
  activeProject: Project | null;
  setActiveProject: (p: Project | null) => void;
  datasources: DataSource[];
  activeDataSource: DataSource | null;
  setActiveDataSource: (ds: DataSource | null) => void;
  schemaTables: SchemaTable[];
  loadingObjects: boolean;
  loadingTree: boolean;
  onRefreshSchemaTables: (datasourceId: string) => Promise<void>;
}

// ═══ PREFIX GROUPS FOR TREE OBJECTS ═══
const MODULE_PREFIXES: [string, string][] = [
  ["account_", "账号模块"],
  ["ai_", "AI 智能模块"],
  ["agent_", "任务模块"],
  ["auto_", "任务模块"],
  ["billing_", "计费模块"],
  ["content_", "内容模块"],
  ["id_", "身份组织模块"],
  ["login_", "认证会话模块"],
  ["media_", "媒体素材模块"],
  ["monitoring_", "监控模块"],
  ["nurture_", "客户培育模块"],
  ["notification_", "通知模块"],
  ["platform_", "平台账号模块"],
  ["publish_", "发布模块"],
  ["rbac_", "权限模块"],
  ["sales_", "销售模块"],
  ["token_", "Token 账户模块"],
  ["user_", "用户模块"],
  ["video_", "视频模块"],
  ["xhs_", "小红书模块"],
  ["audit_", "审计模块"],
  ["scheduler_", "调度模块"],
];

const MODULE_ORDER = [
  "账号模块",
  "身份组织模块",
  "认证会话模块",
  "平台账号模块",
  "Token 账户模块",
  "销售模块",
  "发布模块",
  "媒体素材模块",
  "视频模块",
  "小红书模块",
  "客户培育模块",
  "AI 智能模块",
  "任务模块",
  "计费模块",
  "审计模块",
  "权限模块",
  "监控模块",
  "通知模块",
  "用户模块",
  "内容模块",
  "调度模块",
  "通用模块",
];

function getModuleTag(tableName: string): string {
  for (const [prefix, tag] of MODULE_PREFIXES) {
    if (tableName.startsWith(prefix)) return tag;
  }
  return "通用模块";
}

export const WorkbenchPage = ({
  projects,
  activeProject,
  setActiveProject,
  datasources,
  activeDataSource,
  setActiveDataSource,
  schemaTables,
  loadingObjects,
  loadingTree,
  onRefreshSchemaTables,
}: WorkbenchPageProps) => {
  // Tabs management
  if (false) { console.log(projects, setActiveProject); }
  const [tabs, setTabs] = useState<WorkbenchTab[]>([]);
  const [activeTabId, setActiveTabId] = useState<string | null>(null);

  // Object Explorer Tree expansion states
  const [treeSearch, setTreeSearch] = useState("");
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [tablesFolderExpanded, setTablesFolderExpanded] = useState(true);
  const [viewsFolderExpanded, setViewsFolderExpanded] = useState(false);
  const [funcsFolderExpanded, setFuncsFolderExpanded] = useState(false);
  const [procsFolderExpanded, setProcsFolderExpanded] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Floating Contextual AI Panel
  const [aiPanelOpen, setAiPanelOpen] = useState(false);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiResponse, setAiResponse] = useState("");
  const [aiLoading, setAiLoading] = useState(false);

  // Auto clear tabs on connection changes to maintain database isolation
  useEffect(() => {
    setTabs([]);
    setActiveTabId(null);
  }, [activeDataSource?.id]);

  // Open active tab
  const activeTab = useMemo(() => {
    return tabs.find(t => t.id === activeTabId) || null;
  }, [tabs, activeTabId]);

  // Unified tables grouping algorithm
  const filteredTables = useMemo(() => {
    return schemaTables.filter(
      (t) =>
        t.table_name.toLowerCase().includes(treeSearch.toLowerCase()) ||
        t.table_comment.toLowerCase().includes(treeSearch.toLowerCase()),
    );
  }, [schemaTables, treeSearch]);

  const groupedTables = useMemo(() => {
    const groups = new Map<string, SchemaTable[]>();
    for (const t of filteredTables) {
      const tag = t.module_tag || getModuleTag(t.table_name);
      if (!groups.has(tag)) {
        groups.set(tag, []);
      }
      groups.get(tag)!.push(t);
    }
    return Array.from(groups.entries())
      .sort(([left], [right]) => {
        const leftIndex = MODULE_ORDER.indexOf(left);
        const rightIndex = MODULE_ORDER.indexOf(right);
        const normalizedLeft = leftIndex === -1 ? MODULE_ORDER.length : leftIndex;
        const normalizedRight = rightIndex === -1 ? MODULE_ORDER.length : rightIndex;
        return normalizedLeft - normalizedRight || left.localeCompare(right, "zh-Hans-CN");
      })
      .map(([tag, group]) => ({
        tag,
        tables: [...group].sort((a, b) => a.table_name.localeCompare(b.table_name)),
      }));
  }, [filteredTables]);

  // ── Tab Management Handlers ──
  const handleOpenQueryTab = (sqlDraft?: string, title?: string) => {
    const id = `query:${Date.now()}`;
    const newTab: WorkbenchTab = {
      id,
      type: "query",
      title: title || `查询_${tabs.filter(t => t.type === "query").length + 1}`,
      sqlDraft: sqlDraft || ""
    };
    setTabs(prev => [...prev, newTab]);
    setActiveTabId(id);
  };

  const handleOpenTableTab = (tableName: string, subTab: "data" | "schema" | "er" | "design" = "data") => {
    const id = `table:${tableName}`;
    const exists = tabs.some(t => t.id === id);
    if (exists) {
      setTabs(prev => prev.map(t => t.id === id ? { ...t, activeSubTab: subTab } : t));
      setActiveTabId(id);
    } else {
      const newTab: WorkbenchTab = {
        id,
        type: "table",
        title: `表: ${tableName}`,
        tableName,
        activeSubTab: subTab
      };
      setTabs(prev => [...prev, newTab]);
      setActiveTabId(id);
    }
  };

  const handleCloseTab = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const nextTabs = tabs.filter(t => t.id !== id);
    setTabs(nextTabs);
    if (activeTabId === id) {
      setActiveTabId(nextTabs[nextTabs.length - 1]?.id || null);
    }
  };

  const handleSwitchSubTab = (tabId: string, subTab: "data" | "schema" | "er" | "design") => {
    setTabs(prev => prev.map(t => t.id === tabId ? { ...t, activeSubTab: subTab } : t));
  };

  // Quick SQL select generation
  const handleGenerateSelect = (tableName: string) => {
    const sql = `SELECT * FROM \`${tableName}\` LIMIT 100;`;
    handleOpenQueryTab(sql, `查询: ${tableName}`);
  };

  // Contextual AI prompts based on current tab
  const handleAiContextAction = async (promptText: string) => {
    if (!activeDataSource) return;
    setAiPanelOpen(true);
    setAiLoading(true);
    setAiResponse("");
    setAiPrompt(promptText);
    try {
      // Direct call to general AI SQL/Schema logic
      const prompt = `数据源: ${activeDataSource.name} (${activeDataSource.database_name})\n当前表: ${activeTab?.tableName || "无"}\n当前查询: ${promptText}\n请生成或解释 SQL 架构、优化方案或数据趋势。`;
      const res = await api.generateSql(activeDataSource.id, prompt);
      setAiResponse(res.sql || res.guardrail?.message || "AI 已成功回答。");
    } catch (err: any) {
      setAiResponse(`出错了: ${err.message}`);
    } finally {
      setAiLoading(false);
    }
  };

  const handleAskGeneralAi = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!aiPrompt.trim() || !activeDataSource) return;
    setAiLoading(true);
    setAiResponse("");
    try {
      const res = await api.generateSql(activeDataSource.id, aiPrompt);
      setAiResponse(res.sql || `生成 SQL:\n${res.sql}\n\n安全校验: ${res.guardrail?.message ?? "通过"}`);
    } catch (err: any) {
      setAiResponse(`生成失败: ${err.message}`);
    } finally {
      setAiLoading(false);
    }
  };

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: sidebarCollapsed ? "0px minmax(0, 1fr)" : "250px minmax(0, 1fr)",
        height: "100%",
        width: "100%",
        overflow: "hidden",
        background: "var(--bg-primary)",
        transition: "grid-template-columns 0.22s cubic-bezier(0.4, 0, 0.2, 1)"
      }}
    >
      {/* ═══ LEFT OBJECT EXPLORER TREE ═══ */}
      <aside
        style={{
          display: "flex",
          flexDirection: "column",
          background: "var(--bg-surface)",
          borderRight: sidebarCollapsed ? "none" : "1px solid var(--border-light)",
          overflow: "hidden",
          height: "100%",
        }}
      >
        <div style={{ width: 250, display: "flex", flexDirection: "column", height: "100%" }}>
          
          {/* Sidebar Header with Object Explorer Label */}
          <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--border-light)", background: "rgba(0,0,0,0.01)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--text-primary)", display: "flex", alignItems: "center", gap: 6 }}>
              <Code2 size={13} style={{ color: "var(--accent-indigo)" }} />
              对象资源管理器
            </span>
            <button 
              className="btn-ghost" 
              onClick={() => setSidebarCollapsed(true)}
              style={{ padding: 2 }}
              title="隐藏侧栏"
            >
              <ChevronRight size={13} style={{ transform: "rotate(180deg)" }} />
            </button>
          </div>

          {/* Unified Tree View Scroll Area */}
          <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", padding: "8px 10px" }}>
            {/* Project Connection Root */}
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              {loadingTree ? (
                <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 6 }}>
                  <div className="skeleton" style={{ height: 20, borderRadius: 4 }} />
                  <div className="skeleton" style={{ height: 20, borderRadius: 4 }} />
                </div>
              ) : datasources.length === 0 ? (
                <div style={{ padding: "20px 10px", fontSize: "0.76rem", color: "var(--text-muted)", textAlign: "center" }}>
                  暂无连接，请先去 [数据源] 页面添加
                </div>
              ) : (
                datasources.map((ds) => {
                  const isConnected = activeDataSource?.id === ds.id;
                  return (
                    <div key={ds.id} style={{ display: "flex", flexDirection: "column" }}>
                      {/* Connection Root Node */}
                      <button
                        onClick={() => setActiveDataSource(ds)}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                          width: "100%",
                          padding: "6px 8px",
                          border: "none",
                          borderRadius: 6,
                          background: isConnected ? "var(--bg-active)" : "transparent",
                          color: isConnected ? "var(--accent-indigo)" : "var(--text-secondary)",
                          cursor: "pointer",
                          textAlign: "left",
                          transition: "background 0.15s",
                        }}
                      >
                        <ChevronRight 
                          size={12} 
                          style={{ 
                            transform: isConnected ? "rotate(90deg)" : "rotate(0deg)", 
                            transition: "transform 0.15s",
                            opacity: 0.5 
                          }} 
                        />
                        <Database size={12} style={{ opacity: isConnected ? 1 : 0.6 }} />
                        <span style={{ fontSize: "0.78rem", fontWeight: isConnected ? 700 : 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {ds.name}
                        </span>
                      </button>

                      {/* Database & Children under Active Connection */}
                      {isConnected && (
                        <div style={{ paddingLeft: 16, marginTop: 2, display: "flex", flexDirection: "column", gap: 2 }}>
                          {/* Active Database Node */}
                          <div style={{ display: "flex", flexDirection: "column" }}>
                            <div
                              style={{
                                display: "flex",
                                alignItems: "center",
                                gap: 6,
                                padding: "4px 8px",
                                color: "var(--text-primary)",
                                fontSize: "0.76rem",
                              }}
                            >
                              <ChevronDown size={11} style={{ opacity: 0.5 }} />
                              <HardDrive size={11} style={{ color: "var(--accent-indigo)" }} />
                              <span style={{ fontWeight: 600 }}>{ds.database_name}</span>
                            </div>

                            {/* Schema Folders */}
                            <div style={{ paddingLeft: 12, marginTop: 2, display: "flex", flexDirection: "column", gap: 1 }}>
                              
                              {/* 1. Tables Folder */}
                              <div style={{ display: "flex", flexDirection: "column" }}>
                                <button
                                  onClick={() => setTablesFolderExpanded(!tablesFolderExpanded)}
                                  style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 5,
                                    width: "100%",
                                    padding: "4px 8px",
                                    border: "none",
                                    background: "transparent",
                                    color: "var(--text-secondary)",
                                    fontSize: "0.76rem",
                                    cursor: "pointer",
                                    textAlign: "left",
                                  }}
                                >
                                  {tablesFolderExpanded ? <ChevronDown size={10} style={{ opacity: 0.5 }} /> : <ChevronRight size={10} style={{ opacity: 0.5 }} />}
                                  <Table2 size={11} style={{ color: "var(--accent-indigo)", opacity: 0.8 }} />
                                  <span style={{ fontWeight: 500 }}>表</span>
                                  <span style={{ color: "var(--text-muted)", fontSize: "0.68rem" }}>({schemaTables.length})</span>
                                </button>

                                {tablesFolderExpanded && (
                                  <div style={{ paddingLeft: 12, display: "flex", flexDirection: "column", gap: 2, marginTop: 4 }}>
                                    {/* Search tables input inside tree */}
                                    <div style={{ display: "flex", gap: 4, padding: "0 4px", marginBottom: 4 }}>
                                      <div style={{ position: "relative", flex: 1 }}>
                                        <Search size={10} style={{ position: "absolute", left: 6, top: 7, color: "var(--text-muted)" }} />
                                        <input
                                          className="input-field input-field-sm"
                                          placeholder="过滤数据表..."
                                          value={treeSearch}
                                          onChange={(e) => setTreeSearch(e.target.value)}
                                          style={{ height: 22, fontSize: "0.72rem", paddingLeft: 18 }}
                                        />
                                      </div>
                                      <button
                                        className="btn-ghost"
                                        onClick={() => void onRefreshSchemaTables(ds.id)}
                                        disabled={loadingObjects}
                                        style={{ padding: "2px 4px", border: "1px solid var(--border-light)", borderRadius: 4 }}
                                        title="刷新结构表"
                                      >
                                        <RefreshCw size={10} className={loadingObjects ? "animate-spin" : ""} />
                                      </button>
                                    </div>

                                    {/* Table Items */}
                                    {loadingObjects ? (
                                      <div style={{ display: "flex", flexDirection: "column", gap: 4, padding: "4px 8px" }}>
                                        <div className="skeleton" style={{ height: 18, borderRadius: 3 }} />
                                        <div className="skeleton" style={{ height: 18, borderRadius: 3 }} />
                                      </div>
                                    ) : filteredTables.length === 0 ? (
                                      <div style={{ padding: "8px", fontSize: "0.72rem", color: "var(--text-muted)", textAlign: "center" }}>
                                        没有匹配的表
                                      </div>
                                    ) : (
                                      <div style={{ display: "flex", flexDirection: "column", gap: 1, maxHeight: 380, overflowY: "auto" }}>
                                        {groupedTables.map(({ tag, tables }) => {
                                          const isCollapsed = collapsedGroups.has(tag);
                                          return (
                                            <div key={tag} style={{ margin: "1px 0" }}>
                                              <button
                                                onClick={() => {
                                                  setCollapsedGroups(prev => {
                                                    const next = new Set(prev);
                                                    if (next.has(tag)) next.delete(tag);
                                                    else next.add(tag);
                                                    return next;
                                                  });
                                                }}
                                                style={{
                                                  display: "flex",
                                                  alignItems: "center",
                                                  width: "100%",
                                                  gap: 4,
                                                  padding: "3px 6px",
                                                  border: "none",
                                                  background: "rgba(0,0,0,0.015)",
                                                  borderRadius: 4,
                                                  fontSize: "0.7rem",
                                                  fontWeight: 700,
                                                  color: "var(--text-secondary)",
                                                  cursor: "pointer",
                                                  textAlign: "left"
                                                }}
                                              >
                                                <span style={{ fontSize: "0.55rem", transition: "transform 0.15s", transform: isCollapsed ? "rotate(-90deg)" : "rotate(0deg)" }}>
                                                  ▼
                                                </span>
                                                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
                                                  {tag}
                                                </span>
                                                <span style={{ color: "var(--text-muted)", fontSize: "0.65rem", fontWeight: 400 }}>
                                                  ({tables.length})
                                                </span>
                                              </button>

                                              {!isCollapsed && (
                                                <div style={{ display: "flex", flexDirection: "column", gap: 1, paddingLeft: 8, marginTop: 2 }}>
                                                  {tables.map((table) => {
                                                    const isTabActive = activeTab?.type === "table" && activeTab.tableName === table.table_name;
                                                    return (
                                                      <div
                                                        key={table.id}
                                                        style={{
                                                          display: "flex",
                                                          alignItems: "center",
                                                          borderRadius: 4,
                                                          background: isTabActive ? "var(--bg-active)" : "transparent",
                                                        }}
                                                        className="tree-item-row group"
                                                      >
                                                        <button
                                                          onClick={() => handleOpenTableTab(table.table_name, "schema")}
                                                          onDoubleClick={() => handleOpenTableTab(table.table_name, "data")}
                                                          style={{
                                                            flex: 1,
                                                            display: "flex",
                                                            alignItems: "center",
                                                            gap: 5,
                                                            padding: "4px 6px",
                                                            border: "none",
                                                            background: "transparent",
                                                            color: isTabActive ? "var(--accent-indigo)" : "var(--text-secondary)",
                                                            cursor: "pointer",
                                                            textAlign: "left",
                                                            minWidth: 0,
                                                          }}
                                                          title={`${table.table_name} (${table.table_comment || "无备注"})`}
                                                        >
                                                          <Table2 size={11} style={{ flexShrink: 0, opacity: isTabActive ? 1 : 0.4 }} />
                                                          <span style={{ fontSize: "0.74rem", fontWeight: isTabActive ? 600 : 400, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                                            {table.table_name}
                                                          </span>
                                                        </button>

                                                        <div style={{ display: "flex", alignItems: "center", gap: 2, paddingRight: 4 }}>
                                                          <button
                                                            onClick={() => handleOpenTableTab(table.table_name, "data")}
                                                            className="btn-ghost"
                                                            style={{ padding: 2 }}
                                                            title="直接看数 (Data Mode)"
                                                          >
                                                            <Eye size={10} />
                                                          </button>
                                                          <button
                                                            onClick={() => handleGenerateSelect(table.table_name)}
                                                            className="btn-ghost"
                                                            style={{ padding: 2 }}
                                                            title="生成 SELECT SQL 查询"
                                                          >
                                                            <Terminal size={10} />
                                                          </button>
                                                        </div>
                                                      </div>
                                                    );
                                                  })}
                                                </div>
                                              )}
                                            </div>
                                          );
                                        })}
                                      </div>
                                    )}
                                  </div>
                                )}
                              </div>

                              {/* 2. Views Folder */}
                              <div style={{ display: "flex", flexDirection: "column" }}>
                                <button
                                  onClick={() => setViewsFolderExpanded(!viewsFolderExpanded)}
                                  style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 5,
                                    width: "100%",
                                    padding: "4px 8px",
                                    border: "none",
                                    background: "transparent",
                                    color: "var(--text-secondary)",
                                    fontSize: "0.76rem",
                                    cursor: "pointer",
                                    textAlign: "left",
                                  }}
                                >
                                  {viewsFolderExpanded ? <ChevronDown size={10} style={{ opacity: 0.5 }} /> : <ChevronRight size={10} style={{ opacity: 0.5 }} />}
                                  <Eye size={11} style={{ color: "var(--text-muted)", opacity: 0.7 }} />
                                  <span style={{ fontWeight: 500 }}>视图</span>
                                  <span style={{ color: "var(--text-muted)", fontSize: "0.68rem" }}>(0)</span>
                                </button>
                                {viewsFolderExpanded && (
                                  <div style={{ padding: "4px 24px", fontSize: "0.72rem", color: "var(--text-muted)" }}>
                                    暂无视图
                                  </div>
                                )}
                              </div>

                              {/* 3. Functions Folder */}
                              <div style={{ display: "flex", flexDirection: "column" }}>
                                <button
                                  onClick={() => setFuncsFolderExpanded(!funcsFolderExpanded)}
                                  style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 5,
                                    width: "100%",
                                    padding: "4px 8px",
                                    border: "none",
                                    background: "transparent",
                                    color: "var(--text-secondary)",
                                    fontSize: "0.76rem",
                                    cursor: "pointer",
                                    textAlign: "left",
                                  }}
                                >
                                  {funcsFolderExpanded ? <ChevronDown size={10} style={{ opacity: 0.5 }} /> : <ChevronRight size={10} style={{ opacity: 0.5 }} />}
                                  <Code2 size={11} style={{ color: "var(--text-muted)", opacity: 0.7 }} />
                                  <span style={{ fontWeight: 500 }}>函数</span>
                                  <span style={{ color: "var(--text-muted)", fontSize: "0.68rem" }}>(0)</span>
                                </button>
                                {funcsFolderExpanded && (
                                  <div style={{ padding: "4px 24px", fontSize: "0.72rem", color: "var(--text-muted)" }}>
                                    暂无函数
                                  </div>
                                )}
                              </div>

                              {/* 4. Procedures Folder */}
                              <div style={{ display: "flex", flexDirection: "column" }}>
                                <button
                                  onClick={() => setProcsFolderExpanded(!procsFolderExpanded)}
                                  style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 5,
                                    width: "100%",
                                    padding: "4px 8px",
                                    border: "none",
                                    background: "transparent",
                                    color: "var(--text-secondary)",
                                    fontSize: "0.76rem",
                                    cursor: "pointer",
                                    textAlign: "left",
                                  }}
                                >
                                  {procsFolderExpanded ? <ChevronDown size={10} style={{ opacity: 0.5 }} /> : <ChevronRight size={10} style={{ opacity: 0.5 }} />}
                                  <Terminal size={11} style={{ color: "var(--text-muted)", opacity: 0.7 }} />
                                  <span style={{ fontWeight: 500 }}>存储过程</span>
                                  <span style={{ color: "var(--text-muted)", fontSize: "0.68rem" }}>(0)</span>
                                </button>
                                {procsFolderExpanded && (
                                  <div style={{ padding: "4px 24px", fontSize: "0.72rem", color: "var(--text-muted)" }}>
                                    暂无存储过程
                                  </div>
                                )}
                              </div>

                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </aside>

      {/* ═══ RIGHT WORKSPACE GRID ═══ */}
      <section
        style={{
          display: "flex",
          flexDirection: "column",
          height: "100%",
          width: "100%",
          overflow: "hidden",
          position: "relative"
        }}
      >
        
        {/* ── Layer 1: Global Toolbar ── */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "var(--bg-surface)",
            borderBottom: "1px solid var(--border-light)",
            padding: "8px 16px",
            height: 38,
            flexShrink: 0,
            userSelect: "none"
          }}
        >
          {/* Left section: Logo | Project Selector | Active Connection */}
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ fontSize: "0.85rem", fontWeight: 800, color: "var(--accent-indigo)" }}>
              DataBox Studio
            </span>
            <div style={{ width: 1, height: 12, background: "var(--border-light)" }} />
            
            {/* Project Indicator (plain & sleek) */}
            <span style={{ fontSize: "0.76rem", fontWeight: 600, color: "var(--text-secondary)" }}>
              📁 {activeProject?.name || "默认项目"}
            </span>
            
            <div style={{ width: 1, height: 12, background: "var(--border-light)" }} />

            {/* Connection & DB status */}
            {activeDataSource ? (
              <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "0.76rem" }}>
                <span 
                  style={{ 
                    width: 6, 
                    height: 6, 
                    borderRadius: "50%", 
                    background: activeDataSource.env === "prod" ? "var(--accent-red)" : "var(--accent-green)",
                    boxShadow: activeDataSource.env === "prod" ? "0 0 6px var(--accent-red)" : "0 0 6px var(--accent-green)"
                  }} 
                />
                <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>
                  {activeDataSource.name}
                </span>
                <span style={{ color: "var(--text-muted)" }}>/</span>
                <span className="status-badge status-badge-success" style={{ padding: "1px 6px", fontSize: "0.68rem", borderRadius: 4 }}>
                  {activeDataSource.database_name}
                </span>
                
                {/* Environment badge */}
                {activeDataSource.env === "prod" && (
                  <span style={{ fontSize: "0.68rem", padding: "1px 4px", background: "rgba(220, 38, 38, 0.1)", color: "var(--accent-red)", borderRadius: 3, fontWeight: 700 }}>
                    PROD
                  </span>
                )}
                {activeDataSource.env === "test" && (
                  <span style={{ fontSize: "0.68rem", padding: "1px 4px", background: "rgba(217, 119, 6, 0.1)", color: "var(--accent-amber)", borderRadius: 3, fontWeight: 700 }}>
                    TEST
                  </span>
                )}
              </div>
            ) : (
              <span style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>
                无激活连接
              </span>
            )}
          </div>

          {/* Right section: Global operations (New Query, AI Assistant toggler) */}
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <button
              onClick={() => handleOpenQueryTab()}
              className="btn-primary"
              style={{
                height: 24,
                padding: "0 8px",
                fontSize: "0.72rem",
                borderRadius: 4,
                display: "flex",
                alignItems: "center",
                gap: 4,
                fontWeight: 600
              }}
              title="新建 SQL 编辑器"
            >
              <Plus size={11} />
              <span>新建查询</span>
            </button>

            <button
              onClick={() => setAiPanelOpen(!aiPanelOpen)}
              className="btn-secondary"
              style={{
                height: 24,
                padding: "0 8px",
                fontSize: "0.72rem",
                borderRadius: 4,
                borderColor: aiPanelOpen ? "var(--accent-indigo)" : "var(--border-light)",
                background: aiPanelOpen ? "var(--bg-active)" : "var(--bg-surface)",
                color: "var(--accent-indigo)",
                display: "flex",
                alignItems: "center",
                gap: 4,
                fontWeight: 600
              }}
            >
              <Sparkles size={11} />
              <span>AI 助手</span>
            </button>
          </div>
        </div>
        
        {/* Toggle Sidebar handle when collapsed */}
        {sidebarCollapsed && (
          <button
            onClick={() => setSidebarCollapsed(false)}
            style={{
              position: "absolute",
              left: 0,
              top: 50,
              width: 18,
              height: 28,
              borderRadius: "0 6px 6px 0",
              border: "1px solid var(--border-light)",
              borderLeft: "none",
              background: "var(--bg-surface)",
              color: "var(--text-secondary)",
              display: "grid",
              placeItems: "center",
              cursor: "pointer",
              zIndex: 99,
              boxShadow: "2px 0 6px rgba(0,0,0,0.05)"
            }}
            title="显示侧栏"
          >
            <ChevronRight size={12} />
          </button>
        )}

        {/* ── Tabs bar header ── */}
        {tabs.length > 0 && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              background: "var(--bg-secondary)",
              borderBottom: "1px solid var(--border-light)",
              padding: "5px 12px 0",
              overflowX: "auto",
              flexShrink: 0
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 3, overflowX: "auto" }}>
              {tabs.map((tab) => {
                const isActive = tab.id === activeTabId;
                return (
                  <div
                    key={tab.id}
                    onClick={() => setActiveTabId(tab.id)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      padding: "5px 12px",
                      borderRadius: "4px 4px 0 0",
                      background: isActive ? "var(--bg-surface)" : "transparent",
                      border: "1px solid",
                      borderColor: isActive ? "var(--border-light)" : "transparent",
                      borderBottomColor: isActive ? "var(--bg-surface)" : "transparent",
                      color: isActive ? "var(--accent-indigo)" : "var(--text-secondary)",
                      cursor: "pointer",
                      fontSize: "0.76rem",
                      fontWeight: isActive ? 600 : 500,
                      minWidth: "fit-content",
                      transition: "all 0.15s"
                    }}
                  >
                    {tab.type === "query" ? <Terminal size={11} /> : <Table2 size={11} />}
                    <span>{tab.title}</span>
                    <button
                      onClick={(e) => handleCloseTab(tab.id, e)}
                      className="btn-ghost"
                      style={{ padding: 1, borderRadius: "50%", display: "grid", placeItems: "center" }}
                    >
                      <X size={10} />
                    </button>
                  </div>
                );
              })}
              
              <button
                className="btn-ghost"
                onClick={() => handleOpenQueryTab()}
                style={{ padding: "4px 8px", marginLeft: 4 }}
                title="新建 SQL 编辑器"
              >
                <Plus size={12} />
              </button>
            </div>
          </div>
        )}

        {/* ── Active Tab Viewport Area ── */}
        <div style={{ flex: 1, overflow: "hidden", minHeight: 0, position: "relative" }}>
          
          {tabs.length === 0 ? (
            /* Premium Empty Workspace Dashboard */
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                height: "100%",
                padding: 40,
                overflowY: "auto",
                background: "radial-gradient(circle at top, var(--bg-surface) 0%, var(--bg-primary) 100%)",
                textAlign: "center"
              }}
            >
              <div 
                className="lab-card animate-fade-in stagger"
                style={{
                  maxWidth: 680,
                  width: "100%",
                  padding: "48px 40px",
                  display: "flex",
                  flexDirection: "column",
                  gap: 24,
                  border: "1px solid var(--border-light)",
                  borderRadius: 16,
                  background: "var(--bg-surface)",
                  boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.05)"
                }}
              >
                {/* Visual Identity */}
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
                  <div
                    style={{
                      width: 56,
                      height: 56,
                      borderRadius: 14,
                      background: "rgba(74, 91, 192, 0.08)",
                      display: "grid",
                      placeItems: "center"
                    }}
                  >
                    <Code2 size={28} style={{ color: "var(--accent-indigo)" }} />
                  </div>
                  <div>
                    <h2 className="text-display" style={{ fontSize: "1.45rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: 4 }}>
                      DATABOX 数据库探索工作台
                    </h2>
                    <p style={{ color: "var(--text-secondary)", fontSize: "0.86rem", maxWidth: 440, margin: "0 auto", lineHeight: 1.5 }}>
                      本地优先的高保真 MySQL、PostgreSQL 与 SQLite 数据实验室。在左侧对象树中连接库、双击查表，或者使用下方快捷指令开启会话。
                    </p>
                  </div>
                </div>

                <div style={{ height: "1px", background: "var(--border-light)" }} />

                {/* Quick Actions Grid */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, textAlign: "left" }}>
                  <button
                    onClick={() => handleOpenQueryTab()}
                    className="hover-lift"
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      padding: 16,
                      background: "var(--bg-secondary)",
                      border: "1px solid var(--border-light)",
                      borderRadius: 10,
                      cursor: "pointer",
                      textAlign: "left"
                    }}
                  >
                    <Terminal size={18} style={{ color: "var(--accent-indigo)" }} />
                    <div>
                      <h4 style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: 2 }}>
                        ⚡ 新建 SQL 查询会话
                      </h4>
                      <p style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>
                        开启智能自动补全、DDL 审计与执行计划可视化
                      </p>
                    </div>
                  </button>

                  <button
                    onClick={() => handleAiContextAction("帮我分析当前数据库架构并生成数据洞察")}
                    className="hover-lift"
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      padding: 16,
                      background: "rgba(74, 91, 192, 0.04)",
                      border: "1px solid rgba(74, 91, 192, 0.15)",
                      borderRadius: 10,
                      cursor: "pointer",
                      textAlign: "left"
                    }}
                  >
                    <Sparkles size={18} style={{ color: "var(--accent-indigo)" }} />
                    <div>
                      <h4 style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--accent-indigo)", marginBottom: 2 }}>
                        ✨ 自然语言问数与找表
                      </h4>
                      <p style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>
                        使用大模型对物理表进行模糊关联定位并生成报表
                      </p>
                    </div>
                  </button>
                </div>

                {/* Keyboard Shortcuts Info */}
                <div 
                  style={{ 
                    display: "flex", 
                    alignItems: "center", 
                    justifyContent: "center", 
                    gap: 16, 
                    fontSize: "0.75rem", 
                    color: "var(--text-muted)",
                    background: "rgba(0,0,0,0.01)",
                    padding: "10px",
                    borderRadius: 8,
                    border: "1px dashed var(--border-light)"
                  }}
                >
                  <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <Keyboard size={13} />
                    <span>键盘快捷操作:</span>
                  </span>
                  <span>新建查询: <kbd style={{ background: "var(--bg-secondary)", padding: "2px 4px", borderRadius: 3, border: "1px solid var(--border-medium)" }}>Ctrl + T</kbd></span>
                  <span>执行 SQL: <kbd style={{ background: "var(--bg-secondary)", padding: "2px 4px", borderRadius: 3, border: "1px solid var(--border-medium)" }}>Ctrl + Enter</kbd></span>
                  <span>双击表: <strong style={{ color: "var(--text-secondary)" }}>直接看数</strong></span>
                </div>
              </div>
            </div>
          ) : (
            /* Render active tab viewport based on type */
            <div style={{ height: "100%", width: "100%" }}>
              {activeTab?.type === "query" && activeDataSource && (
                /* Independent Query Page console */
                <ErrorBoundary title="SQL 编辑器加载错误">
                  <QueryPage
                    key={activeTab.id}
                    datasource={activeDataSource}
                    initialDraft={activeTab.sqlDraft ? { sql: activeTab.sqlDraft, nonce: 1 } : null}
                  />
                </ErrorBoundary>
              )}

              {activeTab?.type === "table" && activeTab.tableName && activeDataSource && (
                /* Fully integrated modular Table Detail board */
                <div style={{ display: "flex", flexDirection: "column", height: "100%", width: "100%", overflow: "hidden" }}>
                  
                  {/* High-density horizontal horizontal sub-tab bar inside Table Tab */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      background: "var(--bg-surface)",
                      borderBottom: "1px solid var(--border-light)",
                      padding: "6px 20px 0",
                      gap: 8,
                      flexShrink: 0
                    }}
                  >
                    {[
                      { id: "data", label: "数据" },
                      { id: "schema", label: "字段" },
                      { id: "er", label: "ER 关系" },
                      { id: "design", label: "DDL 变更" }
                    ].map(sub => {
                      const isSubActive = (activeTab.activeSubTab || "data") === sub.id;
                      return (
                        <button
                          key={sub.id}
                          onClick={() => handleSwitchSubTab(activeTab.id, sub.id as any)}
                          style={{
                            padding: "6px 12px 8px",
                            border: "none",
                            background: "transparent",
                            borderBottom: isSubActive ? "2px solid var(--accent-indigo)" : "2px solid transparent",
                            color: isSubActive ? "var(--accent-indigo)" : "var(--text-secondary)",
                            fontWeight: isSubActive ? 600 : 500,
                            fontSize: "0.76rem",
                            cursor: "pointer",
                            transition: "all 0.1s"
                          }}
                        >
                          {sub.label}
                        </button>
                      );
                    })}

                    {/* Table Name Context Indicator */}
                    <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 4, paddingBottom: 6 }}>
                      <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>当前对象: <strong style={{ color: "var(--text-secondary)" }}>{activeTab.tableName}</strong></span>
                    </div>
                  </div>

                  {/* Sub tab content containers */}
                  <div style={{ flex: 1, overflow: "hidden", minHeight: 0 }}>
                    {(activeTab.activeSubTab || "data") === "data" && (
                      <ErrorBoundary title="数据大屏预览组件崩溃">
                        <DataPage
                          datasource={activeDataSource}
                          selectedTableName={activeTab.tableName}
                          schemaTables={schemaTables}
                          onSelectTable={(name) => handleOpenTableTab(name, "data")}
                        />
                      </ErrorBoundary>
                    )}

                    {(activeTab.activeSubTab || "data") === "schema" && (
                      <ErrorBoundary title="架构属性查看组件崩溃">
                        <SchemaPage
                          datasource={activeDataSource}
                          initialViewTab="fields"
                          selectedTableName={activeTab.tableName}
                          onOpenSql={(sql, title) => handleOpenQueryTab(sql, title)}
                        />
                      </ErrorBoundary>
                    )}

                    {(activeTab.activeSubTab || "data") === "er" && (
                      <ErrorBoundary title="表实体ER关联图崩溃">
                        <SchemaPage
                          datasource={activeDataSource}
                          initialViewTab="er"
                          selectedTableName={activeTab.tableName}
                          onOpenSql={(sql, title) => handleOpenQueryTab(sql, title)}
                        />
                      </ErrorBoundary>
                    )}

                    {(activeTab.activeSubTab || "data") === "design" && (
                      <ErrorBoundary title="DDL结构修改设计组件崩溃">
                        <SchemaPage
                          datasource={activeDataSource}
                          initialViewTab="design"
                          selectedTableName={activeTab.tableName}
                          onOpenSql={(sql, title) => handleOpenQueryTab(sql, title)}
                        />
                      </ErrorBoundary>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

        </div>
      </section>

      {/* ═══ FLOATING SLIDE-OVER AI CONTEXT ASSISTANT DRAWER ═══ */}
      {aiPanelOpen && activeDataSource && (
        <aside
          className="animate-slide-left"
          style={{
            position: "absolute",
            top: 40, // Height of the Tab bar
            right: 0,
            bottom: 30, // Footer offset
            width: 320,
            background: "rgba(255, 255, 255, 0.9)",
            backdropFilter: "blur(14px)",
            borderLeft: "1px solid var(--border-light)",
            boxShadow: "-4px 0 24px rgba(0,0,0,0.06)",
            zIndex: 100,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden"
          }}
        >
          {/* AI Header */}
          <div
            style={{
              padding: "12px 16px",
              borderBottom: "1px solid var(--border-light)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              background: "rgba(74, 91, 192, 0.04)"
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Sparkles size={14} style={{ color: "var(--accent-indigo)" }} />
              <span style={{ fontSize: "0.82rem", fontWeight: 700, color: "var(--text-primary)" }}>
                AI 上下文数据库助手
              </span>
            </div>
            <button
              onClick={() => setAiPanelOpen(false)}
              className="btn-ghost"
              style={{ padding: 2 }}
            >
              <X size={14} />
            </button>
          </div>

          {/* AI Context Card */}
          <div style={{ padding: "10px 16px", background: "var(--bg-secondary)", borderBottom: "1px solid var(--border-light)", fontSize: "0.7rem", color: "var(--text-secondary)" }}>
            <div style={{ marginBottom: 4 }}>
              <strong>当前库:</strong> <code style={{ background: "#fff", padding: "1px 4px", borderRadius: 3 }}>{activeDataSource.database_name}</code>
            </div>
            {activeTab?.tableName && (
              <div>
                <strong>当前聚焦表:</strong> <code style={{ background: "#fff", padding: "1px 4px", borderRadius: 3 }}>{activeTab.tableName}</code>
              </div>
            )}
          </div>

          {/* Prompt Conversation Area */}
          <div style={{ flex: 1, overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
            
            {/* Quick AI Presets */}
            <div>
              <span style={{ fontSize: "0.68rem", fontWeight: 700, color: "var(--text-muted)", display: "block", marginBottom: 6 }}>
                快捷分析指令
              </span>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {activeTab?.tableName ? (
                  <>
                    <button
                      onClick={() => handleAiContextAction(`用物理外键和字段名，帮我生成表 ${activeTab.tableName} 关联查询其他表的 JOIN SQL，并包含主要字段说明`)}
                      className="btn-secondary"
                      style={{ padding: "5px 8px", fontSize: "0.72rem", justifyContent: "flex-start", textAlign: "left", width: "100%" }}
                    >
                      🔍 自动生成多表关联 SQL
                    </button>
                    <button
                      onClick={() => handleAiContextAction(`分析并指出表 ${activeTab.tableName} 结构中是否有缺失索引，或者主外键关联的潜在优化风险`)}
                      className="btn-secondary"
                      style={{ padding: "5px 8px", fontSize: "0.72rem", justifyContent: "flex-start", textAlign: "left", width: "100%" }}
                    >
                      🛡️ 审核优化当前表设计
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={() => handleAiContextAction(`列出我当前数据库中最常被用作关联的主键/外键表有哪些，并绘制简略脑图`)}
                      className="btn-secondary"
                      style={{ padding: "5px 8px", fontSize: "0.72rem", justifyContent: "flex-start", textAlign: "left", width: "100%" }}
                    >
                      🗺️ 智能检索全局 Schema 关系
                    </button>
                    <button
                      onClick={() => handleAiContextAction(`用最简单的 MySQL 或 SQL 查询指令帮我测试数据源的读写延迟，并生成诊断代码`)}
                      className="btn-secondary"
                      style={{ padding: "5px 8px", fontSize: "0.72rem", justifyContent: "flex-start", textAlign: "left", width: "100%" }}
                    >
                      ⚡ 数据源读写延迟探针
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Answer Display */}
            {aiResponse && (
              <div
                className="lab-card animate-fade-in"
                style={{
                  padding: 12,
                  background: "var(--bg-surface)",
                  border: "1px solid var(--border-light)",
                  fontSize: "0.78rem",
                  lineHeight: 1.5,
                  borderRadius: 8,
                  position: "relative"
                }}
              >
                <div style={{ fontSize: "0.68rem", fontWeight: 700, color: "var(--text-muted)", marginBottom: 6, display: "flex", alignItems: "center", gap: 4 }}>
                  <ShieldCheck size={11} style={{ color: "var(--accent-green)" }} />
                  <span>AI 脑力分析与 SQL 生成:</span>
                </div>
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.72rem",
                    color: "var(--text-primary)",
                    background: "rgba(0,0,0,0.01)",
                    padding: 8,
                    borderRadius: 4,
                    overflowX: "auto"
                  }}
                >
                  {aiResponse}
                </pre>
                
                {aiResponse.includes("SELECT") && (
                  <button
                    onClick={() => {
                      const match = aiResponse.match(/SELECT[\s\S]+?;/i);
                      handleOpenQueryTab(match ? match[0] : aiResponse, "AI 生成查询");
                    }}
                    className="btn-primary"
                    style={{ width: "100%", marginTop: 8, padding: "4px 0", fontSize: "0.72rem", justifyContent: "center" }}
                  >
                    <Play size={10} />
                    将生成 SQL 发送到新查询窗口
                  </button>
                )}
              </div>
            )}

            {aiLoading && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8, padding: "20px 0", color: "var(--text-muted)" }}>
                <span className="animate-spin" style={{ fontSize: 18 }}>⏳</span>
                <span style={{ fontSize: "0.74rem" }}>正在进行知识检索与智能推理...</span>
              </div>
            )}

          </div>

          {/* Prompt Input Form */}
          <form
            onSubmit={handleAskGeneralAi}
            style={{
              padding: 12,
              borderTop: "1px solid var(--border-light)",
              background: "rgba(0, 0, 0, 0.01)",
              display: "flex",
              flexDirection: "column",
              gap: 8
            }}
          >
            <textarea
              className="input-field"
              placeholder="问我关于库、表结构、或者生成 SQL..."
              value={aiPrompt}
              onChange={(e) => setAiPrompt(e.target.value)}
              style={{ height: 60, fontSize: "0.78rem", resize: "none" }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void handleAskGeneralAi(e);
                }
              }}
            />
            <button
              type="submit"
              className="btn-primary"
              disabled={aiLoading || !aiPrompt.trim()}
              style={{ padding: "6px 0", fontSize: "0.76rem", width: "100%", justifyContent: "center" }}
            >
              🚀 发送指令
            </button>
          </form>

        </aside>
      )}

    </div>
  );
};
