# Workbench Shell 迁移规范

> 文档类型：Workbench ADR 附录 / 开发迁移指南
>
> 状态：已接受
>
> 最后核验：2026-08-16
>
> 关联 ADR：[Workbench Shell 与 Workspace Dock](./workbench-shell-workspace-dock.md)

## 1. 迁移原则

> **能搬就不重写，能拆容器就不重写内容，能复用现有组件就不复制新的。**

本轮真正重新设计的是 App Shell、导航所有权、Workspace Dock 和状态归属，不是 SQL、Table、Conversation、Datasource、Artifact 或 Settings 的业务能力。

## 2. 组件处置清单

### 2.1 优先复用

| 当前能力 | 处理方式 |
| --- | --- |
| `ConversationWorkspace` | 保留 Conversation 内核，移除 Artifact layout ownership |
| Message/Timeline/Plan/Approval/Question/Composer | 直接保留 |
| Conversation view model/store/repository | 直接保留事实和传输职责 |
| `SqlConsoleWorkspace` | 保留执行与 transcript，迁入 Dock |
| `TableWorkspace`、Preview、Schema、ER | 原样迁入 Dock |
| Result/Chart/Markdown renderer | 迁入 ArtifactRenderer contribution |
| `DataSourcesPage` controller/form/API | 拆出并复用到 Project Create/Edit Main View |
| connection test/save/update/delete/sync | 直接保留 |
| `SettingsSidebar` 和 settings panels | 直接保留 |
| `AppCommandPalette` | 保留，重接 Shell actions |
| `DataSourceContextMenu` action 逻辑 | 保留，改变打开目标 |
| `DataSourceTree` schema/table 数据逻辑 | 拆到 ProjectDataList |

### 2.2 迁移完成后退休

| 当前容器 | 最终处理 |
| --- | --- |
| `WorkspaceTabs.tsx` | 删除 Global Tab 产品模型 |
| `WorkspaceRouter.tsx` | 拆为 Main Surface contributions 和 Dock View contributions |
| `DataSourceTree.tsx` | 拆为 ProjectSidebar / ProjectConversationList / ProjectDataList |
| Conversation `ArtifactDock.tsx` container | 删除专属 layout，保留 renderer |
| `ContextDrawer.tsx` | 对象属性归 Table View；AI 建议归 Conversation/Artifact；容器删除 |
| `workspaceStore.ts` | 入口迁完后由 ShellStore + ViewStore 替代 |
| Conversation 内 PanelGroup | 移到 App Shell / Dock 布局层 |
| datasource selector/dropdown 和 quick nav | 删除，改 Project List |
| Conversation History / Datasource Settings Workspace Tab | 删除页面/Tab 模型，保留底层功能 |

## 3. 信息架构约束

每个功能必须属于以下之一：

```text
Project Sidebar
Conversation/Main Surface
Workspace Dock
Settings Mode
Overlay/Menu/Dialog
```

出现“再加一个全局 Tab”“再加一个右侧 Drawer”“再建一个管理页”时，必须停止并重新审查所有权。

### Sidebar

- 顶部固定 New Conversation；
- Projects 标题旁只有一个全局 `+`；
- Project 直接列出，不隐藏在 selector；
- Project 无 Chevron；
- active Project 才显示 Conversation/Data 子资源；
- 一个轻量图标在 Conversation/Data mode 间切换；
- Settings 固定左下；
- Project 管理动作进入 context menu/hover `…`。

### Conversation list

- 列表本身就是 history；
- 不出现重复的“历史记录”页面入口；
- 首版不增加 Card、重复标题、内嵌 New Conversation 或额外搜索；
- row 默认只显示标题，hover/context menu 提供 rename/delete 等操作。

### Data list

- Search 只在 Data mode 出现；
- 不混入 SQL、Settings、Datasource management、Smart Query 或 Conversation history；
- Connection 使用 DB brand icon；Database/Catalog 使用 cylinder icon；Table 使用 table icon；
- 逻辑可以是 tree，视觉优先轻分组和 indentation，避免多层文件树视觉。

### Main Surface

- Workspace 常态是 Conversation；
- New Conversation 使用现有 Smart Query 空状态的有价值部分；
- Project Create/Edit 在 Main 打开并隐藏 Dock；
- 不使用 Dock Tab、Global Tab 或强制 Modal 承载 Project form。

### Workspace Dock

- 默认关闭；
- Table/Artifact/SQL/MultiTable 用户动作才打开；
- 关闭最后一个可见 Tab 后 collapse；
- Tab bar 轻量，不做 Card Header/Pill；
- Settings、Project、History、Global Search 和普通 Confirm 禁止进入。

## 4. 状态迁移

### 4.1 ShellStore

只保存：

```text
app mode
active project
per-project sidebar mode
active conversation ID
main-surface ref
dock open/width/order/active tab/resource refs
settings section
```

### 4.2 ViewStore

SQL state 从 `tabId` keyed 迁为 `projectId` keyed：

```text
draft
transcript entries
running
last result/error
scroll position
```

Table state按 canonical table view key 管理 active subview/filter。Artifact 内容从 Conversation/Artifact repository 或 query cache 获取，不复制进 ShellStore。

### 4.3 Project 切换

每个 Project 独立保存：

```text
active Conversation
sidebar mode
Dock open/width/tabs/active tab
SQL Console state
Table View state
```

切回 Project 恢复原现场。Conversation 切换不关闭 Project 级 SQL/Table Dock View；Artifact 可保持打开并显示来源 Conversation。

## 5. Canonical Dock identity

调用统一动作：

```typescript
openDock({ viewType, projectId, resourceRef, sourceRef? })
```

由注册的 contribution 解析并生成 canonical key。调用方不得维护自己的 tab counter 或 dedup 规则。

首批目标语义：

```text
one SQL console per Project
one Table view per Project + canonical object + requested subview
one Artifact view per Artifact ID
one MultiTable view per canonical selected object set
```

关闭 Tab 默认只隐藏；View lifecycle 决定 state 保留。显式“关闭并清除”需要单独产品动作，不能与 Tab `×` 混同。

## 6. 关键交互迁移

### New Conversation

`Cmd/Ctrl+N` 从打开 SQL 改为 New Conversation。沿用当前 Conversation create/send 生命周期；可以在首次发送时才创建 durable Conversation。

### SQL

- Project context menu、Cmd+K 和 Conversation SQL action 都调用 `openSql(projectId, sql?)`；
- AI → SQL 不自动执行；
- 非空 draft 不静默覆盖，可追加带来源注释或要求用户确认替换；
- SQL result/error → AI 只预填 Composer，不自动发送；
- SQL execution shortcut 继续留在 SQL View 内。

### Table

- Sidebar click → Dock Table；
- context menu 的 Preview/Schema/ER 只改变 Table View subview；
- Table → SQL 激活 Project SQL；
- Table → Ask AI 预填 Conversation；
- 同一表重复点击只激活。

### Artifact

- Conversation 中保留 Artifact reference；
- 用户点击后打开 Dock；
- AI 生成 Artifact 不自动展开 Dock；
- source SQL / source Conversation 作为可导航引用；
- renderer 沿用现有实现。

### Settings

进入前保存 Workspace UI state，返回后恢复。Settings 不修改 Project Dock/Conversation 状态，也不在 Dock 中显示。

### Command Palette

保留现有基础设施，仅将 action 迁到：

```text
switchProject
new/openConversation
openTable
openSql
openProjectCreate/Edit
openSettings
```

不新建第二套全局搜索。

## 7. 分阶段迁移

### F0 冻结旧模型扩张

旧 `WorkspaceTabs`、`ContextDrawer`、DataSource quick nav、ArtifactDock container 和 Datasource Settings Tab 只修 bug，不再添加新功能。

### F1 Characterization 与 feature flag

- 固定 Conversation/SQL/Table/Datasource/Settings 核心测试；
- 建立 Shell V2 feature flag；
- 标记可回退的稳定版本；
- 不回退 Engine/API/SQL/Data 层以解决纯 Shell 问题。

### F2 ShellStore 和 Navigation adapter

新增统一 actions：

```text
newConversation
switchProject
openConversation
openProjectCreate/Edit
openSql/openTable/openArtifact/openMultiTable
openSettings
```

旧组件迁一个改一个；暂不删除 `openXxxTab()`。

### F3 Project Sidebar

先完成 New Conversation、Project List、Conversation/Data mode 和 Settings。Main 可暂时继续旧 Router，先稳定左侧所有权。

### F4 Settings Mode 与 Main Surface

接入 Settings replace/restore；建立 Conversation/New/Project Create/Edit/Empty 的 Main Surface。

### F5 Workspace Dock shell

只实现 open/close/resize/order/activate/collapse、per-project persistence、unknown View fallback 和测试 contribution。

### F6 SQL vertical migration

原样挂载 `SqlConsoleWorkspace`，迁 state 为 Project keyed，验证 close/reopen、Project isolation、Conversation switch、AI↔SQL。

### F7 Table 和 MultiTable

原样挂载现有 View，迁 context-menu action 和 subview state，验证 Preview/Schema/ER/SQL/Ask AI/dedup。

### F8 Artifact

注册现有 renderers，迁 Conversation Artifact click，去掉内部 Artifact panel 和 PanelGroup ownership。

### F9 Project Create/Edit

复用现有 Datasource controller/form logic，重组 Main Surface 外壳；不重写 API、validation、test、credential、SSH/SSL 和 sync。

### F10 Entry point cutover

迁 Sidebar、Conversation、context menu、Cmd+K、keyboard 和所有 `openXxxTab()` 调用。Shell V2 达到 parity 后默认开启。

### F11 Legacy deletion

回退窗口结束后删除旧 Tabs/Router branches/store actions/ContextDrawer/History route/ArtifactDock container。删除必须有反向 import/search test，防止残留双路径。

## 8. 视觉实施边界

允许优化：icon mapping、row height、indent、hover/active/focus、loading/empty、tooltip、Dock resize/tab、状态点和 Project form 层级。

禁止：

- 新 UI framework；
- 新 Typography/Radius/Spacing 系统；
- 重写 Button/Input/Tooltip/ScrollArea 等现有 primitive；
- Project Card、层层白 Card、大量 Pill；
- Connection 与 Database 共用同一 icon；
- 顶部 Global Tab 或第二套右 Drawer；
- 为目标截图从零复制 SQL/Table/Artifact/Settings/Form。

先移动和拆容器，再做局部视觉优化。

## 9. 测试

### Store/identity

- Project state isolation/restore；
- canonical key dedup；
- Tab hide/reopen state；
- Settings round trip；
- unknown View fallback；
- ShellStore 无业务 payload。

### Feature parity

- Conversation stream/cancel/approval/question；
- SQL draft/execute/result/error；
- Table Preview/Schema/ER；
- MultiTable；
- Artifact Result/Chart/Markdown；
- Datasource create/edit/test/sync；
- Settings；
- command palette/context menu/shortcuts。

### Integration

- Table click 不切走 Conversation；
- Artifact click 不切走 Conversation；
- Project/Conversation 切换恢复正确 Dock；
- last tab close collapses Dock；
- no Global Tabs/ContextDrawer/Conversation Artifact panel in Shell V2；
- old Shell feature flag remains usable until cutover approval。

## 10. Code Review checklist

每个 UI PR 必须回答：

1. 是移动/包装现有能力，还是重写？若重写，为什么原实现不可复用？
2. 新组件是在建立所有权 seam，还是复制旧业务组件？
3. 功能属于 Sidebar、Main、Dock、Settings 还是 Overlay？
4. 是否通过 contribution 注册，而不是新增 central switch？
5. ShellStore 是否只保存 ID/layout？View state owner 是否明确？
6. canonical identity、unknown fallback、Project isolation 和回退是否有测试？

## 11. 完成定义

迁移完成必须满足：左侧有 New Conversation/Projects/Settings；Project 无 selector/Chevron；Conversation/Data list 纯净；Main 常态 Conversation；无 Global Workspace Tabs；Dock 默认关闭且唯一；SQL/Table/Artifact/MultiTable 在 Dock；一个 Project 一个 SQL state；相同 target 不重复；Settings/New Project/History 不进 Dock；现有业务能力未被重复实现；Legacy 路径和双状态所有者已删除。
