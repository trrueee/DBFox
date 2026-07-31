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
import { installClientErrorLogging } from "./lib/diagnostics/clientLog";
import { useDatasourceState } from "./features/datasource/useDatasourceState";
import { useWorkspaceStore } from "./stores/workspaceStore";
import { useConversationStore } from "./stores/conversationStore";
import { Search } from "lucide-react";

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
const SettingsSidebar = lazy(() =>
  import("./features/settings/SettingsSidebar").then((module) => ({
    default: module.SettingsSidebar,
  })),
);
const WorkspaceRouter = lazy(() =>
  import("./features/appShell/WorkspaceRouter").then((module) => ({
    default: module.WorkspaceRouter,
  })),
);
const ResizableWorkspaceLayout = lazy(() =>
  import("./features/appShell/ResizableWorkspaceLayout").then((module) => ({
    default: module.ResizableWorkspaceLayout,
  })),
);
const WorkspaceTabs = lazy(() =>
  import("./features/workspace/WorkspaceTabs").then((module) => ({
    default: module.WorkspaceTabs,
  })),
);
const TitleBar = lazy(() => import("./components/TitleBar"));

export default function App() {
  const [treeSearch, setTreeSearch] = useState("");
  const [rightDrawerOpen, setRightDrawerOpen] = useState(false);
  const [rightDrawerType, setRightDrawerType] = useState<"ai-suggest" | "props">("props");
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({ visible: false, x: 0, y: 0, type: "database", targetNode: "" });

  const { toast } = useToast();

  // ── Store initialization (mount once) ──
  useEffect(() => {
    installClientErrorLogging();
    void useConversationStore.getState().initConversations();
  }, []);

  // ── Store selectors (minimal — children read from stores directly) ──
  const activeTab = useWorkspaceStore((s) => s.tabs.find((t) => t.id === s.activeTabId) || s.tabs[0]);
  const { tables, refreshSchema, activeDatasource } = useDatasourceState();

  const openSqlConsole = useWorkspaceStore((s) => s.openSqlConsole);
  const openNewConnectionTab = useWorkspaceStore((s) => s.openNewConnectionTab);
  const openTableTab = useWorkspaceStore((s) => s.openTableTab);
  const openMultiTableWorkspace = useWorkspaceStore((s) => s.openMultiTableWorkspace);
  const selectedTables = useWorkspaceStore((s) => s.selectedTables);
  const setSelectedTables = useWorkspaceStore((s) => s.setSelectedTables);
  const settingsOpen = useWorkspaceStore((s) => s.settingsOpen);
  const settingsSection = useWorkspaceStore((s) => s.settingsSection);
  const openSettings = useWorkspaceStore((s) => s.openSettings);
  const closeSettings = useWorkspaceStore((s) => s.closeSettings);
  const setSettingsSection = useWorkspaceStore((s) => s.setSettingsSection);

  const openTableTabForActiveDatasource = useCallback(
    (tableName: string, initialSubtab?: string) => {
      openTableTab(
        tableName,
        initialSubtab,
        activeDatasource ? { id: activeDatasource.id, dbType: activeDatasource.db_type ?? null } : undefined,
      );
    },
    [activeDatasource, openTableTab],
  );

  // Layout UI states
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const effectiveSidebarCollapsed = sidebarCollapsed && !settingsOpen;
  const toggleSidebarCollapse = useCallback(() => setSidebarCollapsed((value) => !value), []);
  const handleOpenSettings = useCallback(() => {
    setSidebarCollapsed(false);
    openSettings("model");
  }, [openSettings]);

  useEffect(() => {
    const handleDocumentClick = () => setContextMenu((prev) => ({ ...prev, visible: false }));
    window.addEventListener("click", handleDocumentClick);
    return () => window.removeEventListener("click", handleDocumentClick);
  }, []);

  const handleTableClick = (tableName: string, event: MouseEvent) => {
    if (event.ctrlKey || event.metaKey) {
      setSelectedTables((prev) => (prev.includes(tableName) ? prev.filter((table) => table !== tableName) : [...prev, tableName]));
      return;
    }
    openTableTabForActiveDatasource(tableName);
  };

  const handleNodeContextMenu = (event: MouseEvent, type: "database" | "schema" | "table", nodeName: string) => {
    event.preventDefault();
    event.stopPropagation();
    if (type === "table" && selectedTables.length > 1 && selectedTables.includes(nodeName)) {
      setContextMenu({ visible: true, x: event.clientX, y: event.clientY, type: "multi-table", targetNode: nodeName });
      return;
    }
    if (type === "table") setSelectedTables([nodeName]);
    setContextMenu({ visible: true, x: event.clientX, y: event.clientY, type, targetNode: nodeName });
  };

  // Keyboard Event Handlers
  useEffect(() => {
    const handleGlobalKeyDown = (event: KeyboardEvent) => {
      const mod = event.ctrlKey || event.metaKey;
      if (mod && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setShowCommandPalette(true);
      }
      if (mod && event.key.toLowerCase() === "n") {
        event.preventDefault();
        openSqlConsole();
      }
      if (mod && event.key.toLowerCase() === "w") {
        const ws = useWorkspaceStore.getState();
        if (ws.settingsOpen) {
          event.preventDefault();
          ws.closeSettings();
          return;
        }
        const activeId = ws.activeTabId;
        if (activeId) {
          event.preventDefault();
          ws.closeTab(activeId);
        }
      }
    };
    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, [openSqlConsole]);

  const toggleRightDrawer = (type: "ai-suggest" | "props") => {
    if (rightDrawerOpen && rightDrawerType === type) setRightDrawerOpen(false);
    else {
      setRightDrawerOpen(true);
      setRightDrawerType(type);
    }
  };

  return (
    <div className="app-shell">
      <div
        className="app-shell-inner"
        ref={useCallback((el: HTMLDivElement | null) => { setDialogContainer(el); setToastRoot(el); }, [])}
      >
        <Suspense fallback={null}>
          <TitleBar />
        </Suspense>
        {/* Window body: sidebar + main surface + right drawer */}
        <main className="app-body">
          <Suspense fallback={null}>
            <ResizableWorkspaceLayout
              key={effectiveSidebarCollapsed ? "collapsed" : settingsOpen ? "settings" : "expanded"}
              sidebarCollapsed={effectiveSidebarCollapsed}
              settingsOpen={settingsOpen}
              sidebar={settingsOpen ? (
                <Suspense fallback={null}>
                  <SettingsSidebar
                    section={settingsSection}
                    onSectionChange={setSettingsSection}
                    onClose={closeSettings}
                  />
                </Suspense>
              ) : (
                <Suspense fallback={null}>
                  <DataSourceTree
                    treeSearch={treeSearch}
                    collapsed={effectiveSidebarCollapsed}
                    onToggleCollapse={toggleSidebarCollapse}
                    onTreeSearchChange={setTreeSearch}
                    onTableClick={handleTableClick}
                    onTableDoubleClick={openTableTabForActiveDatasource}
                    onNodeContextMenu={handleNodeContextMenu}
                    onRefresh={refreshSchema}
                    onNewConnection={openNewConnectionTab}
                    onOpenSqlConsole={openSqlConsole}
                    onOpenConnectionManager={useWorkspaceStore.getState().openConnectionManagerTab}
                    onOpenSettings={handleOpenSettings}
                  />
                </Suspense>
              )}
              workspace={
                <section className={`app-main${settingsOpen ? " app-main--settings" : ""}`}>
                {settingsOpen ? (
                  <Suspense fallback={null}>
                    <div className="app-main-scroll">
                      <SettingsPage section={settingsSection} showToast={toast} />
                    </div>
                  </Suspense>
                ) : (
                  <>
                    {/* Top Workspace Tab Bar */}
                    <div className="app-tabbar">
                      <Suspense fallback={null}>
                        <WorkspaceTabs onOpenSqlConsole={openSqlConsole} />
                      </Suspense>

                      <div className="app-tabbar-actions">
                        <button
                          className="app-cmd-btn"
                          onClick={() => setShowCommandPalette(true)}
                          title="全局搜索 (Ctrl K)"
                        >
                          <Search size={13} aria-hidden="true" />
                          <span>搜索</span>
                          <kbd>Ctrl K</kbd>
                        </button>
                      </div>
                    </div>

                    <div className="app-main-scroll">
                      <Suspense fallback={null}>
                        <WorkspaceRouter activeTab={activeTab} showToast={toast} />
                      </Suspense>
                    </div>
                  </>
                )}
                </section>
              }
            />
          </Suspense>

          {!settingsOpen && rightDrawerOpen && (
            <Suspense fallback={null}>
              <ContextDrawer
                open
                type={rightDrawerType}
                activeTab={activeTab}
                onClose={() => setRightDrawerOpen(false)}
                onGenerateIndexSql={() => openSqlConsole("ALTER TABLE comment_infos ADD INDEX idx_user_id (user_id);")}
              />
            </Suspense>
          )}
        </main>

        {showCommandPalette && (
          <Suspense fallback={null}>
            <AppCommandPalette
              onClose={() => setShowCommandPalette(false)}
              tables={tables}
              openSqlConsole={openSqlConsole}
              openSmartQueryTab={useWorkspaceStore.getState().openSmartQueryTab}
              openConversationHistoryTab={useWorkspaceStore.getState().openConversationHistoryTab}
              openConversationResult={useWorkspaceStore.getState().openConversationResult}
              openSettings={useWorkspaceStore.getState().openSettings}
              openConnectionManagerTab={useWorkspaceStore.getState().openConnectionManagerTab}
              openNewConnectionTab={openNewConnectionTab}
              openTableTab={openTableTabForActiveDatasource}
            />
          </Suspense>
        )}

        {contextMenu.visible && (
          <Suspense fallback={null}>
            <DataSourceContextMenu
              contextMenu={contextMenu}
              onOpenSqlConsole={openSqlConsole}
              onOpenTable={(tableName, subTab) => openTableTabForActiveDatasource(tableName, subTab)}
              onOpenMultiTableWorkspace={openMultiTableWorkspace}
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
