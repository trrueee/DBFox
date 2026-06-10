import { useEffect, useState, type CSSProperties, type MouseEvent } from "react";
import { Sparkles } from "lucide-react";
import "./App.css";
import { ContextDrawer } from "./features/assistant/ContextDrawer";
import { ConversationHistoryPanel } from "./features/conversation/ConversationHistoryPanel";
import { deleteConversation, listConversations, saveConversation } from "./features/conversation/conversationRepository";
import { DataSourceContextMenu } from "./features/datasource/DataSourceContextMenu";
import { DataSourceTree } from "./features/datasource/DataSourceTree";
import { LlmSettingsWorkspace } from "./features/workspace/LlmSettingsWorkspace";
import { MultiTableWorkspace } from "./features/workspace/MultiTableWorkspace";
import { QueryResultWorkspace } from "./features/workspace/QueryResultWorkspace";
import { SmartQueryHome } from "./features/workspace/SmartQueryHome";
import { SqlConsoleWorkspace } from "./features/workspace/SqlConsoleWorkspace";
import { TableWorkspace } from "./features/workspace/TableWorkspace";
import { WorkspaceTabs } from "./features/workspace/WorkspaceTabs";
import { Header } from "./layouts/Header";
import { defaultSql, type ContextMenuState, type WorkspaceTab } from "./mock/databoxMock";
import type { Conversation, ConversationMessage } from "./types/conversation";

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
  const [conversations, setConversations] = useState<Conversation[]>([]);

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

  useEffect(() => {
    void refreshConversations();
  }, []);

  const showToast = (message: string) => {
    setToastMsg(message);
    setTimeout(() => setToastMsg(null), 2500);
  };

  const refreshConversations = async () => {
    try {
      const history = await listConversations();
      setConversations(history);
    } catch {
      showToast("读取 SQLite 对话历史失败");
    }
  };

  const persistConversation = async (conversation: Conversation) => {
    try {
      await saveConversation(conversation);
      setConversations((prev) => [conversation, ...prev.filter((item) => item.id !== conversation.id)].sort((a, b) => b.updatedAt - a.updatedAt));
    } catch {
      showToast("写入 SQLite 对话历史失败");
    }
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

  const openConversationHistoryTab = () => {
    const tabId = "conversation-history";
    setTabs((prev) => (prev.some((tab) => tab.id === tabId) ? prev : [...prev, { id: tabId, title: "对话历史", type: "conversation-history" }]));
    setActiveTabId(tabId);
    setRecentTab("chat");
  };

  const openLlmSettingsTab = () => {
    const tabId = "llm-settings";
    setTabs((prev) => (prev.some((tab) => tab.id === tabId) ? prev : [...prev, { id: tabId, title: "模型配置", type: "llm-settings" }]));
    setActiveTabId(tabId);
  };

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
    const now = Date.now();
    const conversation: Conversation = {
      id: `conversation-${now}`,
      title: text,
      createdAt: now,
      updatedAt: now,
      contextTables,
      messages: [
        { id: `message-${now}`, role: "user", content: text, createdAt: now },
        { id: `message-${now + 1}`, role: "assistant", content: "问题已提交给 Agent。等待后端返回 artifacts 后，结果会在下方渲染。", createdAt: now + 1 },
      ],
      artifacts: [],
    };
    const tabId = `query-result-${now}`;
    setTabs((prev) => [
      ...prev,
      {
        id: tabId,
        title: "问数结果",
        type: "query-result",
        queryText: text,
        conversationId: conversation.id,
        chatMessages: conversationMessagesToTabMessages(conversation.messages),
        artifacts: conversation.artifacts,
      },
    ]);
    setActiveTabId(tabId);
    setAskInputValue("");
    void persistConversation(conversation);
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
    const content = text.trim();
    if (!content) return;
    const now = Date.now();
    const userMessage: ConversationMessage = { id: `message-${now}`, role: "user", content, createdAt: now };
    const assistantMessage: ConversationMessage = { id: `message-${now + 1}`, role: "assistant", content: "已追加追问，等待 Agent 返回新的 artifacts。", createdAt: now + 1 };
    const targetTab = tabs.find((tab) => tab.id === tabId);

    setTabs((prev) => prev.map((tab) => tab.id === tabId ? { ...tab, chatMessages: [...(tab.chatMessages || []), { id: now, sender: "user", text: content }, { id: now + 1, sender: "ai", text: assistantMessage.content }] } : tab));

    if (targetTab?.conversationId) {
      const origin = conversations.find((item) => item.id === targetTab.conversationId);
      const fallbackMessages = tabMessagesToConversationMessages(targetTab.chatMessages || []);
      const updatedConversation: Conversation = {
        id: targetTab.conversationId,
        title: origin?.title || targetTab.queryText || "未命名问答",
        createdAt: origin?.createdAt || now,
        updatedAt: now,
        contextTables: origin?.contextTables || contextTables,
        messages: [...(origin?.messages || fallbackMessages), userMessage, assistantMessage],
        artifacts: targetTab.artifacts || origin?.artifacts || [],
      };
      void persistConversation(updatedConversation);
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

  const renderActiveTab = () => {
    if (activeTab.type === "smart-query") {
      return (
        <SmartQueryHome
          askInputValue={askInputValue}
          contextTables={contextTables}
          conversations={conversations}
          recentTab={recentTab}
          onAskInputChange={setAskInputValue}
          onSubmitAsk={() => openQueryResultTab(askInputValue)}
          onRecommendClick={setAskInputValue}
          onRecentTabChange={setRecentTab}
          onOpenTable={openTableTab}
          onOpenConversation={openConversationResult}
          onAddContextTable={addContextTable}
          onRemoveContextTable={(tableName) => setContextTables((prev) => prev.filter((table) => table !== tableName))}
          onClearContextTables={() => setContextTables([])}
          onOpenConversationHistory={openConversationHistoryTab}
          onToast={showToast}
        />
      );
    }
    if (activeTab.type === "conversation-history") {
      return <ConversationHistoryPanel conversations={conversations} activeConversationId={activeTab.conversationId} onOpenConversation={openConversationResult} onDeleteConversation={deleteConversationById} />;
    }
    if (activeTab.type === "llm-settings") {
      return <LlmSettingsWorkspace onToast={showToast} />;
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
    return <QueryResultWorkspace tab={activeTab} onOpenSqlConsole={openSqlConsole} onSetSqlQuery={setSqlQuery} onSendFollowUp={sendFollowUp} onToast={showToast} />;
  };

  return (
    <div className="hifi-viewport-wrapper">
      <div className="hifi-canvas-board" style={{ "--scale": scale } as CSSProperties}>
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
              onOpenLlmSettings={openLlmSettingsTab}
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

function conversationMessagesToTabMessages(messages: ConversationMessage[]) {
  return messages.map((message, index) => ({
    id: Number(message.id.replace(/\D/g, "")) || index + 1,
    sender: message.role === "user" ? "user" as const : "ai" as const,
    text: message.content,
  }));
}

function tabMessagesToConversationMessages(messages: NonNullable<WorkspaceTab["chatMessages"]>): ConversationMessage[] {
  return messages.map((message, index) => ({
    id: `message-${message.id || index}`,
    role: message.sender === "user" ? "user" : "assistant",
    content: message.text,
    createdAt: Number(message.id) || Date.now(),
  }));
}
