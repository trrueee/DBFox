import { useState, type MouseEvent } from "react";
import Header from "./Header";
import Sidebar from "./Sidebar";
import Workspace from "./Workspace";
import ContextDrawer from "../features/assistant/ContextDrawer";
import DataSourceContextMenu from "../features/datasource/DataSourceContextMenu";
import type {
  ContextDrawerState,
  ContextDrawerType,
  DataSourceContextMenuKind,
  DataSourceContextMenuState,
  TableSubTab,
  WorkspaceTab,
} from "../types/workspace";

const emptyMenu: DataSourceContextMenuState = {
  show: false,
  x: 0,
  y: 0,
  kind: "table",
  target: "",
};

export default function AppShell() {
  const [tabs, setTabs] = useState<WorkspaceTab[]>([
    { id: "ask", title: "问数工作台", type: "smart-query" },
  ]);
  const [activeTabId, setActiveTabId] = useState("ask");
  const [selectedTables, setSelectedTables] = useState<string[]>([]);
  const [queryContextTables, setQueryContextTables] = useState<string[]>([]);
  const [ask, setAsk] = useState("帮我查最近 7 天新增用户数量趋势");
  const [contextMenu, setContextMenu] = useState<DataSourceContextMenuState>(emptyMenu);
  const [drawer, setDrawer] = useState<ContextDrawerState>({
    open: false,
    type: "props",
  });

  const activeTab = tabs.find((tab) => tab.id === activeTabId) ?? tabs[0];

  const openDrawer = (
    type: ContextDrawerType,
    payload?: ContextDrawerState["payload"],
    title?: string,
  ) => {
    setDrawer({ open: true, type, payload, title });
  };

  const closeDrawer = () => setDrawer((prev) => ({ ...prev, open: false }));

  const openTab = (tab: WorkspaceTab) => {
    setTabs((prev) => (prev.some((item) => item.id === tab.id) ? prev : [...prev, tab]));
    setActiveTabId(tab.id);
  };

  const openTableTab = (tableName: string, initialSubTab: TableSubTab = "preview") => {
    openTab({
      id: `table:${tableName}`,
      title: tableName,
      type: "table",
      tableName,
      initialSubTab,
    });
    setSelectedTables([tableName]);
  };

  const openSqlConsole = () => {
    openTab({ id: `sql:${Date.now()}`, title: "SQL 控制台", type: "sql" });
  };

  const openMultiTableWorkspace = () => {
    if (!selectedTables.length) return;
    openTab({
      id: `multi:${selectedTables.join("|")}`,
      title: `联合 Workspace (${selectedTables.length})`,
      type: "multi-table",
      tableNames: selectedTables,
    });
  };

  const openQueryResult = () => {
    if (!ask.trim()) return;
    openTab({ id: `result:${Date.now()}`, title: "问数结果", type: "query-result", query: ask.trim() });
  };

  const closeTab = (event: MouseEvent, id: string) => {
    event.stopPropagation();
    setTabs((prev) => {
      const next = prev.filter((tab) => tab.id !== id);
      if (activeTabId === id) setActiveTabId(next.at(-1)?.id ?? "ask");
      return next;
    });
  };

  const addQueryContextTable = (tableName: string) => {
    setQueryContextTables((prev) => (prev.includes(tableName) ? prev : [...prev, tableName]));
  };

  const setDataSourceContextMenu = (
    event: MouseEvent,
    kind: DataSourceContextMenuKind,
    target: string,
  ) => {
    event.preventDefault();
    event.stopPropagation();
    const actualKind =
      kind === "table" && selectedTables.length > 1 && selectedTables.includes(target)
        ? "multi-table"
        : kind;
    setContextMenu({ show: true, x: event.clientX, y: event.clientY, kind: actualKind, target });
  };

  const handleTableClick = (event: MouseEvent, tableName: string) => {
    if (event.ctrlKey || event.metaKey) {
      setSelectedTables((prev) =>
        prev.includes(tableName) ? prev.filter((item) => item !== tableName) : [...prev, tableName],
      );
      return;
    }
    openTableTab(tableName);
  };

  return (
    <div className="app-shell" onClick={() => setContextMenu((prev) => ({ ...prev, show: false }))}>
      <Header />
      <main className="app-main">
        <Sidebar
          selectedTables={selectedTables}
          onTableClick={handleTableClick}
          onContextMenu={setDataSourceContextMenu}
        />
        <Workspace
          tabs={tabs}
          activeTab={activeTab}
          activeTabId={activeTabId}
          ask={ask}
          queryContextTables={queryContextTables}
          selectedTables={selectedTables}
          onAskChange={setAsk}
          onActiveTabChange={setActiveTabId}
          onCloseTab={closeTab}
          onOpenTable={openTableTab}
          onOpenSql={openSqlConsole}
          onOpenQueryResult={openQueryResult}
          onOpenDrawer={openDrawer}
          onSetQueryContextTables={setQueryContextTables}
        />
        <ContextDrawer drawer={drawer} onClose={closeDrawer} />
      </main>
      {contextMenu.show && (
        <DataSourceContextMenu
          menu={contextMenu}
          selectedTables={selectedTables}
          onOpenTable={openTableTab}
          onOpenSql={openSqlConsole}
          onOpenMultiTableWorkspace={openMultiTableWorkspace}
          onAddQueryContext={() => addQueryContextTable(contextMenu.target)}
        />
      )}
    </div>
  );
}
