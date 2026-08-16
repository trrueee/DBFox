import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useState,
  type MouseEvent,
} from "react";
import "./App.css";
import { setDialogContainer } from "./components/ui/dialogContainer";
import { setToastRoot, useToast } from "./components/toastState";
import type { ContextMenuState } from "./types/workspace";
import { installClientErrorLogging, recordClientLog } from "./lib/diagnostics/clientLog";
import { useDatasourceState } from "./features/datasource/useDatasourceState";
import { useWorkspaceStore } from "./stores/workspaceStore";
import { useSqlConsoleStore } from "./stores/sqlConsoleStore";
import { useTableWorkspaceStore } from "./stores/tableWorkspaceStore";
import { useArtifactDockStore } from "./stores/artifactDockStore";
import { useConversationStore } from "./stores/conversationStore";
import { DesktopLifecycleMonitor } from "./features/appShell/DesktopLifecycleMonitor";
import { LoadingState } from "./components/ui";
import { ConversationCenter } from "./features/appShell/ConversationCenter";
import { ResizableWorkspaceLayout } from "./features/appShell/ResizableWorkspaceLayout";

const AppCommandPalette = lazy(() =>
  import("./features/appShell/AppCommandPalette").then((module) => ({
    default: module.AppCommandPalette,
  })),
);
const ContextDrawer = lazy(() =>
  import("./features/assistant/ContextDrawer").then((module) => ({
    default: module.ContextDrawer,
  })),
);
const DataSourceContextMenu = lazy(() =>
  import("./features/datasource/DataSourceContextMenu").then((module) => ({
    default: module.DataSourceContextMenu,
  })),
);
const DataSourceTree = lazy(() =>
  import("./features/datasource/DataSourceTree").then((module) => ({
    default: module.DataSourceTree,
  })),
);
const SettingsPage = lazy(() =>
  import("./features/settings/SettingsPage").then((module) => ({
    default: module.SettingsPage,
  })),
);
const ProjectCreateForm = lazy(() =>
  import("./features/projects/ProjectCreateForm").then((module) => ({
    default: module.ProjectCreateForm,
  })),
);
const ConnectionDialog = lazy(() =>
  import("./features/datasource/ConnectionDialog").then((module) => ({
    default: module.ConnectionDialog,
  })),
);
const WorkspaceDock = lazy(() =>
  import("./features/appShell/WorkspaceDock").then((module) => ({
    default: module.WorkspaceDock,
  })),
);
const SettingsSidebar = lazy(() =>
  import("./features/settings/SettingsSidebar").then((module) => ({
    default: module.SettingsSidebar,
  })),
);
const TitleBar = lazy(() => import("./components/TitleBar"));

function TitleBarFallback() {
  return <div className="app-titlebar-fallback" aria-hidden="true" />;
}

function WorkspaceDockFallback() {
  return (
    <div className="app-dock-fallback" role="status" aria-label="正在载入工作台 Dock">
      <LoadingState label="正在载入工作台" />
    </div>
  );
}

function SidebarFallback() {
  return (
    <div className="app-sidebar-fallback" role="status" aria-label="正在载入数据源">
      <span className="app-skeleton app-skeleton--heading" />
      <span className="app-skeleton app-skeleton--control" />
      <span className="app-skeleton app-skeleton--control" />
      <span className="app-skeleton app-skeleton--row" />
      <span className="app-skeleton app-skeleton--row" />
      <span className="app-skeleton app-skeleton--row-short" />
    </div>
  );
}

function AppLayoutFallback() {
  return (
    <div className="app-layout-fallback">
      <SidebarFallback />
      <div className="app-layout-fallback__workspace">
        <LoadingState label="正在载入工作区" />
      </div>
    </div>
  );
}


export default function App() {
  const [rightDrawerOpen, setRightDrawerOpen] = useState(false);
  const [rightDrawerType, setRightDrawerType] = useState<"ai-suggest" | "props">("props");
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({ visible: false, x: 0, y: 0, type: "database", targetNode: "" });
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const [connectionDialog, setConnectionDialog] = useState<{ open: boolean; createMode: boolean }>({
    open: false,
    createMode: true,
  });

  const { toast } = useToast();

  // ── Store initialization (mount once) ──
  useEffect(() => {
    installClientErrorLogging();
    void useConversationStore.getState().initConversations().catch((error) => {
      recordClientLog("error", "初始化对话列表失败", error);
    });
  }, []);

  // ── Store selectors ──
  const { activeDatasource, activeDatasourceId, tables } = useDatasourceState();
  const activeConversationId = useConversationStore((s) => s.activeConversationId);
  const centerMode = useWorkspaceStore((s) => s.centerMode);
  const dock = useWorkspaceStore((s) => s.dock);
  const dockTabs = useWorkspaceStore((s) => s.dockTabs);
  const setDockOpen = useWorkspaceStore((s) => s.setDockOpen);
  const setDockActiveTab = useWorkspaceStore((s) => s.setDockActiveTab);
  const openDockConsole = useSqlConsoleStore((s) => s.openConsole);
  const openDockTable = useTableWorkspaceStore((s) => s.openTable);
  const openDockArtifacts = useArtifactDockStore((s) => s.openArtifacts);
  const openDockMultiTable = useTableWorkspaceStore((s) => s.openMultiTable);
  const showSmartQueryHome = useWorkspaceStore((s) => s.showSmartQueryHome);
  const openConversationCenter = useWorkspaceStore((s) => s.openConversationCenter);
  const setActiveProject = useWorkspaceStore((s) => s.setActiveProject);
  const settingsOpen = useWorkspaceStore((s) => s.settingsOpen);
  const settingsSection = useWorkspaceStore((s) => s.settingsSection);
  const openSettings = useWorkspaceStore((s) => s.openSettings);
  const closeSettings = useWorkspaceStore((s) => s.closeSettings);
  const setSettingsSection = useWorkspaceStore((s) => s.setSettingsSection);

  const openDockTableForActiveDatasource = useCallback(
    (tableName: string, initialSubtab?: string) => {
      openDockTable(
        tableName,
        initialSubtab,
        activeDatasource ? { id: activeDatasource.id, dbType: activeDatasource.db_type ?? null } : undefined,
      );
    },
    [activeDatasource, openDockTable],
  );

  const openDockConsoleForActiveDatasource = useCallback(
    (initialSql?: string) => {
      if (!activeDatasource) return;
      openDockConsole(activeDatasource.id, activeDatasource.db_type, initialSql);
    },
    [activeDatasource, openDockConsole],
  );

  const openConnectionDialog = useCallback((mode: "detail" | "create" = "create") => {
    setConnectionDialog({ open: true, createMode: mode === "create" });
  }, []);

  const openConversationFromPalette = useCallback(
    (conversationId: string) => {
      void useConversationStore.getState()
        .openConversation(conversationId)
        .then(() => openConversationCenter(conversationId));
    },
    [openConversationCenter],
  );

  // Layout UI states
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const toggleSidebarCollapse = useCallback(() => setSidebarCollapsed((value) => !value), []);
  const handleOpenSettings = useCallback(() => {
    setSidebarCollapsed(false);
    openSettings("appearance");
  }, [openSettings]);

  useEffect(() => {
    const handleDocumentClick = () => setContextMenu((prev) => ({ ...prev, visible: false }));
    window.addEventListener("click", handleDocumentClick);
    return () => window.removeEventListener("click", handleDocumentClick);
  }, []);

  const handleTableClick = (tableName: string, event: MouseEvent) => {
    if (event.ctrlKey || event.metaKey) {
      useTableWorkspaceStore.getState().setSelectedTables((prev) => (
        prev.includes(tableName) ? prev.filter((table) => table !== tableName) : [...prev, tableName]
      ));
      return;
    }
    openDockTableForActiveDatasource(tableName);
  };

  const handleNodeContextMenu = (event: MouseEvent, type: "database" | "schema" | "table", nodeName: string) => {
    event.preventDefault();
    event.stopPropagation();
    const selectedTables = useTableWorkspaceStore.getState().selectedTables;
    const setSelectedTables = useTableWorkspaceStore.getState().setSelectedTables;
    if (type === "table" && selectedTables.length > 1 && selectedTables.includes(nodeName)) {
      setContextMenu({ visible: true, x: event.clientX, y: event.clientY, type: "multi-table", targetNode: nodeName });
      return;
    }
    if (type === "table") setSelectedTables([nodeName]);
    setContextMenu({ visible: true, x: event.clientX, y: event.clientY, type, targetNode: nodeName });
  };

  // ── V3 快捷键：焦点与 Dock，不再承担全局搜索 ──
  useEffect(() => {
    const handleGlobalKeyDown = (event: KeyboardEvent) => {
      const mod = event.ctrlKey || event.metaKey;
      if (!mod) return;

      if (event.key.toLowerCase() === "k") {
        event.preventDefault();
        setShowCommandPalette((value) => !value);
      }
      if (event.key === "1") {
        event.preventDefault();
        if (activeConversationId) openConversationCenter(activeConversationId);
        else showSmartQueryHome();
      }
      if (event.key === "2") {
        event.preventDefault();
        openDockConsoleForActiveDatasource();
      }
      if (event.key === "3") {
        event.preventDefault();
        const tableTab = dockTabs.find((tab) => tab.kind === "table" && tab.datasourceId === activeDatasourceId);
        if (tableTab) setDockActiveTab(tableTab.id);
      }
      if (event.key === "4" && activeConversationId) {
        event.preventDefault();
        openDockArtifacts(activeConversationId);
      }
      if (event.key === "\\") {
        event.preventDefault();
        setDockOpen(!dock.open);
      }
    };
    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, [
    activeConversationId,
    activeDatasourceId,
    dock.open,
    dockTabs,
    openConversationCenter,
    openDockArtifacts,
    openDockConsoleForActiveDatasource,
    setDockActiveTab,
    setDockOpen,
    showSmartQueryHome,
  ]);

  const toggleRightDrawer = (type: "ai-suggest" | "props") => {
    if (rightDrawerOpen && rightDrawerType === type) setRightDrawerOpen(false);
    else {
      setRightDrawerOpen(true);
      setRightDrawerType(type);
    }
  };

  const activeDockTab = dockTabs.find((tab) => tab.id === dock.activeTabId);

  return (
    <div className="app-shell">
      <div
        className="app-shell-inner"
        ref={useCallback((el: HTMLDivElement | null) => { setDialogContainer(el); setToastRoot(el); }, [])}
      >
        <DesktopLifecycleMonitor showToast={toast} />
        <Suspense fallback={<TitleBarFallback />}>
          <TitleBar />
        </Suspense>
        {/* Window body: left tree | center conversation | right dock */}
        <main className="app-body">
          <Suspense fallback={<AppLayoutFallback />}>
            <ResizableWorkspaceLayout
              key={settingsOpen ? "settings" : "workspace"}
              sidebarCollapsed={sidebarCollapsed && !settingsOpen}
              settingsOpen={settingsOpen}
              sidebar={settingsOpen ? (
                <Suspense fallback={<SidebarFallback />}>
                  <SettingsSidebar
                    section={settingsSection}
                    onSectionChange={setSettingsSection}
                    onClose={closeSettings}
                  />
                </Suspense>
              ) : (
                <Suspense fallback={<SidebarFallback />}>
                  <DataSourceTree
                    collapsed={sidebarCollapsed && !settingsOpen}
                    onToggleCollapse={toggleSidebarCollapse}
                    onTableClick={handleTableClick}
                    onTableDoubleClick={(tableName) => openDockTableForActiveDatasource(tableName)}
                    onNodeContextMenu={handleNodeContextMenu}
                    onNewConnection={() => openConnectionDialog("create")}
                    onNewProject={() => useWorkspaceStore.getState().openProjectCreate()}
                    onOpenSettings={handleOpenSettings}
                  />
                </Suspense>
              )}
              workspace={
                settingsOpen ? (
                  <section className="app-main app-main--settings">
                    <Suspense fallback={<LoadingState label="正在载入设置" />}>
                      <div className="app-main-scroll">
                        <SettingsPage section={settingsSection} showToast={toast} />
                      </div>
                    </Suspense>
                  </section>
                ) : centerMode === "project-create" ? (
                  <div className="app-v3-stage">
                    <section className="app-main app-main--conversation app-main--project-create">
                      <div className="app-main-scroll">
                        <Suspense fallback={<LoadingState label="正在载入新建项目" />}>
                          <ProjectCreateForm
                            onCreated={(projectId) => {
                              setActiveProject(projectId);
                              showSmartQueryHome();
                            }}
                            onCancel={showSmartQueryHome}
                          />
                        </Suspense>
                      </div>
                    </section>
                    <Suspense fallback={<WorkspaceDockFallback />}>
                      <WorkspaceDock
                        activeDatasourceId={activeDatasourceId}
                        activeConversationId={activeConversationId}
                        showToast={toast}
                      />
                    </Suspense>
                  </div>
                ) : (
                  <div className="app-v3-stage">
                    <section className="app-main app-main--conversation">
                      <div className="app-main-scroll">
                        <ConversationCenter
                          showToast={toast}
                          onNewProject={() => useWorkspaceStore.getState().openProjectCreate()}
                        />
                      </div>
                    </section>
                    <Suspense fallback={<WorkspaceDockFallback />}>
                      <WorkspaceDock
                        activeDatasourceId={activeDatasourceId}
                        activeConversationId={activeConversationId}
                        showToast={toast}
                      />
                    </Suspense>
                  </div>
                )
              }
            />
          </Suspense>

          {connectionDialog.open && (
            <Suspense fallback={null}>
              <ConnectionDialog
                open
                createMode={connectionDialog.createMode}
                onOpenChange={(open) => setConnectionDialog((prev) => ({ ...prev, open }))}
              />
            </Suspense>
          )}

          {showCommandPalette && (
            <Suspense fallback={null}>
              <AppCommandPalette
                tables={tables}
                openSqlConsole={openDockConsoleForActiveDatasource}
                showSmartQueryHome={showSmartQueryHome}
                openConversation={openConversationFromPalette}
                openSettings={openSettings}
                openConnectionDialog={openConnectionDialog}
                openTable={openDockTableForActiveDatasource}
                activeDatasource={
                  activeDatasource
                    ? { id: activeDatasource.id, dbType: activeDatasource.db_type ?? null }
                    : undefined
                }
                onClose={() => setShowCommandPalette(false)}
              />
            </Suspense>
          )}

          {!settingsOpen && rightDrawerOpen && (
            <Suspense fallback={null}>
              <ContextDrawer
                open
                type={rightDrawerType}
                activeTab={activeDockTab}
                onClose={() => setRightDrawerOpen(false)}
              />
            </Suspense>
          )}
        </main>

        {contextMenu.visible && (
          <Suspense fallback={null}>
            <DataSourceContextMenu
              contextMenu={contextMenu}
              onOpenSqlConsole={openDockConsoleForActiveDatasource}
              onOpenTable={(tableName, subTab) => openDockTableForActiveDatasource(tableName, subTab)}
              onOpenMultiTableWorkspace={openDockMultiTable}
              onClose={() => setContextMenu((prev) => ({ ...prev, visible: false }))}
              onToast={toast}
              onOpenProps={() => toggleRightDrawer("props")}
            />
          </Suspense>
        )}
      </div>
    </div>
  );
}
