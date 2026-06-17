import { useEffect, useState, useRef, type MouseEvent, useCallback } from "react";
import "./App.css";
import { setDialogContainer } from "./components/ui/dialog";
import { setToastRoot, useToast } from "./components/Toast";
import { ContextDrawer } from "./features/assistant/ContextDrawer";
import { DataSourceContextMenu } from "./features/datasource/DataSourceContextMenu";
import { DataSourceTree } from "./features/datasource/DataSourceTree";
import { useAgentRunner } from "./features/agentTask/useAgentRunner";
import { WorkspaceTabs } from "./features/workspace/WorkspaceTabs";
import { type ContextMenuState } from "./mock/dbfoxMock";
import { useDatasourceState } from "./features/datasource/useDatasourceState";
import { CommandPalette } from "./components/CommandPalette";
import TitleBar from "./components/TitleBar";
import { useSidebarLayout } from "./features/appShell/useSidebarLayout";
import { useWorkspaceTabs } from "./features/appShell/useWorkspaceTabs";
import { useConversationHistory } from "./features/appShell/useConversationHistory";
import { useWorkspaceSelection } from "./features/appShell/useWorkspaceSelection";
import { useAppCommands } from "./features/appShell/useAppCommands";
import { WorkspaceRouter } from "./features/appShell/WorkspaceRouter";

export default function App() {
  const [treeSearch, setTreeSearch] = useState("");
  const [askInputValue, setAskInputValue] = useState("帮我查一下“市场运营部”上个月发布了多少资产？");
  const [rightDrawerOpen, setRightDrawerOpen] = useState(false);
  const [rightDrawerType, setRightDrawerType] = useState<"ai-suggest" | "props">("props");
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({ visible: false, x: 0, y: 0, type: "database", targetNode: "" });

  const { toast } = useToast();

  const showToast = useCallback((message: string, type?: "success" | "error" | "warning" | "info") => {
    toast(message, type);
  }, [toast]);

  const {
    tabs,
    setTabs,
    activeTabId,
    setActiveTabId,
    activeTab,
    sqlConsoleState,
    setSqlConsoleState,
    tabSeqRef,
    closeTab,
    openSqlConsole,
    openLlmConfigTab,
    openConnectionManagerTab,
    openNewConnectionTab,
    openAgentEvalTab,
    openConversationResult,
    patchTab,
    appendTabMessages,
    updateTabMessage,
    patchTabTimeline,
  } = useWorkspaceTabs();

  const {
    conversations,
    persistConversation,
    deleteConversationById,
  } = useConversationHistory({
    onDeleteSuccess: (convId) => {
      setTabs((prev) => prev.filter((tab) => tab.conversationId !== convId));
    },
  });

  const {
    selectedTables,
    setSelectedTables,
    contextTables,
    setContextTables,
    tableSubTabs,
    setTableSubTabs,
    addContextTable,
    removeContextTable,
    clearContextTables,
  } = useWorkspaceSelection();

  const {
    datasources,
    activeDatasourceForSettings,
    activeDatasourceId,
    setActiveDatasourceId,
    tables,
    loadingSchema,
    schemaError,
    tableColumns,
    loadDatasources,
    refreshSchema,
    createDatasource,
    updateDatasource,
    deleteDatasource,
    syncSchema,
    checkHealth,
  } = useDatasourceState();


  // Release the previous datasource's connection pool when switching
  const prevDatasourceIdRef = useRef(activeDatasourceId);
  useEffect(() => {
    const prev = prevDatasourceIdRef.current;
    prevDatasourceIdRef.current = activeDatasourceId;
    if (prev && prev !== activeDatasourceId) {
      import("./lib/api/datasources").then(({ datasourcesApi }) => {
        datasourcesApi.releaseDatasource(prev).catch((err) => {
          console.warn("Failed to release datasource pool on switch:", err);
        });
      });
    }
  }, [activeDatasourceId]);

  // Layout UI states
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const { collapsed: sidebarCollapsed, width: sidebarWidth, handleResizeStart, toggleCollapse: toggleSidebarCollapse } = useSidebarLayout();

  const msgIdSeq = useRef(1);
  const nextMsgId = useCallback(() => ++msgIdSeq.current, []);

  useEffect(() => {
    const handleDocumentClick = () => setContextMenu((prev) => ({ ...prev, visible: false }));
    window.addEventListener("click", handleDocumentClick);
    return () => window.removeEventListener("click", handleDocumentClick);
  }, []);

  const openTableTab = useCallback((tableName: string, initialSubtab = "preview") => {
    const tabId = `table-${tableName}`;
    setTabs((prev) => (prev.some((tab) => tab.id === tabId) ? prev : [...prev, { id: tabId, title: tableName, type: "table", tableId: tableName }]));
    setActiveTabId(tabId);
    setSelectedTables([tableName]);
    setTableSubTabs((prev) => ({ ...prev, [tableName]: initialSubtab }));
  }, [setTabs, setActiveTabId, setSelectedTables, setTableSubTabs]);

  const openMultiTableWorkspace = useCallback((tables: string[]) => {
    if (tables.length === 0) return;
    const tabId = `multi-table-${tabSeqRef.current.multiTable++}`;
    const title = `Workspace: ${tables.slice(0, 2).join(" & ")}${tables.length > 2 ? "..." : ""}`;
    setTabs((prev) => [...prev, { id: tabId, title, type: "multi-table", selectedTables: tables }]);
    setActiveTabId(tabId);
    showToast(`已创建多表联合 Workspace (${tables.length} 张表)`);
  }, [setTabs, setActiveTabId, tabSeqRef, showToast]);

  const openQueryResultTab = (queryText: string) => {
    const text = queryText.trim();
    if (!text) return;
    const nextId = tabSeqRef.current.queryResult++;
    const tabId = `query-result-${nextId}`;
    setTabs((prev) => [
      ...prev,
      {
        id: tabId,
        title: "问数结果",
        type: "query-result",
        queryText: text,
        conversationId: `conversation-${nextId}`,
        chatMessages: [{ id: nextMsgId(), sender: "user", text }],
        artifacts: [],
      },
    ]);
    setActiveTabId(tabId);
    setAskInputValue("");
    void runAgentForTab(tabId, text);
  };

  const {
    runAgentForTab,
    handleApprovalDecision,
    sendFollowUp,
    cancelAgentRun,
    regenerateAgentRun,
  } = useAgentRunner({
    tabs,
    conversations,
    activeDatasourceId,
    contextTables,
    appendTabMessages,
    updateTabMessage,
    patchTab,
    patchTabTimeline,
    persistConversation,
    nextMsgId,
  });

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
      if (mod && event.key.toLowerCase() === "w" && activeTabId) {
        event.preventDefault();
        closeTab(activeTabId);
      }
    };
    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, [activeTabId, closeTab, openSqlConsole]);

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
    openLlmConfigTab,
    openConnectionManagerTab,
    openNewConnectionTab,
    openAgentEvalTab,
    openTableTab,
    setTabs,
    setActiveTabId,
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
            selectedTables={selectedTables}
            collapsed={sidebarCollapsed}
            onToggleCollapse={toggleSidebarCollapse}
            onTreeSearchChange={setTreeSearch}
            onTableClick={handleTableClick}
            onTableDoubleClick={openTableTab}
            onNodeContextMenu={handleNodeContextMenu}
            onRefresh={refreshSchema}
            onNewConnection={openNewConnectionTab}
            datasources={datasources}
            activeDatasourceId={activeDatasourceId}
            setActiveDatasourceId={setActiveDatasourceId}
            tables={tables}
            loading={loadingSchema}
            error={schemaError}
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
                tabs={tabs}
                activeTabId={activeTabId}
                onActivateTab={(tab) => {
                  setActiveTabId(tab.id);
                  if (tab.type === "table" && tab.tableId) setSelectedTables([tab.tableId]);
                }}
                onCloseTab={closeTab}
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
                askInputValue={askInputValue}
                onAskInputChange={setAskInputValue}
                contextTables={contextTables}
                onAddContextTable={addContextTable}
                onRemoveContextTable={removeContextTable}
                onClearContextTables={clearContextTables}
                openQueryResultTab={openQueryResultTab}
                conversations={conversations}
                openConversationResult={openConversationResult}
                deleteConversationById={deleteConversationById}
                tableSubTabs={tableSubTabs}
                setTableSubTabs={setTableSubTabs}
                openSqlConsole={openSqlConsole}
                showToast={showToast}
                sqlConsoleState={sqlConsoleState}
                setSqlConsoleState={setSqlConsoleState}
                datasources={datasources}
                activeDatasourceId={activeDatasourceId}
                setActiveDatasourceId={setActiveDatasourceId}
                activeDatasourceForSettings={activeDatasourceForSettings}
                loadDatasources={loadDatasources}
                sendFollowUp={sendFollowUp}
                handleApprovalDecision={handleApprovalDecision}
                cancelAgentRun={cancelAgentRun}
                regenerateAgentRun={regenerateAgentRun}
                datasourceActions={{
                  createDatasource,
                  updateDatasource,
                  deleteDatasource,
                  syncSchema,
                  checkHealth,
                }}
              />
            </div>
          </section>

          <ContextDrawer
            open={rightDrawerOpen}
            type={rightDrawerType}
            activeTab={activeTab}
            contextTables={contextTables}
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
          selectedTables={selectedTables}
          onOpenSqlConsole={openSqlConsole}
          onOpenTable={(tableName, subTab) => openTableTab(tableName, subTab)}
          onOpenMultiTableWorkspace={openMultiTableWorkspace}
          onAddContextTable={addContextTable}
          onSetContextTables={(tables) => {
            setContextTables(tables);
            showToast(`已添加 ${tables.length} 张表到问数上下文`);
          }}
          onClearSelectedTables={() => setSelectedTables([])}
          onClose={() => setContextMenu((prev) => ({ ...prev, visible: false }))}
          onToast={showToast}
          onOpenProps={() => toggleRightDrawer("props")}
        />
      </div>
    </div>
  );
}
