import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  Database,
  Layers,
  RefreshCw,
  Settings,
  Sparkles,
  Terminal,
} from "lucide-react";
import { MenuBar, type MenuDef } from "../components/MenuBar";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { PromptDialog } from "../components/PromptDialog";
import { CommandPalette, type CommandItem } from "../components/CommandPalette";
import { useToast } from "../components/Toast";
import { SettingsDialog, useApiConfig } from "../components/SettingsDialog";
import { api } from "../lib/api";
import type { DataSource, Project, SchemaTable } from "../lib/api";
import { AgentCopilotPanel } from "../features/agent/AgentCopilotPanel";
import { SemanticSettingsPanel } from "../features/semantic/SemanticSettingsPanel";
import { WorkbenchShell } from "../features/workbench/WorkbenchShell";
import { WorkbenchSidebar } from "../features/workbench/WorkbenchSidebar";
import { WorkbenchTabs } from "../features/workbench/WorkbenchTabs";
import { WorkbenchTableHeader } from "../features/workbench/WorkbenchTableHeader";
import { WorkbenchStatusBar } from "../features/workbench/WorkbenchStatusBar";
import { WorkbenchModal } from "../features/workbench/WorkbenchModal";
import { WorkbenchContextMenu } from "../features/workbench/WorkbenchContextMenu";
import type { QueryTabStatePatch, WorkbenchActionType, WorkbenchSubTab, WorkbenchTab } from "../features/workbench/types";
import { BackupsPage } from "./BackupsPage";
import { DataSourcesPage } from "./DataSourcesPage";

export type { WorkbenchTab } from "../features/workbench/types";

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

interface WorkbenchPageProps {
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

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function downloadTextFile(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function buildSelectSql(tableName: string) {
  return `SELECT * FROM \`${tableName}\` LIMIT 100;`;
}

export const WorkbenchPage = ({
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
  const apiConfig = useApiConfig();

  const [tabs, setTabs] = useState<WorkbenchTab[]>([]);
  const [activeTabId, setActiveTabId] = useState<string | null>(null);
  const [treeSearch, setTreeSearch] = useState("");
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [tablesFolderExpanded, setTablesFolderExpanded] = useState(true);
  const [aiPanelCollapsed, setAiPanelCollapsed] = useState(true);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [showBackupsModal, setShowBackupsModal] = useState(false);
  const [showDashboardModal, setShowDashboardModal] = useState(false);
  const [showCreateProject, setShowCreateProject] = useState(false);
  const [showSemanticSettings, setShowSemanticSettings] = useState(false);
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const [treeContextMenu, setTreeContextMenu] = useState<{ tableName: string; x: number; y: number } | null>(null);

  const activeTab = useMemo(() => tabs.find((tab) => tab.id === activeTabId) || null, [activeTabId, tabs]);
  const activeTableMeta = useMemo(() => {
    if (!activeTab?.tableName) return null;
    return schemaTables.find((table) => table.table_name === activeTab.tableName) || null;
  }, [activeTab?.tableName, schemaTables]);

  const filteredTables = useMemo(() => {
    const keyword = treeSearch.trim().toLowerCase();
    if (!keyword) return schemaTables;
    return schemaTables.filter((table) =>
      table.table_name.toLowerCase().includes(keyword) ||
      table.table_comment.toLowerCase().includes(keyword),
    );
  }, [schemaTables, treeSearch]);

  const groupedTables = useMemo(() => {
    const groups = new Map<string, SchemaTable[]>();
    for (const table of filteredTables) {
      const tag = table.module_tag || getModuleTag(table.table_name);
      groups.set(tag, [...(groups.get(tag) || []), table]);
    }
    return Array.from(groups.entries())
      .sort(([left], [right]) => {
        const leftIndex = MODULE_ORDER.indexOf(left);
        const rightIndex = MODULE_ORDER.indexOf(right);
        const normalizedLeft = leftIndex === -1 ? MODULE_ORDER.length : leftIndex;
        const normalizedRight = rightIndex === -1 ? MODULE_ORDER.length : rightIndex;
        return normalizedLeft - normalizedRight || left.localeCompare(right, "zh-Hans-CN");
      })
      .map(([tag, tables]) => ({
        tag,
        tables: [...tables].sort((a, b) => a.table_name.localeCompare(b.table_name)),
      }));
  }, [filteredTables]);

  const handleOpenQueryTab = useCallback((sqlDraft = "", title?: string) => {
    const id = `query:${Date.now()}`;
    const queryCount = tabs.filter((tab) => tab.type === "query").length + 1;
    const newTab: WorkbenchTab = {
      id,
      type: "query",
      title: title || `查询_${queryCount}`,
      sqlDraft,
      connectionId: activeDataSource?.id,
      databaseName: activeDataSource?.database_name,
      resultState: "idle",
    };
    setTabs((prev) => [...prev, newTab]);
    setActiveTabId(id);
  }, [activeDataSource?.database_name, activeDataSource?.id, tabs]);

  const handleOpenTableTab = useCallback((tableName: string, subTab: WorkbenchSubTab = "data") => {
    const id = `table:${tableName}`;
    setTabs((prev) => {
      const exists = prev.some((tab) => tab.id === id);
      if (exists) {
        return prev.map((tab) => tab.id === id ? { ...tab, activeSubTab: subTab } : tab);
      }
      return [
        ...prev,
        {
          id,
          type: "table",
          title: `表: ${tableName}`,
          tableName,
          activeSubTab: subTab,
          connectionId: activeDataSource?.id,
          databaseName: activeDataSource?.database_name,
        },
      ];
    });
    setActiveTabId(id);
  }, [activeDataSource?.database_name, activeDataSource?.id]);

  const handleSelectTab = useCallback((tabId: string) => {
    setActiveTabId(tabId);
    const tab = tabs.find((item) => item.id === tabId);
    if (tab?.connectionId && tab.connectionId !== activeDataSource?.id) {
      const datasource = datasources.find((item) => item.id === tab.connectionId);
      if (datasource) setActiveDataSource(datasource);
    }
  }, [activeDataSource?.id, datasources, setActiveDataSource, tabs]);

  const handleCloseTab = useCallback((id: string, event?: React.MouseEvent) => {
    event?.stopPropagation();
    const tab = tabs.find((item) => item.id === id);
    if (tab?.dirty && !window.confirm(`"${tab.title}" 还有未执行或未保存的修改，确认关闭吗？`)) return;

    const nextTabs = tabs.filter((item) => item.id !== id);
    setTabs(nextTabs);
    if (activeTabId === id) {
      setActiveTabId(nextTabs[nextTabs.length - 1]?.id || null);
    }
  }, [activeTabId, tabs]);

  const handleCloseOtherTabs = useCallback(() => {
    if (!activeTabId) return;
    setTabs((prev) => prev.filter((tab) => tab.id === activeTabId));
  }, [activeTabId]);

  const handleCloseTabsToRight = useCallback(() => {
    if (!activeTabId) return;
    setTabs((prev) => {
      const index = prev.findIndex((tab) => tab.id === activeTabId);
      return index === -1 ? prev : prev.slice(0, index + 1);
    });
  }, [activeTabId]);

  const triggerActiveTabAction = useCallback((type: WorkbenchActionType) => {
    if (!activeTabId) return;
    setTabs((prev) => prev.map((tab) => tab.id === activeTabId ? {
      ...tab,
      actionTrigger: { type, nonce: Date.now() },
    } : tab));
  }, [activeTabId]);

  const handleActiveQueryStateChange = useCallback((state: QueryTabStatePatch) => {
    if (!activeTabId) return;
    setTabs((prev) => prev.map((tab) => {
      if (tab.id !== activeTabId) return tab;
      const nextResultState = state.resultState ?? tab.resultState;
      const terminalResult = nextResultState && nextResultState !== tab.resultState && ["success", "error", "timeout", "cancelled"].includes(nextResultState);
      return {
        ...tab,
        resultState: nextResultState,
        sqlDraft: state.sqlDraft ?? tab.sqlDraft,
        dirty: state.dirty ?? tab.dirty,
        lastQueryResultPreview: state.lastQueryResultPreview ?? tab.lastQueryResultPreview,
        lastError: state.lastError ?? tab.lastError,
        lastExecutedAt: terminalResult ? Date.now() : tab.lastExecutedAt,
      };
    }));
  }, [activeTabId]);

  const handleSwitchSubTab = useCallback((tabId: string, subTab: WorkbenchSubTab) => {
    setTabs((prev) => prev.map((tab) => tab.id === tabId ? { ...tab, activeSubTab: subTab } : tab));
  }, []);

  const handleApplySqlToEditor = useCallback((sql: string) => {
    const trimmed = sql.trim();
    if (!trimmed) return;
    if (activeTab?.type === "query" && activeTabId) {
      setTabs((prev) => prev.map((tab) => tab.id === activeTabId ? { ...tab, sqlDraft: trimmed, dirty: true } : tab));
      showToast("SQL 已写入当前编辑器", "success");
      return;
    }
    handleOpenQueryTab(trimmed, "Agent SQL");
  }, [activeTab?.type, activeTabId, handleOpenQueryTab, showToast]);

  const handleSaveCurrentSql = useCallback((saveAs = false) => {
    if (!activeTab || activeTab.type !== "query") {
      showToast("当前不是 SQL 标签页", "info");
      return;
    }
    const sql = activeTab.sqlDraft?.trim();
    if (!sql) {
      showToast("没有可保存的 SQL", "info");
      return;
    }
    downloadTextFile(`${saveAs ? "databox_sql" : activeTab.title}_${new Date().toISOString().slice(0, 10)}.sql`, sql, "text/sql;charset=utf-8");
    setTabs((prev) => prev.map((tab) => tab.id === activeTab.id ? { ...tab, dirty: false } : tab));
    showToast("SQL 已导出", "success");
  }, [activeTab, showToast]);

  const handleExportConnectionConfig = useCallback(() => {
    const payload = datasources.map((datasource) => ({
      id: datasource.id,
      name: datasource.name,
      db_type: datasource.db_type,
      host: datasource.host,
      port: datasource.port,
      database_name: datasource.database_name,
      username: datasource.username,
      connection_mode: datasource.connection_mode,
      is_read_only: datasource.is_read_only,
      env: datasource.env,
      ssh_enabled: datasource.ssh_enabled,
      ssh_host: datasource.ssh_host,
      ssh_port: datasource.ssh_port,
      ssh_username: datasource.ssh_username,
      ssh_pkey_path: datasource.ssh_pkey_path,
      ssl_enabled: datasource.ssl_enabled,
      ssl_ca_path: datasource.ssl_ca_path,
      ssl_cert_path: datasource.ssl_cert_path,
      ssl_key_path: datasource.ssl_key_path,
      ssl_verify_identity: datasource.ssl_verify_identity,
    }));
    downloadTextFile(`databox_connections_${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify(payload, null, 2), "application/json;charset=utf-8");
    showToast("连接配置已导出，密码不会写入文件", "success");
  }, [datasources, showToast]);

  const handleImportConnectionConfig = useCallback(() => {
    setShowSettingsModal(true);
    showToast("请在连接管理器中添加或导入连接配置", "info");
  }, [showToast]);

  const handleTestActiveConnection = useCallback(async () => {
    if (!activeDataSource) {
      showToast("请先选择一个连接", "info");
      return;
    }
    try {
      const result = await api.checkDatasourceHealth(activeDataSource.id);
      showToast(result.message || "连接测试成功", result.ok ? "success" : "warning");
    } catch (error: unknown) {
      showToast(getErrorMessage(error, "连接测试失败"), "error");
    }
  }, [activeDataSource, showToast]);

  const handleGenerateSelect = useCallback((tableName: string) => {
    handleOpenQueryTab(buildSelectSql(tableName), `查询: ${tableName}`);
  }, [handleOpenQueryTab]);

  const handleDragStartNode = useCallback((event: React.DragEvent, tableName: string) => {
    event.dataTransfer.setData("text/plain", buildSelectSql(tableName));
    event.dataTransfer.effectAllowed = "copy";
  }, []);

  const handleCopyTableName = useCallback((tableName: string) => {
    void navigator.clipboard.writeText(tableName);
    showToast("表名已复制", "success");
  }, [showToast]);

  const handleExplainTable = useCallback((tableName: string) => {
    setAiPanelCollapsed(false);
    showToast(`已打开 Agent 面板，可继续分析 ${tableName}`, "info");
  }, [showToast]);

  const handleAiContextAction = useCallback((message: string) => {
    setAiPanelCollapsed(false);
    showToast(message, "info");
  }, [showToast]);

  useEffect(() => {
    const handleGlobalKeyDown = (event: KeyboardEvent) => {
      const mod = event.ctrlKey || event.metaKey;
      if (mod && event.key.toLowerCase() === "t") {
        event.preventDefault();
        handleOpenQueryTab();
      }
      if (mod && event.key.toLowerCase() === "p") {
        event.preventDefault();
        setShowCommandPalette(true);
      }
      if (event.altKey && event.key.toLowerCase() === "a") {
        event.preventDefault();
        setAiPanelCollapsed((prev) => !prev);
      }
      if (mod && event.key.toLowerCase() === "w" && activeTabId) {
        event.preventDefault();
        handleCloseTab(activeTabId);
      }
    };
    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, [activeTabId, handleCloseTab, handleOpenQueryTab]);

  const commandItems = useMemo<CommandItem[]>(() => [
    {
      id: "new-query",
      name: "新建 SQL 控制台",
      category: "编辑器",
      shortcut: "Ctrl + T",
      icon: <Terminal size={13} />,
      action: () => handleOpenQueryTab(),
    },
    {
      id: "refresh-metadata",
      name: "刷新元数据结构",
      category: "数据源",
      icon: <RefreshCw size={13} />,
      action: () => { if (activeDataSource) void onRefreshSchemaTables(activeDataSource.id); },
    },
    {
      id: "open-er",
      name: "打开 ER 关系图",
      category: "视图",
      icon: <Layers size={13} />,
      action: () => { if (schemaTables[0]) handleOpenTableTab(schemaTables[0].table_name, "er"); },
    },
    {
      id: "open-settings",
      name: "打开连接管理器",
      category: "设置",
      icon: <Settings size={13} />,
      action: () => setShowSettingsModal(true),
    },
    {
      id: "open-dashboard",
      name: "打开性能监控面板",
      category: "监控",
      icon: <Activity size={13} />,
      action: () => setShowDashboardModal(true),
    },
  ], [activeDataSource, handleOpenQueryTab, handleOpenTableTab, onRefreshSchemaTables, schemaTables]);

  const menus = useMemo<MenuDef[]>(() => {
    const handleCloseWindow = () => {
      try {
        import("@tauri-apps/api/window").then(({ getCurrentWindow }) => getCurrentWindow().close()).catch(() => {});
      } catch { /* noop */ }
    };
    const hasConnection = !!activeDataSource;
    return [
      {
        id: "file",
        label: "文件",
        items: [
          { label: "新建 SQL 控制台", shortcut: "Ctrl+T", action: () => handleOpenQueryTab() },
          { label: "保存当前 SQL", shortcut: "Ctrl+S", action: () => handleSaveCurrentSql(false) },
          { label: "另存为 SQL 文件", action: () => handleSaveCurrentSql(true) },
          { separator: true, label: "" },
          { label: "导入连接配置", action: handleImportConnectionConfig },
          { label: "导出连接配置", action: handleExportConnectionConfig },
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
          { label: "格式化 SQL", action: () => triggerActiveTabAction("format") },
        ],
      },
      {
        id: "view",
        label: "视图",
        items: [
          { label: "显示 / 隐藏 AI 面板", shortcut: "Alt+A", action: () => setAiPanelCollapsed((prev) => !prev) },
          { label: "性能监控面板", action: () => setShowDashboardModal(true) },
        ],
      },
      {
        id: "run",
        label: "运行",
        items: [
          { label: "执行当前 SQL", shortcut: "Ctrl+Enter", action: () => triggerActiveTabAction("execute") },
          { label: "停止执行", action: () => triggerActiveTabAction("stop") },
          { separator: true, label: "" },
          { label: "格式化 SQL", action: () => triggerActiveTabAction("format") },
          { label: "安全检查", action: () => triggerActiveTabAction("validate") },
          { label: "导出当前结果", action: () => triggerActiveTabAction("export") },
        ],
      },
      {
        id: "database",
        label: "数据库",
        items: [
          { label: "新建连接", action: () => setShowSettingsModal(true) },
          { label: "测试连接", action: handleTestActiveConnection },
          { label: "断开连接", disabled: !hasConnection, action: () => { if (hasConnection) setActiveDataSource(null); } },
          { label: "连接设置", action: () => setShowSettingsModal(true) },
          { separator: true, label: "" },
          { label: "刷新结构", disabled: !hasConnection, action: () => { if (activeDataSource) void onRefreshSchemaTables(activeDataSource.id); } },
          { label: "打开 SQL 控制台", shortcut: "Ctrl+T", action: () => handleOpenQueryTab() },
          { label: "打开 ER 图", disabled: !hasConnection || schemaTables.length === 0, action: () => { if (schemaTables[0]) handleOpenTableTab(schemaTables[0].table_name, "er"); } },
          { separator: true, label: "" },
          { label: "备份数据库", disabled: !hasConnection, action: () => setShowBackupsModal(true) },
          { label: "恢复数据库", disabled: !hasConnection, action: () => setShowBackupsModal(true) },
        ],
      },
      {
        id: "ai",
        label: "AI",
        items: [
          { label: "打开 AI 面板", shortcut: "Alt+A", action: () => setAiPanelCollapsed(false) },
          { separator: true, label: "" },
          { label: "生成 SQL", action: () => handleAiContextAction("已打开 AI 面板，可基于当前上下文生成 SQL") },
          { label: "解释当前 SQL", action: () => handleAiContextAction("已打开 AI 面板，可解释当前 SQL") },
          { label: "诊断表结构", action: () => handleAiContextAction("已打开 AI 面板，可诊断当前表结构") },
        ],
      },
      {
        id: "help",
        label: "帮助",
        items: [
          { label: "快捷键参考", action: () => setShowCommandPalette(true) },
          { label: "性能监控面板", action: () => setShowDashboardModal(true) },
          { separator: true, label: "" },
          { label: "关于 DataBox", action: () => alert("DataBox v1.0.0\nAI 驱动的本地数据库工作台") },
        ],
      },
    ];
  }, [activeDataSource, handleAiContextAction, handleExportConnectionConfig, handleImportConnectionConfig, handleOpenQueryTab, handleOpenTableTab, handleSaveCurrentSql, handleTestActiveConnection, onRefreshSchemaTables, schemaTables, setActiveDataSource, triggerActiveTabAction]);

  const activeTableName = activeTab?.type === "table" ? activeTab.tableName : undefined;

  const sidebar = (
    <WorkbenchSidebar
      datasources={datasources}
      activeDataSource={activeDataSource}
      schemaTables={schemaTables}
      groupedTables={groupedTables}
      loadingTree={loadingTree}
      loadingObjects={loadingObjects}
      treeSearch={treeSearch}
      collapsedGroups={collapsedGroups}
      tablesFolderExpanded={tablesFolderExpanded}
      activeTableName={activeTableName}
      onSelectDataSource={setActiveDataSource}
      onRefreshSchema={(datasourceId) => void onRefreshSchemaTables(datasourceId)}
      onOpenTable={handleOpenTableTab}
      onOpenSemanticSettings={() => setShowSemanticSettings(true)}
      onTreeSearchChange={setTreeSearch}
      onToggleTablesFolder={() => setTablesFolderExpanded((prev) => !prev)}
      onToggleGroup={(tag) => setCollapsedGroups((prev) => {
        const next = new Set(prev);
        if (next.has(tag)) next.delete(tag);
        else next.add(tag);
        return next;
      })}
      onTableContextMenu={(tableName, x, y) => setTreeContextMenu({ tableName, x, y })}
      onDragTableSql={handleDragStartNode}
    />
  );

  const main = (
    <>
      <WorkbenchTabs
        tabs={tabs}
        activeTabId={activeTabId}
        onSelectTab={handleSelectTab}
        onCloseTab={handleCloseTab}
        onNewQuery={() => handleOpenQueryTab()}
        onCloseOtherTabs={handleCloseOtherTabs}
        onCloseTabsToRight={handleCloseTabsToRight}
      />
      <div className="wb-content">
        {tabs.length === 0 ? (
          <div className="wb-empty-state">
            <div className="wb-empty-card">
              <div className="wb-empty-title">
                <Sparkles size={18} />
                DataBox Workbench
              </div>
              <div className="wb-empty-copy">
                先选择左侧数据源和数据表。当前架构把数据库浏览作为主工作区，AI 面板默认收起，避免压缩表格和关系图空间。
              </div>
              <div className="wb-empty-actions">
                <button className="wb-primary-button" type="button" onClick={() => handleOpenQueryTab()}>
                  <Terminal size={14} />
                  新建 SQL 控制台
                </button>
                <button className="wb-secondary-button" type="button" onClick={() => setShowSettingsModal(true)}>
                  <Database size={14} />
                  连接管理器
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="h-full w-full">
            {activeTab?.type === "query" && activeDataSource && (
              <ErrorBoundary title="SQL 终端加载异常">
                <Suspense fallback={<div className="h-full rounded-sm bg-gradient-to-r from-secondary via-muted to-secondary bg-[length:200%_100%] animate-shimmer" />}>
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
              <div className="wb-table-frame">
                <WorkbenchTableHeader
                  tableName={activeTab.tableName}
                  table={activeTableMeta}
                  activeSubTab={activeTab.activeSubTab || "data"}
                  onSwitchSubTab={(subTab) => handleSwitchSubTab(activeTab.id, subTab)}
                />
                <div className="min-h-0 flex-1 overflow-hidden">
                  {(activeTab.activeSubTab || "data") === "data" && (
                    <ErrorBoundary title="DataTable Preview Error">
                      <Suspense fallback={<div className="h-full rounded-sm bg-gradient-to-r from-secondary via-muted to-secondary bg-[length:200%_100%] animate-shimmer" />}>
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
                      <Suspense fallback={<div className="h-full rounded-sm bg-gradient-to-r from-secondary via-muted to-secondary bg-[length:200%_100%] animate-shimmer" />}>
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
                      <Suspense fallback={<div className="h-full rounded-sm bg-gradient-to-r from-secondary via-muted to-secondary bg-[length:200%_100%] animate-shimmer" />}>
                        <SchemaPage
                          datasource={activeDataSource}
                          initialViewTab="er"
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
    </>
  );

  const assistant = (
    <AgentCopilotPanel
      datasource={activeDataSource}
      activeTableName={activeTableName}
      activeSql={activeTab?.type === "query" ? activeTab.sqlDraft || "" : ""}
      lastQueryResult={activeTab?.type === "query" ? activeTab.lastQueryResultPreview || null : null}
      lastError={activeTab?.type === "query" ? activeTab.lastError || null : null}
      isCollapsed={aiPanelCollapsed}
      onCollapse={() => setAiPanelCollapsed((prev) => !prev)}
      onInsertSql={handleApplySqlToEditor}
      onRunSql={(sql) => handleOpenQueryTab(sql, "Agent SQL")}
      onOpenQueryTab={handleOpenQueryTab}
      onOpenApiConfig={() => apiConfig.setOpen(true)}
      apiConfigured={apiConfig.isConfigured}
    />
  );

  return (
    <>
      <WorkbenchShell
        menuBar={<MenuBar menus={menus} />}
        sidebar={sidebar}
        main={main}
        assistant={assistant}
        statusBar={(
          <WorkbenchStatusBar
            activeProject={activeProject}
            activeDataSource={activeDataSource}
            activeTab={activeTab}
            onOpenProjectDialog={() => setShowCreateProject(true)}
            onOpenDatasourceDialog={() => setShowSettingsModal(true)}
            onStopQuery={() => triggerActiveTabAction("stop")}
          />
        )}
        assistantCollapsed={aiPanelCollapsed}
      />

      <WorkbenchContextMenu
        menu={treeContextMenu}
        onClose={() => setTreeContextMenu(null)}
        onOpenData={(tableName) => handleOpenTableTab(tableName, "data")}
        onOpenSchema={(tableName) => handleOpenTableTab(tableName, "schema")}
        onOpenEr={(tableName) => handleOpenTableTab(tableName, "er")}
        onNewQuery={(tableName) => handleOpenQueryTab("", `查询: ${tableName}`)}
        onGenerateSelect={handleGenerateSelect}
        onCopyTableName={handleCopyTableName}
        onExplainTable={handleExplainTable}
      />

      <CommandPalette open={showCommandPalette} onClose={() => setShowCommandPalette(false)} commands={commandItems} />

      {showSettingsModal && (
        <WorkbenchModal title="连接管理器" onClose={() => setShowSettingsModal(false)}>
          <DataSourcesPage
            onSelectDataSource={(datasource) => {
              setActiveDataSource(datasource);
              setShowSettingsModal(false);
            }}
            activeDataSource={activeDataSource}
            activeProject={activeProject}
            onRefreshDatasources={onRefreshDatasources}
          />
        </WorkbenchModal>
      )}

      {showBackupsModal && (
        <WorkbenchModal title="备份与恢复管理器" onClose={() => setShowBackupsModal(false)}>
          <BackupsPage activeProject={activeProject} datasources={datasources} activeDataSource={activeDataSource} />
        </WorkbenchModal>
      )}

      {showDashboardModal && activeDataSource && (
        <WorkbenchModal title="性能监控面板" onClose={() => setShowDashboardModal(false)}>
          <Suspense fallback={<div className="h-60 rounded-lg bg-gradient-to-r from-secondary via-muted to-secondary bg-[length:200%_100%] animate-shimmer" />}>
            <DashboardPage datasource={activeDataSource} />
          </Suspense>
        </WorkbenchModal>
      )}

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

      {showSemanticSettings && activeDataSource && activeProject && (
        <SemanticSettingsPanel datasource={activeDataSource} projectId={activeProject.id} onClose={() => setShowSemanticSettings(false)} />
      )}

      <SettingsDialog
        open={apiConfig.open}
        onOpenChange={apiConfig.setOpen}
        config={apiConfig.config}
        onChange={apiConfig.updateConfig}
        onSave={apiConfig.handleSave}
        saved={apiConfig.saved}
      />
    </>
  );
};
