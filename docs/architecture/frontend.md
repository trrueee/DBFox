# DBFox 前端架构

> 文档类型：架构说明
>
> 状态：当前
>
> 最后核验：2026-08-09
>
> 适用范围：`desktop/src/` 的工作区、传输、状态和用户交互

## 1. 设计目标

前端是 Agent 公共事实的产品投影，而不是第二套 Runtime。它负责工作区导航、流式呈现、人机中断交互、工件浏览和当前页查询结果，但不自行决定 Run、Approval、Evidence 或 Artifact 的权威状态。

## 2. 分层架构

```mermaid
flowchart TB
  subgraph Boot["启动层"]
    MAIN["main.tsx"]
    GATE["EngineStartupGate"]
    APP["App / Providers"]
  end

  subgraph Shell["应用外壳"]
    SIDEBAR["Datasource Sidebar"]
    TABS["Workspace Tabs"]
    ROUTER["WorkspaceRouter"]
    COMMAND["Command Palette"]
  end

  subgraph Features["产品功能"]
    CONV["ConversationWorkspace"]
    SQL["SQL Console / Table Workspace"]
    DS["Datasource Management"]
    SETTINGS["LLM / Diagnostics / Settings"]
  end

  subgraph Conversation["Agent 交互"]
    HEADER["ConversationHeader"]
    MESSAGES["MessageList / AgentTimeline"]
    INTERRUPT["ApprovalAuditCard / QuestionCard"]
    COMPOSER["Composer"]
    DOCK["ArtifactDock / EvidencePanel"]
  end

  subgraph State["状态与投影"]
    WORKSPACE["workspaceStore"]
    DATASOURCE["datasourceStore"]
    STORE["conversationStore"]
    REDUCER["conversationStoreReducer"]
    VM["useConversationViewModel"]
  end

  subgraph Integration["集成层"]
    REPO["conversationRepository"]
    API["Typed API Client"]
    SSE["SSE Parser / reconnect"]
    RESULT["SQL-backed Data Hooks"]
  end

  MAIN --> GATE --> APP --> Shell
  ROUTER --> Features
  CONV --> Conversation
  CONV --> VM
  VM --> STORE
  STORE --> REDUCER
  STORE --> REPO
  REPO --> API
  REPO --> SSE
  DOCK --> RESULT --> API
  ROUTER --> WORKSPACE
  SIDEBAR --> DATASOURCE
```

## 3. 工作区组件关系

```mermaid
flowchart LR
  APP["App Shell"] --> TREE["数据源树"]
  APP --> TABBAR["工作区标签"]
  TABBAR --> HOME["智能问数首页"]
  TABBAR --> CONV["Conversation Workspace"]
  TABBAR --> SQL["SQL Console"]
  TABBAR --> TABLE["Table Workspace"]
  TABBAR --> CONFIG["Datasource / LLM / Diagnostics"]

  CONV --> CENTER["Agent Timeline + Composer"]
  CONV --> RIGHT["Artifact Dock"]
  RIGHT --> SQLART["SQL Artifact"]
  RIGHT --> RESULT["Result View"]
  RIGHT --> CHART["Chart Artifact"]
  RIGHT --> EVIDENCE["Evidence navigation"]
```

布局原则：

- 左侧是数据库环境导航；中间是会话和过程；右侧是当前工件。
- 工件区属于 Conversation Workspace，不作为独立事实源。
- 窄窗口允许工件区折叠并保存布局状态，但不能丢失选中 Artifact ID。
- 设置页复用统一 scaffold，状态色只表达状态，品牌色只表达选中和主操作。

## 4. 会话数据流

```mermaid
sequenceDiagram
  participant User as 用户
  participant Composer as Composer
  participant Store as Conversation Store
  participant Repo as Repository
  participant API as FastAPI
  participant SSE as Event Stream
  participant Reducer as Projection Reducer
  participant View as Timeline / Dock

  User->>Composer: 提交输入与 delivery mode
  Composer->>Store: sendMessage
  Store->>Repo: admit input
  Repo->>API: POST Session Input
  API-->>Repo: Session / Run IDs
  Repo->>API: load snapshot + follow events
  API-->>SSE: replay then live notifications
  SSE->>Reducer: normalized public event
  Reducer->>Store: 幂等更新实体和顺序
  Store->>View: selector / view model
  View-->>User: 回答、过程、工件、批准或问题
```

恢复顺序固定为：

1. 加载 Conversation Snapshot；
2. 从 snapshot cursor 重放已提交事件；
3. 切换到 live 通知；
4. 发现 sequence gap 时放弃局部猜测，重新加载 snapshot。

## 5. Responses Items 与过程呈现

```mermaid
flowchart TB
  EVENT["Committed Runtime Events"] --> REDUCER["Conversation Reducer"]
  REDUCER --> ITEMS["Ordered Run Items"]
  ITEMS --> COMMENTARY["Commentary Message"]
  ITEMS --> TOOL["Function Call + Output"]
  ITEMS --> APPROVAL["Approval / Question / Plan"]
  ITEMS --> ANSWER["Final Answer"]
  ANSWER --> CITE["Evidence / Artifact References"]
```

设计约束：

- Agent Timeline 按服务端 sequence 展示 commentary、工具调用、工具结果、Plan、Approval、Question 和 final answer，不展示私有 chain-of-thought。
- live Item 与 snapshot Item 使用稳定 ID 和 revision，刷新后不得生成重复步骤。
- Approval/Question 在待处理时固定靠近 Composer；处理后成为只读历史部分。
- Answer 使用增量合并和平滑显示；终态消息以持久投影为准。
- Citation 由 Markdown AST 插件解析为句内 Evidence 按钮，不依赖字符串后处理。
- Markdown 不解析通用 raw HTML；GFM、Citation 和安全换行都在 AST 层处理，最终仍经过 sanitize。
- Live delta 使用稳定的 `item_id + revision + offset` 追加到已开始的 RunItem；断线后以 snapshot 的完整持久内容为准，再从 durable event cursor 继续，避免首段缺失或重复。

## 6. Artifact Dock 与 SQL-backed 数据

```mermaid
sequenceDiagram
  participant Dock as Artifact Dock
  participant Store as Conversation Store
  participant Hook as SQL-backed Hook
  participant API as Result Gateway
  participant DB as 用户数据库

  Dock->>Store: 读取 Result Artifact descriptor
  Note over Store: 只有 ID、来源、列和统计
  Dock->>Hook: 打开 Artifact ID
  Hook->>API: page / filters / sort / search
  API->>DB: 校验后按需执行来源 SQL
  DB-->>API: 当前页短暂结果
  API-->>Hook: columns + rows + page metadata
  Hook-->>Dock: 组件内渲染
  Note over Hook,Dock: 关闭或卸载后释放当前页
```

Result Gateway 的页面响应同时携带 `originalExecutedAt` 与 `viewExecutedAt`。UI 必须并列显示“分析取数”和“当前重查”，并说明当前表格不是历史快照；Evidence 的 `observedAt` 仍代表回答当时的最小事实。

禁止进入 Conversation Store、localStorage、IndexedDB 或 SSE Artifact 事件的字段：

- `rows`
- `previewRows`
- Chart `series`
- 任意结果单元格副本

## 7. 状态边界

| 状态类型 | 所有者 | 示例 |
|---|---|---|
| 导航状态 | `workspaceStore` | 活动标签、标签顺序、工件区布局 |
| 本机外观偏好 | `ThemeProvider` + localStorage | 主题模式、受控色板、分区字号 |
| 数据源导航状态 | `datasourceStore` | 当前数据源、Schema 树、同步状态 |
| 会话公共投影 | `conversationStore` | Run、Run Item、Artifact、Approval、Question、Plan |
| 组合视图 | `useConversationViewModel` | 当前 Run、排序后的消息和工件 |
| 当前页面数据 | 组件/SQL-backed hook | Result 当前页、Chart 当前序列 |
| 服务端事实 | FastAPI + 元数据库 | Run 状态、Approval、Artifact 关系、Event sequence |

## 8. 扩展边界

- 新工作区类型通过 `WorkspaceRouter` 和 workspace type 注册，不向 App 添加业务分支。
- 新 Artifact 类型通过统一 Artifact model、renderer 和 dock projection 扩展。
- 新公共事件先定义后端契约和 reducer，再增加视图；视图不得解析原始调试事件。
- 新流式 channel 必须定义去重身份、持久化替代物和断流恢复语义。
- 通用视觉能力进入 `components/ui` 或 `components/settings`，业务状态留在 feature 内。

## 9. 视觉系统与交互语义

前端使用语义 Token 表达 background、panel、border、text、focus、brand 和 status。品牌主色为紫色，数据强调可使用青色；warning/success/danger 只表达状态，狐狸品牌不依赖橙色。

交互状态必须一致：

- 主操作、选中 Tab、focus ring 使用品牌语义；
- warning/success 不能同时出现在同一操作的最终状态；
- disabled 必须说明原因，不能只有低透明度；
- loading 使用产品动作描述，不暴露内部健康检查或技术码；
- 点击区域至少 28–32px，辅助文字不低于 12px。

### 9.1 外观偏好合同

外观设置由 `ThemeProvider` 作为进程内唯一权威，版本化偏好只保存在本机
`dbfox-appearance-v1`。它不进入数据库、会话、诊断包或模型上下文。启动时只对旧的
`dbfox-theme` 明暗值执行一次单向迁移，不保留新旧双写。

- 主题模式为 `system | light | dark`；`system` 通过 React 外部状态订阅跟随操作系统。
- 强调色和中性色来自经过浅色/深色校准的封闭枚举；不接受任意 CSS 或十六进制输入，避免破坏对比度、状态色和焦点环。
- 字号按 UI、数据表、SQL/代码、Agent 对话四个真实阅读场景独立设置，使用受控整数 px：UI 11–16、数据 10–18、代码 11–22、Agent 13–24；组件继续引用语义字号 Token，不保存逐组件覆盖。
- 密度使用 `compact | standard | comfortable` 统一控制工具栏、按钮和主要留白；UI、数据、代码字体家族分别选择受控的本机字体栈。
- Agent 与 SQL/代码行高独立；数据表可配置默认行高、网格线、斑马纹、NULL 呈现和默认主键冻结，不改变手动列固定能力。
- 高对比度、减少动效同时支持显式设置和系统媒体查询；系统 DPI 交给 Tauri WebView，不叠加 CSS zoom。
- 数据源侧栏与 Agent 工件面板把拖拽结果写回同一偏好文档；原生窗口位置与尺寸由官方 Window State 插件独占，不保存第二份窗口坐标。
- 导入/导出使用同一严格 schema，拒绝未知字段与超大文件；结构上不包含 Token、密码、DSN、SQL、会话或日志。
- `ThemeProvider` 只把规范偏好投影为根元素的 `data-*` 属性；`tokens.css` 是色彩和字号的唯一视觉事实来源。
- 设置即时预览并自动保存；重置恢复系统主题、紫色强调、冷灰中性色和标准字号。
- ECharts 在外观投影提交后重新读取同一组 CSS Token，不维护第二份图表主题配置。

这个边界参考成熟桌面工具的“用户设置 + 即时预览”模式和主题系统的受控参数设计，
没有引入新的主题库、任意颜色解析器、兼容 mapper 或组件级持久化。

## 10. 可访问性

Radix 负责 Dialog、Tabs、Collapsible 等焦点管理。自定义列表、Activity、Artifact 和数据表必须提供 role、accessible name、键盘操作和清晰 focus。动画尊重 `prefers-reduced-motion`。

Approval/Question 属于阻塞性交互：待处理卡靠近 Composer，并且屏幕阅读器能获知风险、状态和可执行动作；处理后变为只读历史，不从 DOM 无痕消失。

## 11. 性能策略

- 长对话超过阈值后使用 TanStack Virtual；
- 动态虚拟位置写入 nonce CSSOM，不违反 CSP；
- SSE event 先批处理再进入 reducer，避免 token 级全树重渲染；
- streaming text 使用平滑展示，但 committed Message 到达后立即归并；
- Chart/ECharts 和重型 Artifact renderer 延迟加载；
- Result 新请求取消旧请求，过期 response 通过 sequence 丢弃；
- bundle budget 分别约束 initial entry 和 deferred chart chunk。

## 12. 错误、取消与恢复

API error 先映射为用户可理解文案，技术 detail 留在诊断。EngineStartupGate 区分 starting/ready/failed/stopped，失败提供重试和诊断入口。

组件卸载、来源变化和用户取消会传播 AbortSignal。AbortError 不显示为业务失败。SSE 关闭不等于 Run 失败，UI 会重载 snapshot 或继续跟随；只有 committed terminal state 能显示最终完成/失败/取消。

收到 committed `run.cancelled` 后，Reducer 将该 Run 尚未结算的 pending/running/waiting Activity 统一投影为 cancelled，并保留已产生的回答草稿、步骤和 Artifact。取消不是失败，也不删除已有产品成果。

## 13. 测试策略

前端测试分为：

- reducer/event contract：去重、gap、correlation、Plan、Approval、Question、Artifact；
- product interaction：Composer、Agent Timeline、Question、Artifact Dock、SQL-backed table；
- accessibility：焦点、role、label、键盘、reduced motion；
- security：CSP、sanitize、外部导航、secret-safe error；
- engineering：TypeScript、ESLint、production build、bundle budget。

具体通过数量会随测试增长而变化，不在架构事实文档中固化。当前结果以绑定 commit 的 CI
记录为准；权威命令和门禁范围见[工程质量门禁](../quality/engineering-gates.md)。

## 14. 关键文件

| 领域 | 文件 |
|---|---|
| 启动 | `desktop/src/components/EngineStartupGate.tsx` |
| Workspace | `desktop/src/features/appShell/WorkspaceRouter.tsx` |
| Conversation | `desktop/src/features/conversation/workspace/ConversationWorkspace.tsx` |
| Reducer | `desktop/src/stores/conversationStoreReducer.ts` |
| Stream | `desktop/src/features/conversation/conversationStreamRuntime.ts`、`conversationRepository.ts` |
| Timeline | `desktop/src/features/conversation/workspace/MessageList.tsx`、`AgentTimeline.tsx` |
| Artifact Dock | `desktop/src/features/conversation/workspace/ArtifactDock.tsx` |
| Result state | `desktop/src/features/workspace/sqlBacked/useSqlBackedDataView.ts` |
| Tokens | `desktop/src/styles/tokens.css` |
| Appearance contract | `desktop/src/lib/appearance.ts`、`desktop/src/hooks/useTheme.tsx` |
| Appearance settings | `desktop/src/features/settings/AppearanceSettingsPanel.tsx` |
