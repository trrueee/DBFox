# Workbench Shell 与 Workspace Dock

> 文档类型：ADR
>
> 状态：已接受
>
> 最后核验：2026-08-16
>
> 基线：`main@641ddf98a962189f0a2959e6b752533087c2cd65`
>
> 上位 RFC：[DBFox 可扩展 Runtime 与 Workbench 架构计划](./extensible-runtime-workbench-program.md)

## 1. 决策

DBFox 桌面端收敛为两个 App Mode：

```text
Workspace Mode
Project Sidebar | Conversation Main | optional Workspace Dock

Settings Mode
Settings Sidebar | Settings Main
```

Workbench Shell Kernel 只拥有导航、布局、View identity 和生命周期；SQL、Table、Artifact、File、Diff 等内容由注册的 View contribution 提供。模型只能生成或引用资源/Artifact，不能控制 React View、路由或 Dock Tab。

本重构优先搬、拆、复用现有能力，不重写已经工作的 Conversation、SQL Console、Table Workspace、Artifact renderer、Datasource connection、Settings 和 Command Palette。

## 2. 当前所有权问题

当前 `WorkspaceTabType` 同时包含 Smart Query、Table、SQL、Multi Table、Query Result、Artifact Result、Conversation History 和 Datasource Settings；`WorkspaceRouter` 理解所有页面；`workspaceStore` 同时保存 Tab identity、SQL draft/transcript 和多种业务 payload；`App.tsx` 又并存 Datasource Tree、Global Workspace Tabs、ContextDrawer 和 Settings；Conversation 内还有独立 ArtifactDock。

问题不是视觉风格，而是一个功能究竟属于 Sidebar、Conversation、Workspace Dock、Settings 还是 Overlay 没有稳定答案。

## 3. Workbench Shell Kernel 所有权

Shell Kernel 负责：

- `appMode`；
- active Project 和每个 Project 的 UI workspace；
- Main Surface 路由；
- Workspace Dock open/close/resize/order/activate；
- Dock canonical identity 和 dedup；
- unknown View/Artifact fallback；
- Settings 进入/返回现场恢复；
- Command/keyboard 到 Shell action 的路由。

Shell Kernel 不负责：

- SQL 执行、结果或 transcript；
- Table 数据、字段或 ER；
- Conversation/Run/Artifact 事实；
- Datasource API、表结构或凭据；
- File content、Patch、GitHub/Browser 数据；
- 领域 View 的标题/身份计算细节。

## 4. Workspace Mode

```text
┌─────────────────┬────────────────────────┬────────────────────┐
│ Project Sidebar │ Conversation Main      │ Workspace Dock     │
│                 │                        │ optional/closed     │
└─────────────────┴────────────────────────┴────────────────────┘
```

规则：

- 左侧负责 Project、Conversation 和数据资源导航；
- 中间常态是 Conversation；
- 右侧只承载需要与 Conversation 同屏协作的资源或工具；
- Dock 默认关闭；
- 不再存在顶部 Global Workspace Tabs；
- 全应用只有一个 Workspace Dock，不再保留 Conversation 专属 Artifact panel 或第二套 ContextDrawer。

## 5. Settings Mode

进入 Settings 后，Project Sidebar 被 SettingsSidebar 替换，Main 变成 Settings Main，Dock 隐藏。返回 Workspace 时恢复：

```text
active Project
active Conversation
sidebar mode
Dock open/width/tabs/active tab
各 View 临时状态
Conversation scroll where supported
```

Settings、Project create/edit、Connection management、Conversation history 和全局搜索都不进入 Dock。

## 6. Project Sidebar

目标结构：

```text
DBFox
New Conversation

Projects                            +
Project A                           data/conversation toggle
  Conversation list or Data list
Project B

Settings
```

当前阶段 UI 中 `Project ≈ Datasource/Connection`，但新 Runtime/Wire contract 不将 Datasource 当作 universal scope。未来无数据库 Workspace Session 仍需要独立数据模型迁移。

Project 是选择项，不是 Tree Node：

- 无展开/折叠 Chevron；
- 无 datasource dropdown；
- active Project 才显示下级资源；
- Connection 使用数据库品牌 Icon；
- Database/Catalog 使用经典数据库 Icon；
- Table 使用 Table Icon；
- 正常连接不常驻第二行状态文本；
- 管理动作优先放 context menu，hover 可显示轻量 `…`。

Project 右侧只保留一个轻量 mode action，在 Conversation list 与 Data list 之间切换。

### 6.1 Conversation list

Conversation history 不再是独立页面。当前 Project 下的 Conversation summaries 就是历史列表。首版不再增加重复 Header、Card、内嵌“新建对话”或额外搜索入口。

### 6.2 Data list

只保留 Catalog/Schema/Table 搜索和资源列表，不混入 SQL Console、Datasource management、Smart Query、Conversation history 或 Settings。数据结构可为树，但视觉优先轻分组而不是文件资源管理器式多层 Chevron。

## 7. Main Surface

Main Surface Router 只管理：

```text
Conversation
New Conversation / empty state
Project Create
Project Edit
Empty / error
```

ConversationWorkspace 保留 Message Timeline、Plan、Tool、Approval、Question、Composer、streaming/cancel、answer 和 Artifact reference；只移除内部右侧 Artifact layout ownership。

Project Create/Edit 在 Main 打开并隐藏 Dock。复用现有 Datasource form/controller、validation、connection test、credential enrollment、save/update/delete 和 schema sync，不重新实现连接业务逻辑。

## 8. Workspace Dock

Dock 只负责：

```text
layout
open / close / collapse
resize
tab order
active tab
canonical target dedup
view mount/error/fallback
```

首批 View：

```text
core.sql-console
dbfox.data.table
dbfox.data.multi-table
core.artifact
```

未来：

```text
dbfox.workspace.file
dbfox.workspace.diff
dbfox.github.pull-request
dbfox.web.document
```

不允许进入 Dock：Settings、Project create/edit、Datasource management、Conversation history、新 Conversation、Project management、全局搜索和普通 confirm/dialog。

## 9. Dock View contribution

```typescript
interface DockViewContribution<TRef> {
  viewType: string;
  parseResourceRef(value: unknown): TRef;
  canonicalKey(ref: TRef): string;
  resolveTitle(ref: TRef): string;
  render(props: { ref: TRef; tabId: string }): ReactNode;
}
```

调用方只传 `viewType + resourceRef`。Dock Kernel 由 contribution 的 `canonicalKey()` 生成 identity，调用方不得各自拼接未校验字符串。

```typescript
interface DockTabRef {
  id: string;
  projectId: string;
  viewType: string;
  resourceRef: unknown;
  sourceRef?: string;
}
```

每个 contribution 必须有运行时 validator。未知 View 显示 fallback，并保留 tab/resource metadata；不能使整个 Workspace 崩溃。

## 10. Artifact renderer contribution

`core.artifact` 是一个 Dock View；其内部根据 Artifact `type_id/schema_version` 调用 Renderer Registry：

```typescript
interface ArtifactRendererContribution<TPayload> {
  typeId: string;
  supportedSchemaVersions: readonly number[];
  parsePayload(value: unknown): TPayload;
  render(artifact: ArtifactEnvelope<TPayload>): ReactNode;
}
```

现有 Result、Chart、Markdown renderer 原样迁入：

```text
dbfox.data.result_view → TableArtifactView
dbfox.data.chart       → DeferredChartArtifactView
core.markdown          → MarkdownArtifactView
```

未知 Artifact 使用 metadata fallback。Conversation、Evidence、relations 和来源仍可读。

## 11. Shell state 与 View state

```typescript
interface ShellState {
  appMode: "workspace" | "settings";
  activeProjectId?: string;
  workspaceByProject: Record<string, ProjectShellState>;
  settingsSection: AppSettingsSection;
}

interface ProjectShellState {
  sidebarMode: "conversations" | "data";
  activeConversationId?: string;
  mainSurface: MainSurfaceRef;
  dock: {
    open: boolean;
    width: number;
    activeTabId?: string;
    tabs: DockTabRef[];
  };
}
```

ShellStore 只保存 UI identity/layout。它不复制 Conversation、Artifact payload、Table metadata、SQL Result 或 File content。

具体 View 可以拥有临时交互状态：

```text
SqlConsoleViewStore → draft/transcript/running/result/error/scroll
TableViewStore      → active subview/filter/view options
Artifact query/cache→ canonical resource projection
```

关闭 Dock Tab 只隐藏 View；是否保留 View state 由 contribution lifecycle contract 决定。SQL Console 首版按 Project 持久：一个 Project 一个 console，关闭/重开不丢 draft 和 transcript。

## 12. 关键产品行为

### SQL

- 不再是 Global Tab；
- `sql:${project}` identity 由 View contribution 生成；
- AI → SQL 只打开/激活并填充或追加 draft，不自动执行、不静默覆盖已有 draft；
- SQL error/result → AI 只预填 Composer，不自动发送；
- Conversation 切换不关闭 Project SQL Console。

### Table

- 单击 Table 打开/激活 Dock Table View，不切走 Conversation；
- Preview、Schema、ER 和 context-menu 业务逻辑复用；
- Table → SQL 进入 Project SQL Console；
- Table → Ask AI 进入 Conversation Composer；
- 相同 canonical table 不创建重复 View。

### Artifact

- AI 生成 Artifact 只在 Conversation 中出现引用；
- 用户点击后才打开 Dock；
- 不强制压缩 Conversation；
- renderer 复用，不重写；
- 可显示 source Conversation，并允许切回来源。

### Multi Table

保留现有能力，迁入 Dock，不因 Shell 重构删除。

## 13. 模型与 UI 边界

错误：模型要求“打开 Diff Viewer”或“创建 Tab X”。

正确：

```text
Model → Tool → CodePatch Artifact
Conversation → Artifact reference
User action → ArtifactRenderer contribution → Workspace Dock
```

Runtime event/wire contract 不包含 React component、Dock layout 或 tab command。

## 14. 迁移和回退

Shell V2 通过 feature flag 建立，新旧 Shell 在 parity 期并存。旧 `WorkspaceTabs`、`WorkspaceRouter`、`DataSourceTree` quick nav、ArtifactDock container、ContextDrawer 和 `workspaceStore.openXxxTab()` 只有在所有入口迁移和回退窗口结束后删除。

迁移过程中禁止重新实现 SQL、Table、Artifact、Connection、Settings 或 Conversation 内核。

## 15. 验收

- Workspace/Settings 两种 mode 清晰，Settings 返回恢复现场；
- 顶部无 Global Workspace Tabs；
- Main 常态是 Conversation，Dock 默认关闭；
- 全应用只有一个注册式 Workspace Dock；
- 新 Dock View 不修改 Dock switch；
- 新 Artifact renderer 通过 registration；
- Project 无 Chevron/dropdown，Conversation/Data list 纯净；
- SQL/Table/Artifact/MultiTable 迁移后功能 parity；
- 一个 Project 一个 SQL Console，close/reopen 恢复；
- 相同 canonical target 不重复；
- ShellStore 不保存业务对象，View state 有明确 owner；
- Unknown View/Artifact fail-soft；
- 模型不直接控制 Dock；
- Settings、Project Create/Edit、History 不进入 Dock。

具体组件复用、迁移阶段、视觉约束、快捷键和删除清单见[Workbench Shell 迁移规范](./workbench-shell-migration-guide.md)。
