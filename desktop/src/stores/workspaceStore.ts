import { create } from "zustand";
import type { WorkspaceTab } from "../mock/dbfoxMock";
import { defaultSql } from "../mock/dbfoxMock";
import type { Conversation, ConversationMessage } from "../types/conversation";
import type { SqlConsoleTabState } from "../features/workspace/SqlConsoleWorkspace";
import {
  deleteConversation,
  listConversations,
  saveConversation,
} from "../features/conversation/conversationRepository";

interface WorkspaceState {
  tabs: WorkspaceTab[];
  activeTabId: string;
  sqlConsoleState: Record<string, SqlConsoleTabState>;
  selectedTables: string[];
  contextTables: string[];
  tableSubTabs: Record<string, string>;
  conversations: Conversation[];
  _tabSeq: { sql: number; multiTable: number; queryResult: number; message: number };
}

interface WorkspaceActions {
  setActiveTabId: (id: string) => void;
  setTabs: (updater: WorkspaceTab[] | ((prev: WorkspaceTab[]) => WorkspaceTab[])) => void;
  closeTab: (tabId: string) => void;
  openSqlConsole: (initialSql?: string) => void;
  openLlmConfigTab: () => void;
  openConnectionManagerTab: () => void;
  openNewConnectionTab: () => void;
  openAgentEvalTab: () => void;
  openDiagnosticsTab: () => void;
  openConversationResult: (conv: Conversation) => void;
  openTableTab: (tableName: string, initialSubtab?: string) => void;
  openMultiTableWorkspace: (tables: string[]) => void;
  openQueryResultTab: (queryText: string) => string | undefined;
  patchTab: (tabId: string, patch: Partial<WorkspaceTab>) => void;
  appendTabMessages: (tabId: string, messages: NonNullable<WorkspaceTab["chatMessages"]>) => void;
  updateTabMessage: (tabId: string, messageId: number, text: string) => void;
  patchTabTimeline: (
    tabId: string,
    updater: (items: NonNullable<WorkspaceTab["agentTimeline"]>) => NonNullable<WorkspaceTab["agentTimeline"]>,
  ) => void;
  setSelectedTables: (tables: string[] | ((prev: string[]) => string[])) => void;
  addContextTable: (name: string) => void;
  removeContextTable: (name: string) => void;
  clearContextTables: () => void;
  setTableSubTabs: (
    updater: Record<string, string> | ((prev: Record<string, string>) => Record<string, string>),
  ) => void;
  persistConversation: (conv: Conversation) => Promise<void>;
  deleteConversationById: (id: string) => Promise<void>;
  initConversations: () => Promise<void>;
  _nextMsgId: () => number;
  _activeTab: () => WorkspaceTab | undefined;
}

export type WorkspaceStore = WorkspaceState & WorkspaceActions;

function conversationMessagesToTabMessages(messages: ConversationMessage[]) {
  return messages.map((message, index) => ({
    id: Number(message.id.replace(/\D/g, "")) || index + 1,
    sender: (message.role === "user" ? "user" : "ai") as "user" | "ai",
    text: message.content,
  }));
}

export const useWorkspaceStore = create<WorkspaceStore>()((set, get) => ({
  tabs: [{ id: "smart-query", title: "问数工作台", type: "smart-query" }],
  activeTabId: "smart-query",
  sqlConsoleState: {},
  selectedTables: [],
  contextTables: [],
  tableSubTabs: {},
  conversations: [],
  _tabSeq: { sql: 1, multiTable: 1, queryResult: 1, message: 1 },

  setActiveTabId: (id) => set({ activeTabId: id }),

  setTabs: (updater) =>
    set((s) => ({ tabs: typeof updater === "function" ? updater(s.tabs) : updater })),

  closeTab: (tabId) => {
    const { tabs, activeTabId } = get();
    const nextTabs = tabs.filter((t) => t.id !== tabId);
    if (nextTabs.length === 0) {
      set((s) => {
        const { [tabId]: _, ...rest } = s.sqlConsoleState;
        return {
          tabs: [{ id: "smart-query", title: "问数工作台", type: "smart-query" }],
          activeTabId: "smart-query",
          sqlConsoleState: rest,
        };
      });
      return;
    }
    set((s) => {
      const { [tabId]: _, ...rest } = s.sqlConsoleState;
      const nextActiveId = activeTabId === tabId ? nextTabs[nextTabs.length - 1].id : activeTabId;
      return {
        tabs: nextTabs,
        activeTabId: nextActiveId,
        sqlConsoleState: rest,
      };
    });
  },

  openSqlConsole: (initialSql) => {
    const seq = get()._tabSeq;
    const tabId = `sql-${seq.sql++}`;
    set({ _tabSeq: { ...seq } });
    set((s) => ({ tabs: [...s.tabs, { id: tabId, title: "SQL 控制台", type: "sql" }], activeTabId: tabId }));
    set((s) => ({
      sqlConsoleState: {
        ...s.sqlConsoleState,
        [tabId]: { draftSql: initialSql ?? defaultSql, entries: [], running: false },
      },
    }));
  },

  openLlmConfigTab: () => {
    const tabId = "llm-config";
    set((s) => ({
      tabs: s.tabs.some((t) => t.id === tabId) ? s.tabs : [...s.tabs, { id: tabId, title: "LLM 配置", type: "llm-config" }],
      activeTabId: tabId,
    }));
  },

  openConnectionManagerTab: () => {
    const tabId = "datasource-settings";
    set((s) => ({
      tabs: s.tabs.some((t) => t.id === tabId)
        ? s.tabs.map((t) => (t.id === tabId ? { ...t, title: "数据源管理" } : t))
        : [...s.tabs, { id: tabId, title: "数据源管理", type: "datasource-settings" }],
      activeTabId: tabId,
    }));
  },

  openNewConnectionTab: () => {
    const tabId = "datasource-settings";
    set((s) => ({
      tabs: s.tabs.some((t) => t.id === tabId)
        ? s.tabs.map((t) => (t.id === tabId ? { ...t, title: "新建数据源" } : t))
        : [...s.tabs, { id: tabId, title: "新建数据源", type: "datasource-settings" }],
      activeTabId: tabId,
    }));
  },

  openAgentEvalTab: () => {
    const tabId = "agent-eval";
    set((s) => ({
      tabs: s.tabs.some((t) => t.id === tabId) ? s.tabs : [...s.tabs, { id: tabId, title: "Agent 评测", type: "agent-eval" }],
      activeTabId: tabId,
    }));
  },

  openDiagnosticsTab: () => {
    const tabId = "diagnostics";
    set((s) => ({
      tabs: s.tabs.some((t) => t.id === tabId)
        ? s.tabs
        : [...s.tabs, { id: tabId, title: "诊断日志", type: "diagnostics" }],
      activeTabId: tabId,
    }));
  },

  openConversationResult: (conv) => {
    const tabId = `conversation-${conv.id}`;
    const tab: WorkspaceTab = {
      id: tabId,
      title: conv.title,
      type: "query-result",
      queryText: conv.title,
      conversationId: conv.id,
      chatMessages: conversationMessagesToTabMessages(conv.messages),
      artifacts: conv.artifacts,
    };
    set((s) => ({
      tabs: s.tabs.some((t) => t.id === tabId) ? s.tabs.map((t) => (t.id === tabId ? tab : t)) : [...s.tabs, tab],
      activeTabId: tabId,
    }));
  },

  openTableTab: (tableName, initialSubtab = "preview") => {
    const tabId = `table-${tableName}`;
    set((s) => ({
      tabs: s.tabs.some((t) => t.id === tabId)
        ? s.tabs
        : [...s.tabs, { id: tabId, title: tableName, type: "table", tableId: tableName }],
      activeTabId: tabId,
      selectedTables: [tableName],
    }));
    if (initialSubtab) {
      set((s) => ({ tableSubTabs: { ...s.tableSubTabs, [tableName]: initialSubtab } }));
    }
  },

  openMultiTableWorkspace: (tables) => {
    if (tables.length === 0) return;
    const seq = get()._tabSeq;
    const tabId = `multi-table-${seq.multiTable++}`;
    set({ _tabSeq: { ...seq } });
    const title = `Workspace: ${tables.slice(0, 2).join(" & ")}${tables.length > 2 ? "..." : ""}`;
    set((s) => ({
      tabs: [...s.tabs, { id: tabId, title, type: "multi-table", selectedTables: tables }],
      activeTabId: tabId,
    }));
  },

  openQueryResultTab: (queryText) => {
    const text = queryText.trim();
    if (!text) return undefined;
    const seq = get()._tabSeq;
    const nextId = seq.queryResult++;
    set({ _tabSeq: { ...seq } });
    const tabId = `query-result-${nextId}`;
    const msgId = seq.message++;
    set((s) => ({
      tabs: [
        ...s.tabs,
        {
          id: tabId,
          title: text.length > 30 ? text.slice(0, 30) + "…" : text,
          type: "query-result",
          queryText: text,
          conversationId: `conversation-${nextId}`,
          chatMessages: [{ id: msgId, sender: "user", text }],
          artifacts: [],
        },
      ],
      activeTabId: tabId,
    }));
    return tabId;
  },

  patchTab: (tabId, patch) =>
    set((s) => ({ tabs: s.tabs.map((t) => (t.id === tabId ? { ...t, ...patch } : t)) })),

  appendTabMessages: (tabId, messages) =>
    set((s) => ({
      tabs: s.tabs.map((t) =>
        t.id === tabId ? { ...t, chatMessages: [...(t.chatMessages || []), ...messages] } : t,
      ),
    })),

  updateTabMessage: (tabId, messageId, text) =>
    set((s) => ({
      tabs: s.tabs.map((t) =>
        t.id === tabId
          ? {
              ...t,
              chatMessages: (t.chatMessages || []).map((m) =>
                m.id === messageId ? { ...m, text } : m,
              ),
            }
          : t,
      ),
    })),

  patchTabTimeline: (tabId, updater) =>
    set((s) => ({
      tabs: s.tabs.map((t) =>
        t.id === tabId ? { ...t, agentTimeline: updater(t.agentTimeline || []) } : t,
      ),
    })),

  setSelectedTables: (tables) =>
    set((s) => ({
      selectedTables: typeof tables === "function" ? tables(s.selectedTables) : tables,
    })),

  addContextTable: (name) =>
    set((s) => ({
      contextTables: s.contextTables.includes(name) ? s.contextTables : [...s.contextTables, name],
    })),

  removeContextTable: (name) =>
    set((s) => ({ contextTables: s.contextTables.filter((t) => t !== name) })),

  clearContextTables: () => set({ contextTables: [] }),

  setTableSubTabs: (updater) =>
    set((s) => ({
      tableSubTabs: typeof updater === "function" ? updater(s.tableSubTabs) : updater,
    })),

  persistConversation: async (conv) => {
    try {
      await saveConversation(conv);
      set((s) => ({
        conversations: [conv, ...s.conversations.filter((c) => c.id !== conv.id)].sort(
          (a, b) => b.updatedAt - a.updatedAt,
        ),
      }));
    } catch (err) {
      console.error("persistConversation failed:", err);
    }
  },

  deleteConversationById: async (id) => {
    try {
      await deleteConversation(id);
      set((s) => ({ conversations: s.conversations.filter((c) => c.id !== id) }));
    } catch (err) {
      console.error("deleteConversationById failed:", err);
    }
  },

  initConversations: async () => {
    // Legacy Tauri rusqlite conversation migration has been removed.
    // Set the flag so any residual migration check is a no-op.
    if (typeof window !== "undefined") {
      localStorage.setItem("dbfox_legacy_conversations_migrated", "true");
    }
    try {
      const history = await listConversations();
      set({ conversations: history });
    } catch (err) {
      console.error("initConversations failed:", err);
    }
  },

  _nextMsgId: () => {
    const seq = get()._tabSeq;
    const id = seq.message++;
    set({ _tabSeq: { ...seq } });
    return id;
  },

  _activeTab: () => {
    const { tabs, activeTabId } = get();
    return tabs.find((t) => t.id === activeTabId) || tabs[0];
  },
}));
