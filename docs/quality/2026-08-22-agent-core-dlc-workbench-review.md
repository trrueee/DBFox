# Agent Core、Capability DLC 与 Workbench 深度质量评审

> 文档类型：质量评审与整改依据
>
> 状态：当前
>
> 最后核验：2026-08-23
>
> 基线：`feat/quiet-workbench@7902ced52339fb0e5d12282d03bf07a71166cbcd`
>
> 范围：Agent Resource authority、Runtime DLC composition、Project/Conversation/Data/Workspace 模型，以及 Workbench Dock、Project Resource Sidebar、Conversation Composer

## 1. 结论

当前 Runtime 已经具备应当保留的正确核心：Project 资源发现、服务端授权、canonical version fence，以及持久化到 `AgentSessionInput.resource_refs_json` 的不可变 Run authority。重构不应另建 Agent Runtime，而应让执行期资源模型、Conversation intent、Workbench 交互和 first-party domain composition 收敛到这条主链。

本轮确认五个高价值问题：

| 优先级 | 结论 | 状态 | 影响 |
| --- | --- | --- | --- |
| P1 | 同 kind 多资源在 Tool Runtime 中退化为单值 | 已修复（阶段 A） | Runtime 已以 `(kind,id)` 解析并有双同类资源回归测试 |
| P1 | 前端 UI focus 与 DLC contributor 可静默扩大下一次 Run 的 requested resources | 已修复（阶段 B） | durable intent、显式 context selection 与 server admission 已闭环 |
| P1 | `DataSource.database_name` 曾把 Connection 与 Database 粘连；`Project.workspace_root` 已物理删除 | 已修复 | System Data 使用 `ConnectionProfile → DatabaseResource(s)`；旧 HTTP/Workbench DataSource 管理面与 Core Data 表已删除 |
| P2 | Dock tab 使用 flex 收缩后的宽度规划 overflow | 已修复并实机验收 | 900px 窗口下 active tab 可读，其余进入 overflow |
| P2 | 左侧 Resource ScrollArea 可发生水平漂移；Composer 在当前提交被压缩 | 已修复并实机验收 | 资源树固定列宽；Composer 恢复旧版比例并与正文同 rail |

System Data 的连接创建 Dialog 已由 DLC 自有 Connector 接管：核心字段首屏完成、数据库类型使用轻量
segmented choice、连接选项渐进披露、凭据经 Host broker 写入 OS vault。旧连接管理 Dialog 仅供源码
System Data 是源码与 Frozen 发行的唯一连接管理面；Kernel-only 启动不会注册旧连接 fallback。

## 2. 值得保留的基础

- `RequestedResourceRef` 不接受前端 version，服务端通过 `discover_project_resources()` 与 `authorize_project_resources()` 附加 canonical version。
- `ResourceScopeRef` 已以 `(kind, id)` 校验唯一性，协议层没有把 kind 错当完整身份。
- Runtime DLC 已有 `.dbfox-dlc → verify → install → snapshot → typed host contributions` 正式链路。
- `dbfox.github` 已证明 DLC 自有 SQLite、幂等 legacy import、失败保留、absence/conformance 与冻结包身份。
- SQL 仍有唯一 `sql_validate → immutable Artifact → sql_execute_readonly` 执行链；重构不得引入第二条 SQL 路径。
- Dock 已有 host-owned envelope、独立 collapsed rail、registry 和 overflow menu，问题可以在现有边界修复，不需要再建 Dock framework。

## 3. 深度缺陷报告

### 3.1 同 kind 多资源在执行期丢失身份

- **位置：** `engine/tools/runtime/attempt.py::CompositeResourceResolver.resolve`、`engine/tools/runtime/resource_context.py::build_tool_scope_context`、`engine/tools/runtime/context.py::ToolRunContext`
- **结论状态：** 已修复（2026-08-22，阶段 A）
- **类型与严重程度：** 高 | **修复优先级：** 高
- **证据与复现：** `ResourceScopeRef.canonical()` 返回 `(kind,id)`，但 resolver 返回 `dict[str, Any]` 并执行 `resolved[ref.kind] = resolver(ref)`；scope builder 对每个 required kind 使用一次 `next(...)`；`require_resource(kind)` 只返回单值。现有测试只覆盖一个 database 与一个 workspace，没有两个同 kind ref 的执行合同。
- **触发条件与根因：** 一个 Run 授权两个 `database` 或两个 `github.repository`，而工具声明该 kind。协议身份模型已经升级，执行上下文仍停留在“一种 kind 一个资源”。
- **影响范围：** 跨库分析、同 Project 多仓库、未来任意同类资源。最危险的结果不是明确失败，而是 Agent 看到的授权集合与工具实际使用集合不一致。
- **建议修复方案：** 引入 `ResourceKey(kind,id)`；resolved resource 使用 `Mapping[ResourceKey, ResourceHandle]`；上下文提供 `resource(ref)`、`resources(kind)` 和显式 `require_one(kind)`。工具需要多数据库时把 resource id 放入工具输入并再次校验它属于当前 Run。
- **建议回归测试：** 两个同 kind ref 均被解析且保持顺序；`require_one` 在 0/2 个资源时明确失败；按 `(kind,id)` 读取正确 handle；in-process 与 worker transport 结果一致。

### 3.2 UI focus 与 Run authority 混淆

- **位置：** 历史路径为 `conversationStore.ts::sendMessage/createAndOpenConversation` 与已删除的 `requestedResourceComposition.ts`；当前合同位于 `ConversationResourceIntent`、`conversationContextSelection.ts`、`ResourceContextPicker.tsx`
- **结论状态：** 已修复（2026-08-22，阶段 B）并通过 1440×900 实机复验
- **类型与严重程度：** 高 | **修复优先级：** 高
- **证据与复现：** Conversation 创建读取 `activeDatasourceId`；发送时 Data contributor 自动加入该 datasource，Workspace contributor 根据 `Project.workspace_root` 自动加入 workspace，Runtime DLC 也可注册 requested-resource contributor。用户未在 Composer 明示选择资源，也可能形成非空 requested resource set。
- **触发条件与根因：** 打开/浏览资源后发送消息，或启用一个带 requested-resource contributor 的 DLC。根因是把 connector 的便利聚合放进 authority 路径。
- **影响范围：** 用户对“Agent 这次能用什么”的理解、审计解释、DLC 能力边界和未来敏感资源。
- **建议修复方案：** Core 持久化 `ConversationResourceIntent`；Composer 由 Host 渲染 context chips；DLC UI 只能通过 Host selection API 响应用户操作，不能静默贡献 authority。发送时只合并 durable intent 与本条消息显式 attachment，服务端继续做 membership authorization 与 version fence。
- **建议回归测试：** 左栏浏览资源不改变下一次 input；添加/移除 chip 改变 intent；DLC 未经用户操作不能加入 requested refs；非法/陈旧 ref 被服务端拒绝；前端不发送 version。

### 3.3 Project、Workspace、Connection 与 Database 模型粘连

- **位置：** `engine/models.py::Project/DataSource`、`engine/schemas/project.py`、`desktop/src/features/projects/ProjectCreateForm.tsx`、`desktop/src/features/resources/DataConnector.tsx/WorkspaceConnector.tsx`
- **结论状态：** 目标模型已落地；旧 DataSource 管理面为待删除迁移债务
- **类型与严重程度：** 高 | **修复优先级：** 中（必须在删除字段前完成迁移）
- **证据与复现：** Project 持有 `workspace_root`；DataSource 同时持有连接坐标、CredentialRef、连接 generation、单个必填 `database_name`、catalog revision 和数据库对象；创建 Project 强制选择文件夹。
- **触发条件与根因：** 一个服务器暴露多个数据库、Project 没有本地目录、Workspace/GitHub/Data 需要平等组合，或 Data/Workspace 迁入 System DLC。
- **影响范围：** Core schema、API、迁移、备份恢复、Catalog、SQL、Sidebar、Conversation compatibility fields。
- **建议修复方案：** Project v2 只保留 identity/metadata；Data DLC 采用 `ConnectionProfile → DatabaseResource → provider-owned objects`；Workspace DLC 自有 Project binding。复用 GitHub DLC 的独立状态库和 legacy import 模式，不建 Core 万能 `ProjectResourceBinding(config_json)`。
- **建议回归测试：** 无文件夹 Project；一个 MySQL connection 发现多个 DatabaseResource；PostgreSQL 每个 database 使用独立连接；SQLite 文件形成一个 DatabaseResource；DLC absence 时 Core 可启动；迁移可重放且冲突拒绝静默覆盖。

### 3.4 Dock overflow 以收缩后宽度作为规划输入

- **位置：** `desktop/src/features/appShell/WorkspaceDock.tsx::planDockTabWindow/registerTabNode`、`WorkspaceDock.css::.workspace-dock__tab`
- **结论状态：** 已修复并通过长资源列表实机复验
- **类型与严重程度：** 中 | **修复优先级：** 高
- **证据与复现：** 真实页面在 900×760、SQL Console 加两个 table view 时出现标题和关闭按钮重叠。`.workspace-dock__tab` 使用 `flex: 0 1 auto`，DOM ref 记录的是已经被压缩的 `offsetWidth`，规划器因此误判所有 tabs 均能直接显示。
- **建议修复方案：** tab 本体禁止收缩，规划 intrinsic width；active tab 必须直接可见，其余进入 overflow。collapsed rail 继续只显示 icon，不渲染文字。
- **建议回归测试：** 320px Dock 下三条长标题只出现可容纳的 direct tabs；overflow 可打开隐藏 tab；折叠态没有 `role=tab` 文本；1440/900 和窄窗口截图无重叠。

### 3.5 Resource tree 水平漂移与 Composer 视觉回归

- **位置：** `desktop/src/features/resources/ProjectResourceSidebar.tsx`、`desktop/src/features/datasource/DataSourceTree.css`、`desktop/src/features/conversation/workspace/conversationWorkspace.css`
- **结论状态：** 已修复并通过 900px/1440px 实机复验
- **类型与严重程度：** 中 | **修复优先级：** 高
- **证据与复现：** 打开长表格内容后折叠 Dock，Sidebar ScrollArea 的水平位置可偏移，树只剩长对话标题尾部。Git history 显示基线提交把 Composer 从 `min-height:86px`、textarea `44px`、按钮 `36px` 压缩为 `52px/30px/28px`，与用户反馈的上一版更好一致。
- **建议修复方案：** Sidebar viewport 明确 `overflow-x:hidden`，每一级 row/body 都建立 `min-width:0/max-width:100%`；UI focus 与多选状态分离；恢复 Composer 上一版的空间比例，但保持透明外围和正文同一 rail。
- **建议回归测试：** 长标题、深目录、50+ tables 下 `scrollLeft` 始终为 0；键盘 focus 可见；Dock 开关不改变 Sidebar 横向位置；Composer 与 message column 的 computed width/left/right 一致。

## 4. 成熟方案与复用决策

调查日期：2026-08-22。

| 能力 | 调查结果 | 决策 |
| --- | --- | --- |
| Workbench contribution points | VS Code 将 Sidebar/Panel/View Container 与 extension contribution 分开，TreeView 用 data provider；extension 不能直接修改 Workbench DOM。[官方 Contribution Points](https://code.visualstudio.com/api/references/contribution-points)、[Extending Workbench](https://code.visualstudio.com/api/extension-capabilities/extending-workbench) | 参考其“Host owns chrome / extension contributes typed content”原则；不引入 VS Code 依赖，不复制其完整 View framework |
| Extension isolation | VS Code Extension Host 负责运行 extension，并通过独立 host 与 lazy activation 降低 UI/启动影响。[官方 Extension Host](https://code.visualstudio.com/api/advanced-topics/extension-host) | DBFox v1 继续 trusted-publisher-only；不把当前同进程 DLC 宣称为安全沙箱，未来 untrusted gate 单独决策 |
| Tree keyboard/focus | WAI-ARIA 明确 DOM focus 与 selection 是不同状态，并规定方向键、Home/End、Enter 等交互。[W3C Tree View Pattern](https://www.w3.org/WAI/ARIA/apg/patterns/treeview/) | 复用交互语义；实现最小 hosted resource tree，不引入新 tree library，也不把 Sidebar 做成通用大型 Tree framework |
| 数据库层级 | PostgreSQL 连接一次只能访问一个 database，database 下有 schemas；MySQL `SCHEMATA` 中 schema 即 database；SQLite database 通常是单文件。[PostgreSQL](https://www.postgresql.org/docs/18/ddl-schemas.html)、[MySQL](https://dev.mysql.com/doc/refman/8.4/en/information-schema-schemata-table.html)、[SQLite](https://www.sqlite.org/onefile.html) | Core 只定义 Connection/DatabaseResource 边界；provider adapter 决定 database/schema/table 层级，禁止强制统一树深度 |
| 连接创建 | SQLAlchemy `URL` 已提供 immutable connection URL 和 dialect/driver/host/database 字段。[SQLAlchemy Engine](https://docs.sqlalchemy.org/en/20/core/engines.html) | 继续复用 SQLAlchemy Engine/URL，不自研连接池；但 durable ConnectionProfile/DatabaseResource 是产品领域模型，不能用 URL 代替 |
| Extension secrets | VS Code 为每个 ExtensionContext 提供不可同步的 encrypted SecretStorage；官方同时明确同进程 extension host 具有宿主进程权限。[SecretStorage](https://code.visualstudio.com/api/references/vscode-api#SecretStorage)、[Extension runtime security](https://code.visualstudio.com/docs/configure/extensions/extension-runtime-security) | Core 保留 OS vault；Backend DLC 只获得按签名 manifest credential kind 限定、不可枚举的 `credentials.get`，不获得全局 vault；继续明确 trusted-publisher-only |
| DLC 状态迁移 | 项目内 `dbfox.github` 已有独立 SQLite、幂等 legacy import、冲突检测和 Core removal conformance | Data/Workspace 外置直接复用该迁移方法；不建第二套通用迁移框架，先提取真正重复的最小 helper（若第二个 DLC 证明需要） |
| UI primitives | 当前已有 Radix Dialog/Dropdown/ScrollArea/Tooltip/Tabs、React、Zustand | 不新增 UI 依赖；Dock 和 Sidebar 在现有 primitives 与 Host contract 上修复 |

## 5. 测试矩阵

| 测试目标 | 前置条件 / 输入 | 操作 | 预期 | 优先级 |
| --- | --- | --- | --- | --- |
| 同 kind 多资源解析 | 两个相同 kind、不同 id/version | 构建 Tool context | 两个 handle 均可按 ResourceKey 获取，`require_one` 报 ambiguity | P1 |
| Authority 不随浏览变化 | Conversation intent 只有 DB1 | 左栏打开 DB2/Table，再发送 | frozen refs 仍只有 DB1 | P1 |
| Intent 增删 | DB1/DB2 均属于 Project | 在 Composer 显式增删 chip | 后端 durable intent 与下一次 frozen refs 一致 | P1 |
| Version fence | Intent 指向旧 generation | 更新连接后发送 | admission 拒绝或附加最新 canonical version，不执行旧 handle | P1 |
| Dock tab overflow | 320px Dock、三个长 tab | 激活首/中/末 tab | active 直接可见，其余在 overflow；无 box overlap | P2 |
| Dock collapsed | 多 tab | 收起 Dock | 44px rail、icon-only、均可通过 tooltip/aria-label 识别 | P2 |
| Sidebar overflow | 长对话名、长表名、深目录 | 打开资源、切 Dock、键盘导航 | `scrollLeft=0`、文本 ellipsis、focus/selection 分离 | P2 |
| Composer rail | Dock 开/关、宽/窄窗口 | 比较 message/composer bounds | 同版心、无底部白条、输入高度稳定 | P2 |
| Data migration | legacy DataSource + catalog + history + backup | 重放导入/模拟中断 | 幂等、冲突失败、旧事实保留到 cutover 完成 | P1 |
| DLC absence | 移除 Data/Workspace DLC | 启动 Core 与打开 Project | Core 可启动，资源显示 capability unavailable，不 import domain code | P1 |

## 6. 安全重构路线

1. 先修复三项前端确定性回归，不改变业务 API。
2. 增加 ResourceKey 与多资源保护性测试，再改变 resolver/context。
3. 建立 durable Conversation Resource Intent 和 Host-owned selection；切断 requested-resource contributor 的 authority 作用。
4. 删除 Session/Run datasource 新写入，再以 migration 清除兼容字段。
5. 冻结 Project v2，先迁 Workspace binding，后删除 `workspace_root`。

本轮实施结果：Workspace binding 已完成签名包 cutover，`projects.workspace_root` 已经 Alembic
物理删除；Core Workspace service/builtin/context 与其隐式 resolver 也已删除。关键路径 containment、
二进制拒绝、Artifact freshness 和 DLC disable/state retention 由包级 conformance 接管。
6. 在 Data 域内拆 ConnectionProfile 与 DatabaseResource，保持唯一 SQL 校验/执行链。
7. 复用 GitHub 的独立 DLC state/import/cutover/absence 证明，外置 Data，再外置 Workspace。
8. Core composition 不再 import Data/Workspace concrete code 后，删除所有 legacy fallback 和兼容 API。

每一阶段必须有独立迁移、回归门禁、失败保留和旧路径删除条件；不得长期双写，也不得同时维护 Core 与 DLC 两份 Data/Workspace 事实。

## 7. 2026-08-22 已落地证据

- Resource resolver 与 `ToolRunContext` 使用 `ResourceKey=(kind,id)`；新增
  `resource(ref)`、`resources(kind)`、`scopes(kind)`、`require_one(kind)`。
- `build_tool_scope_context()` 保留同一 required kind 的全部 frozen refs，不再 `next()`
  截断；第三方 resource resolver 测试已改为两个同 kind resource。
- Extension API v2 已删除 `require_resource(kind)`；v1 包在安装时明确拒绝，所有官方 DLC 使用 `require_one(kind)` 或精确资源身份
  Runtime Extension 合同；新 Core/System DLC 调用点禁止使用。
- 900×760 真实页面验证：SQL Console + 两个长 table tab 时只保留 active tab，
  另外两个进入 overflow；无标题/关闭按钮重叠。
- 资源树覆盖 Radix ScrollArea 的 intrinsic `display:table` wrapper，长表名聚焦和 Dock
  开关后不再横向漂移；50 张表显示轻量筛选与结果计数。
- Composer 恢复 `86/44/36px` 空间比例，透明外围保留；header、message、composer 和
  pinned action 不再在 Dock 打开时切换独立 920px 版心。
- `ConversationResourceIntent` 使用独立 Core 表保存无 version 的 `(kind,id)`；旧
  `datasource_id` 仅在 Alembic upgrade 中一次性播种为可见、可移除 intent，workspace
  membership 不参与播种。
- create/PATCH/input admission 均重新调用 Project resource authorization；空 intent 冻结为空
  resource refs，不再通过 legacy datasource/workspace fallback 静默扩权。
- Frontend 删除 `requestedResourceComposition` 与 product/DLC 自动 authority 聚合；新对话
  draft、已有 Conversation PATCH、Composer chips 和左树显式加入/移除共用 Host-owned
  selection 路径。
- 1440×900 真实页面验证：左树显式加入后首页 Composer 出现 `creatorhub` chip；打开旧
  Conversation 后移除会产生成功 PATCH，并同步清掉 Composer chip；控制台 0 error。
- Stage C 完整 Agent deterministic suite：`330 passed, 3 deselected`。Context、Tool、
  Memory、Artifact 与 Result View 的新 Run 路径都从 frozen `AgentSessionInput.resource_refs_json`
  读取 authority；Session/Run 不再写 datasource compatibility identity。
- Stage D Engine deterministic core suite：`975 passed, 108 deselected`；Workspace System DLC
  package 与一次性数据迁移测试 `3 passed`。默认 Core snapshot 已证明不含 Workspace
  tool/provider/resolver/context；禁用 DLC 后 contribution 消失而 `state.sqlite3` 保留。
- Project create OpenAPI 已收敛为 name/description，生成 client 已更新；前端定向交互测试
  `30 passed`，`typecheck:test`、lint、production build 均通过（lint 仅有既有 Fast Refresh warning）。
- Extension API v2 尚无 installable DLC isolated worker，故没有放宽 `filesystem_write`
  安全限制。System DLC 当前发布 read/search；旧 Core isolated write vertical 改为 fail-closed
  证明，启用写入的删除条件是 package-aware worker 与 frozen Sidecar 回归完成。
- Stage E 已建立 Data DLC 自有 `ConnectionProfile → DatabaseResource(s)` 目标状态和可重放、
  冲突拒绝的 legacy staging import。只有 DatabaseResource 是 authority；Profile 与 Database
  identity 分别具有 generation fence。网络/SQLite/SSH/TLS 不变量在写入源头校验。
- 调研确认既有 `engine.connectivity.ConnectionFactory` 已覆盖凭据、SSH/TLS、pool 与 driver
  生命周期，后续整体迁移复用，不另造连接栈。Core 新增的 Credential Broker 只有 manifest-kind
  scoped `get`，没有 vault 枚举、Session、store/delete 或跨库 lease 写协议。
- Stage E 定向门禁：Data domain、staging import、Credential Broker 合计 `11 passed`；相关
  DLC/Host Python 源通过 pyflakes。
- Data System DLC 新增 hosted `ConnectionProfile → DatabaseResource` Connector；profile 展开、
  database focus 与 explicit context selection 分离，不注册 requested-resource contributor。
  Package frontend entrypoint conformance 为 `7 passed`，frontend fixture 为 `1 passed`；
  `typecheck:test` 与 lint 通过（lint 仅 25 条既有 Fast Refresh warning）。
- Stage E 执行侧新增显式 database resource selection：单库可省略 `database_id`，多库必须指定，
  未在 frozen refs 内的 id 直接拒绝。Approval authority 从 `datasource_generation` 升级为完整
  `ResourceScopeRef`；Artifact envelope 以新 `resource_refs_json` 保存精确来源并验证为 Run
  authority 子集。复合字符串 resource version 全程原值比较，不再经 `int(...)` 丢失语义。
- 官方 System DLC 生产 bootstrap 尚未伪装为“已完成”。当前调查确认 lifecycle 只有用户安装
  与 registry compile，没有 bundled package seed。阶段 F 将采用随签名桌面包发布、固定 digest、
  启动时仍走 package verify → installed snapshot 的方案；不会添加 source-tree 隐式 loader，
  也不会把 trusted publisher 错称为 OS sandbox。
- 本轮完整确定性门禁：Engine `989 passed, 108 deselected`；Agent Runtime
  `331 passed, 3 deselected`；完整 Alembic migration 链 `31 passed`；Frontend
  `99 files / 442 tests passed`；production build 通过。
  Core mypy（312 source files）、逐 DLC backend mypy、工程合同与 Stage E 定向集合（42 项）、package verifier、
  `git diff --check` 均通过。
- Conversation 产品合同已删除 `datasource_id` 与 `context_tables`：create/PATCH/snapshot/list、
  生成 API client、Zustand 与 Project Sidebar 都只使用 `project_id + resource_intents`。迁移
  `b9c0d1e2f3a5` 已物理删除 `agent_sessions.datasource_id/context_tables_json`；downgrade 只从仍可解析为
  Core DataSource 的 database intent 恢复旧身份，不为 DLC-only resource 制造映射或第二份事实。
- `authorize_project_resources()` 已删除 `fallback_datasource_id`。缺少显式 requested identities
  必须得到空授权，即使 Project 下存在数据库也不能隐式获得 authority。新增/更新的定向门禁为
  backend `41 + 26 passed`、frontend `9 files / 48 tests passed`，相关 mypy、pyflakes 与
  `typecheck:test` 通过。
- Stage F 已实现真实 production bootstrap：release builder 使用外部 Ed25519 私钥构建确定性
  `dbfox.data` / `dbfox.workspace` 包，Frozen Sidecar 内嵌 publisher key 与 exact pins，Electron
  只注入 `Resources/system-dlcs` 路径。启动复用 verifier、content-addressed store、registry
  selection 与 compiler snapshot；tampered package 在 registry 写入前拒绝。
- Host trust roots 与用户持久 trust store 采用单一并集合约；持久状态不能移除或替换内嵌 key，
  也没有新增第二份 trust registry。首次安装按 package pin 设置默认启用，后续启动保留用户
  disable；包升级只切换 Frozen build 指定的 exact digest。
- 初期 bundle 曾以 `dbfox.data.default_enabled=false` 验证互斥组合；在 Data SQL/Catalog/Preview/
  Result/Chart/SQLite Backup 垂直链与耐久 Artifact read path 完成后，发行 pins 已切换为 Data/Workspace
  均默认启用。双包启动证明两者 active、0 activation failure，legacy Data Tool 不进入同一 snapshot。
- System bundle、trust merge、Sidecar staging、DLC compiler 与 Workspace package 定向回归：
  `84 passed`；Electron supervisor `8 passed`；新增/修改 Python 源通过 pyflakes 与 mypy。
- Conversation 历史列删除后的完整迁移链 `31 passed`，Agent Runtime `331 passed, 3 deselected`；
  Engine deterministic `993 passed, 109 deselected` 后仅发现一处测试写死旧 Alembic head，更新为
  `b9c0d1e2f3a5` 后定向通过。隔离临时数据库执行 upgrade + Alembic check 为
  `No new upgrade operations detected`，未迁移或修改本机开发数据库。
- Tool materialization 与 execution scope 已删除 pre-P4 datasource/workspace derivation。
  `frozen_resource_refs` 缺失和显式空集合都表示零 authority；`datasource_id` 即使仍存在于
  Data 执行兼容请求中，也不能扩大数据库或 Workspace 权限。定向合同 `27 passed`，随后
  Agent Runtime `330 passed, 3 deselected`、Engine deterministic `994 passed, 109 deselected`；
  pyflakes 与 mypy（314 source files）通过。
- Run authority 的物理兼容债务继续删除：Alembic `c0d1e2f3a4b7` 删除
  `agent_runs.datasource_id/datasource_generation`、`agent_session_memories.datasource_id` 及对应
  FK/index；Run OpenAPI/生成 client/前端 projection 同步移除该字段。历史 Input 缺失 frozen refs
  时 fail closed，不再读取 Run 行 fallback。迁移链 `32 passed`，Agent Runtime `330 passed,
  3 deselected`，相关前端 `7 files / 40 tests passed` 且 `typecheck:test` 通过。
- Extension API v2 也删除 Memory Catalog scope JSON 中的 datasource/generation 镜像，统一为
  canonical `resource_ref`。迁移 `c0d1e2f3a4ba` 精确失效旧的可重建 Catalog projection，保留
  Memory Core 与其他 DLC projection；迁移与 Memory 定向回归 `51 passed`。最终 Engine
  deterministic `973 passed, 6 skipped, 115 deselected`，Agent Runtime `329 passed,
  3 deselected`，工程合同 `33 passed`，DLC 前端夹具 `4 files / 11 tests passed` 且
  `typecheck:test` 通过，pyflakes 与 mypy（315 source files）通过。
- Completion contribution seam 已落地到公共 Extension API 与 immutable snapshot。Core 通用
  `SemanticCitationConstraint` / `SemanticArtifactCompletionSupport` 按 semantic capability 工作；
  `dbfox.data` package 通过 `host.completion` 声明 `query_result` 语义。禁用 package 后 constraint
  与 support 同时消失，ID 冲突会拒绝整个 package，定向 Data/Runtime/Completion 回归
  `40 passed, 2 skipped`，Data package 独立 conformance `10 passed`。
- Tool execution context 的 Data 单值镜像已删除：`ToolRequest`、isolated attempt request、
  `ToolRunContext` 不再拥有 datasource/generation/dialect 字段，legacy Data Tool 也只从 frozen
  `ResourceScopeRef` 选择数据库。查询取消 registry 只在 Run 恰有一个 database ref 时绑定，
  多库不会被压成 active datasource；Tool/DB/Attempt 定向回归 `97 passed`。
- 本轮收口后的完整门禁：Engine deterministic `966 passed, 6 skipped, 110 deselected`；Agent
  Runtime `330 passed, 3 deselected`；Frontend `100 files / 439 tests passed`；Alembic migration
  `32 passed`；engineering contracts `30 passed`。Python pyflakes、Core mypy（310 source files）、
  frontend `typecheck:test`、lint（0 error，22 条既有 Fast Refresh warning）与 production build
  全部通过。
- Frozen refs 存储完成规范化：`c0d1e2f3a4b8` 将历史 NULL backfill 为 `[]` 后把
  `agent_session_inputs.resource_refs_json` 设为 NOT NULL；零 authority 不再有第二种数据库表示。
  Migration/resource codec/session admission 定向回归 `59 passed`。
- Frontend SDK/Host/loader 已删除 deprecated `requestedResources` 注册与聚合 seam，官方 GitHub
  package 同步迁到显式 `contextSelection` 模式；不存在“保留但不消费”的 authority 旁路。
  未被 product composition 使用的旧 Core `WorkspaceConnector.tsx` 同步删除，资源树只由
  `dbfox.workspace` package 贡献。前端完整回归 `99 files / 441 tests passed`，test typecheck、
  lint（仅 23 条既有 Fast Refresh warning）与 production build 通过。
- Project/Workspace 最终 cutover 已落地：`c0d1e2f3a4b6` 在删列前再次运行可重放 importer，
  覆盖初次切换后被旧版本晚写入的目录；Core `Project` model、OpenAPI/generated client 与最终
  SQLite schema 均不再含 `workspace_root`。迁移/Project/Workspace 包定向集合 `39 passed`。
- Core Workspace service、builtin Tool、Context contributor、resolver 与专属旧测试已删除；
  Kernel 的 materialization/attempt runner 测试改用无文件系统领域逻辑的 Resource probe。
  Workspace 签名包 conformance 接管 path containment、binary rejection、Artifact freshness、
  disable/state retention 与 frontend Artifact renderer 注册。
- 删除后的完整门禁：Engine deterministic `964 passed, 6 skipped, 110 deselected`；Agent Runtime
  `330 passed, 3 deselected`；Frontend `100 files / 439 tests passed`；工程合同 `30 passed`；
  pyflakes、mypy（310 source files）、test typecheck、production build 与 `git diff --check` 通过；
  lint 0 error，仅 22 条既有 Fast Refresh warning。
- Data 签名包 conformance 现覆盖 Profile 多 DatabaseResource、双 generation fence、跨 Project
  拒绝，以及 disable 后 contribution 消失但 state 保留、重新启用恢复；该文件 `8 passed`。
- Authority 存储最终规范化后，Agent Runtime 完整集合为 `329 passed, 3 deselected`，Python
  pyflakes 与 mypy（311 source files）通过；Migration/resource codec/session admission 定向集合
  `59 passed`。此前 `330` 的差异来自删除了 nullable codec 行为本身的旧测试，不是覆盖率缺口。
- Core `Project` 已删除到 DataSource/Backup 的反向 ORM collections。调查确认没有业务调用者；
  验证发现同事务插入仍需要 Data child 到 Project 的单向关系做 SQLAlchemy dependency ordering，
  因而保留真实的 `Data → Project identity` 边界，而不是恢复双向对象图。Project/Backup/
  datasource lifecycle/runtime reset 定向回归 `51 passed`。
- 临时 legacy Data provider、resolver 与 completion 声明已从 Kernel composition 收拢到
  `engine.tools.builtin.data_capability`，owner 统一为 `dbfox.data`；`runtime_composition.py` 不再
  import `DataSource`，Compiler 只在明确的 legacy 开关内取这些通用 contribution。未新增依赖、
  状态镜像、service locator 或 fallback；Data/DLC/Resource/Completion 定向回归 `47 passed,
  2 skipped`，独立 Data package conformance `10 passed`。新增防回归工程合同后该集合为
  `32 passed`。
- 本次 composition/Project 边界收口后的完整 Engine deterministic 集合为 `966 passed,
  6 skipped, 113 deselected`；全量 pyflakes 与 mypy（312 source files）通过，`git diff --check`
  无空白错误（仅工作树既有 LF→CRLF 提示）。
- 2026-08-23 Credential recovery 调研：SQLite 官方 `ATTACH DATABASE`/WAL 文档确认 WAL 下多文件
  commit 不具备跨文件原子性；SQLAlchemy 官方文档的 two-phase transaction 只适用于底层支持 2PC
  的后端。因此未采用 ATTACH、切换 journal mode 或 SQLAlchemy 多 bind 假事务，选择 owner-bound
  recoverable saga。
- Recovery seam 第一段已实现：Credential Core 不再 import `DataSource`，Runtime snapshot 新增带
  owner 的 read-only reference probe；legacy Data 与签名 `dbfox.data` 分别查询自己的唯一 durable
  state。DLC 注册受 manifest credential permission 约束且只允许一个 probe。定向 Credential/Data/
  Host/Runtime 回归 `54 passed`，pyflakes 与 mypy（312 source files）通过；工程合同新增
  “Credential lifecycle 不得查询 Data 字段”的防回归项。
- 增加真实跨存储恢复证明后，Credential/Data/Host/Runtime/engineering 定向集合为 `88 passed`。
  完整 Engine deterministic 为 `968 passed, 6 skipped, 114 deselected`，Agent Runtime 为
  `329 passed, 3 deselected`，工程合同 `33 passed`；全量 pyflakes、mypy（313 source files）和
  `git diff --check` 通过。
- 2026-08-23 写侧 credential adoption 已接入 generic DLC operation Host。Lease claim 新增 durable
  `owner_id / owner_operation / owner_project_id`，调用顺序固定为 Core intent commit → DLC 单库事务 →
  exact-owner probe 验证全部 refs → Core finalize；不自动重放 handler。owner 不活跃时保留 claim，
  handler 虚假 success 但未耐久拥有全部 refs 时返回 `CREDENTIAL_ADOPTION_NOT_DURABLE` 并清理 lease。
  Frontend SDK operation options 增加 opaque `credentialLeaseId`，只映射到正式 OpenAPI header。
  Credential/Data/Host 定向回归当前为 `26 passed`，新增正反 operation proof 单测通过；完整门禁见本轮
  后续记录。
- Owner-bound credential adoption 收口后的门禁：相关 Credential/Data/DLC Host/Runtime/Migration/
  engineering 定向集合 `123 passed`；Engine deterministic `970 passed, 6 skipped, 114 deselected`；
  Agent Runtime `329 passed, 3 deselected`；Frontend `100 files / 439 tests passed`。Frontend
  `typecheck:test`、lint（0 error，22 条既有 Fast Refresh warning）与 production build 通过；Python
  pyflakes、mypy（313 source files）通过。首次 frontend 全量命令因 120 秒外层超时被终止，使用同一
  串行参数和 300 秒上限重跑后完整通过，不把超时误记成测试失败。
- Data management UI cutover 的 Credential Broker 前置 seam 已补齐：Frontend Extension Host 新增绑定
  当前 `dlc_id` 的 `credentials.enrollBatch`；Engine 从 immutable active identity 读取签名 manifest
  permissions，在 vault write 前拒绝未声明 kind，成功只返回 opaque refs + lease。真实 HTTP proof 覆盖
  允许的 datasource password、拒绝的 LLM key、lease header adoption、durable owner finalize 与虚假
  success cleanup；相关后端 `23 passed`、前端 Host/Data fixture `9 passed`，生成 API 与 test typecheck 通过。
  再次完整验证为 Engine deterministic `970 passed, 6 skipped, 114 deselected`、Frontend
  `100 files / 440 tests passed`、production build 通过；pyflakes、mypy（314 source files）与
  engineering contracts `33 passed`。
- System Data Connector 已拥有 quiet connection dialog、Profile → DatabaseResource 树、显式
  Conversation context selection 和新建连接动作；Shell 在 `dbfox.data` 激活时不再同时挂载 legacy
  DataConnector，命令面也不再暴露旧连接管理器。发行 bundle 现默认启用签名 Data package；源码直跑
  fallback 有明确 warning 与删除条件。System bundle/Runtime 定向 `15 passed`，前端 Connector/Host/
  command 定向 `7 passed`，test typecheck 与 lint 通过。
- 最终发行切换门禁：Engine deterministic `974 passed, 6 skipped, 120 deselected`；Agent Runtime
  `331 passed, 3 deselected`；engineering contracts `36 passed`；Frontend `101 files / 443 tests`；
  Electron Main/Preload `9 files / 28 tests`。Core 与三个官方 DLC 的 pyflakes/mypy、frontend lint
  （0 error，22 条既有 Fast Refresh warning）、test typecheck、production token/bundle budget 和生产
  build 均通过。

## 9. 最终 Data cutover 证据（2026-08-23）

- Alembic head `e2f3a4b5c6d8` 使用与 Workspace/GitHub 相同的单向、可重放、冲突失败迁移方式：先保存 ConnectionProfile、DatabaseResource identity 和 opaque credential refs，验证 DLC state，再删除 Core Data tables/FTS。没有跨 SQLite 双写、ATTACH 假事务或恢复 fallback。
- Catalog、search docs、query history 与 result rows 没有被复制到第二份事实源：Catalog 在 owner 状态中重建，Result 继续通过有界 Artifact view 访问。
- 生产 composition 只注册 Kernel/Conversation/Remote Job built-ins 与已验证 DLC contributions；旧 Data registrar、Core HTTP routes、Workbench Data components 和 automatic requested-resource contributor 已移除。
- Agent 测试启动与产品相同的签名 System DLC bundle。与旧 Core DataSource/Catalog Memory v4 物理表绑定的场景已退役，Data package domain tests 接管连接、Catalog、SQL、Result 和 backup/restore 证明。
- 本次调查直接复用项目现有 DLC verifier/compiler、typed Host API、Credential Broker、Tool Runtime、Artifact envelope、SQLite/Alembic 和 Workspace 迁移模式。未引入新依赖或供应商锁定；未采用通用 binding JSON、service locator 或内外两套 Data execution chain。
- 最终门禁：Engine deterministic `633 passed, 4 skipped, 120 deselected`；Agent Runtime `282 passed, 8 skipped, 3 deselected`；Frontend `86 files / 369 tests`；Electron `9 files / 28 tests`；Runtime Reset `25 passed`；engineering contracts `36 passed`；pyflakes、mypy（301 source files）、frontend lint/typecheck 和 production build 通过。
