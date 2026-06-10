import { useEffect, useState, type MouseEvent } from "react";
import { Sparkles } from "lucide-react";
import "./App.css";
import { Header } from "./layouts/Header";
import { ContextDrawer } from "./features/assistant/ContextDrawer";
import { DataSourceContextMenu } from "./features/datasource/DataSourceContextMenu";
import { DataSourceTree } from "./features/datasource/DataSourceTree";
import { MultiTableWorkspace } from "./features/workspace/MultiTableWorkspace";
import { QueryResultWorkspace } from "./features/workspace/QueryResultWorkspace";
import { SmartQueryHome } from "./features/workspace/SmartQueryHome";
import { SqlConsoleWorkspace } from "./features/workspace/SqlConsoleWorkspace";
import { TableWorkspace } from "./features/workspace/TableWorkspace";
import { WorkspaceTabs } from "./features/workspace/WorkspaceTabs";
import { defaultSql, type ContextMenuState, type WorkspaceTab } from "./mock/databoxMock";

export default function App() {
  const [scale, setScale] = useState(1);
  const [treeSearch, setTreeSearch] = useState("");
  const [askInputValue, setAskInputValue] = useState("帮我查一下“市场运营部”上个月发布了多少资产？");
  const [tabs, setTabs] = useState<WorkspaceTab[]>([{ id: "smart-query", title: "问数工作台", type: "smart-query" }]);
  const [activeTabId, setActiveTabId] = useState("smart-query");
  const [selectedTables, setSelectedTables] = useState<string[]>([]);
  const [contextTables, setContextTables] = useState<string[]>([]);
  const [tableSubTabs, setTableSubTabs] = useState<Record<string, string>>({});
  const [rightDrawerOpen, setRightDrawerOpen] = useState(false);
  const [rightDrawerType, setRightDrawerType] = useState<"ai-suggest" | "props">("props");
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({ visible: false, x: 0, y: 0, type: "database", targetNode: "" });
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [sqlQuery, setSqlQuery] = useState(defaultSql);
  const [sqlResultsRun, setSqlResultsRun] = useState(false);
  const [sqlConsoleTab, setSqlConsoleTab] = useState<"results" | "history" | "ai-explain">("results");
  const [recentTab, setRecentTab] = useState("tables");
  const [activeHeaderTab, setActiveHeaderTab] = useState("workbench");

  const activeTab = tabs.find((tab) => tab.id === activeTabId) || tabs[0];

  useEffect(() => {
    const handleResize = () => {
      const targetWidth = 1598;
      const targetHeight = 1066;
      setScale(Math.min(window.innerWidth / targetWidth, window.innerHeight / targetHeight));
    };
    window.addEventListener("resize", handleResize);
    handleResize();
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    const handleDocumentClick = () => setContextMenu((prev) => ({ ...prev, visible: false }));
    window.addEventListener("click", handleDocumentClick);
    return () => window.removeEventListener("click", handleDocumentClick);
  }, []);

  const showToast = (message: string) => {
    setToastMsg(message);
    setTimeout(() => setToastMsg(null), 2500);
  };

  const openTableTab = (tableName: string, initialSubtab = "preview") => {
    const tabId = `table-${tableName}`;
    setTabs((prev) => (prev.some((tab) => tab.id === tabId) ? prev : [...prev, { id: tabId, title: tableName, type: "table", tableId: tableName }]));
    setActiveTabId(tabId);
    setSelectedTables([tableName]);
    setTableSubTabs((prev) => ({ ...prev, [tableName]: initialSubtab }));
  };

  const closeTab = (tabId: string, event: MouseEvent) => {
    event.stopPropagation();
    const nextTabs = tabs.filter((tab) => tab.id !== tabId);
    if (nextTabs.length === 0) {
      setTabs([{ id: "smart-query", title: "问数工作台", type: "smart-query" }]);
      setActiveTabId("smart-query");
      return;
    }
    setTabs(nextTabs);
    if (activeTabId === tabId) setActiveTabId(nextTabs[nextTabs.length - 1].id);
  };

  const openSqlConsole = () => {
    const tabId = `sql-${Date.now()}`;
    setTabs((prev) => [...prev, { id: tabId, title: "SQL 控制台", type: "sql" }]);
    setActiveTabId(tabId);
    showToast("已打开 SQL 控制台");
  };

  const openMultiTableWorkspace = (tables: string[]) => {
    if (tables.length === 0) return;
    const tabId = `multi-table-${Date.now()}`;
    const title = `Workspace: ${tables.slice(0, 2).join(" & ")}${tables.length > 2 ? "..." : ""}`;
    setTabs((prev) => [...prev, { id: tabId, title, type: "multi-table", selectedTables: tables }]);
    setActiveTabId(tabId);
    showToast(`已创建多表联合 Workspace (${tables.length} 张表)`);
  };

  const openQueryResultTab = (queryText: string) => {
    if (!queryText.trim()) return;
    const tabId = `query-result-${Date.now()}`;
    setTabs((prev) => [
      ...prev,
      {
        id: tabId,
        title: "问数结果",
        type: "query-result",
        queryText,
        chatMessages: [{ id: 1, sender: "ai", text: "你好！我是你的智能问数助理。针对您的查询，已为您生成以下的可视化分析图表与 SQL。" }],
      },
    ]);
    setActiveTabId(tabId);
    setAskInputValue("");
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

  const addContextTable = (tableName: string) => {
    setContextTables((prev) => (prev.includes(tableName) ? prev : [...prev, tableName]));
    showToast(`已添加表 ${tableName} 到问数上下文`);
  };

  const toggleRightDrawer = (type: "ai-suggest" | "props") => {
    if (rightDrawerOpen && rightDrawerType === type) setRightDrawerOpen(false);
    else {
      setRightDrawerOpen(true);
      setRightDrawerType(type);
    }
  };

  const sendFollowUp = (tabId: string, text: string) => {
    if (!text.trim()) return;
    setTabs((prev) => prev.map((tab) => tab.id === tabId ? { ...tab, chatMessages: [...(tab.chatMessages || []), { id: Date.now(), sender: "user", text }, { id: Date.now() + 1, sender: "ai", text: "正在根据上下文查询与分析，请稍候..." }] } : tab));
  };

  const renderActiveTab = () => {
    if (activeTab.type === "smart-query") {
      return (
        <SmartQueryHome
          askInputValue={askInputValue}
          contextTables={contextTables}
          recentTab={recentTab}
          onAskInputChange={setAskInputValue}
          onSubmitAsk={() => openQueryResultTab(askInputValue)}
          onRecommendClick={setAskInputValue}
          onRecentTabChange={setRecentTab}
          onOpenTable={openTableTab}
          onAddContextTable={addContextTable}
          onRemoveContextTable={(tableName) => setContextTables((prev) => prev.filter((table) => table !== tableName))}
          onClearContextTables={() => setContextTables([])}
          onToast={showToast}
        />
      );
    }
    if (activeTab.type === "table") {
      const tableId = activeTab.tableId || "id_users";
      return <TableWorkspace tableId={tableId} currentSubTab={tableSubTabs[tableId] || "preview"} onSubTabChange={(subTab) => setTableSubTabs((prev) => ({ ...prev, [tableId]: subTab }))} onOpenSqlConsole={openSqlConsole} onToast={showToast} />;
    }
    if (activeTab.type === "sql") {
      return <SqlConsoleWorkspace sqlQuery={sqlQuery} sqlResultsRun={sqlResultsRun} sqlConsoleTab={sqlConsoleTab} onSqlQueryChange={setSqlQuery} onRunSql={() => setSqlResultsRun(true)} onSqlConsoleTabChange={setSqlConsoleTab} onToast={showToast} />;
    }
    if (activeTab.type === "multi-table") {
      return <MultiTableWorkspace tables={activeTab.selectedTables || []} onOpenQueryResult={openQueryResultTab} onToast={showToast} />;
    }
    return <QueryResultWorkspace tab={activeTab} onOpenSqlConsole={openSqlConsole} onSetSqlQuery={setSqlQuery} onSendFollowUp={sendFollowUp} />;
  };

  return (
    <div className="hifi-viewport-wrapper">
      <div className="hifi-canvas-board" style={{ "--scale": scale } as React.CSSProperties}>
        <Header activeHeaderTab={activeHeaderTab} onHeaderTabChange={setActiveHeaderTab} />
        <main className="hifi-workspace">
          <DataSourceTree
            treeSearch={treeSearch}
            selectedTables={selectedTables}
            onTreeSearchChange={setTreeSearch}
            onTableClick={handleTableClick}
            onTableDoubleClick={openTableTab}
            onNodeContextMenu={handleNodeContextMenu}
            onRefresh={() => showToast("已刷新数据源树")}
          />

          <section className="hifi-col hifi-main-workspace-col">
            <WorkspaceTabs
              tabs={tabs}
              activeTabId={activeTabId}
              rightDrawerOpen={rightDrawerOpen}
              rightDrawerType={rightDrawerType}
              onActivateTab={(tab) => {
                setActiveTabId(tab.id);
                if (tab.type === "table" && tab.tableId) setSelectedTables([tab.tableId]);
              }}
              onCloseTab={closeTab}
              onOpenSqlConsole={openSqlConsole}
              onToggleRightDrawer={toggleRightDrawer}
            />
            {renderActiveTab()}
          </section>

          <ContextDrawer
            open={rightDrawerOpen}
            type={rightDrawerType}
            activeTab={activeTab}
            contextTables={contextTables}
            onClose={() => setRightDrawerOpen(false)}
            onGenerateIndexSql={() => {
              setSqlQuery("ALTER TABLE comment_infos ADD INDEX idx_user_id (user_id);");
              openSqlConsole();
            }}
          />
        </main>
      </div>

      <DataSourceContextMenu
        contextMenu={contextMenu}
        selectedTables={selectedTables}
        onOpenSqlConsole={openSqlConsole}
        onOpenTable={openTableTab}
        onOpenMultiTableWorkspace={openMultiTableWorkspace}
        onAddContextTable={addContextTable}
        onSetContextTables={(tables) => {
          setContextTables(tables);
          setActiveTabId("smart-query");
          showToast(`已将 ${tables.length} 张表载入问数上下文`);
        }}
        onClearSelectedTables={() => setSelectedTables([])}
        onClose={() => setContextMenu((prev) => ({ ...prev, visible: false }))}
        onToast={showToast}
        onOpenProps={() => toggleRightDrawer("props")}
      />

      {toastMsg && <div className="hifi-toast"><Sparkles size={12} className="text-yellow-400" /><span>{toastMsg}</span></div>}
    </div>
  );
}
