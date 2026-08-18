import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useState,
} from "react";
import "./App.css";
import { setDialogContainer } from "./components/ui/dialogContainer";
import { setToastRoot, useToast } from "./components/toastState";
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
import { ProjectResourceSidebar } from "./features/resources/ProjectResourceSidebar";
import { productResourceConnectors, ResourceConnectorDialog } from "./features/resources/resourceConnectorComposition";
import { useConnectionDialogStore } from "./features/resources/connectionDialogStore";

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
  const [showCommandPalette, setShowCommandPalette] = useState(false);

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
  const openDockArtifacts = useArtifactDockStore((s) => s.openArtifacts);
  const showSmartQueryHome = useWorkspaceStore((s) => s.showSmartQueryHome);
  const openConversationCenter = useWorkspaceStore((s) => s.openConversationCenter);
  const setActiveProject = useWorkspaceStore((s) => s.setActiveProject);
  const settingsOpen = useWorkspaceStore((s) => s.settingsOpen);
  const settingsSection = useWorkspaceStore((s) => s.settingsSection);
  const openSettings = useWorkspaceStore((s) => s.openSettings);
  const closeSettings = useWorkspaceStore((s) => s.closeSettings);
  const setSettingsSection = useWorkspaceStore((s) => s.setSettingsSection);

  const openDockConsoleForActiveDatasource = useCallback(
    (initialSql?: string) => {
      if (!activeDatasource) return;
      openDockConsole(activeDatasource.id, activeDatasource.db_type, initialSql);
    },
    [activeDatasource, openDockConsole],
  );

  const openConversationFromPalette = useCallback(
    (conversationId: string) => {
      void useConversationStore.getState()
        .openConversation(conversationId)
        .then(() => openConversationCenter(conversationId));
    },
    [openConversationCenter],
  );

  // Resource connector composition
  const connectors = productResourceConnectors(toast);

  // Layout UI states
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const toggleSidebarCollapse = useCallback(() => setSidebarCollapsed((value) => !value), []);
  const handleOpenSettings = useCallback(() => {
    setSidebarCollapsed(false);
    openSettings("appearance");
  }, [openSettings]);

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
                <ProjectResourceSidebar
                  collapsed={sidebarCollapsed && !settingsOpen}
                  onToggleCollapse={toggleSidebarCollapse}
                  onNewProject={() => useWorkspaceStore.getState().openProjectCreate()}
                  onOpenSettings={handleOpenSettings}
                  connectors={connectors}
                />
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
                        activeConversationId={activeConversationId}
                        showToast={toast}
                      />
                    </Suspense>
                  </div>
                )
              }
            />
          </Suspense>

          <ResourceConnectorDialog />

          {showCommandPalette && (
            <Suspense fallback={null}>
              <AppCommandPalette
                tables={tables}
                openSqlConsole={openDockConsoleForActiveDatasource}
                showSmartQueryHome={showSmartQueryHome}
                openConversation={openConversationFromPalette}
                openSettings={openSettings}
                openConnectionDialog={() => useConnectionDialogStore.getState().openCreate()}
                openTable={(tableName) => {
                  const openDockTable = useTableWorkspaceStore.getState().openTable;
                  openDockTable(
                    tableName,
                    undefined,
                    activeDatasource ? { id: activeDatasource.id, dbType: activeDatasource.db_type ?? null } : undefined,
                  );
                }}
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
                type="props"
                activeTab={activeDockTab}
                onClose={() => setRightDrawerOpen(false)}
              />
            </Suspense>
          )}
        </main>
      </div>
    </div>
  );
}
