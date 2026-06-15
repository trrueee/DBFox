import { useState, useRef, useCallback } from "react";
import type { WorkspaceTab } from "../../mock/databoxMock";
import type { SqlConsoleTabState } from "../workspace/SqlConsoleWorkspace";
import { defaultSql } from "../../mock/databoxMock";
import type { Conversation, ConversationMessage } from "../../types/conversation";
import { useToast } from "../../components/Toast";

function conversationMessagesToTabMessages(messages: ConversationMessage[]) {
  return messages.map((message, index) => ({
    id: Number(message.id.replace(/\D/g, "")) || index + 1,
    sender: message.role === "user" ? ("user" as const) : ("ai" as const),
    text: message.content,
  }));
}


export function useWorkspaceTabs(onToastParam?: (msg: string) => void) {
  const { toast } = useToast();
  const onToast = onToastParam || toast;
  const [tabs, setTabs] = useState<WorkspaceTab[]>([
    { id: "smart-query", title: "问数工作台", type: "smart-query" }
  ]);
  const [activeTabId, setActiveTabId] = useState("smart-query");
  const [sqlConsoleState, setSqlConsoleState] = useState<Record<string, SqlConsoleTabState>>({});
  const tabSeqRef = useRef({ sql: 1, multiTable: 1, queryResult: 1 });

  const activeTab = tabs.find((tab) => tab.id === activeTabId) || tabs[0];

  const closeTab = useCallback((tabId: string, event?: { stopPropagation: () => void }) => {
    event?.stopPropagation();
    const nextTabs = tabs.filter((tab) => tab.id !== tabId);
    if (nextTabs.length === 0) {
      setTabs([{ id: "smart-query", title: "问数工作台", type: "smart-query" }]);
      setActiveTabId("smart-query");
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      setSqlConsoleState((prev) => { const { [tabId]: _, ...rest } = prev; return rest; });
      return;
    }
    setTabs(nextTabs);
    if (activeTabId === tabId) setActiveTabId(nextTabs[nextTabs.length - 1].id);
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    setSqlConsoleState((prev) => { const { [tabId]: _, ...rest } = prev; return rest; });
  }, [activeTabId, tabs]);

  const openSqlConsole = useCallback((initialSql?: string) => {
    const tabId = `sql-${tabSeqRef.current.sql++}`;
    setTabs((prev) => [...prev, { id: tabId, title: "SQL 控制台", type: "sql" }]);
    setActiveTabId(tabId);
    setSqlConsoleState((prev) => ({
      ...prev,
      [tabId]: { draftSql: initialSql ?? defaultSql, entries: [], running: false },
    }));
    onToast("已打开 SQL 控制台");
  }, [onToast]);

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

  const openAgentEvalTab = useCallback(() => {
    const tabId = "agent-eval";
    setTabs((prev) => (prev.some((tab) => tab.id === tabId) ? prev : [...prev, { id: tabId, title: "Agent 评测", type: "agent-eval" }]));
    setActiveTabId(tabId);
  }, []);

  const openConversationResult = useCallback((conversation: Conversation) => {
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
  }, []);

  const patchTab = useCallback((tabId: string, patch: Partial<WorkspaceTab>) => {
    setTabs((prev) => prev.map((tab) => (tab.id === tabId ? { ...tab, ...patch } : tab)));
  }, []);

  const appendTabMessages = useCallback((tabId: string, messages: NonNullable<WorkspaceTab["chatMessages"]>) => {
    setTabs((prev) => prev.map((tab) => (
      tab.id === tabId ? { ...tab, chatMessages: [...(tab.chatMessages || []), ...messages] } : tab
    )));
  }, []);

  const updateTabMessage = useCallback((tabId: string, messageId: number, text: string) => {
    setTabs((prev) => prev.map((tab) => (
      tab.id === tabId
        ? { ...tab, chatMessages: (tab.chatMessages || []).map((message) => (message.id === messageId ? { ...message, text } : message)) }
        : tab
    )));
  }, []);

  const patchTabTimeline = useCallback((
    tabId: string,
    updater: (items: NonNullable<WorkspaceTab["agentTimeline"]>) => NonNullable<WorkspaceTab["agentTimeline"]>,
  ) => {
    setTabs((prev) => prev.map((tab) => (
      tab.id === tabId ? { ...tab, agentTimeline: updater(tab.agentTimeline || []) } : tab
    )));
  }, []);

  return {
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
  };
}
