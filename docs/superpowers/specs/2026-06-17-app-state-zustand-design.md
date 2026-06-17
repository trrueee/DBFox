# Design Doc: App.tsx 状态管理重构 — Zustand

**日期:** 2026-06-17  
**状态:** 待评审  
**关联:** `docs/软件重构和测试.md` — C3/Phase 2

## 目标

消除 App.tsx 中 ~54 个 props 的逐层透传（prop drilling），将业务状态从组件树中剥离到 Zustand stores。子组件直接从 store 消费，不再通过 props 接收数据。

**不改外部行为**：所有 UI 交互、API 调用、SSE 流式逻辑保持不变。纯架构重构。

---

## 方案：Zustand（3 个 store）

选择 Zustand 的理由：
- 组件级 selector 避免全量重渲染（vs React Context 的缺陷）
- 零 Provider 嵌套，直接 `import { useStore } from "./store"` 即可
- `persist` 中间件为后续持久化需求（窗口布局、用户偏好、ConfirmationManager 持久化）留好基础
- ~1KB gzipped，API 和 Context 一样简单

### Store 架构

```
desktop/src/stores/
├── datasourceStore.ts
├── workspaceStore.ts
└── agentStore.ts
```

3 个 store 各自独立，无交叉依赖。agentStore 需要访问 workspaceStore 时通过 `useWorkspaceStore.getState()` 直接调用。

---

## Store 1: datasourceStore

替代 `useDatasourceState()` + App.tsx 中的 `prevDatasourceIdRef` 逻辑。

### State

```ts
interface DatasourceState {
  datasources: DataSource[];
  activeDatasourceId: string;
  activeDatasourceForSettings: DataSource | null;
  tables: SchemaTable[];
  tableColumns: Record<string, SchemaColumn[]>;
  loadingSchema: boolean;
  schemaError: string | null;
}
```

### Actions

```ts
interface DatasourceActions {
  setActiveDatasourceId: (id: string) => void;
  loadDatasources: (preferredId?: string) => Promise<void>;
  refreshSchema: () => Promise<void>;
  createDatasource: (params: DataSourceCreateParams) => Promise<DataSource>;
  updateDatasource: (id: string, params: DataSourceUpdateParams) => Promise<void>;
  deleteDatasource: (id: string) => Promise<void>;
  syncSchema: (id: string) => Promise<void>;
  checkHealth: (id: string) => Promise<HealthResult>;
}
```

### 内部副作用

`setActiveDatasourceId` 切换数据源时，自动调用 `datasourcesApi.releaseDatasource(prevId)` 释放上一个连接池。这是当前 App.tsx L97-109 的逻辑，从组件移入 store 使行为更可靠。

### 消费方式

```ts
// 组件中
const datasources = useDatasourceStore(s => s.datasources);
const activeId = useDatasourceStore(s => s.activeDatasourceId);
const setActiveId = useDatasourceStore(s => s.setActiveDatasourceId);
```

---

## Store 2: workspaceStore

替代 `useWorkspaceTabs()` + `useWorkspaceSelection()` + `useConversationHistory()` + App.tsx 中的 `msgIdSeq`。

### State

```ts
interface WorkspaceState {
  tabs: WorkspaceTab[];
  activeTabId: string;
  activeTab: WorkspaceTab | undefined;              // derived: tabs.find(t => t.id === activeTabId)
  sqlConsoleState: Record<string, SqlConsoleTabState>;
  selectedTables: string[];
  contextTables: string[];
  tableSubTabs: Record<string, string>;
  conversations: Conversation[];
  _tabSeq: { multiTable: number; queryResult: number; message: number };  // 替代 tabSeqRef + msgIdSeq
}
```

### Actions

```ts
interface WorkspaceActions {
  // 标签页操作
  closeTab: (id: string) => void;
  openSqlConsole: (initialSql?: string) => void;
  openLlmConfigTab: () => void;
  openConnectionManagerTab: () => void;
  openNewConnectionTab: () => void;
  openAgentEvalTab: () => void;
  openConversationResult: (conv: Conversation) => void;
  openTableTab: (tableName: string, initialSubtab?: string) => void;
  openMultiTableWorkspace: (tables: string[]) => void;
  openQueryResultTab: (queryText: string) => void;
  setActiveTabId: (id: string) => void;
  setTabs: (updater: WorkspaceTab[] | ((prev: WorkspaceTab[]) => WorkspaceTab[])) => void;

  // SQL Console
  setSqlConsoleState: (updater: Record<string, SqlConsoleTabState> | ((prev: Record<string, SqlConsoleTabState>) => Record<string, SqlConsoleTabState>)) => void;
  patchTab: (tabId: string, patch: Partial<WorkspaceTab>) => void;
  appendTabMessages: (tabId: string, messages: ChatMessage[]) => void;
  updateTabMessage: (tabId: string, msgId: number, updater: (msg: ChatMessage) => ChatMessage) => void;
  patchTabTimeline: (tabId: string, updater: (prev: TimelineEvent[]) => TimelineEvent[]) => void;

  // 选择
  setSelectedTables: (tables: string[] | ((prev: string[]) => string[])) => void;
  addContextTable: (name: string) => void;
  removeContextTable: (name: string) => void;
  clearContextTables: () => void;
  setTableSubTabs: (updater: Record<string, string> | ((prev: Record<string, string>) => Record<string, string>)) => void;

  // 会话
  persistConversation: (conv: Conversation) => void;
  deleteConversationById: (id: string) => void;

  // 内部
  _nextMsgId: () => number;
}
```

### 消费方式

```ts
const tabs = useWorkspaceStore(s => s.tabs);
const activeTab = useWorkspaceStore(s => s.tabs.find(t => t.id === s.activeTabId));
```

---

## Store 3: agentStore

替代 `useAgentRunner()`。

### State

```ts
interface AgentState {
  runningTabs: Record<string, { runId: string; status: "running" | "waiting_approval" | "cancelled" }>;
  timelineByTab: Record<string, TimelineEvent[]>;
}
```

### Actions

```ts
interface AgentActions {
  runAgentForTab: (tabId: string, question: string) => Promise<void>;
  sendFollowUp: (tabId: string, text: string) => void;
  handleApprovalDecision: (tabId: string, approved: boolean) => Promise<void>;
  cancelAgentRun: (tabId: string) => Promise<void>;
  regenerateAgentRun: (tabId: string) => void;
}
```

### 跨 store 交互

Agent 执行过程中需要对 workspaceStore 写入（`appendTabMessages`、`updateTabMessage`、`patchTab`、`persistConversation`）。通过 `useWorkspaceStore.getState()` 获取 snapshot 后直接调用，不重复持有状态。

```ts
// 在 agentStore 的 action 中
const ws = useWorkspaceStore.getState();
ws.appendTabMessages(tabId, [{ id: ws._nextMsgId(), sender: "ai", text: answer }]);
ws.persistConversation(ws.tabs.find(t => t.id === tabId));
```

### 消费方式

```ts
const runAgentForTab = useAgentStore(s => s.runAgentForTab);
const running = useAgentStore(s => s.runningTabs[tabId]?.status === "running");
```

---

## App.tsx 精简后

只保留 4 个纯 UI 的本地 state + 键盘快捷键：

```tsx
export default function App() {
  // 纯 UI state — 不进 store
  const [treeSearch, setTreeSearch] = useState("");
  const [rightDrawerOpen, setRightDrawerOpen] = useState(false);
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({ visible: false, x: 0, y: 0, type: "database", targetNode: "" });
  const [showCommandPalette, setShowCommandPalette] = useState(false);

  // 纯 UI hook
  const { collapsed, width, handleResizeStart, toggleCollapse } = useSidebarLayout();
  const { toast } = useToast();

  // 全局快捷键
  useEffect(() => { /* Ctrl+K, Ctrl+N, Ctrl+W */ }, [/* workspace actions from store */]);

  // showToast 保持本地，因为它是纯 UI 行为
  const showToast = useCallback((msg, type) => toast(msg, type), [toast]);

  return (
    <div className="app-shell">
      {/* DataSourceTree — 只传纯 UI props */}
      <DataSourceTree
        treeSearch={treeSearch} collapsed={collapsed}
        onTreeSearchChange={setTreeSearch} onToggleCollapse={toggleCollapse}
        sidebarWidth={width}
      />
      {/* ... */}
      {/* WorkspaceRouter — 从 27 props → ~3 */}
      <WorkspaceRouter showToast={showToast} />
    </div>
  );
}
```

**Props 减少对比：**

| 组件 | 之前 | 之后 | 剩余 props 全部是纯 UI |
|------|------|------|------------------------|
| WorkspaceRouter | 27 | 1 (showToast) | — |
| DataSourceTree | 15 | 6 | search/collapse/width（纯 UI）|
| ContextDrawer | 5 | 1 | open（纯 UI） |
| DataSourceContextMenu | 12 | 2 | x/y（纯 UI） |

---

## 当前 hooks 迁移表

| 当前 hook | 迁移目标 | 删除 |
|-----------|---------|------|
| `useDatasourceState` | datasourceStore | ✅ |
| `useWorkspaceTabs` | workspaceStore | ✅ |
| `useWorkspaceSelection` | workspaceStore | ✅ |
| `useConversationHistory` | workspaceStore | ✅ |
| `useAgentRunner` | agentStore | ✅ |
| `useAppCommands` | 保持不变（纯 UI） | — |
| `useSidebarLayout` | 保持不变（纯 UI） | — |

---

## 实施步骤

1. 安装 `zustand` → `npm install zustand`
2. 创建 `datasourceStore.ts` — 从 `useDatasourceState` 迁移
3. 创建 `workspaceStore.ts` — 从 `useWorkspaceTabs` + `useWorkspaceSelection` + `useConversationHistory` 迁移
4. 创建 `agentStore.ts` — 从 `useAgentRunner` 迁移
5. 重构 App.tsx — 移除 hooks 调用，子组件直接从 store 消费
6. 逐个改造子组件 — 从 props 改为 `useXxxStore` selector
7. 删除旧 hook 文件
8. 全量回归测试：`cd desktop && npm test && npx tsc --noEmit`

---

## 测试策略

- 现有 22 个前端测试保持通过
- 新增 store 单元测试（纯函数，不依赖 DOM）：每个 action 验证 state 变化
- 不改 E2E 测试

## 风险

| 风险 | 缓解 |
|------|------|
| Zustand 新增依赖 | ~1KB，MIT license，React 社区标准 |
| selector 用法错误导致渲染循环 | 每个 store 提供 `s => s.field` selector，组件只需订阅自己用的字段 |
| 跨 store 时序问题 | agentStore 通过 `getState()` 同步读取 workspaceStore，确保拿到最新值 |
