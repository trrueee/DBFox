import { useEffect, useState, useMemo, useRef, type MouseEvent, useCallback } from "react";
import { Sparkles, Cpu, Database, FileText, Terminal, HelpCircle, FlaskConical } from "lucide-react";
import "./App.css";
import { setDialogContainer } from "./components/ui/dialog";
import { setToastRoot } from "./components/Toast";
import { ContextDrawer } from "./features/assistant/ContextDrawer";
import { ConversationHistoryPanel } from "./features/conversation/ConversationHistoryPanel";
import { deleteConversation, listConversations, saveConversation } from "./features/conversation/conversationRepository";
import { DataSourceContextMenu } from "./features/datasource/DataSourceContextMenu";
import { DataSourceTree } from "./features/datasource/DataSourceTree";
import { useAgentRunner } from "./features/agentTask/useAgentRunner";
import { MultiTableWorkspace } from "./features/workspace/MultiTableWorkspace";
import { QueryResultWorkspace } from "./features/workspace/QueryResultWorkspace";
import { SmartQueryHome } from "./features/workspace/SmartQueryHome";
import { SqlConsoleWorkspace } from "./features/workspace/SqlConsoleWorkspace";
import { TableWorkspace } from "./features/workspace/TableWorkspace";
import { WorkspaceTabs } from "./features/workspace/WorkspaceTabs";
import { defaultSql, type ContextMenuState, type WorkspaceTab } from "./mock/databoxMock";
import type { Conversation, ConversationMessage } from "./types/conversation";
import { useDatasourceState } from "./features/datasource/useDatasourceState";
import { DataSourcesPage } from "./pages/DataSourcesPage";
import { AgentEvalPage } from "./pages/AgentEvalPage";
import { useApiConfig } from "./components/SettingsDialog";
import { CommandPalette, type CommandItem } from "./components/CommandPalette";
import { LlmConfigPanel } from "./components/LlmConfigPanel";
import TitleBar from "./components/TitleBar";
import { testLlmConnection } from "./lib/api/agent";
import { useSidebarLayout } from "./features/appShell/useSidebarLayout";

export default function App() {
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
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const showToast = useCallback((message: string) => {
    setToastMsg(message);
    setTimeout(() => setToastMsg(null), 2500);
  }, []);
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
  } = useDatasourceState({ onToast: showToast });

  // Layout UI states
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const { collapsed: sidebarCollapsed, width: sidebarWidth, handleResizeStart, toggleCollapse: toggleSidebarCollapse } = useSidebarLayout();

  const activeTab = tabs.find((tab) => tab.id === activeTabId) || tabs[0];

  const msgIdSeq = useRef(1);
  const nextMsgId = useCallback(() => ++msgIdSeq.current, []);
  const tabSeqRef = useRef({ sql: 1, multiTable: 1, queryResult: 1 });

  useEffect(() => {
    const handleDocumentClick = () => setContextMenu((prev) => ({ ...prev, visible: false }));
    window.addEventListener("click", handleDocumentClick);
    return () => window.removeEventListener("click", handleDocumentClick);
  }, []);

  const refreshConversations = useCallback(async () => {
    try {
      const history = await listConversations();
      setConversations(history);
    } catch {
      showToast("读取 SQLite 对话历史失败");
    }
  }, [showToast]);

  useEffect(() => {
    void refreshConversations();
  }, [refreshConversations]);

  const persistConversation = useCallback(async (conversation: Conversation) => {
    try {
      await saveConversation(conversation);
      setConversations((prev) => [conversation, ...prev.filter((item) => item.id !== conversation.id)].sort((a, b) => b.updatedAt - a.updatedAt));
    } catch {
      showToast("写入 SQLite 对话历史失败");
    }
  }, [showToast]);

  const openTableTab = useCallback((tableName: string, initialSubtab = "preview") => {
    const tabId = `table-${tableName}`;
    setTabs((prev) => (prev.some((tab) => tab.id === tabId) ? prev : [...prev, { id: tabId, title: tableName, type: "table", tableId: tableName }]));
    setActiveTabId(tabId);
    setSelectedTables([tableName]);
    setTableSubTabs((prev) => ({ ...prev, [tableName]: initialSubtab }));
  }, []);

  const closeTab = useCallback((tabId: string, event?: { stopPropagation: () => void }) => {
    event?.stopPropagation();
    const nextTabs = tabs.filter((tab) => tab.id !== tabId);
    if (nextTabs.length === 0) {
      setTabs([{ id: "smart-query", title: "问数工作台", type: "smart-query" }]);
      setActiveTabId("smart-query");
      return;
    }
    setTabs(nextTabs);
    if (activeTabId === tabId) setActiveTabId(nextTabs[nextTabs.length - 1].id);
  }, [activeTabId, tabs]);

  const openSqlConsole = useCallback(() => {
    const tabId = `sql-${tabSeqRef.current.sql++}`;
    setTabs((prev) => [...prev, { id: tabId, title: "SQL 控制台", type: "sql" }]);
    setActiveTabId(tabId);
    showToast("已打开 SQL 控制台");
  }, [showToast]);

  const openLlmConfigTab = useCallback(() => {
    const tabId = "llm-config";
    setTabs((prev) => (prev.some((tab) => tab.id === tabId) ? prev : [...prev, { id: tabId, title: "LLM 配置", type: "llm-config" }]));
    setActiveTabId(tabId);
  }, []);

  const openConnectionManagerTab = useCallback(() => {
    const tabId = "datasource-settings";
    setTabs((prev) =>
      prev.some((tab) => tab.id === tabId)
        ? prev.map((tab) => (tab.id === tabId ? { ...tab, title: "数据源管理" } : tab))
        : [...prev, { id: tabId, title: "数据源管理", type: "datasource-settings" }],
    );
    setActiveTabId(tabId);
  }, []);

  const openNewConnectionTab = useCallback(() => {
    const tabId = "datasource-settings";
    setTabs((prev) =>
      prev.some((tab) => tab.id === tabId)
        ? prev.map((tab) => (tab.id === tabId ? { ...tab, title: "新建数据源" } : tab))
        : [...prev, { id: tabId, title: "新建数据源", type: "datasource-settings" }],
    );
    setActiveTabId(tabId);
  }, []);

  const openMultiTableWorkspace = useCallback((tables: string[]) => {
    if (tables.length === 0) return;
    const tabId = `multi-table-${tabSeqRef.current.multiTable++}`;
    const title = `Workspace: ${tables.slice(0, 2).join(" & ")}${tables.length > 2 ? "..." : ""}`;
    setTabs((prev) => [...prev, { id: tabId, title, type: "multi-table", selectedTables: tables }]);
    setActiveTabId(tabId);
    showToast(`已创建多表联合 Workspace (${tables.length} 张表)`);
  }, [showToast]);

  const openAgentEvalTab = useCallback(() => {
    const tabId = "agent-eval";
    setTabs((prev) => (prev.some((tab) => tab.id === tabId) ? prev : [...prev, { id: tabId, title: "Agent 评测", type: "agent-eval" }]));
    setActiveTabId(tabId);
  }, []);

  const openConversationResult = (conversation: Conversation) => {
    const tabId = `conversation-${conversation.id}`;
    const tab: WorkspaceTab = {
      id: tabId,
      title: conversation.title,
      type: "query-result",
      queryText: conversation.title,
      conversationId: conversation.id,
      chatMessages: conversationMessagesToTabMessages(conversation.messages),
      artifacts: conversation.artifacts,
    };
    setTabs((prev) => (prev.some((item) => item.id === tabId) ? prev.map((item) => (item.id === tabId ? tab : item)) : [...prev, tab]));
    setActiveTabId(tabId);
  };

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

  // ---- Agent runtime wiring -------------------------------------------------

  const patchTab = (tabId: string, patch: Partial<WorkspaceTab>) => {
    setTabs((prev) => prev.map((tab) => (tab.id === tabId ? { ...tab, ...patch } : tab)));
  };

  const appendTabMessages = (tabId: string, messages: NonNullable<WorkspaceTab["chatMessages"]>) => {
    setTabs((prev) => prev.map((tab) => (
      tab.id === tabId ? { ...tab, chatMessages: [...(tab.chatMessages || []), ...messages] } : tab
    )));
  };

  const updateTabMessage = (tabId: string, messageId: number, text: string) => {
    setTabs((prev) => prev.map((tab) => (
      tab.id === tabId
        ? { ...tab, chatMessages: (tab.chatMessages || []).map((message) => (message.id === messageId ? { ...message, text } : message)) }
        : tab
    )));
  };

  const patchTabTimeline = (
    tabId: string,
    updater: (items: NonNullable<WorkspaceTab["agentTimeline"]>) => NonNullable<WorkspaceTab["agentTimeline"]>,
  ) => {
    setTabs((prev) => prev.map((tab) => (
      tab.id === tabId ? { ...tab, agentTimeline: updater(tab.agentTimeline || []) } : tab
    )));
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
    showToast,
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

  const deleteConversationById = async (conversationId: string) => {
    try {
      await deleteConversation(conversationId);
      setConversations((prev) => prev.filter((item) => item.id !== conversationId));
      setTabs((prev) => prev.filter((tab) => tab.conversationId !== conversationId));
      showToast("已删除对话历史");
    } catch {
      showToast("删除 SQLite 对话历史失败");
    }
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

  const commandItems = useMemo<CommandItem[]>(() => {
    const items: CommandItem[] = [
      {
        id: "new-sql",
        name: "新建 SQL 控制台",
        category: "快捷入口",
        shortcut: "⌘N",
        icon: <Terminal size={13} className="text-green-500" />,
        action: () => openSqlConsole()
      },
      {
        id: "smart-query",
        name: "智能问数 (AI 问数)",
        category: "快捷入口",
        icon: <Sparkles size={13} className="text-purple-500" />,
        action: () => {
          setTabs((prev) => prev.some(t => t.type === "smart-query") ? prev : [...prev, { id: "smart-query", title: "问数工作台", type: "smart-query" }]);
          setActiveTabId("smart-query");
        }
      },
      {
        id: "llm-config",
        name: "打开 LLM 配置",
        category: "系统配置",
        icon: <Cpu size={13} className="text-pink-500" />,
        action: () => openLlmConfigTab()
      },
      {
        id: "create-datasource",
        name: "新建数据源连接",
        category: "数据源",
        icon: <Database size={13} className="text-blue-500" />,
        action: () => openNewConnectionTab()
      },
      {
        id: "connection-manager",
        name: "数据源连接管理",
        category: "数据源",
        icon: <Database size={13} className="text-slate-500" />,
        action: () => openConnectionManagerTab()
      },
      {
        id: "agent-eval",
        name: "Agent 评测 (Golden 任务)",
        category: "AI 能力",
        icon: <FlaskConical size={13} className="text-amber-500" />,
        action: () => openAgentEvalTab()
      }
    ];

    tables.forEach((table) => {
      items.push({
        id: `table-${table.table_name}`,
        name: `打开表: ${table.table_name}`,
        category: `数据表 (${table.module_tag || "未分组"})`,
        icon: <FileText size={13} className="text-blue-500" />,
        action: () => openTableTab(table.table_name)
      });
    });

    Object.entries(tableColumns).forEach(([tableName, columns]) => {
      columns.forEach((col) => {
        items.push({
          id: `field-${tableName}-${col.column_name}`,
          name: `查看字段: ${tableName}.${col.column_name} (${col.column_type})`,
          category: `表字段 (${tableName})`,
          icon: <HelpCircle size={13} className="text-slate-400" />,
          action: () => openTableTab(tableName, "schema")
        });
      });
    });

    return items;
  }, [
    openAgentEvalTab,
    openConnectionManagerTab,
    openLlmConfigTab,
    openNewConnectionTab,
    openSqlConsole,
    openTableTab,
    tables,
    tableColumns,
  ]);

  const renderActiveTab = () => {
    if (activeTab.type === "smart-query") {
      return (
        <SmartQueryHome
          askInputValue={askInputValue}
          contextTables={contextTables}
          onAskInputChange={setAskInputValue}
          onSubmitAsk={() => openQueryResultTab(askInputValue)}
          onAddContextTable={addContextTable}
          onRemoveContextTable={(tableName) => setContextTables((prev) => prev.filter((table) => table !== tableName))}
          onClearContextTables={() => setContextTables([])}
        />
      );
    }
    if (activeTab.type === "conversation-history") {
      return <ConversationHistoryPanel conversations={conversations} activeConversationId={activeTab.conversationId} onOpenConversation={openConversationResult} onDeleteConversation={deleteConversationById} />;
    }
    if (activeTab.type === "table") {
      const tableId = activeTab.tableId || "id_users";
      return <TableWorkspace tableId={tableId} currentSubTab={tableSubTabs[tableId] || "preview"} onSubTabChange={(subTab) => setTableSubTabs((prev) => ({ ...prev, [tableId]: subTab }))} onOpenSqlConsole={openSqlConsole} onToast={showToast} />;
    }
    if (activeTab.type === "sql") {
      return <SqlConsoleWorkspace sqlQuery={sqlQuery} onSqlQueryChange={setSqlQuery} onToast={showToast} />;
    }
    if (activeTab.type === "multi-table") {
      return <MultiTableWorkspace tables={activeTab.selectedTables || []} onOpenQueryResult={openQueryResultTab} onToast={showToast} />;
    }
    if (activeTab.type === "llm-config") {
      return <LlmConfigTabContent showToast={showToast} />;
    }
    if (activeTab.type === "agent-eval") {
      return (
        <AgentEvalPage
          datasources={datasources}
          activeDatasourceId={activeDatasourceId}
          onToast={showToast}
        />
      );
    }
    if (activeTab.type === "datasource-settings") {
      return (
        <div className="hifi-settings-tab-frame">
          <DataSourcesPage
            onSelectDataSource={(ds) => {
              if (ds) {
                setActiveDatasourceId(ds.id);
                showToast(`已激活数据源: ${ds.name}`);
              } else {
                setActiveDatasourceId("");
              }
            }}
            activeDataSource={activeDatasourceForSettings}
            activeProject={null}
            onRefreshDatasources={loadDatasources}
            initialShowAddForm={activeTab.title === "新建数据源"}
          />
        </div>
      );
    }
    return (
      <QueryResultWorkspace
        tab={activeTab}
        onOpenSqlConsole={openSqlConsole}
        onSetSqlQuery={setSqlQuery}
        onSendFollowUp={sendFollowUp}
        onApproveAgent={(tabId) => void handleApprovalDecision(tabId, true)}
        onRejectAgent={(tabId) => void handleApprovalDecision(tabId, false)}
        onCancelRun={cancelAgentRun}
        onRegenerateRun={regenerateAgentRun}
        onToast={showToast}
      />
    );
  };

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
              {renderActiveTab()}
            </div>
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

      <CommandPalette open={showCommandPalette} onClose={() => setShowCommandPalette(false)} commands={commandItems} />
    </div>
  );
}

function conversationMessagesToTabMessages(messages: ConversationMessage[]) {
  return messages.map((message, index) => ({
    id: Number(message.id.replace(/\D/g, "")) || index + 1,
    sender: message.role === "user" ? "user" as const : "ai" as const,
    text: message.content,
  }));
}

function LlmConfigTabContent({ showToast }: { showToast: (msg: string) => void }) {
  const { config, updateConfig, handleSave } = useApiConfig();

  return (
    <div className="hifi-settings-tab-frame">
      <LlmConfigPanel
        variant="page"
        config={config}
        onChange={updateConfig}
        onSave={() => {
          handleSave();
          showToast("LLM 配置保存成功");
        }}
        onTestConnection={async () => {
          showToast("正在测试与模型接口握手…");
          try {
            const result = await testLlmConnection(
              config.apiKey || "",
              config.apiBase || "https://api.openai.com/v1",
              config.modelName || "gpt-4o-mini",
            );
            if (result.ok) {
              showToast(
                `连接测试通过 (${result.latency_ms}ms)，模型 ${result.model} 可达`,
              );
            } else {
              showToast(
                `连接失败 [${result.error_code || "UNKNOWN"}]: ${result.error_message || "未知错误"}`,
              );
            }
          } catch (e: unknown) {
            const msg =
              e instanceof Error ? e.message : "无法连接到引擎服务，请确认引擎正在运行。";
            showToast(`连接测试失败: ${msg}`);
          }
        }}
      />
    </div>
  );
}
