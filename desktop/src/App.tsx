import { useEffect, useState, useCallback, type MouseEvent } from "react";
import "./App.css";
import { setDialogContainer } from "./components/ui/dialog";
import { setToastRoot, useToast } from "./components/Toast";
import { ContextDrawer } from "./features/assistant/ContextDrawer";
import { DataSourceContextMenu } from "./features/datasource/DataSourceContextMenu";
import { DataSourceTree } from "./features/datasource/DataSourceTree";
import { WorkspaceTabs } from "./features/workspace/WorkspaceTabs";
import { type ContextMenuState } from "./mock/dbfoxMock";
import { CommandPalette } from "./components/CommandPalette";
import TitleBar from "./components/TitleBar";
import { useSidebarLayout } from "./features/appShell/useSidebarLayout";
import { useAppCommands } from "./features/appShell/useAppCommands";
import { WorkspaceRouter } from "./features/appShell/WorkspaceRouter";
import { useDatasourceStore } from "./stores/datasourceStore";
import { useWorkspaceStore } from "./stores/workspaceStore";
import { useAgentStore } from "./stores/agentStore";

export default function App() {
  const [treeSearch, setTreeSearch] = useState("");
  const [askInputValue, setAskInputValue] = useState(“”);
  const [rightDrawerOpen, setRightDrawerOpen] = useState(false);
  const [rightDrawerType, setRightDrawerType] = useState<"ai-suggest" | "props">("props");
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({ visible: false, x: 0, y: 0, type: "database", targetNode: "" });

  const { toast } = useToast();

  // ── Store initialization (mount once) ──
  useEffect(() => {
    useDatasourceStore.getState().loadDatasources();
    useWorkspaceStore.getState().initConversations();
  }, []);

  // ── Store selectors (minimal — children read from stores directly) ──
  const activeTab = useWorkspaceStore((s) => s.tabs.find((t) => t.id === s.activeTabId) || s.tabs[0]);
  const closeTab = useWorkspaceStore((s) => s.closeTab);
  const setTabs = useWorkspaceStore((s) => s.setTabs);

  const tables = useDatasourceStore((s) => s.tables);
  const tableColumns = useDatasourceStore((s) => s.tableColumns);
  const datasources = useDatasourceStore((s) => s.datasources);
  const activeDatasourceId = useDatasourceStore((s) => s.activeDatasourceId);
  const loadingSchema = useDatasourceStore((s) => s.loadingSchema);
  const schemaError = useDatasourceStore((s) => s.schemaError);
  const refreshSchema = useDatasourceStore((s) => s.refreshSchema);

  const openSqlConsole = useWorkspaceStore((s) => s.openSqlConsole);
  const openNewConnectionTab = useWorkspaceStore((s) => s.openNewConnectionTab);
  const openTableTab = useWorkspaceStore((s) => s.openTableTab);
  const openMultiTableWorkspace = useWorkspaceStore((s) => s.openMultiTableWorkspace);
  const selectedTables = useWorkspaceStore((s) => s.selectedTables);
  const setSelectedTables = useWorkspaceStore((s) => s.setSelectedTables);
  const contextTables = useWorkspaceStore((s) => s.contextTables);
  const setContextTables = useWorkspaceStore((s) => {
    const add = s.addContextTable;
    const clear = s.clearContextTable;
    return (tables: string[]) => {
      clear();
      tables.forEach((t) => add(t));
    };
  });
  const addContextTable = useWorkspaceStore((s) => s.addContextTable);
  const removeContextTable = useWorkspaceStore((s) => s.removeContextTable);
  const clearContextTable = useWorkspaceStore((s) => s.clearContextTables);
  const deleteConversationById = useWorkspaceStore((s) => s.deleteConversationById);

  const runAgentForTab = useAgentStore((s) => s.runAgentForTab);
  const handleApprovalDecision = useAgentStore((s) => s.handleApprovalDecision);
  const sendFollowUp = useAgentStore((s) => s.sendFollowUp);
  const cancelAgentRun = useAgentStore((s) => s.cancelAgentRun);
  const regenerateAgentRun = useAgentStore((s) => s.regenerateAgentRun);

  // Layout UI states
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const { collapsed: sidebarCollapsed, width: sidebarWidth, handleResizeStart, toggleCollapse: toggleSidebarCollapse } = useSidebarLayout();

  useEffect(() => {
    const handleDocumentClick = () => setContextMenu((prev) => ({ ...prev, visible: false }));
    window.addEventListener("click", handleDocumentClick);
    return () => window.removeEventListener("click", handleDocumentClick);
  }, []);

  const openQueryResultTab = (queryText: string) => {
    const text = queryText.trim();
    if (!text) return;
    const tabId = useWorkspaceStore.getState().openQueryResultTab(text);
    setAskInputValue("");
    if (tabId) void runAgentForTab(tabId, text);
  };

  const handleTableClick = (tableName: string, event: MouseEvent) => {
    if (event.ctrlKey || event.metaKey) {
      setSelectedTables((prev) => (prev.includes(tableName) ? prev.filter((table) => table !== tableName) : [...prev, tableName]));
      return;
    }
    openTableTab(tableName);
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

  const { commandItems } = useAppCommands({
    tables,
    tableColumns,
    openSqlConsole,
    openLlmConfigTab: useWorkspaceStore.getState().openLlmConfigTab,
    openConnectionManagerTab: useWorkspaceStore.getState().openConnectionManagerTab,
    openNewConnectionTab,
    openAgentEvalTab: useWorkspaceStore.getState().openAgentEvalTab,
    openTableTab,
    setTabs,
    setActiveTabId: useWorkspaceStore.getState().setActiveTabId,
  });

  return (
    <div className="app-shell">
      <div
        className="app-shell-inner"
        ref={useCallback((el: HTMLDivElement | null) => { setDialogContainer(el); setToastRoot(el); }, [])}
      >
        <TitleBar />
        {/* Window body: sidebar + main surface + right drawer */}
        <main className="app-body">
          <DataSourceTree
            treeSearch={treeSearch}
            collapsed={sidebarCollapsed}
            onToggleCollapse={toggleSidebarCollapse}
            onTreeSearchChange={setTreeSearch}
            onTableClick={handleTableClick}
            onTableDoubleClick={openTableTab}
            onNodeContextMenu={handleNodeContextMenu}
            onRefresh={refreshSchema}
            onNewConnection={openNewConnectionTab}
            sidebarWidth={sidebarWidth}
          />

          {/* Resize handle */}
          {!sidebarCollapsed && (
            <div
              className="app-resizer"
              onMouseDown={handleResizeStart}
            />
          )}

          <section className="app-main">
            {/* Top Workspace Tab Bar */}
            <div className="app-tabbar">
              <WorkspaceTabs
                onOpenSqlConsole={openSqlConsole}
              />

              {/* Top Right Actions */}
              <div className="app-tabbar-actions">
                <button
                  className="app-cmd-btn"
                  onClick={() => setShowCommandPalette(true)}
                  title="打开命令面板 (⌘K)"
                >
                  <span>命令面板</span>
                  <kbd>⌘K</kbd>
                </button>
              </div>
            </div>

            <div className="app-main-scroll">
              <WorkspaceRouter
                activeTab={activeTab}
                showToast={toast}
              />
            </div>
          </section>

          <ContextDrawer
            open={rightDrawerOpen}
            type={rightDrawerType}
            activeTab={activeTab}
            onClose={() => setRightDrawerOpen(false)}
            onGenerateIndexSql={() => openSqlConsole("ALTER TABLE comment_infos ADD INDEX idx_user_id (user_id);")}
          />
        </main>

        <CommandPalette
          open={showCommandPalette}
          onClose={() => setShowCommandPalette(false)}
          commands={commandItems}
        />

        <DataSourceContextMenu
          contextMenu={contextMenu}
          onOpenSqlConsole={openSqlConsole}
          onOpenTable={(tableName, subTab) => openTableTab(tableName, subTab)}
          onOpenMultiTableWorkspace={openMultiTableWorkspace}
          onClose={() => setContextMenu((prev) => ({ ...prev, visible: false }))}
          onToast={showToast}
          onOpenProps={() => toggleRightDrawer("props")}
        />
      </div>
    </div>
  );
}
