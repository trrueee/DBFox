# Workbench Shell 迁移规范

> 文档类型：Workbench ADR 附录 / 开发迁移指南
>
> 状态：已接受
>
> 最后核验：2026-08-16
>
> 基线：`main@daa99d048decd7f5f8dc010cbe5465f332686a3c`
>
> 关联 ADR：[Workbench Shell 与 Workspace Dock](./workbench-shell-workspace-dock.md)

## 1. 迁移原则

> **能搬就不重写；能直接调用就不加 Mapper；开放点才用 Registry；固定状态保持显式。**

本轮重新设计的是 App Shell、导航所有权、Workspace Dock 和状态归属，不是 SQL、Table、Conversation、Datasource、Project、Artifact 或 Settings 的业务实现。

任何新层都必须回答：它消除了哪一个真实 switch/ownership 冲突？如果答案只是“以后可能统一”，不加入。

## 2. 真实 Project / Datasource 边界

Shell V2 直接使用仓库现有 Project model 和 list/create API。

```text
Project
  ├── DataSource A
  ├── DataSource B
  └── UI workspace state
```

当前 Conversation 仍 datasource-bound，因此 Conversation 的 Project 归属通过：

```text
AgentSession.datasource_id
→ DataSource.project_id
```

禁止：

```text
projectId = datasourceId
Project ≈ Connection
```

Project Create 使用当前 Project create contract。若产品确实需要 Project Edit，先补最小 Project update API/contract，再接 Main Surface；不得复用 Datasource form 充当 Project form。

Datasource form 只用于 Project 内的 DataSource create/edit/test/credential/schema sync。

## 3. 组件处置

### 3.1 直接复用

| 当前能力 | 处理 |
| --- | --- |
| `ConversationWorkspace` | 保留，移除 Artifact layout ownership |
| Message/Timeline/Plan/Approval/Question/Composer | 保留 |
| Conversation store/repository | 保留 |
| `SqlConsoleWorkspace` | 原样迁入 Dock |
| `TableWorkspace` / Preview / Schema / ER | 原样迁入 Dock |
| MultiTable | 原样迁入 Dock |
| Result/Chart/Markdown renderer | 注册到 Artifact renderer map |
| Project list/create API | 直接用于 Sidebar/Create |
| Datasource controller/form/API | 作为 Project DataSource 管理能力保留 |
| Settings panels | 保留 |
| AppCommandPalette | 保留，重接 Shell actions |
| DataSourceTree 数据逻辑 | 拆出到 Project Data list |

### 3.2 最终删除

- `WorkspaceTabs.tsx` Global Tabs 模型；
- `WorkspaceRouter.tsx` 的领域页面中央 switch；
- Conversation History workspace tab；
- Datasource Settings workspace tab；
- Conversation `ArtifactDock` layout container；
- `ContextDrawer` 中已经有明确新 owner 的职责；
- `workspaceStore` 中 SQL/Table/Artifact 业务 payload；
- 所有 `openXxxTab()` legacy action；
- `sql-N/query-result-N` 等仅为 Tab identity 的 counter。

## 4. 信息架构

每个 UI 功能必须归属：

```text
Project Sidebar
Conversation / Main Surface
Workspace Dock
Settings Mode
Overlay / Menu / Dialog
```

### Sidebar

- New Conversation；
- Project list；
- active Project 下 Conversations/Data 两种 mode；
- Data mode 下才出现 DataSource/Schema/Table；
- Settings 固定入口。

### Main

固定状态：

```text
Conversation
New Conversation
Project Create
Project Edit（仅当 update contract 存在）
Empty/Error
```

不要把固定 Main Surface 做成 contribution registry。

### Dock

开放资源 View：SQL、Table、MultiTable、Artifact，未来 File/Diff/GitHub/Web。

## 5. ShellStore

只保存：

```text
app mode
active project
per-project active datasource
per-project active conversation
per-project sidebar mode
main surface identity
dock open/width/active key/views
settings section
```

不保存：

```text
SQL draft/result/transcript
Table metadata/result
Artifact payload
Conversation payload
File content
Patch content
Datasource credentials
```

## 6. ViewStore

### SQL

```text
SqlConsoleViewStore[projectId]
  selectedDatasourceId
  draft
  transcript
  running
  last result/error
  scroll
```

一个 Project 一个 SQL state；console 内可以选择该 Project 下的 DataSource。

### Table

```text
TableViewStore[projectId + datasourceId + canonical table]
  active subview
  filter/options
```

### Artifact

Artifact content 由 canonical conversation/artifact repository 或 query cache 读取，不复制到 ShellStore。

## 7. Dock identity

统一动作：

```typescript
openDock({ viewType, projectId, resourceRef, sourceRef? })
```

贡献点只做四件事：

```text
parse/validate resourceRef
canonicalize identity
resolve title
render
```

Shell 在 open 时只 canonicalize 一次，得到唯一 `viewKey`。

首批 key：

```text
SQL
  projectId

Table
  projectId + datasourceId + canonical schema/table

Artifact
  artifactId

MultiTable
  projectId + datasourceId + dedup/sorted canonical table set
```

不使用递增 counter，不允许 caller 拼自己的 dedup key。

## 8. 状态数据结构

Dock view 数量小，使用单一有序数组：

```typescript
views: DockViewRef[]
activeKey?: string
```

打开时线性查找 canonical key；这比维护 `viewsByKey + order` 两份可变状态更可靠。

只有真实 profiling 证明这里成为热点后才添加派生 index。

## 9. F0 — Characterization 与旧模型冻结

先固定：

- Conversation stream/cancel/approval/question；
- SQL draft/execute/result/error；
- Table Preview/Schema/ER；
- Artifact open/render；
- Project list/create；
- Datasource create/edit/test/sync；
- Settings；
- keyboard/command palette。

旧 Global Tabs/ContextDrawer/ArtifactDock 只修 bug，不再增加产品能力。

## 10. F1 — Shell state 与真实 Project navigation

- 加载 Project list API；
- activeProjectId 成为 Shell identity；
- activeDatasourceId 变成 per-project navigation state；
- Conversation list 按 datasource.project_id 归组；
- 建立 Project Sidebar；
- 不改变 Main/Dock 业务组件。

验收：Project 切换能恢复其 active datasource/conversation/sidebar mode。

## 11. F2 — Main Surface

建立固定 Main Surface：

- Conversation；
- New Conversation；
- Project Create；
- Empty/Error；
- Settings Mode replace/restore。

如果 Project Edit 是本轮产品需求，本阶段先单独补最小 Project update backend contract 和测试，再接 Edit Main Surface；不复用 Datasource form。

此阶段可保留短期 Navigation facade 把旧入口转到新 Main action。

## 12. F3 — Dock Kernel

只实现：

- open/close/collapse；
- resize；
- active key；
- ordered views；
- canonical dedup；
- unknown View fallback；
- per-project restore。

先用一个测试 contribution 证明 Kernel 不知道领域 View。

## 13. F4 — SQL vertical slice

- 直接挂载 `SqlConsoleWorkspace`；
- state 从 `tabId` keyed 迁为 `projectId` keyed；
- console 内 datasource 选择限制为当前 Project；
- `openSql(projectId, sql?)` 只激活一个 canonical view；
- 非空 draft 不静默覆盖。

删除 SQL tab counter。

## 14. F5 — Table / MultiTable

- 直接挂载现有 Table/MultiTable；
- Table key 包含真实 datasource；
- Preview/Schema/ER 只改 View state；
- Table → SQL 激活同 Project SQL 并切对应 datasource；
- canonical MultiTable set 去重+排序。

## 15. F6 — Artifact

- Artifact renderer 使用只读注册表；
- 现有 renderer 直接迁入；
- Conversation Artifact click 打开 Dock；
- 删除 Conversation 专属 Artifact layout container；
- unknown Artifact metadata fallback。

## 16. F7 — Entry cutover

迁移：

- Sidebar actions；
- Conversation actions；
- DataSource/Table context menu；
- Command Palette；
- keyboard shortcuts；
- 所有 `openXxxTab()` callsite。

每迁一个入口就改成新 Shell action；不要再加一层长期 adapter。

## 17. F8 — Legacy deletion

feature flag 达到稳定窗口后删除：

- WorkspaceTabs；
- central WorkspaceRouter domain branches；
- old workspace tab types；
- old workspaceStore business state；
- History/Datasource Settings tabs；
- old ContextDrawer ownership；
- Navigation facade。

加反向 grep/import test，确保没有旧 action/type 残留。

## 18. 关键交互

### New Conversation

当前 AgentSession datasource-bound：如果 active Project 没有 active DataSource，UI 必须先让用户选择/创建 DataSource，而不是传一个假的 Project ID 给 Agent API。

### Project switch

切换 Project：

```text
save current Shell identity
→ activate target ProjectShellState
→ activate its datasource/conversation/dock
```

业务 ViewStore 不复制进 Shell snapshot。

### SQL

AI → SQL 只填/追加 draft，不执行；SQL → AI 只预填 composer，不自动发送。

### Table

单击打开 Dock，不切走 Conversation；同一 canonical table 只激活已有 View。

### Artifact

AI 创建 Artifact 不自动控制 Dock；用户点击 reference 才打开。

## 19. 测试

### Ownership

- Project ≠ Datasource；
- Project list/create API drives sidebar/create；
- 不假设当前存在 Project update API；
- Conversation datasource→project grouping；
- ShellStore 无业务 payload。

### Identity

- SQL one/project；
- Table dedup project+datasource+table；
- MultiTable canonical set；
- Artifact by artifact ID；
- open/close/reopen state。

### Lifecycle

- Project state isolation/restore；
- Settings round trip；
- last Dock view close collapse；
- unknown View/Artifact fallback；
- legacy facade removal。

### Feature parity

- Conversation；
- SQL；
- Table/MultiTable；
- Artifact；
- Project list/create（以及未来独立 update contract）；
- Datasource；
- Settings；
- commands/shortcuts。

## 20. Code Review checklist

每个 UI PR 必须回答：

1. 这是移动/复用，还是重写？
2. 新抽象是否有两个真实使用者？
3. Project/Datasource ownership 是否正确？
4. 是否假设了仓库当前不存在的 Project contract？
5. 固定 Main Surface 是否被无必要 Registry 化？
6. 开放 Dock/Artifact type 是否通过直接 registration，而不是新 central switch？
7. ShellStore 是否只保存 identity/layout？
8. 是否新增了随机 tab ID、重复 canonical key 或双索引状态？
9. 兼容 facade 的删除条件是什么？

## 21. 完成定义

- Project Sidebar 使用真实 Project；
- Conversation/Data list 归属明确；
- Main 常态 Conversation；
- 无 Global Tabs；
- Dock 唯一且默认关闭；
- SQL/Table/Artifact/MultiTable 功能 parity；
- 一个 Project 一个 SQL state；
- canonical resource 不重复；
- Settings/Project management 不进入 Dock；
- existing business logic 未复制；
- legacy navigation/store owners 删除。
