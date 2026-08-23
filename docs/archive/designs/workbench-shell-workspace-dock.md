# Workbench Shell 与 Workspace Dock

> 文档类型：ADR
>
> 状态：历史
>
> 替代关系：当前 Workbench 与 DLC contribution 边界见 [`../../architecture/frontend.md`](../../architecture/frontend.md)。
>
> 最后核验：2026-08-16
>
> 基线：`main@daa99d048decd7f5f8dc010cbe5465f332686a3c`
>
> 上位 RFC：[DBFox 可扩展 Runtime 与 Workbench 架构计划](./extensible-runtime-workbench-program.md)
>
> 替代关系：本文保留 2026-08-16 Shell/Dock 设计背景；其中 datasource-bound
> Conversation、`Project.workspace_root`、`project_id = datasource_id` 与左栏 selection
> authority 规则已被 [Agent Core 与 Capability DLC 架构合同](./agent-core-capability-dlc-contract.md)
> 取代，不能作为当前实现依据。

## 1. 决策

DBFox 桌面端收敛为两个 App Mode：

```text
Workspace Mode
Entity Sidebar（项目/连接） | Conversation Main | optional Workspace Dock

Settings Mode
Settings Sidebar | Settings Main
```

Workbench Shell 只拥有导航、布局、稳定 View identity 和 UI lifecycle。SQL、Table、Artifact、File、Diff 等工作视图拥有自己的业务状态。

本重构优先搬、拆、复用现有能力，不重写 Conversation、SQL Console、Table Workspace、Artifact renderer、Datasource management、Project API 或 Settings。

## 2. 当前真实问题

当前前端：

- `WorkspaceTabType` 是封闭 union；
- `WorkspaceRouter` 集中理解 Smart Query、Conversation、Table、SQL、MultiTable、Artifact、Datasource Settings；
- `workspaceStore` 同时保存 Tab identity、SQL draft/transcript、Table subview、Settings 状态和业务 payload；
- `openSqlConsole()` 使用递增 `sql-N`，一个 Project 可产生多个等价 SQL Tab；
- Conversation 内还有独立 ArtifactDock；
- Datasource Tree、Global Tabs、ContextDrawer、Settings 又形成多套导航所有权。

重构目标是收敛 ownership，不是换一套视觉组件。

## 3. 使用真实 Project 模型

仓库已经存在真实：

```text
Project
  id
  name
  description
  status

DataSource.project_id → Project.id
```

当前还已有 Project list/create API；Project update/edit API 尚不是当前合同。

Workbench 必须直接使用真实 Project，不再使用：

```text
Project ≈ Datasource
project_id = datasource_id
```

这种临时映射。

### 3.1 当前 Agent Session 仍是 datasource-bound

当前 `AgentSession.datasource_id` 仍为非空，因此当前 Conversation 实际绑定一个 DataSource。

Shell 中 Conversation 归属 Project 的规则是：

```text
Conversation Session
→ datasource_id
→ DataSource.project_id
→ Project
```

Project 可以有多个 DataSource。创建新 Conversation 时，在 AgentSession 模型未迁移前仍必须选择/沿用 active DataSource。

未来 datasource-free Workspace Session 是独立后端数据模型迁移，不在本次 Shell 重构中伪造。

## 4. Shell ownership

Shell 负责：

- `appMode`；
- active Project；
- active DataSource navigation identity（当前 datasource-bound 产品需要）；
- active Conversation；
- Main Surface；
- Dock open/close/width/order/active key；
- Settings 进入/返回时 UI 现场；
- keyboard/command → Shell action；
- unknown View fallback。

Shell 不负责：

- SQL draft/result/transcript；
- Table metadata/Preview/ER；
- Conversation/Run/Artifact 事实；
- File content / Patch；
- datasource credential/config business logic；
- Artifact payload；
- View 内 filter/scroll/running state。

## 5. Workspace Mode

```text
┌──────────────────┬────────────────────────┬────────────────────┐
│ Entity Sidebar   │ Conversation Main      │ Workspace Dock     │
│ 项目 / 连接      │                        │ optional/closed     │
└──────────────────┴────────────────────────┴────────────────────┘
```

规则：

- Main 常态是 Conversation；
- Dock 默认关闭；
- 不再有 Global Workspace Tabs；
- 全应用只有一个 Workspace Dock；
- Conversation 不再拥有第二个 Artifact layout panel；
- Settings/Project management 不进入 Dock。

## 6. Entity Sidebar（项目 / 连接）

最终侧栏是「实体列表 + 行内子胶囊」，不是同时展示多个面板：

```text
[ 项目 | 连接 ]                        [+ / 收起]
Project A            [+新对话]  [ 对话 | 文件 ]
  会话 1
  README.md
Project B            [+新对话]  [ 对话 | 文件 ]

-- 切到连接 --
[ 项目 | 连接 ]                        [+ / 收起]
MySQL 生产            [+新对话]  [ 对话 | 数据库 ]
  会话 2
  schema/table resources
Postgres 分析         [+新对话]  [ 对话 | 数据库 ]
```

规则：

- 顶层「项目 / 连接」是互斥胶囊；每行实体自己有独立的 `[对话|文件]` 或 `[对话|数据库]` 子胶囊，切换后行内内容直接替换。
- 不再出现「对话列表」「文件」「数据库对象树」等分区标题。
- 项目用 Folder/FolderOpen 两态图标；连接用数据库图标，当前数据库节点继续使用数据源品牌图标。
- 每个项目行和连接行都有一个「+ 新对话」按钮。当前 AgentSession 仍 datasource-bound 时，项目新对话沿用该项目首个 DataSource，连接新对话沿用该连接；不伪造 datasource-free Session。
- 项目文件子模式只显示本地 `workspace_root` 的文件树，点击文件在 Dock 打开只读视图；文件事实不进入 Shell Store。
- Project 行不显示数据库连接状态。

### 6.1 Conversation list

Conversation history 就是当前项目/连接下的 Conversation summaries，不再有独立 History workspace page。因为当前 Conversation datasource-bound，项目列表通过 datasource→project 关系归组，连接列表直接按 `datasource_id` 归组。

### 6.2 Project files

新建项目时必须选择本地文件夹并把 `workspace_root` 持久化到 Project。文件树由 Electron preload 的 `listProjectFolder` 按需读取一层；目录展开后才读取子目录，并跳过 `.git`、`node_modules`、`.venv`、`target` 等重目录。文本文件经 `readProjectFile` 读取后以 `dbfox.workspace.file` Dock 视图渲染，只支持 UTF-8 且不超过 1 MiB；二进制、超大或非 UTF-8 文件显示明确错误。

## 7. Main Surface

Main Surface 是固定 Shell 状态，不是开放 Extension contribution point。

只管理：

```text
Conversation
New Conversation / empty state
Project Create
Project Edit（仅在存在正式 update contract 后启用）
Empty / error
```

一个小而显式的 switch 比把这些固定状态再塞进 Registry 更清楚。

ConversationWorkspace 继续拥有 Message Timeline、Plan、Tool、Approval、Question、Composer、streaming/cancel 和 Artifact references；只移除右侧 Artifact layout ownership。

Project Create 使用现有 Project create API 的 `name`/`description`/`workspace_root` contract：`workspace_root` 来自 Electron 系统文件夹选择器，项目名默认取文件夹 basename，用户仍可修改名称。若产品需要 Project Edit，先在后端补一个最小、明确的 Project update contract，再接 Main Surface；不能复用 Datasource form 假装 Project form。

Datasource create/edit/test/credential/schema sync 在 Navicat 式连接管理 Dialog 中完成，不占用 Main Surface，也不进入 Dock。

## 8. Workspace Dock

Dock 只负责：

```text
layout
open / close / collapse
resize
tab order
active view key
canonical target dedup
view mount/error/fallback
```

首批 View：

```text
core.sql-console
dbfox.data.table
dbfox.data.multi-table
core.artifact
core.artifacts
dbfox.workspace.file
```

未来：

```text
dbfox.workspace.diff
dbfox.github.pull-request
dbfox.web.document
```

Dock 是开放 contribution point，因为未来确实会增加不同资源 View。

## 9. Dock View contribution

当前实现入口是 `desktop/src/features/appShell/dockViewRegistry.tsx`：

```typescript
interface DockViewContribution {
  kind: WorkspaceDockTab["kind"];
  viewType: string;
  icon: (tab: WorkspaceDockTab) => ReactNode;
  resolveTitle: (tab: WorkspaceDockTab) => string;
  isVisible: (tab: WorkspaceDockTab, context: DockViewContext) => boolean;
  render: (tab: WorkspaceDockTab, context: DockRenderContext) => ReactNode;
}
```

Registry 是启动时构建并 freeze 的 `Map<kind, DockViewContribution>`，不需要 ViewManager/Factory/Adapter 多层对象。WorkspaceDock 本身 lazy 加载，让 `core.*`/`dbfox.*` 视图和 Artifact renderer 保持在独立 chunk 中。

### 9.1 Identity

每个 Shell action 以明确调用参数构造 canonical tab id，重复调用只激活已有 Tab，不用递增序号：

```text
openDockConsole → console-<projectId|datasourceId>
openDockTable   → table-<datasourceId>-<tableName>
openDockArtifact → artifact-<artifactId>
openDockMultiTable → multi-table-<sorted table set>
openDockFile    → file-<projectId>-<absolute path>
```

`tab.id` 就是 Dock identity，Store 不再同时保存随机 `tabId` 和另一份 canonical key。禁止用递增 `_tabSeq` 或裸字符串拼接不同 namespace；新增资源 View 时先补 contract test 固定其 canonical id。

Store 中只保存规范化后的 view descriptor；render 时不重复 canonicalize。项目文件的路径和读取结果不进入 Shell Store，`WorkspaceFileDockContent` 在渲染时经 `read_project_file` 按需读取。

## 10. Dock state 数据结构

Tab 数量天然很小，优先保持一个数组，不维护 `order[] + byId{}` 双结构。

```typescript
interface DockViewRef {
  key: string;
  projectId: string;
  viewType: string;
  resourceRef: unknown;
  sourceRef?: string;
}

interface DockState {
  open: boolean;
  width: number;
  activeKey?: string;
  views: DockViewRef[];
}
```

Dedup 对小数组线性查找足够；canonical identity 的正确性比为理论 O(1) 维护两份索引更重要。

若以后实际 View 数量证明线性查找成为瓶颈，再引入索引且必须由单一结构派生，不持久化第二份 order truth。

## 11. Artifact Renderer contribution

Artifact type 是开放集合，因此 Renderer Registry 是合理开放点：

```typescript
interface ArtifactRendererContribution<TPayload> {
  type: string;
  supportedSchemaVersions: readonly number[];
  parsePayload(value: unknown): TPayload;
  render(artifact: ArtifactEnvelope<TPayload>): ReactNode;
}
```

现有 ID 保持：

```text
result_view
chart
markdown
sql
```

新 Extension type 才要求 namespace。

未知 Artifact 使用 metadata fallback；Conversation、Evidence、relations 和来源仍可读。

## 12. Shell state

当前实现（`desktop/src/stores/workspaceStore.ts`）：

```typescript
interface WorkspaceState {
  activeProjectId: string;
  sidebarEntityMode: "projects" | "connections";
  projectSubMode: Record<string, "conversations" | "files">;
  connectionSubMode: Record<string, "conversations" | "database">;
  projectShell: Record<string, ProjectShellState>;
  mainSurfaceByProject: Record<string, MainSurfaceRef>;
  centerMode: WorkspaceCenterMode;
  dock: { open: boolean; activeTabId: string | null };
  dockTabs: WorkspaceDockTab[];
}
```

`activeDatasourceId`/`activeConversationId` 是当前 Project 内的导航选择，不等于 Project identity。ShellStore 只提供通用 `openDockTab`/`updateDockTab`；它不保存 SQL draft/entries、表选择、表子页或 Artifact payload，也不提供 `openDockConsole` 等领域打开动作。

- `sqlConsoleStore`：SQL console state + canonical `openConsole`；
- `tableWorkspaceStore`：`selectedTables`/`tableSubTabs` + `openTable`/`openMultiTable`；
- `artifactDockStore`：`openArtifacts`/`openArtifact`；
- `workspaceFileStore`：`openFile`。

`WorkspaceDockTabKind` 是开放 string；Shell/Registry 不 switch 所有 domain kind，未知 kind 由 Registry fallback 渲染。

## 13. View state

业务 View 自己拥有临时状态：

```text
SqlConsoleViewStore[projectId]
  draft / transcript / running / result / error / selectedDatasource / scroll

TableViewStore[canonical table key]
  subview / filter / view options

Artifact
  canonical repository/query cache projection
```

SQL Console 首版保持“一个 Project 一个 console state”。因为一个 Project 可有多个 DataSource，console 内允许选择当前 Project 下的 DataSource；切 Project 后恢复各自 SQL state。

关闭 Dock View 默认只隐藏 View。是否清除业务 state 由 View lifecycle 决定，不能让 ShellStore自行删除业务状态。

## 14. Canonical View rules

首批：

```text
SQL        one per Project
Table      one per Project + datasource + canonical table
Artifact   one per Artifact ID
MultiTable one per Project + datasource + canonical sorted object set
```

MultiTable canonical key 使用去重后稳定排序的 object IDs，不使用打开顺序或递增 counter。

## 15. 关键交互

### New Conversation

- active Project 必须确定；
- 在当前 datasource-bound AgentSession 下必须有 active DataSource；
- 沿用现有 create/send 生命周期；
- 不创建新的 Conversation 页面框架。

### SQL

- Project action / Command Palette / Conversation SQL action 都调用 `openSql(projectId, sql?)`；
- AI → SQL 不自动执行；
- 非空 draft 不静默覆盖；
- SQL result/error → AI 只预填 Composer；
- Conversation 切换不关闭 Project SQL console。

### Table

- Data list click → Dock Table；
- Preview/Schema/ER 只是 Table View subview；
- Table → SQL 激活 Project SQL console，并选择对应 datasource；
- 同一 canonical table 重复点击只 activate。

### Artifact

- AI 生成 Artifact 只产生 Conversation reference；
- 用户点击后打开 Dock；
- 不自动压缩/切换 Conversation；
- renderer 复用。

### Settings

进入前保存 Shell UI identity/layout，返回恢复。View business store 保持自己的状态。

## 16. 模型与 UI 边界

模型不能要求：

```text
open tab X
render component Y
resize Dock
```

正确链路：

```text
Model
→ Tool
→ Resource / Artifact
→ Conversation reference
→ user/UI action
→ Dock contribution
```

Runtime wire 不包含 React component、Dock command 或 layout 指令。

## 17. Feature flag 与迁移

Shell V2 使用短期 feature flag。

允许短期 Navigation facade 将旧 `openXxxTab()` 调用转到新 Shell action，但 facade 必须有删除条件；不能形成长期“旧 Tab API → Adapter → Dock API”双模型。

迁移完成后删除：

- Global WorkspaceTabs；
- central domain WorkspaceRouter branches；
- Conversation History tab；
- Datasource Settings tab；
- Conversation ArtifactDock layout container；
- ContextDrawer 容器中被 Table/Conversation owner 接管的职责；
- `workspaceStore` 中业务 payload ownership。

## 18. 验收

- 使用真实 Project API/model；
- Project 与 Datasource 不混同；
- 当前不存在的 Project Edit API 不被文档虚构；
- Main 常态 Conversation；
- Global Tabs 删除；
- Dock 默认关闭且全应用唯一；
- 新 Dock View 只需 contribution registration；
- Main Surface 不被无必要 Registry 化；
- ShellStore 无 SQL Result、Artifact payload、Table metadata、File content；
- 一个 Project 一个 SQL console state；
- Table/Artifact/MultiTable canonical dedup；
- Settings round trip 恢复 Shell UI；
- unknown View/Artifact fail-soft；
- 模型不直接控制 Dock；
- legacy navigation facade 在 rollback window 后删除。
