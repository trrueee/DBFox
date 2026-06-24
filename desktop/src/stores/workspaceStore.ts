import { create } from "zustand";
import type { WorkspaceTab } from "../types/workspace";
import { defaultSql } from "../features/workspace/defaultSql";
import type { SqlConsoleTabState } from "../features/workspace/SqlConsoleWorkspace";
import type { ConversationSummary } from "../types/conversation";
import type { TableArtifact, ResultViewArtifact } from "../types/agentArtifact";

interface WorkspaceState {
  tabs: WorkspaceTab[];
  activeTabId: string;
  sqlConsoleState: Record<string, SqlConsoleTabState>;
  selectedTables: string[];
  contextTables: string[];
  tableSubTabs: Record<string, string>;
  _tabSeq: { sql: number; multiTable: number; queryResult: number; message: number };
}

interface TableTabDatasourceContext {
  id: string;
  dbType?: string | null;
}

interface WorkspaceActions {
  setActiveTabId: (id: string) => void;
  setTabs: (updater: WorkspaceTab[] | ((prev: WorkspaceTab[]) => WorkspaceTab[])) => void;
  closeTab: (tabId: string) => void;
  openSqlConsole: (initialSql?: string) => void;
  openLlmConfigTab: () => void;
  openConversationHistoryTab: () => void;
  openSmartQueryTab: () => void;
  openConnectionManagerTab: () => void;
  openNewConnectionTab: () => void;
  openAgentEvalTab: () => void;
  openDiagnosticsTab: () => void;
  openConversationResult: (conv: Pick<ConversationSummary, "id" | "title">) => void;
  openArtifactResultTab: (artifact: TableArtifact | ResultViewArtifact) => void;
  openTableTab: (tableName: string, initialSubtab?: string, datasource?: TableTabDatasourceContext) => void;
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
  _nextMsgId: () => number;
  _activeTab: () => WorkspaceTab | undefined;
}

export type WorkspaceStore = WorkspaceState & WorkspaceActions;

const HOME_TAB: WorkspaceTab = { id: "smart-query", title: "智能问数", type: "smart-query" };

function tableTabId(tableName: string, datasource?: TableTabDatasourceContext) {
  return datasource?.id ? `table-${datasource.id}-${tableName}` : `table-${tableName}`;
}

export const useWorkspaceStore = create<WorkspaceStore>()((set, get) => ({
  tabs: [HOME_TAB],
  activeTabId: HOME_TAB.id,
  sqlConsoleState: {},
  selectedTables: [],
  contextTables: [],
  tableSubTabs: {},
  _tabSeq: { sql: 1, multiTable: 1, queryResult: 1, message: 1 },

  setActiveTabId: (id) => set({ activeTabId: id }),

  setTabs: (updater) =>
    set((state) => ({ tabs: typeof updater === "function" ? updater(state.tabs) : updater })),

  closeTab: (tabId) => {
    const { tabs, activeTabId } = get();
    const nextTabs = tabs.filter((tab) => tab.id !== tabId);
    set((state) => {
      const { [tabId]: _closed, ...sqlConsoleState } = state.sqlConsoleState;
      void _closed;
      if (nextTabs.length === 0) {
        return { tabs: [HOME_TAB], activeTabId: HOME_TAB.id, sqlConsoleState };
      }
      return {
        tabs: nextTabs,
        activeTabId: activeTabId === tabId ? nextTabs[nextTabs.length - 1].id : activeTabId,
        sqlConsoleState,
      };
    });
  },

  openSqlConsole: (initialSql) => {
    const seq = get()._tabSeq;
    const tabId = `sql-${seq.sql++}`;
    set({ _tabSeq: { ...seq } });
    set((state) => ({
      tabs: [...state.tabs, { id: tabId, title: "SQL 控制台", type: "sql" }],
      activeTabId: tabId,
      sqlConsoleState: {
        ...state.sqlConsoleState,
        [tabId]: { draftSql: initialSql ?? defaultSql, entries: [], running: false },
      },
    }));
  },

  openLlmConfigTab: () => {
    const tabId = "llm-config";
    set((state) => ({
      tabs: state.tabs.some((tab) => tab.id === tabId)
        ? state.tabs
        : [...state.tabs, { id: tabId, title: "LLM 配置", type: "llm-config" }],
      activeTabId: tabId,
    }));
  },

  openConversationHistoryTab: () => {
    const tabId = "conversation-history";
    set((state) => ({
      tabs: state.tabs.some((tab) => tab.id === tabId)
        ? state.tabs
        : [...state.tabs, { id: tabId, title: "历史记录", type: "conversation-history" }],
      activeTabId: tabId,
    }));
  },

  openSmartQueryTab: () => {
    set((state) => ({
      tabs: state.tabs.some((tab) => tab.id === HOME_TAB.id) ? state.tabs : [HOME_TAB, ...state.tabs],
      activeTabId: HOME_TAB.id,
    }));
  },

  openConnectionManagerTab: () => {
    const tabId = "datasource-settings";
    set((state) => ({
      tabs: state.tabs.some((tab) => tab.id === tabId)
        ? state.tabs.map((tab) => (tab.id === tabId ? { ...tab, title: "数据源管理" } : tab))
        : [...state.tabs, { id: tabId, title: "数据源管理", type: "datasource-settings" }],
      activeTabId: tabId,
    }));
  },

  openNewConnectionTab: () => {
    const tabId = "datasource-settings";
    set((state) => ({
      tabs: state.tabs.some((tab) => tab.id === tabId)
        ? state.tabs.map((tab) => (tab.id === tabId ? { ...tab, title: "新建数据源" } : tab))
        : [...state.tabs, { id: tabId, title: "新建数据源", type: "datasource-settings" }],
      activeTabId: tabId,
    }));
  },

  openAgentEvalTab: () => {
    const tabId = "agent-eval";
    set((state) => ({
      tabs: state.tabs.some((tab) => tab.id === tabId)
        ? state.tabs
        : [...state.tabs, { id: tabId, title: "Agent 评估", type: "agent-eval" }],
      activeTabId: tabId,
    }));
  },

  openDiagnosticsTab: () => {
    const tabId = "diagnostics";
    set((state) => ({
      tabs: state.tabs.some((tab) => tab.id === tabId)
        ? state.tabs
        : [...state.tabs, { id: tabId, title: "诊断日志", type: "diagnostics" }],
      activeTabId: tabId,
    }));
  },

  openConversationResult: (conv) => {
    const tabId = `conversation-${conv.id}`;
    set((state) => ({
      tabs: state.tabs.some((tab) => tab.id === tabId)
        ? state.tabs
        : [...state.tabs, { id: tabId, title: conv.title, type: "query-result", conversationId: conv.id }],
      activeTabId: tabId,
    }));
  },

  openArtifactResultTab: (artifact) => {
    const tabId = `artifact-result-${artifact.id}`;
    set((state) => ({
      tabs: state.tabs.some((tab) => tab.id === tabId)
        ? state.tabs.map((tab) =>
            tab.id === tabId ? { ...tab, title: artifact.title, artifactResult: artifact } : tab,
          )
        : [...state.tabs, { id: tabId, title: artifact.title, type: "artifact-result", artifactResult: artifact }],
      activeTabId: tabId,
    }));
  },

  openTableTab: (tableName, initialSubtab = "preview", datasource) => {
    const tabId = tableTabId(tableName, datasource);
    set((state) => ({
      tabs: state.tabs.some((tab) => tab.id === tabId)
        ? state.tabs
        : [
            ...state.tabs,
            {
              id: tabId,
              title: tableName,
              type: "table",
              tableId: tableName,
              datasourceId: datasource?.id,
              datasourceDbType: datasource?.dbType ?? null,
            },
          ],
      activeTabId: tabId,
      selectedTables: [tableName],
      tableSubTabs: initialSubtab
        ? { ...state.tableSubTabs, [tabId]: initialSubtab }
        : state.tableSubTabs,
    }));
  },

  openMultiTableWorkspace: (tables) => {
    if (tables.length === 0) return;
    const seq = get()._tabSeq;
    const tabId = `multi-table-${seq.multiTable++}`;
    set({ _tabSeq: { ...seq } });
    const title = `Workspace: ${tables.slice(0, 2).join(" & ")}${tables.length > 2 ? "..." : ""}`;
    set((state) => ({
      tabs: [...state.tabs, { id: tabId, title, type: "multi-table", selectedTables: tables }],
      activeTabId: tabId,
    }));
  },

  openQueryResultTab: (queryText) => {
    const text = queryText.trim();
    if (!text) return undefined;
    const seq = get()._tabSeq;
    const nextId = seq.queryResult++;
    const msgId = seq.message++;
    set({ _tabSeq: { ...seq } });
    const tabId = `query-result-${nextId}`;
    set((state) => ({
      tabs: [
        ...state.tabs,
        {
          id: tabId,
          title: text.length > 30 ? `${text.slice(0, 30)}...` : text,
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
    set((state) => ({
      tabs: state.tabs.map((tab) => (tab.id === tabId ? { ...tab, ...patch } : tab)),
    })),

  appendTabMessages: (tabId, messages) =>
    set((state) => ({
      tabs: state.tabs.map((tab) =>
        tab.id === tabId ? { ...tab, chatMessages: [...(tab.chatMessages || []), ...messages] } : tab,
      ),
    })),

  updateTabMessage: (tabId, messageId, text) =>
    set((state) => ({
      tabs: state.tabs.map((tab) =>
        tab.id === tabId
          ? {
              ...tab,
              chatMessages: (tab.chatMessages || []).map((message) =>
                message.id === messageId ? { ...message, text } : message,
              ),
            }
          : tab,
      ),
    })),

  patchTabTimeline: (tabId, updater) =>
    set((state) => ({
      tabs: state.tabs.map((tab) =>
        tab.id === tabId ? { ...tab, agentTimeline: updater(tab.agentTimeline || []) } : tab,
      ),
    })),

  setSelectedTables: (tables) =>
    set((state) => ({
      selectedTables: typeof tables === "function" ? tables(state.selectedTables) : tables,
    })),

  addContextTable: (name) =>
    set((state) => ({
      contextTables: state.contextTables.includes(name) ? state.contextTables : [...state.contextTables, name],
    })),

  removeContextTable: (name) =>
    set((state) => ({ contextTables: state.contextTables.filter((table) => table !== name) })),

  clearContextTables: () => set({ contextTables: [] }),

  setTableSubTabs: (updater) =>
    set((state) => ({
      tableSubTabs: typeof updater === "function" ? updater(state.tableSubTabs) : updater,
    })),

  _nextMsgId: () => {
    const seq = get()._tabSeq;
    const id = seq.message++;
    set({ _tabSeq: { ...seq } });
    return id;
  },

  _activeTab: () => {
    const { tabs, activeTabId } = get();
    return tabs.find((tab) => tab.id === activeTabId) || tabs[0];
  },
}));
