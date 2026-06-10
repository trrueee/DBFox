import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { Database, PanelRightClose, PanelRightOpen, Search, Settings, Terminal } from "lucide-react";
import { MenuBar, type MenuDef } from "../components/MenuBar";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { PromptDialog } from "../components/PromptDialog";
import { CommandPalette, type CommandItem } from "../components/CommandPalette";
import { useToast } from "../components/Toast";
import { ApiConfigDialog, useApiConfig } from "../components/ApiConfigDialog";
import { DataSourcesPage } from "./DataSourcesPage";
import type { DataSource, Project, SchemaTable } from "../lib/api";
import { AgentCopilotPanel } from "../features/agent/AgentCopilotPanel";
import { SemanticSettingsPanel } from "../features/semantic/SemanticSettingsPanel";
import { LayoutRegion } from "../features/workbench/LayoutRegion";
import { ObjectExplorer } from "../features/workbench/ObjectExplorer";
import { WorkbenchHome } from "../features/workbench/WorkbenchHome";
import { WorkbenchStatusBar } from "../features/workbench/WorkbenchStatusBar";
import { WorkbenchTabs } from "../features/workbench/WorkbenchTabs";
import { useWorkbenchTabs } from "../features/workbench/useWorkbenchTabs";
import type { TableSubTab } from "../features/workbench/types";
import "../features/workbench/workbench.css";

const QueryPage = lazy(() => import("./QueryPage").then((module) => ({ default: module.QueryPage })));
const SchemaPage = lazy(() => import("./SchemaPage").then((module) => ({ default: module.SchemaPage })));
const DataPage = lazy(() => import("./DataPage").then((module) => ({ default: module.DataPage })));

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

const TABLE_TABS: { id: TableSubTab; label: string }[] = [
  { id: "data", label: "Data" },
  { id: "schema", label: "Schema" },
  { id: "er", label: "ER Diagram" },
];

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
  const { toast } = useToast();
  const apiConfig = useApiConfig();
  const tabs = useWorkbenchTabs(activeDataSource);

  const [showDataSources, setShowDataSources] = useState(false);
  const [showCreateProject, setShowCreateProject] = useState(false);
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const [showSemanticSettings, setShowSemanticSettings] = useState(false);
  const [copilotCollapsed, setCopilotCollapsed] = useState(true);

  useEffect(() => {
    const connectionId = tabs.activeTab?.connectionId;
    if (!connectionId || connectionId === activeDataSource?.id) return;
    const next = datasources.find((datasource) => datasource.id === connectionId);
    if (next) setActiveDataSource(next);
  }, [activeDataSource?.id, datasources, setActiveDataSource, tabs.activeTab?.connectionId]);

  const openQueryTab = useCallback((sql = "", title?: string) => {
    tabs.openQueryTab(sql, title);
  }, [tabs]);

  const openTableTab = useCallback((tableName: string, subTab: TableSubTab = "data") => {
    tabs.openTableTab(tableName, subTab);
  }, [tabs]);

  const handleApplySqlToEditor = useCallback((sql: string) => {
    if (tabs.applySqlToActiveEditor(sql)) {
      toast("SQL 已写入当前编辑器", "success");
      return;
    }
    tabs.openQueryTab(sql.trim(), "Agent SQL");
    toast("SQL 已打开到新编辑器", "success");
  }, [tabs, toast]);

  const commandItems = useMemo<CommandItem[]>(() => [
    { id: "new-query", name: "新建 SQL 控制台", category: "Workbench", shortcut: "Ctrl+T", icon: <Terminal size={14} />, action: () => openQueryTab() },
    { id: "connections", name: "连接管理", category: "Database", icon: <Database size={14} />, action: () => setShowDataSources(true) },
    { id: "toggle-copilot", name: "显示 / 隐藏 Agent Copilot", category: "View", icon: copilotCollapsed ? <PanelRightOpen size={14} /> : <PanelRightClose size={14} />, action: () => setCopilotCollapsed((prev) => !prev) },
    { id: "api-config", name: "模型 API 配置", category: "AI", icon: <Settings size={14} />, action: () => apiConfig.setOpen(true) },
    ...schemaTables.slice(0, 40).map((table) => ({
      id: `table:${table.id}`,
      name: table.table_name,
      category: "Tables",
      icon: <Search size={14} />,
      action: () => openTableTab(table.table_name, "schema"),
    })),
  ], [apiConfig, copilotCollapsed, openQueryTab, openTableTab, schemaTables]);

  const menus = useMemo<MenuDef[]>(() => [
    {
      id: "file",
      label: "文件",
      items: [
        { label: "新建项目", action: () => setShowCreateProject(true) },
        { label: "新建 SQL 控制台", shortcut: "Ctrl+T", action: () => openQueryTab() },
        { separator: true, label: "" },
        { label: "连接管理", action: () => setShowDataSources(true) },
      ],
    },
    {
      id: "view",
      label: "视图",
      items: [
        { label: "命令面板", shortcut: "Ctrl+P", action: () => setShowCommandPalette(true) },
        { label: "显示 / 隐藏 Agent Copilot", shortcut: "Alt+A", action: () => setCopilotCollapsed((prev) => !prev) },
      ],
    },
    {
      id: "run",
      label: "运行",
      items: [
        { label: "执行当前 SQL", shortcut: "Ctrl+Enter", action: () => tabs.triggerActiveAction("execute") },
        { label: "停止执行", action: () => tabs.triggerActiveAction("stop") },
        { separator: true, label: "" },
        { label: "格式化 SQL", action: () => tabs.triggerActiveAction("format") },
        { label: "安全检查", action: () => tabs.triggerActiveAction("validate") },
        { label: "导出当前结果", action: () => tabs.triggerActiveAction("export") },
      ],
    },
    {
      id: "ai",
      label: "AI",
      items: [
        { label: "打开 Agent Copilot", action: () => setCopilotCollapsed(false) },
        { label: "模型 API 配置", action: () => apiConfig.setOpen(true) },
        { label: "Semantic Settings", disabled: !activeDataSource, action: () => setShowSemanticSettings(true) },
      ],
    },
  ], [activeDataSource, apiConfig, openQueryTab, tabs]);

  const renderTableContextBar = () => {
    if (tabs.activeTab?.type !== "table" || !tabs.activeTab.tableName) return null;
    const table = schemaTables.find((item) => item.table_name === tabs.activeTab?.tableName);
    return (
      <div className="table-context-bar">
        <div className="table-context-bar__title">{tabs.activeTab.tableName}</div>
        <div className="table-context-bar__meta">{table?.columns?.length ?? 0} columns</div>
        {table?.table_comment && <div className="table-context-bar__meta">{table.table_comment}</div>}
        <div className="table-context-bar__tabs">
          {TABLE_TABS.map((item) => {
            const active = (tabs.activeTab?.activeSubTab || "data") === item.id;
            return (
              <button key={item.id} className={active ? "is-active" : undefined} onClick={() => tabs.switchTableSubTab(tabs.activeTab!.id, item.id)}>
                {item.label}
              </button>
            );
          })}
        </div>
      </div>
    );
  };

  const renderActiveContent = () => {
    if (!tabs.activeTab) {
      return (
        <WorkbenchHome
          datasource={activeDataSource}
          tables={schemaTables}
          onOpenQuery={() => openQueryTab()}
          onOpenDataSources={() => setShowDataSources(true)}
          onOpenTable={(name) => openTableTab(name, "data")}
        />
      );
    }

    if (!activeDataSource) {
      return <WorkbenchHome datasource={null} tables={[]} onOpenQuery={() => openQueryTab()} onOpenDataSources={() => setShowDataSources(true)} onOpenTable={() => undefined} />;
    }

    if (tabs.activeTab.type === "query") {
      return (
        <ErrorBoundary title="SQL 控制台加载异常">
          <Suspense fallback={<div className="workbench-home__empty">正在加载 SQL 控制台...</div>}>
            <QueryPage
              key={tabs.activeTab.id}
              datasource={activeDataSource}
              initialDraft={tabs.activeTab.sqlDraft ? { sql: tabs.activeTab.sqlDraft, nonce: 1 } : null}
              actionTrigger={tabs.activeTab.actionTrigger}
              onStateChange={tabs.updateActiveQueryState}
            />
          </Suspense>
        </ErrorBoundary>
      );
    }

    if (tabs.activeTab.type === "table" && tabs.activeTab.tableName) {
      const subTab = tabs.activeTab.activeSubTab || "data";
      return (
        <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
          {renderTableContextBar()}
          <div style={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
            {subTab === "data" && (
              <ErrorBoundary title="数据预览加载异常">
                <Suspense fallback={<div className="workbench-home__empty">正在加载数据预览...</div>}>
                  <DataPage
                    datasource={activeDataSource}
                    selectedTableName={tabs.activeTab.tableName}
                    schemaTables={schemaTables}
                    onSelectTable={(name) => openTableTab(name, "data")}
                  />
                </Suspense>
              </ErrorBoundary>
            )}

            {subTab === "schema" && (
              <ErrorBoundary title="表结构加载异常">
                <Suspense fallback={<div className="workbench-home__empty">正在加载表结构...</div>}>
                  <SchemaPage
                    datasource={activeDataSource}
                    initialViewTab="fields"
                    selectedTableName={tabs.activeTab.tableName}
                    onOpenSql={(sql, title) => openQueryTab(sql, title)}
                  />
                </Suspense>
              </ErrorBoundary>
            )}

            {subTab === "er" && (
              <ErrorBoundary title="ER 图加载异常">
                <Suspense fallback={<div className="workbench-home__empty">正在加载 ER 图...</div>}>
                  <SchemaPage
                    datasource={activeDataSource}
                    initialViewTab="er"
                    selectedTableName={tabs.activeTab.tableName}
                    onOpenSql={(sql, title) => openQueryTab(sql, title)}
                  />
                </Suspense>
              </ErrorBoundary>
            )}
          </div>
        </div>
      );
    }

    return <WorkbenchHome datasource={activeDataSource} tables={schemaTables} onOpenQuery={() => openQueryTab()} onOpenDataSources={() => setShowDataSources(true)} onOpenTable={(name) => openTableTab(name, "data")} />;
  };

  return (
    <>
      <LayoutRegion
        top={<MenuBar menus={menus} />}
        left={(
          <ObjectExplorer
            datasources={datasources}
            activeDataSource={activeDataSource}
            schemaTables={schemaTables}
            loadingTree={loadingTree}
            loadingObjects={loadingObjects}
            onSelectDataSource={setActiveDataSource}
            onOpenTable={openTableTab}
            onRefreshTables={(datasourceId) => void onRefreshSchemaTables(datasourceId)}
            onOpenDataSources={() => setShowDataSources(true)}
            onOpenSemanticSettings={() => setShowSemanticSettings(true)}
          />
        )}
        center={(
          <>
            <WorkbenchTabs
              tabs={tabs.tabs}
              activeTabId={tabs.activeTabId}
              onSelect={tabs.setActiveTabId}
              onClose={tabs.closeTab}
              onNewQuery={() => openQueryTab()}
              onCloseOtherTabs={tabs.closeOtherTabs}
              onCloseTabsToRight={tabs.closeTabsToRight}
            />
            <div className="workbench-main">{renderActiveContent()}</div>
          </>
        )}
        right={(
          <AgentCopilotPanel
            datasource={activeDataSource}
            activeTableName={tabs.activeTab?.tableName}
            activeSql={tabs.activeTab?.type === "query" ? tabs.activeTab.sqlDraft || "" : ""}
            lastQueryResult={tabs.activeTab?.type === "query" ? tabs.activeTab.lastQueryResultPreview || null : null}
            lastError={tabs.activeTab?.type === "query" ? tabs.activeTab.lastError || null : null}
            isCollapsed={copilotCollapsed}
            onCollapse={() => setCopilotCollapsed((prev) => !prev)}
            onInsertSql={handleApplySqlToEditor}
            onRunSql={(sql) => openQueryTab(sql, "Agent SQL")}
            onOpenQueryTab={openQueryTab}
            onOpenApiConfig={() => apiConfig.setOpen(true)}
            apiConfigured={apiConfig.isConfigured}
          />
        )}
        bottom={(
          <WorkbenchStatusBar
            project={activeProject}
            datasource={activeDataSource}
            activeTab={tabs.activeTab}
            onOpenProjects={() => setShowCreateProject(true)}
            onOpenDataSources={() => setShowDataSources(true)}
            onStopQuery={() => tabs.triggerActiveAction("stop")}
          />
        )}
      />

      <CommandPalette open={showCommandPalette} onClose={() => setShowCommandPalette(false)} commands={commandItems} />

      <PromptDialog
        open={showCreateProject}
        title="新建项目"
        placeholder="例如：本地数仓 / 客户增长分析"
        confirmLabel="创建"
        onCancel={() => setShowCreateProject(false)}
        onConfirm={(name) => {
          void onCreateProject(name).finally(() => setShowCreateProject(false));
        }}
      />

      {showDataSources && (
        <div className="workbench-modal">
          <div className="workbench-modal__panel">
            <div className="workbench-modal__header">
              <span>连接管理器</span>
              <button className="icon-button" onClick={() => setShowDataSources(false)}>关闭</button>
            </div>
            <div className="workbench-modal__body">
              <DataSourcesPage
                activeDataSource={activeDataSource}
                activeProject={activeProject}
                onRefreshDatasources={onRefreshDatasources}
                onSelectDataSource={(datasource) => {
                  setActiveDataSource(datasource);
                  setShowDataSources(false);
                }}
              />
            </div>
          </div>
        </div>
      )}

      {showSemanticSettings && activeDataSource && activeProject && (
        <SemanticSettingsPanel datasource={activeDataSource} projectId={activeProject.id} onClose={() => setShowSemanticSettings(false)} />
      )}

      <ApiConfigDialog
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
