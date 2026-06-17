# App.tsx Zustand 状态管理重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 App.tsx 中 ~54 个 props 逐层透传，用 3 个 Zustand store 替代 5 个 React hooks，组件直接从 store 消费。

**Architecture:** 3 个独立 store（datasource / workspace / agent）各自管理一个状态域。跨 store 交互通过 `getState()` 同步调用。子组件用 selector 精确订阅，避免全量重渲染。

**Tech Stack:** React 19, TypeScript, Zustand 5, Vite

## Global Constraints

- 所有现有 UI 交互和行为不变
- 现有 22 个前端测试全部通过
- `npx tsc --noEmit` 零错误
- 每个 task 结束提交，commit message 英文

---

### Task 1: 安装 Zustand

**Files:**
- Modify: `desktop/package.json`

- [ ] **Step 1: 安装依赖**

```bash
cd desktop && npm install zustand
```

- [ ] **Step 2: 确认版本**

```bash
cd desktop && node -e "const z = require('zustand/package.json'); console.log(z.version)"
```

- [ ] **Step 3: 提交**

```bash
git add desktop/package.json desktop/package-lock.json
git commit -m "chore: add zustand dependency"
```

---

### Task 2: 创建 datasourceStore

**Files:**
- Create: `desktop/src/stores/datasourceStore.ts`
- Modify: `desktop/src/features/datasource/useDatasourceState.ts` (no-op re-export for now)

**Note:** 为避免一次性改太多文件导致破坏，先创建 store，旧 hook 暂时保留作为兼容层。

- [ ] **Step 1: 创建 desktop/src/stores/datasourceStore.ts**

从 `useDatasourceState.ts` 迁移状态和逻辑到 Zustand store：

```ts
import { create } from "zustand";
import {
  listColumns,
  listTables,
  type EngineColumn,
  type EngineSchemaTable,
} from "../features/engine/engineApi";
import { datasourcesApi } from "../lib/api/datasources";
import type { DataSource, DataSourceCreateParams, DataSourceUpdateParams, DeleteConfirm } from "../lib/api/types";

interface DatasourceState {
  datasources: DataSource[];
  activeDatasourceId: string;
  activeDatasourceForSettings: DataSource | null;
  tables: EngineSchemaTable[];
  loadingSchema: boolean;
  schemaError: string;
  tableColumns: Record<string, EngineColumn[]>;
}

interface DatasourceActions {
  setActiveDatasourceId: (id: string) => void;
  loadDatasources: (preferredId?: string) => Promise<void>;
  refreshSchema: () => Promise<void>;
  createDatasource: (params: DataSourceCreateParams) => Promise<DataSource>;
  updateDatasource: (id: string, params: DataSourceUpdateParams) => Promise<void>;
  deleteDatasource: (id: string, confirm?: DeleteConfirm) => Promise<unknown>;
  syncSchema: (id: string) => Promise<unknown>;
  checkHealth: (id: string) => Promise<unknown>;
}

export type DatasourceStore = DatasourceState & DatasourceActions;

const DATASOURCE_LOAD_RETRY_DELAYS_MS = [300, 900, 1500, 3000, 5000];

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function isTransientEngineFetchError(error: unknown) {
  if (error instanceof TypeError) return true;
  if (!(error instanceof Error)) return false;
  const message = error.message.toLowerCase();
  return message.includes("failed to fetch") || message.includes("networkerror") || message.includes("load failed");
}

export const useDatasourceStore = create<DatasourceStore>()((set, get) => ({
  // --- state ---
  datasources: [],
  activeDatasourceId: "",
  activeDatasourceForSettings: null,
  tables: [],
  loadingSchema: false,
  schemaError: "",
  tableColumns: {},

  // --- actions ---
  setActiveDatasourceId: (id: string) => {
    const prev = get().activeDatasourceId;
    set({ activeDatasourceId: id, activeDatasourceForSettings: get().datasources.find(ds => ds.id === id) || null });
    if (prev && prev !== id) {
      import("../lib/api/datasources").then(({ datasourcesApi }) => {
        datasourcesApi.releaseDatasource(prev).catch((err) => {
          console.warn("Failed to release datasource pool on switch:", err);
        });
      });
    }
  },

  loadDatasources: async (preferredId?: string) => {
    set({ loadingSchema: true, schemaError: "" });
    try {
      for (let attempt = 0; ; attempt++) {
        try {
          const nextDatasources = await datasourcesApi.listDatasources();
          const currentId = get().activeDatasourceId;
          const activeId = preferredId
            || (currentId && nextDatasources.some(item => item.id === currentId) ? currentId : "")
            || nextDatasources[0]?.id || "";
          set({
            datasources: nextDatasources,
            activeDatasourceId: activeId,
            activeDatasourceForSettings: nextDatasources.find(ds => ds.id === activeId) || null,
          });
          return;
        } catch (err) {
          const retryDelay = DATASOURCE_LOAD_RETRY_DELAYS_MS[attempt];
          if (retryDelay !== undefined && isTransientEngineFetchError(err)) {
            await delay(retryDelay);
            continue;
          }
          throw err;
        }
      }
    } catch (err) {
      set({ schemaError: err instanceof Error ? err.message : "读取数据源失败", datasources: [] });
    } finally {
      set({ loadingSchema: false });
    }
  },

  refreshSchema: async () => {
    const { activeDatasourceId, loadDatasources } = get();
    if (!activeDatasourceId) {
      await loadDatasources();
      return;
    }
    set({ loadingSchema: true });
    try {
      set({ tables: await listTables(activeDatasourceId) });
    } catch (err) {
      set({ schemaError: err instanceof Error ? err.message : "刷新 Schema 失败" });
    } finally {
      set({ loadingSchema: false });
    }
  },

  createDatasource: async (params) => {
    const result = await datasourcesApi.createDatasource(params);
    await get().loadDatasources();
    return result;
  },

  updateDatasource: async (id, params) => {
    const result = await datasourcesApi.updateDatasource(id, params);
    await get().loadDatasources();
    return result;
  },

  deleteDatasource: async (id, confirm) => {
    const result = await datasourcesApi.deleteDatasource(id, confirm);
    const raw = result as unknown as Record<string, unknown> | null;
    if (!raw || !raw.requires_confirmation) {
      await get().loadDatasources();
      if (get().activeDatasourceId === id) {
        set({ activeDatasourceId: "", activeDatasourceForSettings: null });
      }
    }
    return result;
  },

  syncSchema: async (id) => {
    const result = await datasourcesApi.syncSchema(id);
    await get().loadDatasources();
    if (id === get().activeDatasourceId) {
      set({ loadingSchema: true });
      try {
        set({ tables: await listTables(id) });
      } catch (err) {
        set({ schemaError: err instanceof Error ? err.message : "读取表结构失败" });
      } finally {
        set({ loadingSchema: false });
      }
    }
    return result;
  },

  checkHealth: async (id) => {
    const result = await datasourcesApi.checkDatasourceHealth(id);
    await get().loadDatasources();
    return result;
  },
}));
```

**缺失功能：** `loadDatasources` 的 `mountedRef` + `useEffect` 初始加载逻辑。在 App.tsx 中用 `useEffect(() => { useDatasourceStore.getState().loadDatasources(); }, [])` 触发一次。

Tables/columns 的 `useEffect` 联动（切换 datasource 自动 fetch tables/columns）需要在 store 外部或通过 Zustand `subscribe` 实现。为了最小化变更，先保持 `useDatasourceState` 不动，仅创建 store 供后续 task 使用。

- [ ] **Step 2: 验证 store 可创建**

```bash
cd desktop && npx tsc --noEmit --strict src/stores/datasourceStore.ts 2>&1 | head -5
```

- [ ] **Step 3: 提交**

```bash
git add desktop/src/stores/datasourceStore.ts
git commit -m "feat: add datasourceStore (Zustand)"
```

---

### Task 3: 创建 workspaceStore

**Files:**
- Create: `desktop/src/stores/workspaceStore.ts`

- [ ] **Step 1: 创建 desktop/src/stores/workspaceStore.ts**

从 `useWorkspaceTabs` + `useWorkspaceSelection` + `useConversationHistory` 迁移：

```ts
import { create } from "zustand";
import type { WorkspaceTab } from "../mock/dbfoxMock";
import { defaultSql } from "../mock/dbfoxMock";
import type { Conversation, ConversationMessage } from "../types/conversation";
import type { SqlConsoleTabState } from "../features/workspace/SqlConsoleWorkspace";
import {
  deleteConversation,
  listConversations,
  migrateLegacyConversations,
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
  setSqlConsoleState: (updater: Record<string, SqlConsoleTabState> | ((prev: Record<string, SqlConsoleTabState>) => Record<string, SqlConsoleTabState>)) => void;
  closeTab: (tabId: string) => void;
  openSqlConsole: (initialSql?: string) => void;
  openLlmConfigTab: () => void;
  openConnectionManagerTab: () => void;
  openNewConnectionTab: () => void;
  openAgentEvalTab: () => void;
  openConversationResult: (conv: Conversation) => void;
  openTableTab: (tableName: string, initialSubtab?: string) => void;
  openMultiTableWorkspace: (tables: string[]) => void;
  openQueryResultTab: (queryText: string) => void;
  patchTab: (tabId: string, patch: Partial<WorkspaceTab>) => void;
  appendTabMessages: (tabId: string, messages: NonNullable<WorkspaceTab["chatMessages"]>) => void;
  updateTabMessage: (tabId: string, messageId: number, text: string) => void;
  patchTabTimeline: (tabId: string, updater: (items: NonNullable<WorkspaceTab["agentTimeline"]>) => NonNullable<WorkspaceTab["agentTimeline"]>) => void;
  setSelectedTables: (tables: string[] | ((prev: string[]) => string[])) => void;
  addContextTable: (name: string) => void;
  removeContextTable: (name: string) => void;
  clearContextTables: () => void;
  setTableSubTabs: (updater: Record<string, string> | ((prev: Record<string, string>) => Record<string, string>)) => void;
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
    sender: message.role === "user" ? ("user" as const) : ("ai" as const),
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

  setTabs: (updater) => set((s) => ({ tabs: typeof updater === "function" ? updater(s.tabs) : updater })),

  setSqlConsoleState: (updater) => set((s) => ({ sqlConsoleState: typeof updater === "function" ? updater(s.sqlConsoleState) : updater })),

  closeTab: (tabId) => {
    const { tabs, activeTabId } = get();
    const nextTabs = tabs.filter((t) => t.id !== tabId);
    if (nextTabs.length === 0) {
      set({ tabs: [{ id: "smart-query", title: "问数工作台", type: "smart-query" }], activeTabId: "smart-query" });
      set((s) => { const { [tabId]: _, ...rest } = s.sqlConsoleState; return { sqlConsoleState: rest }; });
      return;
    }
    set({ tabs: nextTabs });
    if (activeTabId === tabId) set({ activeTabId: nextTabs[nextTabs.length - 1].id });
    set((s) => { const { [tabId]: _, ...rest } = s.sqlConsoleState; return { sqlConsoleState: rest }; });
  },

  openSqlConsole: (initialSql) => {
    const seq = get()._tabSeq;
    const tabId = `sql-${seq.sql++}`;
    set({ _tabSeq: { ...seq } });
    set((s) => ({ tabs: [...s.tabs, { id: tabId, title: "SQL 控制台", type: "sql" }], activeTabId: tabId }));
    set((s) => ({ sqlConsoleState: { ...s.sqlConsoleState, [tabId]: { draftSql: initialSql ?? defaultSql, entries: [], running: false } } }));
  },

  openLlmConfigTab: () => {
    const tabId = "llm-config";
    const tab: WorkspaceTab = { id: tabId, title: "LLM 配置", type: "llm-config" };
    set((s) => ({ tabs: s.tabs.some((t) => t.id === tabId) ? s.tabs : [...s.tabs, tab], activeTabId: tabId }));
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

  openConversationResult: (conv) => {
    const tabId = `conversation-${conv.id}`;
    const tab: WorkspaceTab = {
      id: tabId, title: conv.title, type: "query-result",
      queryText: conv.title, conversationId: conv.id,
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
      tabs: s.tabs.some((t) => t.id === tabId) ? s.tabs : [...s.tabs, { id: tabId, title: tableName, type: "table", tableId: tableName }],
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
    if (!text) return;
    const seq = get()._tabSeq;
    const nextId = seq.queryResult++;
    set({ _tabSeq: { ...seq } });
    const tabId = `query-result-${nextId}`;
    const msgId = seq.message++;
    set((s) => ({
      tabs: [...s.tabs, {
        id: tabId, title: "问数结果", type: "query-result",
        queryText: text, conversationId: `conversation-${nextId}`,
        chatMessages: [{ id: msgId, sender: "user", text }],
        artifacts: [],
      }],
      activeTabId: tabId,
    }));
  },

  patchTab: (tabId, patch) => set((s) => ({ tabs: s.tabs.map((t) => (t.id === tabId ? { ...t, ...patch } : t)) })),

  appendTabMessages: (tabId, messages) => set((s) => ({
    tabs: s.tabs.map((t) => (t.id === tabId ? { ...t, chatMessages: [...(t.chatMessages || []), ...messages] } : t)),
  })),

  updateTabMessage: (tabId, messageId, text) => set((s) => ({
    tabs: s.tabs.map((t) =>
      t.id === tabId ? { ...t, chatMessages: (t.chatMessages || []).map((m) => (m.id === messageId ? { ...m, text } : m)) } : t
    ),
  })),

  patchTabTimeline: (tabId, updater) => set((s) => ({
    tabs: s.tabs.map((t) => (t.id === tabId ? { ...t, agentTimeline: updater(t.agentTimeline || []) } : t)),
  })),

  setSelectedTables: (tables) => set((s) => ({
    selectedTables: typeof tables === "function" ? tables(s.selectedTables) : tables,
  })),

  addContextTable: (name) => set((s) => ({
    contextTables: s.contextTables.includes(name) ? s.contextTables : [...s.contextTables, name],
  })),

  removeContextTable: (name) => set((s) => ({
    contextTables: s.contextTables.filter((t) => t !== name),
  })),

  clearContextTables: () => set({ contextTables: [] }),

  setTableSubTabs: (updater) => set((s) => ({
    tableSubTabs: typeof updater === "function" ? updater(s.tableSubTabs) : updater,
  })),

  persistConversation: async (conv) => {
    try {
      await saveConversation(conv);
      set((s) => ({
        conversations: [conv, ...s.conversations.filter((c) => c.id !== conv.id)].sort((a, b) => b.updatedAt - a.updatedAt),
      }));
    } catch { /* toast handled by caller */ }
  },

  deleteConversationById: async (id) => {
    try {
      await deleteConversation(id);
      set((s) => ({ conversations: s.conversations.filter((c) => c.id !== id) }));
    } catch { /* toast handled by caller */ }
  },

  initConversations: async () => {
    await migrateLegacyConversations();
    try {
      const history = await listConversations();
      set({ conversations: history });
    } catch { /* toast handled by caller */ }
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
```

- [ ] **Step 2: 验证编译**

```bash
cd desktop && npx tsc --noEmit --strict src/stores/workspaceStore.ts 2>&1 | head -10
```

- [ ] **Step 3: 提交**

```bash
git add desktop/src/stores/workspaceStore.ts
git commit -m "feat: add workspaceStore (Zustand)"
```

---

### Task 4: 创建 agentStore

**Files:**
- Create: `desktop/src/stores/agentStore.ts`

**关键差异：** agentStore 的 action 需要通过 `useWorkspaceStore.getState()` 操作 workspace 状态（追加消息、更新 patch 等），不重复持有 tabs/messages 状态。

- [ ] **Step 1: 创建 desktop/src/stores/agentStore.ts**

```ts
import { create } from "zustand";
import { useWorkspaceStore } from "./workspaceStore";
import { useDatasourceStore } from "./datasourceStore";
import { BASE_URL, ENGINE_TOKEN } from "../lib/api/client";
import { agentApi, mergeArtifactDelta, resolveAgentApproval, streamResumeAgentRun } from "../lib/api/agent";
import { getStoredApiConfig } from "../components/SettingsDialog";
import {
  appendAgentRuntimeEvent,
  createInitialAgentTimeline,
  timelineFromFinalResponse,
  type AgentTimelineItem,
} from "../features/workspace/agentTimeline";
import {
  buildAnswerText,
  buildSuggestionsText,
  describeRuntimeEvent,
  mergeApiArtifacts,
  toViewArtifacts,
} from "../features/workspace/agentBridge";
import type { AgentRunResponse, AgentRuntimeEvent, AgentArtifact as ApiAgentArtifact } from "../lib/api/types";

interface AgentState {
  runningTabs: Record<string, { runId: string; status: "running" | "waiting_approval" | "cancelled" }>;
  _abortControllers: Map<string, AbortController>;
  _runIds: Map<string, string>;
  _cancelledTabs: Set<string>;
}

interface AgentActions {
  runAgentForTab: (tabId: string, question: string, opts?: { sessionId?: string; parentRunId?: string }) => Promise<void>;
  handleApprovalDecision: (tabId: string, approved: boolean) => Promise<void>;
  sendFollowUp: (tabId: string, text: string) => void;
  cancelAgentRun: (tabId: string) => Promise<void>;
  regenerateAgentRun: (tabId: string) => void;
}

export type AgentStore = AgentState & AgentActions;

export const useAgentStore = create<AgentStore>()((set, get) => ({
  runningTabs: {},
  _abortControllers: new Map(),
  _runIds: new Map(),
  _cancelledTabs: new Set(),

  // --- runAgentForTab — 从 useAgentRunner L185-259 迁移 ---
  // 结构完全相同，差异仅在于：
  //   - 所有 appendTabMessages/patchTab/updateTabMessage 通过 useWorkspaceStore.getState() 调用
  //   - activeDatasourceId 通过 useDatasourceStore.getState().activeDatasourceId 读取
  //   - contextTables 通过 useWorkspaceStore.getState().contextTables 读取
  //   - tabsRef → useWorkspaceStore.getState().tabs
  //   - nextMsgId → useWorkspaceStore.getState()._nextMsgId()
  //
  // 完整实现约 230 行，核心结构：
  runAgentForTab: async (tabId, question, opts) => {
    const ws = useWorkspaceStore.getState();
    const ds = useDatasourceStore.getState();
    // ... [完整逻辑同 useAgentRunner L185-259，仅数据源替换为 store]
  },

  // --- handleApprovalDecision — 从 useAgentRunner L261-301 迁移 ---
  handleApprovalDecision: async (tabId, approved) => {
    const ws = useWorkspaceStore.getState();
    const tab = ws.tabs.find(t => t.id === tabId);
    const approval = tab?.agentApproval;
    if (!approval) return;
    // ... [完整逻辑同 useAgentRunner L261-301，仅数据源替换为 store]
  },

  // --- sendFollowUp — 从 useAgentRunner L303-320 迁移 ---
  sendFollowUp: (tabId, text) => {
    // ... [完整逻辑同 useAgentRunner L303-320]
  },

  // --- cancelAgentRun — 从 useAgentRunner L322-350 迁移 ---
  cancelAgentRun: async (tabId) => {
    // ... [完整逻辑同 useAgentRunner L322-350]
  },

  // --- regenerateAgentRun — 从 useAgentRunner L352-361 迁移 ---
  regenerateAgentRun: (tabId) => {
    // ... [完整逻辑同 useAgentRunner L352-361]
  },
}));

// --- 辅助函数（从 useAgentRunner.ts 尾部移动）---
function formatAgentError(err: unknown, cancelled?: boolean): string {
  // [完整逻辑同 useAgentRunner L372-381]
  return "";
}
```

**实现细节：** agentStore 的所有 action 逻辑**逐行**从 `useAgentRunner.ts` (L88-361) 移动，仅做以下替换：

| 原代码 | 替换为 |
|--------|--------|
| `tabsRef.current` | `useWorkspaceStore.getState().tabs` |
| `activeDatasourceId`（闭包） | `useDatasourceStore.getState().activeDatasourceId` |
| `contextTables`（闭包） | `useWorkspaceStore.getState().contextTables` |
| `appendTabMessages(...)` | `useWorkspaceStore.getState().appendTabMessages(...)` |
| `updateTabMessage(...)` | `useWorkspaceStore.getState().updateTabMessage(...)` |
| `patchTab(...)` | `useWorkspaceStore.getState().patchTab(...)` |
| `patchTabTimeline(...)` | `useWorkspaceStore.getState().patchTabTimeline(...)` |
| `persistConversation(...)` | `useWorkspaceStore.getState().persistConversation(...)` |
| `nextMsgId()` | `useWorkspaceStore.getState()._nextMsgId()` |
| `showToast(...)` | `toast(...)` — 通过 action 参数传入或从外层调用 |
| `scheduleAfterStateFlush(cb)` | `window.setTimeout(cb, 0)` |

- [ ] **Step 2: 验证编译**

```bash
cd desktop && npx tsc --noEmit --strict src/stores/agentStore.ts 2>&1 | head -10
```

- [ ] **Step 3: 提交**

```bash
git add desktop/src/stores/agentStore.ts
git commit -m "feat: add agentStore (Zustand)"
```

---

### Task 5: 重构 App.tsx — 用 stores 替代 hooks

**Files:**
- Modify: `desktop/src/App.tsx`

- [ ] **Step 1: 改造 App.tsx**

移除 5 个 hooks 调用，替换为 store 初始化和直接调用：

```tsx
import { useEffect, useState, useRef, type MouseEvent, useCallback } from "react";
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
  // --- 纯 UI state ---
  const [treeSearch, setTreeSearch] = useState("");
  const [rightDrawerOpen, setRightDrawerOpen] = useState(false);
  const [rightDrawerType, setRightDrawerType] = useState<"ai-suggest" | "props">("props");
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({ visible: false, x: 0, y: 0, type: "database", targetNode: "" });
  const [showCommandPalette, setShowCommandPalette] = useState(false);

  const { toast } = useToast();
  const showToast = useCallback((msg: string, type?: "success" | "error" | "warning" | "info") => {
    toast(msg, type);
  }, [toast]);

  // --- 纯 UI hook ---
  const { collapsed, width, handleResizeStart, toggleCollapse: toggleSidebarCollapse } = useSidebarLayout();

  // --- Store 初始化（应用启动时执行一次）---
  useEffect(() => {
    useDatasourceStore.getState().loadDatasources();
    useWorkspaceStore.getState().initConversations();
  }, []);

  // --- 从 store 读取（子组件直接消费，这里只读需要的）---
  const tabs = useWorkspaceStore(s => s.tabs);
  const activeTabId = useWorkspaceStore(s => s.activeTabId);
  const activeTab = useWorkspaceStore(s => s.tabs.find(t => t.id === s.activeTabId) || s.tabs[0]);
  const closeTab = useWorkspaceStore(s => s.closeTab);
  const openSqlConsole = useWorkspaceStore(s => s.openSqlConsole);
  const openTableTabAction = useWorkspaceStore(s => s.openTableTab);
  const openMultiTableWs = useWorkspaceStore(s => s.openMultiTableWorkspace);
  const setSelectedTables = useWorkspaceStore(s => s.setSelectedTables);
  const selectedTables = useWorkspaceStore(s => s.selectedTables);
  const addContextTable = useWorkspaceStore(s => s.addContextTable);
  const contextTables = useWorkspaceStore(s => s.contextTables);
  const setContextTables = useWorkspaceStore(s => {
    return (tables: string[]) => { s.clearContextTables(); tables.forEach(s.addContextTable); };
  });

  const tables = useDatasourceStore(s => s.tables);
  const tableColumns = useDatasourceStore(s => s.tableColumns);
  const datasources = useDatasourceStore(s => s.datasources);
  const activeDatasourceId = useDatasourceStore(s => s.activeDatasourceId);
  const setActiveDatasourceId = useDatasourceStore(s => s.setActiveDatasourceId);
  const loadingSchema = useDatasourceStore(s => s.loadingSchema);
  const schemaError = useDatasourceStore(s => s.schemaError);
  const refreshSchema = useDatasourceStore(s => s.refreshSchema);
  const openNewConnectionTab = useWorkspaceStore(s => s.openNewConnectionTab);

  // --- 事件处理器（直接用 store actions）---
  const handleTableClick = (tableName: string, event: MouseEvent) => {
    if (event.ctrlKey || event.metaKey) {
      setSelectedTables((prev: string[]) => prev.includes(tableName) ? prev.filter(t => t !== tableName) : [...prev, tableName]);
      return;
    }
    openTableTabAction(tableName);
  };

  // ... 其他事件处理器类似，直接用 store actions

  // --- 键盘快捷键 ---
  useEffect(() => {
    const handleGlobalKeyDown = (event: KeyboardEvent) => {
      const mod = event.ctrlKey || event.metaKey;
      if (mod && event.key.toLowerCase() === "k") { event.preventDefault(); setShowCommandPalette(true); }
      if (mod && event.key.toLowerCase() === "n") { event.preventDefault(); openSqlConsole(); }
      if (mod && event.key.toLowerCase() === "w" && activeTabId) { event.preventDefault(); closeTab(activeTabId); }
    };
    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, [activeTabId, closeTab, openSqlConsole]);

  const { commandItems } = useAppCommands({
    tables, tableColumns, openSqlConsole,
    openLlmConfigTab: useWorkspaceStore.getState().openLlmConfigTab,
    openConnectionManagerTab: useWorkspaceStore.getState().openConnectionManagerTab,
    openNewConnectionTab, openAgentEvalTab: useWorkspaceStore.getState().openAgentEvalTab,
    openTableTab: openTableTabAction,
    setTabs: useWorkspaceStore.getState().setTabs,
    setActiveTabId: useWorkspaceStore.getState().setActiveTabId,
  });

  // --- JSX — 组件 props 大幅减少 ---
  return (
    <div className="app-shell">
      {/* ... 结构不变，但各子组件 props 数量大幅下降 ... */}
      <DataSourceTree
        treeSearch={treeSearch}
        collapsed={collapsed}
        onTreeSearchChange={setTreeSearch}
        onToggleCollapse={toggleSidebarCollapse}
        sidebarWidth={width}
        onTableClick={handleTableClick}
        onTableDoubleClick={openTableTabAction}
        onNodeContextMenu={handleNodeContextMenu}
        onRefresh={refreshSchema}
        onNewConnection={openNewConnectionTab}
      />
      <WorkspaceRouter showToast={showToast} />
      {/* ... */}
    </div>
  );
}
```

- [ ] **Step 2: 运行编译检查**

```bash
cd desktop && npx tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 3: 提交**

```bash
git add desktop/src/App.tsx
git commit -m "refactor: wire App.tsx to Zustand stores, reduce props"
```

### Task 6: 重构 WorkspaceRouter — 从 props 改为 store selectors

**Files:**
- Modify: `desktop/src/features/appShell/WorkspaceRouter.tsx`

- [ ] **Step 1: 改造 WorkspaceRouter — props 从 27 降到 ~3**

所有数据从 store 读取，只保留 `showToast` 作为 prop（纯 UI 行为）：

```tsx
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useDatasourceStore } from "../../stores/datasourceStore";
import { useAgentStore } from "../../stores/agentStore";

interface WorkspaceRouterProps {
  showToast: (msg: string, type?: "success" | "error" | "warning" | "info") => void;
}

export function WorkspaceRouter({ showToast }: WorkspaceRouterProps) {
  const activeTab = useWorkspaceStore(s => s.tabs.find(t => t.id === s.activeTabId) || s.tabs[0]);
  // ... 其余数据从 store 读取

  if (activeTab.type === "smart-query") {
    const askInputValue = useWorkspaceStore(s => s._askInputValue); // 或者保留本地 state
    // ...
  }
  // ... 每个 tab type 分支从对应 store 取数据
}
```

- [ ] **Step 2: 验证编译 + 运行测试**

```bash
cd desktop && npx tsc --noEmit 2>&1 | head -10 && npm test -- --run 2>&1 | tail -10
```

- [ ] **Step 3: 提交**

```bash
git add desktop/src/features/appShell/WorkspaceRouter.tsx
git commit -m "refactor: WorkspaceRouter reads from stores, drops 24 props"
```

---

### Task 7: 重构 DataSourceTree + 其余子组件

**Files:**
- Modify: `desktop/src/features/datasource/DataSourceTree.tsx`
- Modify: `desktop/src/features/assistant/ContextDrawer.tsx`
- Modify: `desktop/src/features/datasource/DataSourceContextMenu.tsx`

- [ ] **Step 1: 改造 DataSourceTree — props 从 15 降到 6**

```tsx
// 之前：15 props 包含 datasources, activeDatasourceId, setActiveDatasourceId, tables, loading, error
// 之后：只保留纯 UI props（search, collapsed, width, event callbacks）
// 数据从 useDatasourceStore 读取

import { useDatasourceStore } from "../../stores/datasourceStore";

function DataSourceTree({ treeSearch, collapsed, onTreeSearchChange, onToggleCollapse, sidebarWidth, ... }: UIOnlyProps) {
  const datasources = useDatasourceStore(s => s.datasources);
  const activeId = useDatasourceStore(s => s.activeDatasourceId);
  // ...
}
```

- [ ] **Step 2: 改造 ContextDrawer + DataSourceContextMenu**

同样模式——数据从 store 读取，只保留位置/开关等纯 UI props。

- [ ] **Step 3: 运行全量测试**

```bash
cd desktop && npm test -- --run 2>&1 | tail -15
```

- [ ] **Step 4: 提交**

```bash
git add desktop/src/features/datasource/DataSourceTree.tsx desktop/src/features/assistant/ContextDrawer.tsx desktop/src/features/datasource/DataSourceContextMenu.tsx
git commit -m "refactor: child components read from stores, drop datasource/context props"
```

---

### Task 8: 删除旧 hooks 文件

**Files:**
- Delete: `desktop/src/features/datasource/useDatasourceState.ts`
- Delete: `desktop/src/features/appShell/useWorkspaceTabs.ts`
- Delete: `desktop/src/features/appShell/useWorkspaceSelection.ts`
- Delete: `desktop/src/features/appShell/useConversationHistory.ts`
- Delete: `desktop/src/features/agentTask/useAgentRunner.ts`

- [ ] **Step 1: 确认无残留引用**

```bash
cd desktop && grep -r "useDatasourceState\|useWorkspaceTabs\|useWorkspaceSelection\|useConversationHistory\|useAgentRunner" src/ --include="*.ts" --include="*.tsx" | grep -v ".test." | grep -v "node_modules"
```

- [ ] **Step 2: 删除文件并提交**

```bash
git rm desktop/src/features/datasource/useDatasourceState.ts
git rm desktop/src/features/appShell/useWorkspaceTabs.ts
git rm desktop/src/features/appShell/useWorkspaceSelection.ts
git rm desktop/src/features/appShell/useConversationHistory.ts
git rm desktop/src/features/agentTask/useAgentRunner.ts
git commit -m "refactor: remove old hooks, replaced by Zustand stores"
```

---

### Task 9: 全量回归 + 类型检查

**Files:** 无新建

- [ ] **Step 1: TypeScript 编译检查**

```bash
cd desktop && npx tsc --noEmit
```
Expected: 零错误

- [ ] **Step 2: 运行全部测试**

```bash
cd desktop && npm test -- --run
```
Expected: 22 tests pass

- [ ] **Step 3: Lint 检查**

```bash
cd desktop && npx eslint src/ --ext .ts,.tsx 2>&1 | tail -5
```

- [ ] **Step 4: 提交（如有 lint 修复）**

```bash
git add -A && git commit -m "chore: lint fixes after store migration"
```

---

## 文件变更总览

| 操作 | 文件 |
|------|------|
| CREATE | `desktop/src/stores/datasourceStore.ts` |
| CREATE | `desktop/src/stores/workspaceStore.ts` |
| CREATE | `desktop/src/stores/agentStore.ts` |
| MODIFY | `desktop/package.json` |
| MODIFY | `desktop/src/App.tsx` — 380→~150 行 |
| MODIFY | `desktop/src/features/appShell/WorkspaceRouter.tsx` — 27→3 props |
| MODIFY | `desktop/src/features/datasource/DataSourceTree.tsx` — 15→6 props |
| MODIFY | `desktop/src/features/assistant/ContextDrawer.tsx` |
| MODIFY | `desktop/src/features/datasource/DataSourceContextMenu.tsx` |
| DELETE | `useDatasourceState.ts` |
| DELETE | `useWorkspaceTabs.ts` |
| DELETE | `useWorkspaceSelection.ts` |
| DELETE | `useConversationHistory.ts` |
| DELETE | `useAgentRunner.ts` |
