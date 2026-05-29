// Force Vite Hot-Reload to clear stale parser cache
import { lazy, Suspense, useState, useMemo, useEffect, useCallback } from "react";
import {
  Database,
  Table2,
  Terminal,
  ChevronDown,
  ChevronRight,
  Plus,
  X,
  Sparkles,
  Search,
  RefreshCw,
  Code2,
  HardDrive,
  Settings,
  Activity,
  Layers
} from "lucide-react";
import { MenuBar, type MenuDef } from "../components/MenuBar";
import { api } from "../lib/api";
import type { DataSource, Project, SchemaTable } from "../lib/api";
import { EnvironmentsPage } from "./EnvironmentsPage";
import { BackupsPage } from "./BackupsPage";
import { DataSourcesPage } from "./DataSourcesPage";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { PromptDialog } from "../components/PromptDialog";
import { CommandPalette, type CommandItem } from "../components/CommandPalette";
import { DemoTourGuide } from "../components/DemoTourGuide";
import { useToast } from "../components/Toast";

// Tab structure for the workspace
export interface WorkbenchTab {
  id: string; // e.g. "query_123" or "table:users"
  type: "query" | "table" | "er" | "datasources" | "history" | "diagnostics";
  title: string;
  dirty?: boolean;
  closable?: boolean;
  connectionId?: string;
  databaseName?: string;
  tableName?: string;
  activeSubTab?: "data" | "schema" | "er" | "design";
  sqlDraft?: string;
  resultState?: "idle" | "running" | "success" | "error" | "timeout" | "cancelled";
  lastExecutedAt?: number;
  actionTrigger?: {
    type: "execute" | "stop" | "validate" | "export" | "format";
    nonce: number;
  };
}

interface WorkbenchPageProps {
  // Connections and metadata states
  projects: Project[];
  activeProject: Project | null;
  datasources: DataSource[];
  activeDataSource: DataSource | null;
  setActiveDataSource: (ds: DataSource | null) => void;
  schemaTables: SchemaTable[];
  loadingObjects: boolean;
  loadingTree: boolean;
  onRefreshSchemaTables: (datasourceId: string) => Promise<void>;
  onRefreshDatasources: () => Promise<void>;
  onCreateProject: (name: string) => Promise<void>;
}

type QueryTabStatePatch = Pick<WorkbenchTab, "resultState" | "sqlDraft" | "dirty">;

const DashboardPage = lazy(() =>
  import("./DashboardPage").then((module) => ({ default: module.DashboardPage })),
);
const QueryPage = lazy(() =>
  import("./QueryPage").then((module) => ({ default: module.QueryPage })),
);
const SchemaPage = lazy(() =>
  import("./SchemaPage").then((module) => ({ default: module.SchemaPage })),
);
const DataPage = lazy(() =>
  import("./DataPage").then((module) => ({ default: module.DataPage })),
);

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

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
  datasources,
  activeDataSource,
  setActiveDataSource,
  schemaTables,
  loadingObjects,
  loadingTree,
  onRefreshSchemaTables,
  onRefreshDatasources,
  onCreateProject,
}: WorkbenchPageProps) => {
  const { toast: showToast } = useToast();
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [showBackupsModal, setShowBackupsModal] = useState(false);
  const [showEnvironmentsModal, setShowEnvironmentsModal] = useState(false);
  const [showDashboardModal, setShowDashboardModal] = useState(false);
  const [showCreateProject, setShowCreateProject] = useState(false);

  // Tabs management
  const [tabs, setTabs] = useState<WorkbenchTab[]>([]);
  const [activeTabId, setActiveTabId] = useState<string | null>(null);

  // Object Explorer Tree expansion states
  const [treeSearch, setTreeSearch] = useState("");
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [tablesFolderExpanded, setTablesFolderExpanded] = useState(true);

  // Global resizable AI Panel on the right (defaults to open, resizable, collapsible to 48px strip)
  const [aiPanelCollapsed, setAiPanelCollapsed] = useState(false);
  const [aiPanelWidth] = useState(340);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiResponse, setAiResponse] = useState("");
  const [aiLoading, setAiLoading] = useState(false);

  // Tree context menu
  const [treeContextMenu, setTreeContextMenu] = useState<{
    tableName: string;
    x: number;
    y: number;
  } | null>(null);

  // Command Palette
  const [showCommandPalette, setShowCommandPalette] = useState(false);

  // Stepper Tour Guide Dialog state in bottom status bar
  const [showTourDialog, setShowTourDialog] = useState(false);

  // Active tab context RAG
  const activeTab = useMemo(() => {
    return tabs.find(t => t.id === activeTabId) || null;
  }, [tabs, activeTabId]);

  const handleActiveQueryStateChange = useCallback((state: QueryTabStatePatch) => {
    if (!activeTabId) return;
    setTabs((prev) =>
      prev.map((tab) => {
        if (tab.id !== activeTabId) return tab;
        const nextResultState = state.resultState ?? tab.resultState;
        const nextSqlDraft = state.sqlDraft ?? tab.sqlDraft;
        const nextDirty = state.dirty ?? tab.dirty;
        if (
          tab.resultState === nextResultState &&
          tab.sqlDraft === nextSqlDraft &&
          tab.dirty === nextDirty
        ) {
          return tab;
        }
        return {
          ...tab,
          resultState: nextResultState,
          sqlDraft: nextSqlDraft,
          dirty: nextDirty,
        };
      }),
    );
  }, [activeTabId]);

  // Sync focussed tab with left Explorer
  const handleSelectTab = (tabId: string) => {
    setActiveTabId(tabId);
    const tab = tabs.find(t => t.id === tabId);
    if (tab && tab.connectionId && datasources) {
      const boundDs = datasources.find(d => d.id === tab.connectionId);
      if (boundDs && boundDs.id !== activeDataSource?.id) {
        setActiveDataSource(boundDs);
      }
    }
  };

  // Trigger executing, stopping, validating, etc.
  const triggerActiveTabAction = (actionType: "execute" | "stop" | "validate" | "export" | "format") => {
    if (!activeTabId) return;
    setTabs(prev => prev.map(t => t.id === activeTabId ? {
      ...t,
      actionTrigger: {
        type: actionType,
        nonce: Date.now()
      }
    } : t));
  };

  const getEnvBadgeStyle = () => {
    if (!activeDataSource) return { bg: "rgba(148, 163, 184, 0.1)", color: "var(--text-muted)", label: "OFFLINE" };
    if (activeDataSource.env === "prod") return { bg: "rgba(239, 68, 68, 0.12)", color: "var(--accent-red)", label: "PROD" };
    if (activeDataSource.env === "test") return { bg: "rgba(245, 158, 11, 0.12)", color: "var(--accent-amber)", label: "TEST" };
    return { bg: "rgba(16, 185, 129, 0.12)", color: "var(--accent-green)", label: "DEV" };
  };
  const envBadge = getEnvBadgeStyle();

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

  const handleOpenQueryTab = useCallback((sqlDraft?: string, title?: string) => {
    const id = `query:${Date.now()}`;
    const newTab: WorkbenchTab = {
      id,
      type: "query",
      title: title || `查询_${tabs.filter(t => t.type === "query").length + 1}`,
      sqlDraft: sqlDraft || "",
      connectionId: activeDataSource?.id,
      databaseName: activeDataSource?.database_name
    };
    setTabs(prev => [...prev, newTab]);
    setActiveTabId(id);
  }, [activeDataSource?.database_name, activeDataSource?.id, tabs]);

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
        activeSubTab: subTab,
        connectionId: activeDataSource?.id,
        databaseName: activeDataSource?.database_name
      };
      setTabs(prev => [...prev, newTab]);
      setActiveTabId(id);
    }
  };

  const handleCloseTab = (id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    const tab = tabs.find(t => t.id === id);
    if (tab && tab.dirty) {
      const confirmed = window.confirm(`"${tab.title}" 还有未执行或未保存的修改，确认关闭吗？`);
      if (!confirmed) return;
    }
    const nextTabs = tabs.filter(t => t.id !== id);
    setTabs(nextTabs);
    if (activeTabId === id) {
      setActiveTabId(nextTabs[nextTabs.length - 1]?.id || null);
    }
  };

  const handleCloseOtherTabs = () => {
    if (!activeTabId) return;
    const confirmed = window.confirm("确定关闭其他所有标签页吗？");
    if (!confirmed) return;
    setTabs(tabs.filter(t => t.id === activeTabId));
  };

  const handleCloseTabsToRight = () => {
    if (!activeTabId) return;
    const index = tabs.findIndex(t => t.id === activeTabId);
    if (index === -1) return;
    const confirmed = window.confirm("确定关闭右侧所有标签页吗？");
    if (!confirmed) return;
    setTabs(tabs.slice(0, index + 1));
  };

  const handleSwitchSubTab = (tabId: string, subTab: "data" | "schema" | "er" | "design") => {
    setTabs(prev => prev.map(t => t.id === tabId ? { ...t, activeSubTab: subTab } : t));
  };

  const handleGenerateSelect = (tableName: string) => {
    const sql = `SELECT * FROM \`${tableName}\` LIMIT 100;`;
    handleOpenQueryTab(sql, `查询: ${tableName}`);
  };

  const handleAiContextAction = async (promptText: string) => {
    if (!activeDataSource) return;
    setAiPanelCollapsed(false);
    setAiLoading(true);
    setAiResponse("");
    setAiPrompt(promptText);
    try {
      const prompt = `数据源: ${activeDataSource.name} (${activeDataSource.database_name})\n当前聚焦表: ${activeTab?.tableName || "无"}\n当前指令: ${promptText}\n请提供专业的 DDL 修改、优化的标准 SQL，或详细的数据结构建模建议。`;
      const res = await api.generateSql(activeDataSource.id, prompt);
      setAiResponse(res.sql || res.guardrail?.message || "AI 诊断完毕，建议执行结构同步。");
    } catch (err: unknown) {
      setAiResponse(`请求失败: ${getErrorMessage(err, "AI request failed")}`);
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
    } catch (err: unknown) {
      setAiResponse(`生成失败: ${getErrorMessage(err, "AI request failed")}`);
    } finally {
      setAiLoading(false);
    }
  };

  // Drag and drop table node to middle editor
  const handleDragStartNode = (e: React.DragEvent, tableName: string) => {
    e.dataTransfer.setData("text/plain", `SELECT * FROM \`${tableName}\` LIMIT 100;`);
    e.dataTransfer.effectAllowed = "copy";
  };

  // Keyboard shortcut listeners
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "t") {
        e.preventDefault();
        handleOpenQueryTab();
      }
      if (mod && e.shiftKey && e.key.toLowerCase() === "p") {
        e.preventDefault();
        setShowCommandPalette(true);
      } else if (mod && e.key.toLowerCase() === "p") {
        e.preventDefault();
        setShowCommandPalette(true);
      }
      if (e.altKey && e.key.toLowerCase() === "a") {
        e.preventDefault();
        setAiPanelCollapsed(prev => !prev);
      }
      if (mod && e.key.toLowerCase() === "w" && activeTabId) {
        e.preventDefault();
        handleCloseTab(activeTabId);
      }
    };
    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, [handleOpenQueryTab, activeTabId, tabs]);

  // Command palette configuration actions
  const commandItems = useMemo<CommandItem[]>(() => {
    return [
      {
        id: "new-query",
        name: "新建 SQL 控制台",
        category: "编辑器",
        shortcut: "Ctrl + T",
        icon: <Terminal size={13} />,
        action: () => handleOpenQueryTab()
      },
      {
        id: "refresh-metadata",
        name: "刷新元数据结构",
        category: "数据源",
        icon: <RefreshCw size={13} />,
        action: () => {
          if (activeDataSource) void onRefreshSchemaTables(activeDataSource.id);
        }
      },
      {
        id: "open-er",
        name: "打开 ER 关系图",
        category: "视图",
        icon: <Layers size={13} />,
        action: () => {
          if (schemaTables[0]) {
            handleOpenTableTab(schemaTables[0].table_name, "er");
          } else {
            alert("没有可用的数据表生成关系图");
          }
        }
      },
      {
        id: "open-settings",
        name: "打开连接管理器",
        category: "设置",
        icon: <Settings size={13} />,
        action: () => setShowSettingsModal(true)
      },
      {
        id: "open-backups",
        name: "打开备份管理器",
        category: "灾备",
        icon: <Database size={13} />,
        action: () => setShowBackupsModal(true)
      },
      {
        id: "open-dashboard",
        name: "打开性能监控面板",
        category: "监控",
        icon: <Activity size={13} />,
        action: () => setShowDashboardModal(true)
      },
      {
        id: "trigger-tour",
        name: "演示 Demo 引导向导",
        category: "教程",
        icon: <Sparkles size={13} />,
        action: () => setShowTourDialog(true)
      }
    ];
  }, [activeDataSource, handleOpenQueryTab, onRefreshSchemaTables, schemaTables]);

  // Menu bar definitions
  const menus = useMemo<MenuDef[]>(() => {
    const handleCloseWindow = () => {
      try {
        import("@tauri-apps/api/window").then(({ getCurrentWindow }) => {
          getCurrentWindow().close();
        }).catch(() => {});
      } catch { /* non-Tauri env */ }
    };

    const hasConn = !!activeDataSource;

    return [
      {
        id: "file",
        label: "文件",
        items: [
          { label: "新建 SQL 控制台", shortcut: "Ctrl+T", action: () => handleOpenQueryTab() },
          { label: "打开 SQL 文件", disabled: true },
          { label: "保存当前 SQL", shortcut: "Ctrl+S", disabled: true },
          { label: "另存为 SQL 文件", disabled: true },
          { separator: true, label: "" },
          { label: "保存控制台会话", disabled: true },
          { label: "打开控制台会话", disabled: true },
          { separator: true, label: "" },
          { label: "导入连接配置", disabled: true },
          { label: "导出连接配置", disabled: true },
          { separator: true, label: "" },
          { label: "退出", action: handleCloseWindow },
        ],
      },
      {
        id: "edit",
        label: "编辑",
        items: [
          { label: "撤销", shortcut: "Ctrl+Z", action: () => document.execCommand("undo") },
          { label: "重做", shortcut: "Ctrl+Shift+Z", action: () => document.execCommand("redo") },
          { separator: true, label: "" },
          { label: "剪切", shortcut: "Ctrl+X", action: () => document.execCommand("cut") },
          { label: "复制", shortcut: "Ctrl+C", action: () => document.execCommand("copy") },
          { label: "粘贴", shortcut: "Ctrl+V", action: () => document.execCommand("paste") },
          { separator: true, label: "" },
          { label: "查找", shortcut: "Ctrl+F", disabled: true },
          { label: "替换", shortcut: "Ctrl+H", disabled: true },
          { separator: true, label: "" },
          { label: "格式化 SQL", action: () => triggerActiveTabAction("format") },
          { label: "注释 / 取消注释", shortcut: "Ctrl+/", disabled: true },
        ],
      },
      {
        id: "select",
        label: "选择",
        items: [
          { label: "全选", shortcut: "Ctrl+A", action: () => document.execCommand("selectAll") },
          { label: "选择当前行", disabled: true },
          { label: "选择当前 SQL 语句", disabled: true },
          { separator: true, label: "" },
          { label: "取消选择", disabled: true },
        ],
      },
      {
        id: "view",
        label: "视图",
        items: [
          { label: "显示 / 隐藏 AI 面板", shortcut: "Alt+A", action: () => setAiPanelCollapsed(prev => !prev) },
          { label: "显示 / 隐藏资源管理器", disabled: true },
          { separator: true, label: "" },
          { label: "紧凑表格模式", disabled: true },
          { label: "舒适表格模式", disabled: true },
          { separator: true, label: "" },
          { label: "放大", shortcut: "Ctrl+=", disabled: true },
          { label: "缩小", shortcut: "Ctrl+-", disabled: true },
          { label: "重置缩放", shortcut: "Ctrl+0", disabled: true },
        ],
      },
      {
        id: "go",
        label: "转到",
        items: [
          { label: "快速打开对象", shortcut: "Ctrl+P", action: () => setShowCommandPalette(true) },
          { label: "转到 SQL 标签页", shortcut: "Ctrl+Tab", disabled: true },
          { label: "转到最近打开", disabled: true },
          { label: "转到查询历史", disabled: true },
        ],
      },
      {
        id: "run",
        label: "运行",
        items: [
          { label: "执行当前 SQL", shortcut: "Ctrl+Enter", action: () => triggerActiveTabAction("execute") },
          { label: "执行选中 SQL", shortcut: "Ctrl+Shift+Enter", disabled: true },
          { label: "停止执行", action: () => triggerActiveTabAction("stop") },
          { separator: true, label: "" },
          { label: "提交事务", disabled: true },
          { label: "回滚事务", disabled: true },
          { separator: true, label: "" },
          { label: "重新运行上次查询", disabled: true },
        ],
      },
      {
        id: "database",
        label: "数据库",
        items: [
          { label: "新建连接", action: () => setShowSettingsModal(true) },
          { label: "测试连接", disabled: !hasConn },
          { label: "断开连接", disabled: !hasConn, action: () => { if (hasConn) setActiveDataSource(null); } },
          { label: "连接设置", action: () => setShowSettingsModal(true) },
          { separator: true, label: "" },
          { label: "刷新结构", disabled: !hasConn, action: () => { if (activeDataSource) void onRefreshSchemaTables(activeDataSource.id); } },
          { label: "打开 SQL 控制台", shortcut: "Ctrl+T", action: () => handleOpenQueryTab() },
          { label: "打开 ER 图", disabled: !hasConn || schemaTables.length === 0, action: () => { if (schemaTables[0]) handleOpenTableTab(schemaTables[0].table_name, "er"); } },
          { separator: true, label: "" },
          { label: "生成 DDL", disabled: !hasConn },
          { label: "导入数据", disabled: !hasConn },
          { label: "导出数据", disabled: !hasConn },
          { separator: true, label: "" },
          { label: "备份数据库", disabled: !hasConn, action: () => setShowBackupsModal(true) },
          { label: "恢复数据库", disabled: !hasConn, action: () => setShowBackupsModal(true) },
        ],
      },
      {
        id: "ai",
        label: "AI",
        items: [
          { label: "打开 AI 面板", shortcut: "Alt+A", action: () => setAiPanelCollapsed(false) },
          { label: "生成 SQL", disabled: true },
          { label: "解释当前 SQL", disabled: true },
          { label: "优化当前 SQL", disabled: true },
          { label: "诊断表结构", disabled: true },
          { separator: true, label: "" },
          { label: "生成测试数据", disabled: true },
        ],
      },
      {
        id: "help",
        label: "帮助",
        items: [
          { label: "快捷键参考", action: () => setShowCommandPalette(true) },
          { label: "引导向导", action: () => setShowTourDialog(true) },
          { separator: true, label: "" },
          { label: "性能监控面板", action: () => setShowDashboardModal(true) },
          { label: "Docker 环境管理", action: () => setShowEnvironmentsModal(true) },
          { separator: true, label: "" },
          { label: "使用文档", disabled: true },
          { label: "查看日志", disabled: true },
          { label: "检查更新", disabled: true },
          { separator: true, label: "" },
          { label: "关于 DataBox", action: () => alert("DataBox v1.0.0\nAI 驱动的本地数据库工作台") },
        ],
      },
    ];
  }, [activeDataSource, handleOpenQueryTab, handleOpenTableTab, handleAiContextAction, onRefreshSchemaTables, triggerActiveTabAction, schemaTables, setAiPanelCollapsed, setShowCommandPalette, setShowSettingsModal, setShowBackupsModal, setShowDashboardModal, setShowEnvironmentsModal, setShowTourDialog, setActiveDataSource]);

  return (
    <div
      style={{
        display: "grid",
        gridTemplateRows: "30px 1fr 28px",
        height: "100%",
        width: "100%",
        overflow: "hidden",
        background: "var(--bg-primary)"
      }}
    >
      {/* ── Menu Bar ── */}
      <MenuBar menus={menus} />

      {/* ── Layer 2: Main Three-Column Workspace Viewport (Resizable) ── */}
      <main
        style={{
          display: "grid",
          gridTemplateColumns: `230px 1fr ${aiPanelCollapsed ? "48px" : `${aiPanelWidth}px`}`,
          transition: "grid-template-columns 0.18s ease",
          minHeight: 0,
          overflow: "hidden"
        }}
      >
        {/* Column 1: Object Explorer (Left Sidebar) */}
        <aside
          style={{
            display: "flex",
            flexDirection: "column",
            background: "var(--bg-surface)",
            borderRight: "1px solid var(--border-light)",
            overflow: "hidden",
            height: "100%",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
            {/* Explorer Title bar */}
            <div style={{ padding: "6px 8px", borderBottom: "1px solid var(--border-light)", display: "flex", justifyContent: "space-between", alignItems: "center", userSelect: "none" }}>
              <span style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: 4 }}>
                <Code2 size={11} style={{ color: "var(--text-muted)" }} />
                对象资源管理器
              </span>
            </div>

            {/* Tree Nodes scrolling container */}
            <div style={{ flex: 1, overflowY: "auto", padding: "4px 4px", display: "flex", flexDirection: "column", gap: 0 }}>
              {loadingTree ? (
                <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 6 }}>
                  <div className="skeleton" style={{ height: 18, borderRadius: 4 }} />
                  <div className="skeleton" style={{ height: 18, borderRadius: 4 }} />
                </div>
              ) : datasources.length === 0 ? (
                <div style={{ padding: "20px 10px", fontSize: "0.72rem", color: "var(--text-muted)", textAlign: "center" }}>
                  无激活连接，请先在右上角添加设置数据源。
                </div>
              ) : (
                datasources.map((ds) => {
                  const isConnected = activeDataSource?.id === ds.id;
                  return (
                    <div key={ds.id} style={{ display: "flex", flexDirection: "column" }}>
                      <button
                        onClick={() => setActiveDataSource(ds)}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                          width: "100%",
                          padding: "3px 4px",
                          border: "none",
                          borderRadius: 6,
                          background: isConnected ? "var(--bg-active)" : "transparent",
                          color: isConnected ? "var(--accent-indigo)" : "var(--text-secondary)",
                          cursor: "pointer",
                          textAlign: "left",
                        }}
                      >
                        <ChevronRight
                          size={11}
                          style={{
                            transform: isConnected ? "rotate(90deg)" : "rotate(0deg)",
                            transition: "transform 0.1s",
                            opacity: 0.5
                          }}
                        />
                        <Database size={11} style={{ opacity: isConnected ? 1 : 0.6 }} />
                        <span style={{ fontSize: "0.76rem", fontWeight: isConnected ? 700 : 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {ds.name}
                        </span>
                      </button>

                      {isConnected && (
                        <div style={{ paddingLeft: 12, marginTop: 2, display: "flex", flexDirection: "column", gap: 1 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 5, padding: "3px 6px", color: "var(--text-primary)", fontSize: "0.72rem" }}>
                            <ChevronDown size={10} style={{ opacity: 0.5 }} />
                            <HardDrive size={10} style={{ color: "var(--accent-indigo)" }} />
                            <span style={{ fontWeight: 600 }}>{ds.database_name}</span>
                          </div>

                          <div style={{ paddingLeft: 10, display: "flex", flexDirection: "column", gap: 1 }}>
                            {/* Tables Folder */}
                            <div>
                              <button
                                onClick={() => setTablesFolderExpanded(!tablesFolderExpanded)}
                                style={{
                                  display: "flex",
                                  alignItems: "center",
                                  gap: 5,
                                  width: "100%",
                                  padding: "3px 6px",
                                  border: "none",
                                  background: "transparent",
                                  color: "var(--text-secondary)",
                                  fontSize: "0.72rem",
                                  cursor: "pointer",
                                  textAlign: "left",
                                }}
                              >
                                {tablesFolderExpanded ? <ChevronDown size={9} style={{ opacity: 0.5 }} /> : <ChevronRight size={9} style={{ opacity: 0.5 }} />}
                                <Table2 size={10} style={{ color: "var(--accent-indigo)", opacity: 0.8 }} />
                                <span style={{ fontWeight: 500 }}>表</span>
                                <span style={{ color: "var(--text-muted)", fontSize: "0.64rem" }}>({schemaTables.length})</span>
                              </button>

                              {tablesFolderExpanded && (
                                <div style={{ paddingLeft: 10, display: "flex", flexDirection: "column", gap: 1, marginTop: 3 }}>
                                  {/* Filter input */}
                                  <div style={{ display: "flex", gap: 4, padding: "0 2px", marginBottom: 4 }}>
                                    <div style={{ position: "relative", flex: 1 }}>
                                      <Search size={9} style={{ position: "absolute", left: 5, top: 6, color: "var(--text-muted)" }} />
                                      <input
                                        className="input-field input-field-sm"
                                        placeholder="过滤数据表..."
                                        value={treeSearch}
                                        onChange={(e) => setTreeSearch(e.target.value)}
                                        style={{ height: 20, fontSize: "0.68rem", paddingLeft: 16 }}
                                      />
                                    </div>
                                    <button
                                      className="btn-ghost"
                                      onClick={() => void onRefreshSchemaTables(ds.id)}
                                      disabled={loadingObjects}
                                      style={{ padding: "1px 3px", border: "1px solid var(--border-light)", borderRadius: 3 }}
                                    >
                                      <RefreshCw size={9} className={loadingObjects ? "animate-spin" : ""} />
                                    </button>
                                  </div>

                                  {/* Dynamic Groupings */}
                                  <div style={{ display: "flex", flexDirection: "column", gap: 1, maxHeight: 340, overflowY: "auto" }}>
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
                                              padding: "2px 4px",
                                              border: "none",
                                              background: "rgba(0,0,0,0.015)",
                                              borderRadius: 4,
                                              fontSize: "0.68rem",
                                              fontWeight: 700,
                                              color: "var(--text-secondary)",
                                              cursor: "pointer",
                                              textAlign: "left"
                                            }}
                                          >
                                            <span style={{ fontSize: "0.5rem", transition: "transform 0.1s", transform: isCollapsed ? "rotate(-90deg)" : "rotate(0deg)" }}>
                                              ▾
                                            </span>
                                            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{tag}</span>
                                            <span style={{ color: "var(--text-muted)", fontSize: "0.6rem" }}>({tables.length})</span>
                                          </button>

                                          {!isCollapsed && (
                                            <div style={{ display: "flex", flexDirection: "column", gap: 1, paddingLeft: 6, marginTop: 2 }}>
                                              {tables.map((table) => {
                                                const isTabActive = activeTab?.type === "table" && activeTab.tableName === table.table_name;
                                                return (
                                                  <div
                                                    key={table.id}
                                                    draggable
                                                    onDragStart={(e) => handleDragStartNode(e, table.table_name)}
                                                    onContextMenu={(e) => {
                                                      e.preventDefault();
                                                      setTreeContextMenu({
                                                        tableName: table.table_name,
                                                        x: e.clientX,
                                                        y: e.clientY
                                                      });
                                                    }}
                                                    style={{
                                                      display: "flex",
                                                      alignItems: "center",
                                                      borderRadius: 4,
                                                      background: isTabActive ? "var(--bg-active)" : "transparent",
                                                    }}
                                                    className="tree-item-row"
                                                  >
                                                    <button
                                                      onClick={() => handleOpenTableTab(table.table_name, "schema")}
                                                      onDoubleClick={() => handleOpenTableTab(table.table_name, "data")}
                                                      style={{
                                                        flex: 1,
                                                        display: "flex",
                                                        alignItems: "center",
                                                        gap: 4,
                                                        padding: "3px 4px",
                                                        border: "none",
                                                        background: "transparent",
                                                        color: isTabActive ? "var(--accent-indigo)" : "var(--text-secondary)",
                                                        cursor: "pointer",
                                                        textAlign: "left",
                                                        minWidth: 0
                                                      }}
                                                      title={`${table.table_name} (${table.table_comment || "无备注"})`}
                                                    >
                                                      <Table2 size={9} style={{ flexShrink: 0, opacity: isTabActive ? 1 : 0.4 }} />
                                                      <span style={{ fontSize: "0.72rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                                        {table.table_name}
                                                      </span>
                                                    </button>
                                                  </div>
                                                );
                                              })}
                                            </div>
                                          )}
                                        </div>
                                      );
                                    })}
                                  </div>
                                </div>
                              )}
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
        </aside>

        {/* Column 2: Workspace tabs area (Middle area) */}
        <section
          style={{
            display: "flex",
            flexDirection: "column",
            height: "100%",
            width: "100%",
            overflow: "hidden",
            borderRight: "1px solid var(--border-light)"
          }}
        >
          {/* Workspace Tabs strip */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              background: "var(--bg-secondary)",
              borderBottom: "1px solid var(--border-light)",
              padding: "4px 8px 0",
              overflowX: "auto",
              flexShrink: 0,
              height: 32,
              userSelect: "none"
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 3, overflowX: "auto", height: "100%" }}>
              {tabs.map((tab) => {
                const isActive = tab.id === activeTabId;
                return (
                  <div
                    key={tab.id}
                    onClick={() => handleSelectTab(tab.id)}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      if (window.confirm("确定关闭该标签页吗？")) {
                        handleCloseTab(tab.id);
                      }
                    }}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      padding: "0 8px",
                      borderRadius: "4px 4px 0 0",
                      background: isActive ? "var(--bg-surface)" : "transparent",
                      border: "1px solid",
                      borderColor: isActive ? "var(--border-light)" : "transparent",
                      borderBottomColor: isActive ? "var(--bg-surface)" : "transparent",
                      color: isActive ? "var(--accent-indigo)" : "var(--text-secondary)",
                      cursor: "pointer",
                      fontSize: "0.72rem",
                      fontWeight: isActive ? 700 : 500,
                      minWidth: "fit-content",
                      height: "100%"
                    }}
                  >
                    {tab.resultState === "running" ? (
                      <span className="animate-spin" style={{ fontSize: "0.68rem" }}>↻</span>
                    ) : tab.type === "query" ? (
                      <Terminal size={10} style={{ opacity: isActive ? 1 : 0.6 }} />
                    ) : (
                      <Table2 size={10} style={{ opacity: isActive ? 1 : 0.6 }} />
                    )}

                    <span>{tab.title}</span>

                    {tab.dirty && (
                      <span style={{ color: "var(--accent-amber)", fontSize: "0.65rem" }}>●</span>
                    )}

                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleCloseTab(tab.id);
                      }}
                      className="btn-ghost"
                      style={{ padding: 1, borderRadius: "50%", color: "var(--text-muted)" }}
                    >
                      <X size={9} />
                    </button>
                  </div>
                );
              })}

              <button
                className="btn-ghost"
                onClick={() => handleOpenQueryTab()}
                style={{ padding: "2px 5px", display: "flex", alignItems: "center" }}
                title="新建 SQL 查询 (Ctrl+T)"
              >
                <Plus size={11} />
              </button>
            </div>

            {/* Quick clean tab actions */}
            {tabs.length > 1 && (
              <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 4, paddingBottom: 2 }}>
                <button
                  className="btn-ghost"
                  onClick={handleCloseOtherTabs}
                  style={{ fontSize: "0.66rem", padding: "1px 4px" }}
                >
                  关闭其他
                </button>
                <button
                  className="btn-ghost"
                  onClick={handleCloseTabsToRight}
                  style={{ fontSize: "0.66rem", padding: "1px 4px" }}
                >
                  关闭右侧
                </button>
              </div>
            )}
          </div>

          {/* Active Tab content viewport */}
          <div style={{ flex: 1, overflow: "hidden", minHeight: 0, position: "relative" }}>
            {tabs.length === 0 ? (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", padding: 30, background: "var(--bg-primary)" }}>
                <div style={{ maxWidth: 380, width: "100%" }}>
                  <div style={{ marginBottom: 20, textAlign: "center" }}>
                    <span style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text-secondary)" }}>快捷键</span>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "4px 16px", fontSize: "0.76rem", color: "var(--text-secondary)", marginBottom: 16 }}>
                    <span>新建 SQL 查询</span>
                    <kbd style={{
                      background: "var(--bg-secondary)", padding: "1px 5px", borderRadius: 3,
                      border: "1px solid var(--border-medium)", fontFamily: "var(--font-mono)", fontSize: "0.64rem",
                      color: "var(--text-muted)"
                    }}>Ctrl+T</kbd>

                    <span>快速打开对象</span>
                    <kbd style={{
                      background: "var(--bg-secondary)", padding: "1px 5px", borderRadius: 3,
                      border: "1px solid var(--border-medium)", fontFamily: "var(--font-mono)", fontSize: "0.64rem",
                      color: "var(--text-muted)"
                    }}>Ctrl+P</kbd>

                    <span>执行当前 SQL</span>
                    <kbd style={{
                      background: "var(--bg-secondary)", padding: "1px 5px", borderRadius: 3,
                      border: "1px solid var(--border-medium)", fontFamily: "var(--font-mono)", fontSize: "0.64rem",
                      color: "var(--text-muted)"
                    }}>Ctrl+Enter</kbd>

                    <span>聚焦 AI 面板</span>
                    <kbd style={{
                      background: "var(--bg-secondary)", padding: "1px 5px", borderRadius: 3,
                      border: "1px solid var(--border-medium)", fontFamily: "var(--font-mono)", fontSize: "0.64rem",
                      color: "var(--text-muted)"
                    }}>Alt+A</kbd>

                    <span>打开命令面板</span>
                    <kbd style={{
                      background: "var(--bg-secondary)", padding: "1px 5px", borderRadius: 3,
                      border: "1px solid var(--border-medium)", fontFamily: "var(--font-mono)", fontSize: "0.64rem",
                      color: "var(--text-muted)"
                    }}>Ctrl+Shift+P</kbd>
                  </div>

                  <div style={{ height: "1px", background: "var(--border-light)", margin: "0 0 16px" }} />

                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      className="btn-primary"
                      onClick={() => handleOpenQueryTab()}
                      style={{ flex: 1, justifyContent: "center", fontSize: "0.78rem", padding: "5px 0" }}
                    >
                      <Plus size={12} />
                      新建 SQL 标签页
                    </button>
                    <button
                      className="btn-secondary"
                      onClick={() => setShowCommandPalette(true)}
                      style={{ flex: 1, justifyContent: "center", fontSize: "0.78rem", padding: "5px 0" }}
                    >
                      打开命令面板
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ height: "100%", width: "100%" }}>
                {activeTab?.type === "query" && activeDataSource && (
                  <ErrorBoundary title="SQL 终端加载异常">
                    <Suspense fallback={<div className="skeleton" style={{ height: "100%" }} />}>
                      <QueryPage
                        key={activeTab.id}
                        datasource={activeDataSource}
                        initialDraft={activeTab.sqlDraft ? { sql: activeTab.sqlDraft, nonce: 1 } : null}
                        actionTrigger={activeTab.actionTrigger}
                        onStateChange={handleActiveQueryStateChange}
                      />
                    </Suspense>
                  </ErrorBoundary>
                )}

                {activeTab?.type === "table" && activeTab.tableName && activeDataSource && (
                  <div style={{ display: "flex", flexDirection: "column", height: "100%", width: "100%", overflow: "hidden" }}>
                    {/* Secondary mini tab strip within Table Tab */}
                    <div style={{ display: "flex", alignItems: "center", background: "var(--bg-surface)", borderBottom: "1px solid var(--border-light)", padding: "4px 16px 0", gap: 6, flexShrink: 0 }}>
                      {[
                        { id: "data", label: "数据预览" },
                        { id: "schema", label: "结构字段" },
                        { id: "er", label: "ER关系图" },
                        { id: "design", label: "AI 变更草稿" }
                      ].map(sub => {
                        const isSubActive = (activeTab.activeSubTab || "data") === sub.id;
                        return (
                          <button
                            key={sub.id}
                            onClick={() => handleSwitchSubTab(activeTab.id, sub.id as any)}
                            style={{
                              padding: "4px 10px 6px",
                              border: "none",
                              background: "transparent",
                              borderBottom: isSubActive ? "2px solid var(--accent-indigo)" : "2px solid transparent",
                              color: isSubActive ? "var(--accent-indigo)" : "var(--text-secondary)",
                              fontWeight: isSubActive ? 700 : 500,
                              fontSize: "0.74rem",
                              cursor: "pointer",
                              transition: "all 0.15s"
                            }}
                          >
                            {sub.label}
                          </button>
                        );
                      })}
                      <div style={{ marginLeft: "auto", fontSize: "0.76rem", color: "var(--text-muted)", paddingBottom: 4 }}>
                        聚焦表: <strong style={{ color: "var(--text-secondary)" }}>{activeTab.tableName}</strong>
                      </div>
                    </div>

                    {/* Modular tab pages viewport */}
                    <div style={{ flex: 1, overflow: "hidden", minHeight: 0 }}>
                      {(activeTab.activeSubTab || "data") === "data" && (
                        <ErrorBoundary title="DataTable Preview Error">
                          <Suspense fallback={<div className="skeleton" style={{ height: "100%" }} />}>
                            <DataPage
                              datasource={activeDataSource}
                              selectedTableName={activeTab.tableName}
                              schemaTables={schemaTables}
                              onSelectTable={(name) => handleOpenTableTab(name, "data")}
                            />
                          </Suspense>
                        </ErrorBoundary>
                      )}

                      {(activeTab.activeSubTab || "data") === "schema" && (
                        <ErrorBoundary title="Column Definition Schema Error">
                          <Suspense fallback={<div className="skeleton" style={{ height: "100%" }} />}>
                            <SchemaPage
                              datasource={activeDataSource}
                              initialViewTab="fields"
                              selectedTableName={activeTab.tableName}
                              onOpenSql={(sql, title) => handleOpenQueryTab(sql, title)}
                            />
                          </Suspense>
                        </ErrorBoundary>
                      )}

                      {(activeTab.activeSubTab || "data") === "er" && (
                        <ErrorBoundary title="ER Graph Diagram Error">
                          <Suspense fallback={<div className="skeleton" style={{ height: "100%" }} />}>
                            <SchemaPage
                              datasource={activeDataSource}
                              initialViewTab="er"
                              selectedTableName={activeTab.tableName}
                              onOpenSql={(sql, title) => handleOpenQueryTab(sql, title)}
                            />
                          </Suspense>
                        </ErrorBoundary>
                      )}

                      {(activeTab.activeSubTab || "data") === "design" && (
                        <ErrorBoundary title="AI Table DDL Design Draft Error">
                          <Suspense fallback={<div className="skeleton" style={{ height: "100%" }} />}>
                            <SchemaPage
                              datasource={activeDataSource}
                              initialViewTab="design"
                              selectedTableName={activeTab.tableName}
                              onOpenSql={(sql, title) => handleOpenQueryTab(sql, title)}
                            />
                          </Suspense>
                        </ErrorBoundary>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </section>

        {/* Column 3: Collapsible AI Agent Panel (Right Sidebar) */}
        <aside
          style={{
            display: "flex",
            flexDirection: "column",
            background: "var(--bg-surface)",
            borderLeft: "1px solid var(--border-light)",
            overflow: "hidden",
            height: "100%",
            zIndex: 100
          }}
        >
          {aiPanelCollapsed ? (
            /* Collapsed narrow strip vertical toolbar */
            <div
              style={{
                width: 48,
                height: "100%",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                paddingTop: 12,
                gap: 16,
                background: "var(--bg-secondary)",
                userSelect: "none"
              }}
            >
              <button
                onClick={() => setAiPanelCollapsed(false)}
                className="btn-ghost hover-lift"
                style={{ padding: 4, borderRadius: "50%", background: "rgba(74,91,192,0.1)", color: "var(--accent-indigo)" }}
                title="展开 AI Agent 工具箱 (Alt+A)"
              >
                <Sparkles size={16} />
              </button>
            </div>
          ) : (
            /* Expanded rich tools and prompt console */
            <div style={{ display: "flex", flexDirection: "column", height: "100%", width: "100%" }}>
              {/* Header bar */}
              <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--border-light)", display: "flex", justifyContent: "space-between", alignItems: "center", background: "rgba(74, 91, 192, 0.03)" }}>
                <span style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--text-primary)", display: "flex", alignItems: "center", gap: 5 }}>
                  <Sparkles size={12} style={{ color: "var(--accent-indigo)" }} />
                  DataBox AI Copilot
                </span>
                <button
                  onClick={() => setAiPanelCollapsed(true)}
                  className="btn-ghost"
                  style={{ padding: 2 }}
                  title="折叠面板"
                >
                  <X size={12} />
                </button>
              </div>

              {/* Context Strip */}
              <div style={{ padding: "6px 10px", background: "var(--bg-secondary)", borderBottom: "1px solid var(--border-light)", fontSize: "0.65rem", color: "var(--text-secondary)", display: "flex", flexDirection: "column", gap: 1 }}>
                <div><span style={{ opacity: 0.6 }}>数据库</span> <strong style={{ color: "var(--text-primary)" }}>{activeDataSource?.database_name || "未连接"}</strong></div>
                {activeTab ? (
                  <>
                    <div><span style={{ opacity: 0.6 }}>会话</span> <strong style={{ color: "var(--text-primary)" }}>{activeTab.type === "query" ? `SQL Console (${activeTab.title})` : activeTab.type === "table" ? `表: ${activeTab.tableName}` : activeTab.title}</strong></div>
                    {activeTab?.tableName && (
                      <div><span style={{ opacity: 0.6 }}>当前表</span> <code style={{ color: "var(--accent-primary)", fontSize: "0.62rem" }}>{activeTab.tableName}</code></div>
                    )}
                    {activeTab?.lastExecutedAt && (
                      <div><span style={{ opacity: 0.6 }}>最近执行</span> <strong style={{ color: "var(--text-primary)" }}>{activeTab.lastExecutedAt ? Math.round((Date.now() - activeTab.lastExecutedAt) / 1000) + "s 前" : ""}</strong></div>
                    )}
                  </>
                ) : (
                  <div><span style={{ opacity: 0.6 }}>状态</span> <span style={{ color: "var(--text-muted)" }}>未打开标签页</span></div>
                )}
              </div>

              {/* Main panel content */}
              <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column" }}>
                {/* Quick actions — context-aware */}
                <div style={{ padding: "8px 10px", borderBottom: "1px solid var(--border-light)" }}>
                  <div style={{ fontSize: "0.64rem", fontWeight: 600, color: "var(--text-muted)", marginBottom: 4 }}>
                    快捷动作
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                    {activeTab?.type === "query" && (
                      <>
                        <button onClick={() => triggerActiveTabAction("execute")}
                          className="btn-secondary" style={{ fontSize: "0.66rem", padding: "2px 7px", height: 24 }}>执行</button>
                        <button onClick={() => triggerActiveTabAction("format")}
                          className="btn-secondary" style={{ fontSize: "0.66rem", padding: "2px 7px", height: 24 }}>格式化</button>
                        <button onClick={() => triggerActiveTabAction("validate")}
                          className="btn-secondary" style={{ fontSize: "0.66rem", padding: "2px 7px", height: 24 }}>安全检查</button>
                        <button onClick={() => handleAiContextAction("优化当前 SQL 的性能和可读性，返回优化后的标准 SQL。")}
                          className="btn-secondary" style={{ fontSize: "0.66rem", padding: "2px 7px", height: 24 }}>AI 优化</button>
                      </>
                    )}
                    {activeTab?.type === "table" && (
                      <>
                        <button onClick={() => handleAiContextAction(`为表 ${activeTab.tableName} 生成标准 SELECT 查询模板。`)}
                          className="btn-secondary" style={{ fontSize: "0.66rem", padding: "2px 7px", height: 24 }}>生成查询</button>
                        <button onClick={() => handleAiContextAction(`诊断表 ${activeTab.tableName} 的索引、外键和结构问题。`)}
                          className="btn-secondary" style={{ fontSize: "0.66rem", padding: "2px 7px", height: 24 }}>诊断结构</button>
                        <button onClick={() => handleAiContextAction(`分析表 ${activeTab.tableName} 的 ER 关系拓扑。`)}
                          className="btn-secondary" style={{ fontSize: "0.66rem", padding: "2px 7px", height: 24 }}>分析关系</button>
                      </>
                    )}
                    {!activeTab && (
                      <>
                        <button onClick={() => handleOpenQueryTab()}
                          className="btn-secondary" style={{ fontSize: "0.66rem", padding: "2px 7px", height: 24 }}>打开控制台</button>
                        <button onClick={() => handleAiContextAction("列出当前数据库的所有表和视图。")}
                          className="btn-secondary" style={{ fontSize: "0.66rem", padding: "2px 7px", height: 24 }}>探索数据库</button>
                        <button onClick={() => handleAiContextAction("分析当前数据库的表命名规范和整体架构。")}
                          className="btn-secondary" style={{ fontSize: "0.66rem", padding: "2px 7px", height: 24 }}>诊断架构</button>
                      </>
                    )}
                  </div>
                </div>

                {/* Response / suggestions area */}
                <div style={{ flex: 1, overflowY: "auto", padding: 8 }}>
                  {aiResponse ? (
                    <div style={{ padding: 6, background: "var(--bg-secondary)", border: "1px solid var(--border-light)", fontSize: "0.7rem", lineHeight: 1.4 }}>
                      <div style={{ fontWeight: 600, color: "var(--accent-primary)", marginBottom: 3, fontSize: "0.64rem" }}>
                        Copilot 结果
                      </div>
                      <pre style={{ whiteSpace: "pre-wrap", fontFamily: "var(--font-mono)", fontSize: "0.66rem", color: "var(--text-primary)", background: "#fff", padding: 4, overflowX: "auto", border: "1px solid var(--border-light)", margin: 0 }}>
                        {aiResponse}
                      </pre>
                      {aiResponse.includes("SELECT") && (
                        <div style={{ marginTop: 4 }}>
                          <button onClick={() => {
                            const match = aiResponse.match(/SELECT[\s\S]+?;/i);
                            handleOpenQueryTab(match ? match[0] : aiResponse, "AI 生成 SQL");
                          }}
                            className="btn-primary" style={{ padding: "2px 0", fontSize: "0.64rem", width: "100%", justifyContent: "center" }}>
                            插入新控制台
                          </button>
                        </div>
                      )}
                    </div>
                  ) : aiLoading ? (
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6, padding: "16px 0", color: "var(--text-muted)", fontSize: "0.66rem" }}>
                      <span className="animate-spin" style={{ fontSize: 12 }}>↻</span> AI 推理中...
                    </div>
                  ) : (
                    <div style={{ fontSize: "0.64rem", color: "var(--text-muted)", lineHeight: 1.5 }}>
                      <div style={{ fontWeight: 600, marginBottom: 4, color: "var(--text-secondary)" }}>可以试试:</div>
                      {activeTab?.type === "query" ? (
                        <>
                          <div style={{ marginBottom: 2 }}>· 优化当前 SQL 语句</div>
                          <div style={{ marginBottom: 2 }}>· 加 @limit 限制返回行数</div>
                          <div style={{ marginBottom: 2 }}>· 加 @export 导出查询结果</div>
                          <div>· 解释 SQL 执行逻辑</div>
                        </>
                      ) : activeTab?.type === "table" ? (
                        <>
                          <div style={{ marginBottom: 2 }}>· 统计 {activeTab.tableName} 中各字段分布</div>
                          <div style={{ marginBottom: 2 }}>· 找出和 {activeTab.tableName} 关联的表</div>
                          <div style={{ marginBottom: 2 }}>· 为 {activeTab.tableName} 生成测试数据</div>
                          <div>· 诊断 {activeTab.tableName} 的索引和外键</div>
                        </>
                      ) : (
                        <>
                          <div style={{ marginBottom: 2 }}>· 统计各表数据量</div>
                          <div style={{ marginBottom: 2 }}>· 找出数据库中的核心关系表</div>
                          <div style={{ marginBottom: 2 }}>· 生成当前库的 ER 图</div>
                          <div>· 分析表命名规范</div>
                        </>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Input form */}
              <form onSubmit={handleAskGeneralAi}
                style={{ padding: "6px 8px", borderTop: "1px solid var(--border-light)", background: "var(--bg-secondary)", display: "flex", flexDirection: "column", gap: 3 }}>
                <textarea className="input-field" placeholder="Ask 数据库、SQL、结构..."
                  value={aiPrompt} onChange={(e) => setAiPrompt(e.target.value)}
                  style={{ height: 34, fontSize: "0.7rem", resize: "none" }}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void handleAskGeneralAi(e); } }} />
                <button type="submit" className="btn-primary" disabled={aiLoading || !aiPrompt.trim()}
                  style={{ padding: "2px 0", fontSize: "0.68rem", width: "100%", justifyContent: "center" }}>
                  发送
                </button>
              </form>
            </div>
          )}
        </aside>
      </main>

      {/* ── Bottom Status Bar ── */}
      <footer
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: "var(--bg-secondary)",
          borderTop: "1px solid var(--border-light)",
          padding: "0 12px",
          height: 28,
          fontSize: "0.76rem",
          color: "var(--text-secondary)",
          userSelect: "none"
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ color: "var(--accent-green)", fontWeight: 700 }}>
            ● ONLINE
          </span>
          {activeProject && (
            <>
              <span style={{ opacity: 0.4 }}>|</span>
              <span
                onClick={() => setShowCreateProject(true)}
                style={{
                  cursor: "pointer",
                  fontWeight: 600,
                  color: "var(--text-primary)"
                }}
                title="点击切换项目"
              >
                {activeProject.name}
              </span>
            </>
          )}
          {activeDataSource && (
            <>
              <span style={{ opacity: 0.4 }}>|</span>
              <span
                onClick={() => setShowSettingsModal(true)}
                style={{
                  cursor: "pointer",
                  fontWeight: 600,
                  color: "var(--text-primary)"
                }}
                title="点击管理连接"
              >
                {activeDataSource.name}
              </span>
              <span style={{ opacity: 0.4 }}>|</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.66rem" }}>
                {activeDataSource.db_type || "mysql"}
              </span>
              <span style={{ opacity: 0.4 }}>|</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.66rem", color: "var(--accent-indigo)", fontWeight: 600 }}>
                {activeDataSource.database_name}
              </span>
              <span style={{ opacity: 0.4 }}>|</span>
              <span
                style={{
                  fontSize: "0.64rem",
                  fontWeight: 700,
                  padding: "0 4px",
                  borderRadius: 2,
                  background: envBadge.bg,
                  color: envBadge.color,
                }}
              >
                {envBadge.label}
              </span>
              <span style={{ opacity: 0.4 }}>|</span>
              <span>
                只读: <strong style={{ color: "var(--text-primary)" }}>{activeDataSource.is_read_only ? "是" : "否"}</strong>
              </span>
            </>
          )}
          {activeTab?.resultState === "running" && (
            <>
              <span style={{ opacity: 0.4 }}>|</span>
              <span className="animate-pulse" style={{ color: "var(--accent-indigo)", fontWeight: 700 }}>
                执行中...
              </span>
              <button
                onClick={() => triggerActiveTabAction("stop")}
                style={{
                  background: "var(--accent-red)",
                  color: "#fff",
                  border: "none",
                  borderRadius: 3,
                  padding: "0 4px",
                  fontSize: "0.6rem",
                  cursor: "pointer"
                }}
              >
                取消
              </button>
            </>
          )}
          {activeTab?.resultState === "error" && (
            <>
              <span style={{ opacity: 0.4 }}>|</span>
              <span style={{ color: "var(--accent-red)", fontWeight: 700 }}>SQL 执行报错</span>
            </>
          )}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {activeTab?.lastExecutedAt && (
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.64rem", opacity: 0.7 }}>
              {activeTab.lastExecutedAt ? `${Date.now() - activeTab.lastExecutedAt}ms` : ""}
            </span>
          )}
          <button
            onClick={() => setShowTourDialog(!showTourDialog)}
            style={{
              background: "transparent",
              border: "none",
              cursor: "pointer",
              fontSize: "0.76rem",
              color: "var(--accent-indigo)",
              display: "flex",
              alignItems: "center",
              gap: 3,
              fontWeight: 600
            }}
          >
            <Sparkles size={10} />
            引导向导
          </button>
        </div>
      </footer>

      {/* ── Layer 4: Popups and Overlays Modals ── */}

      {/* Object Explorer Tree Context Menu popup */}
      {treeContextMenu && (
        <>
          <div
            onClick={() => setTreeContextMenu(null)}
            onContextMenu={(e) => { e.preventDefault(); setTreeContextMenu(null); }}
            style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, zIndex: 1999 }}
          />
          <div
            style={{
              position: "fixed",
              top: treeContextMenu.y,
              left: treeContextMenu.x,
              minWidth: 160,
              background: "var(--bg-surface)",
              border: "1px solid var(--border-light)",
              borderRadius: 8,
              boxShadow: "var(--shadow-lg)",
              padding: 6,
              zIndex: 2000,
              textAlign: "left"
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ padding: "4px 8px", fontSize: "0.76rem", color: "var(--text-muted)", borderBottom: "1px solid var(--border-light)", marginBottom: 4, fontWeight: 600 }}>
              数据表: {treeContextMenu.tableName}
            </div>
            <button
              className="data-table-menu-item"
              onClick={() => {
                handleOpenTableTab(treeContextMenu.tableName, "data");
                setTreeContextMenu(null);
              }}
            >
              打开数据 (Data Preview)
            </button>
            <button
              className="data-table-menu-item"
              onClick={() => {
                handleOpenTableTab(treeContextMenu.tableName, "schema");
                setTreeContextMenu(null);
              }}
            >
              打开结构字段 (Columns)
            </button>
            <button
              className="data-table-menu-item"
              onClick={() => {
                handleOpenTableTab(treeContextMenu.tableName, "er");
                setTreeContextMenu(null);
              }}
            >
              查看 ER 实体关联图
            </button>
            <button
              className="data-table-menu-item"
              onClick={() => {
                handleOpenQueryTab("", `查询: ${treeContextMenu.tableName}`);
                setTreeContextMenu(null);
              }}
            >
              新建 SQL 查询
            </button>
            <button
              className="data-table-menu-item"
              onClick={() => {
                handleGenerateSelect(treeContextMenu.tableName);
                setTreeContextMenu(null);
              }}
            >
              生成 SELECT SQL
            </button>
            <div style={{ height: 1, background: "var(--border-light)", margin: "4px 0" }} />
            <button
              className="data-table-menu-item"
              onClick={() => {
                void navigator.clipboard.writeText(treeContextMenu.tableName);
                setTreeContextMenu(null);
                showToast?.("表名已复制");
              }}
            >
              复制表名
            </button>
            <button
              className="data-table-menu-item"
              onClick={() => {
                handleAiContextAction(`用物理字段命名规范，详细解释数据库表 ${treeContextMenu.tableName} 的设计含义，并归纳关联模型。`);
                setTreeContextMenu(null);
              }}
            >
              🪄 AI 解释表结构
            </button>
          </div>
        </>
      )}

      {/* Global Command Palette */}
      <CommandPalette
        open={showCommandPalette}
        onClose={() => setShowCommandPalette(false)}
        commands={commandItems}
      />

      {/* Quiet Stepper Tour Guide Dialog triggered from status bar */}
      {showTourDialog && (
        <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(15, 23, 42, 0.4)", backdropFilter: "blur(3px)", zIndex: 1999, display: "grid", placeItems: "center" }}>
          <div style={{ background: "var(--bg-surface)", width: 440, borderRadius: 12, border: "1px solid var(--border-light)", display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "var(--shadow-xl)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 20px", borderBottom: "1px solid var(--border-light)", background: "var(--bg-secondary)" }}>
              <span style={{ fontWeight: 700, fontSize: "0.82rem", color: "var(--text-primary)", display: "flex", alignItems: "center", gap: 5 }}><Sparkles size={13} />体验 Demo 引导向导</span>
              <button onClick={() => setShowTourDialog(false)} className="btn-ghost" style={{ padding: 4 }}><X size={16} /></button>
            </div>
            <div style={{ padding: 10, overflow: "auto", maxHeight: "70vh" }}>
              <DemoTourGuide
                activeTab={activeTab?.type || "workbench"}
                setActiveTab={() => {}}
                projects={projects}
                activeProject={activeProject}
                datasources={datasources}
                activeDataSource={activeDataSource}
                schemaTables={schemaTables}
                handleCreateProject={async (name) => {
                  await onCreateProject(name || "演示项目");
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Settings Modal (Datasources Manager) */}
      {showSettingsModal && (
        <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(15, 23, 42, 0.4)", backdropFilter: "blur(4px)", zIndex: 1000, display: "grid", placeItems: "center" }}>
          <div style={{ background: "var(--bg-surface)", width: "80%", height: "85%", borderRadius: 12, border: "1px solid var(--border-light)", display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 20px 50px rgba(0,0,0,0.15)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 20px", borderBottom: "1px solid var(--border-light)", background: "var(--bg-secondary)" }}>
              <span style={{ fontWeight: 700, fontSize: "0.82rem", color: "var(--text-primary)" }}>连接管理器（数据源设置）</span>
              <button onClick={() => setShowSettingsModal(false)} className="btn-ghost" style={{ padding: 4 }}><X size={16} /></button>
            </div>
            <div style={{ flex: 1, overflow: "auto", padding: 20 }}>
              <DataSourcesPage
                onSelectDataSource={(ds) => {
                  setActiveDataSource(ds);
                  setShowSettingsModal(false);
                }}
                activeDataSource={activeDataSource}
                activeProject={activeProject}
                onRefreshDatasources={onRefreshDatasources}
              />
            </div>
          </div>
        </div>
      )}

      {/* Environments Config Modal */}
      {showEnvironmentsModal && (
        <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(15, 23, 42, 0.4)", backdropFilter: "blur(4px)", zIndex: 1000, display: "grid", placeItems: "center" }}>
          <div style={{ background: "var(--bg-surface)", width: "80%", height: "85%", borderRadius: 12, border: "1px solid var(--border-light)", display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 20px 50px rgba(0,0,0,0.15)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 20px", borderBottom: "1px solid var(--border-light)", background: "var(--bg-secondary)" }}>
              <span style={{ fontWeight: 700, fontSize: "0.82rem", color: "var(--text-primary)" }}>环境配置</span>
              <button onClick={() => setShowEnvironmentsModal(false)} className="btn-ghost" style={{ padding: 4 }}><X size={16} /></button>
            </div>
            <div style={{ flex: 1, overflow: "auto", padding: 20 }}>
              <EnvironmentsPage
                activeProject={activeProject}
                onRefreshDatasources={onRefreshDatasources}
                onSelectDataSource={(ds) => {
                  setActiveDataSource(ds);
                  setShowEnvironmentsModal(false);
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Backups Manager Modal */}
      {showBackupsModal && (
        <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(15, 23, 42, 0.4)", backdropFilter: "blur(4px)", zIndex: 1000, display: "grid", placeItems: "center" }}>
          <div style={{ background: "var(--bg-surface)", width: "80%", height: "85%", borderRadius: 12, border: "1px solid var(--border-light)", display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 20px 50px rgba(0,0,0,0.15)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 20px", borderBottom: "1px solid var(--border-light)", background: "var(--bg-secondary)" }}>
              <span style={{ fontWeight: 700, fontSize: "0.82rem", color: "var(--text-primary)" }}>备份与恢复管理器</span>
              <button onClick={() => setShowBackupsModal(false)} className="btn-ghost" style={{ padding: 4 }}><X size={16} /></button>
            </div>
            <div style={{ flex: 1, overflow: "auto", padding: 20 }}>
              <BackupsPage
                activeProject={activeProject}
                datasources={datasources}
                activeDataSource={activeDataSource}
              />
            </div>
          </div>
        </div>
      )}

      {/* Performance Monitoring Modal */}
      {showDashboardModal && activeDataSource && (
        <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(15, 23, 42, 0.4)", backdropFilter: "blur(4px)", zIndex: 1000, display: "grid", placeItems: "center" }}>
          <div style={{ background: "var(--bg-surface)", width: "80%", height: "85%", borderRadius: 12, border: "1px solid var(--border-light)", display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 20px 50px rgba(0,0,0,0.15)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 20px", borderBottom: "1px solid var(--border-light)", background: "var(--bg-secondary)" }}>
              <span style={{ fontWeight: 700, fontSize: "0.82rem", color: "var(--text-primary)" }}>性能监控面板</span>
              <button onClick={() => setShowDashboardModal(false)} className="btn-ghost" style={{ padding: 4 }}><X size={16} /></button>
            </div>
            <div style={{ flex: 1, overflow: "auto", padding: 20 }}>
              <Suspense fallback={<div className="skeleton" style={{ height: 240, borderRadius: 8 }} />}>
                <DashboardPage datasource={activeDataSource} />
              </Suspense>
            </div>
          </div>
        </div>
      )}

      {/* Prompt Dialog for New Project */}
      <PromptDialog
        open={showCreateProject}
        title="创建新项目"
        placeholder="请输入项目名称"
        onConfirm={(name) => {
          setShowCreateProject(false);
          void onCreateProject(name);
        }}
        onCancel={() => setShowCreateProject(false)}
      />

    </div>
  );
};
