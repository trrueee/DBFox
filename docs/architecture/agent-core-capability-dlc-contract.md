# Agent Core 与 Capability DLC 架构合同

> 文档类型：目标架构合同（ADR）
>
> 状态：已接受
>
> 最后核验：2026-08-28
>
> 适用范围：Project、Conversation、Run authority、Resource Runtime、Capability DLC、Workbench resource/context composition
>
> 实施状态：已完成；切换证据见 [`../quality/2026-08-22-agent-core-dlc-workbench-review.md`](../quality/2026-08-22-agent-core-dlc-workbench-review.md)

## 1. 决策

DBFox 采用以下终态：

> **Core 只拥有 Agent Runtime、Workbench composition、lifecycle 与 authority；Data、Workspace、GitHub 以及未来业务域均为 Capability DLC。Project 是这些 capability 的共同耐久工作上下文，不是数据库、连接或文件夹。**

Data 与 Workspace 作为官方发行、默认安装启用的 **System DLC**，仍必须走与其他受信 DLC 相同的 package verification、snapshot、typed Extension API 和 contribution lifecycle。Core 不保留隐藏的 Data/Workspace 特殊加载路径。

Runtime DLC v1 仍是 trusted-publisher-only 扩展系统，不是恶意代码安全沙箱。

## 2. 唯一稳定关系

```text
Project
  ├─ Conversations
  ├─ Capability-owned resource world
  └─ Artifacts

Project Resource Discovery
          ↓
capability / Tool discoverability only

legacy durable Conversation intent
  + current message Reference authority
          ↓
server project discovery + canonical version fence
          ↓
AgentSessionInput.resource_refs_json
          ↓
immutable initial explicit authority

validated domain Tool call
          ↓
current Project membership + canonical version
          ↓
ToolInvocation.resource_refs_json
          ↓
exact execution authority
```

领域 Tool 的直接执行权威是：

> **Invocation Authority = server-authorized, version-fenced `ToolInvocation.resource_refs_json`.**

`AgentSessionInput.resource_refs_json` 只是不可变 admission fact；它可以帮助 Invocation 选择 identity，
但不能替代调用当时的 Project membership，也不能提供过期 canonical version。

以下等号均禁止：

```text
Project ≠ Resource
Project ≠ Workspace
Connection ≠ Database
Conversation ≠ DataSource
UI Focus ≠ Conversation Intent
Project Membership ≠ Run Authority
Object Selection ≠ Resource Authority
```

## 3. Core 所有权

Core 永久拥有：

- Project identity 与 lifecycle；
- Conversation、Input、Run、Turn、Message；
- `RequestedResourceRef`、`ResourceScopeRef`、`ResourceKey` envelope；
- project resource discovery、server authorization 与 version fence；
- Tool contract/lifecycle、Policy、Approval、Question、idempotency、timeout、cancellation；
- Observation、Artifact、Evidence envelope；
- Context lane/budget 与 Memory lifecycle；
- DLC verifier、installer、registry、activation snapshot 与 typed Host API；
- Workbench Connector/Dock/Artifact/Conversation Context slots；
- Credential Broker 与 native picker 等 OS boundary。

Core 不理解或持久化以下领域语义：

```text
database / schema / table / SQL
workspace root / file path / patch
GitHub repository / issue / pull request
Slack channel / browser page / future capability objects
```

Core 数据模型终态只包含通用 runtime 事实：Project、Conversation、ConversationResourceIntent、SessionInput、Run、Turn、Message、ToolInvocation、Observation、Artifact、Evidence、Approval、Question、Memory projection、Runtime event 与 DLC registry。

## 4. Project v2

Project 是 durable work context：

```text
Project
├── id
├── name
├── description
├── status
├── created_at
└── updated_at
```

创建 Project 只需要名称，可选描述。`workspace_root`、datasource、repository 等 binding 由对应 DLC 在创建后贡献。Project 删除必须先通过 DLC lifecycle 协调其自有状态清理；Core 不建立跨 SQLite foreign key。

## 5. 四层资源概念

| 概念 | 示例 | 是否 Run authority |
| --- | --- | --- |
| Binding / Connection | MySQL server profile、GitHub account binding | 否 |
| Resource | billing database、workspace root、GitHub repository | 是 |
| Object | schema、table、file、issue、PR | 通常否 |
| Selection | tables A+B、file range、artifact | Context hint，不自动扩大 authority |

Project resource 应保持粗粒度。Database 是 Resource；Schema/Table/Column 是 Data DLC object。Workspace root 是 Resource；File 是 Workspace object。用户对象选择可以影响 Context，但不能隐式创造新的 Resource authority。

## 6. Resource Runtime v3

> 实施状态：当前。Tool discoverability 与 ToolInvocation execution authority 已分离；
> Runtime、Tool context、resolver 与 audit 均使用 `(kind,id)` identity，不保留单值 datasource
> 执行通道，也不通过资源选择 Control Tool 扩大 Run authority。

```python
ResourceKey = (kind, id)

resolved: Mapping[ResourceKey, ResourceHandle]

context.resource(ref)
context.resources(kind)
context.scopes(kind)
context.require_one(kind)
```

- 同一 Project 可以包含多个相同 kind、不同 id 的资源。
- `require_one(kind)` 仅服务于明确的单资源工具；0 个或多个都必须给出确定性错误。
- 多资源工具输入必须携带 resource id；Tool Runtime 在 Invocation admission 时验证该 identity
  属于当前 Project discovery ceiling、附加 server-canonical version，并只把这个精确 ref 冻结到
  `ToolInvocation.resource_refs_json`。
- Data 工具的 `database_id` 可以只在 Project 恰好发现一个数据库时省略；多个同 kind 数据库时省略
  必须确定性拒绝，不能取第一个。
- Kernel 不解释跨数据库 join。provider 可以在安全合同允许时实现该领域能力。
- wire uniqueness、resolver identity、context lookup、prompt summary 和 audit log 全部使用 `(kind,id)`。
- 所有 Resource kind 必须是 namespaced identifier；当前 canonical 值包括
  `dbfox.data.database`、`dbfox.workspace.root` 与 `dbfox.github.repository`。裸
  `workspace` 及旧 `github.repository` 由 Alembic `f4a5b6c7d8ea` 一次性改写，Runtime 不保留
  alias、mapper 或 dual-read。
- 一个 DLC 只能注册和直接 resolve `owner_id.*` Resource kind；其 Tool 的
  `required_resources` 也只能引用本 owner namespace。每个 requirement 显式声明
  `selector_field`，或声明从同一 Run 的不可变 Artifact resource refs 派生。普通跨 capability 工作由 Agent
  composition 完成；真正需要联合私有资源的实现必须成为显式 Composition DLC，并在未来先冻结
  dependency contract，不能依赖 `Any` duck typing 偷读另一个 DLC 的 handle。

Tool 的 canonical identity 是 `ToolKey(owner_id, local_name)`，不是全局 `tool.name` 字符串。
DLC 内部合同、Workbench Action 与领域测试使用 local name；Core materialization 在 provider 边界
确定性生成不超过 64 字符的 provider-safe wire name，并把该 name 与 owner/package digest 一起冻结。
因此两个 DLC 可以同时注册相同 local name，而模型、Dispatcher、Policy、Approval、恢复与结算仍只接受
唯一 wire identity。Platform built-in Tool 保留其既有 wire name；这项特权由 composition root 显式声明，
不在 Tool Runtime 中增加 owner 特判。

Tool availability 与 execution authority 是两个合同：

```text
Project discovery kinds
        → 决定本 Turn 可以向模型展示哪些 capability Tools

实际 domain Tool call + validated selector / Artifact
        → Dispatcher 绑定一个最小、精确、server-canonical 的 Invocation authority
        → Policy / Approval / resolver / retry / recovery 全部只消费该 Invocation refs
```

`AgentSessionInput.resource_refs_json` 仍是 immutable admission fact，只保存用户明确附加或 durable
Conversation intent 产生的初始 authority；Run 中途不得修改。自动资源使用不创建 mutable
`RunAuthority`，也不调用 `select_project_resources`。ToolInvocation 是执行权限第一次真正需要被
耐久冻结的边界。

每个 Turn 只保存最多 32 条排序后的 Project resource directory 摘要、完整 kind count 与
`truncated` 标记。超过摘要的资源通过只读、分页、可筛选的 `project_resource_search` 查询；该 Tool
不选择、不授权、不写 Input/Run，也以 developer visibility 隐藏实现噪音。Project 资源数量不会导致
Input admission 失败。

没有 `required_resources` 的 Tool 当前仍按既有语义全局 materialize。显式
`global / project_bound / resource_bound / explicit_only` availability 属于后续协议演进；在真实需求和
迁移方案冻结前不提前增加枚举或兼容层。

## 7. Conversation Intent 与 authority

Core 持久化通用 `ConversationResourceIntent`，内容只允许无 version 的 Resource identity：

```json
[
  { "kind": "dbfox.data.database", "id": "db_1" },
  { "kind": "dbfox.github.repository", "id": "repo_1" }
]
```

它只服务于历史 durable intent/API 数据兼容，不再是当前产品的用户交互或 Frontend Extension seam。
每次输入会把仍存在的历史 intent 与本条消息 Reference authority 统一重新校验、附加 canonical
version 后冻结到 SessionInput；没有显式 authority 时允许保持空数组。Agent 依据当前 Project resource
directory 直接调用实际领域 Tool，精确执行 authority 只在 ToolInvocation admission 时绑定。

Workbench 的“询问 DBFox”发送 typed reference，而不是把 Object 伪装成 Resource：

```text
authority  = parent Resource identity（可选）
object     = table / file / measure 等具体对象，不产生 authority
locator    = rows / line range / measures 等选择
artifact   = 可选 immutable Artifact identity
```

该 envelope 与消息原子 admission 并写入 `AgentSessionInput.references_json`。它是不可变输入事实；
Context 明确把 label/locator 作为 untrusted data。Backend 从 Reference 提取 `authority`，与 legacy
durable intent 一次性 server-authorize；Frontend 不再双写 `requested_resources`。

**实施状态（2026-08-22）：阶段 B 已完成。** Core 已持久化 identity-only
`ConversationResourceIntent`；创建与 PATCH 都经过 Project resource discovery 校验；input
admission 合并 legacy durable intent 与本条消息 Reference authority，再由服务端附加 canonical
version；Project discovery 只影响 Tool discoverability，不扩大 Input。Frontend 已删除 product
requested-resource composition、`contextSelection`、`composerContext` 及其 stores/helper，
`activeDatasourceId` 不再参与 Conversation 创建或发送。DLC 不再存在手工选择或隐式 authority
contributor 的入口。`DockRenderContext.onAsk` 是 Host 正式合同，
以 `authority + object + locator + artifact` 把 Workbench 选择交给 Composer。

## 8. Data System DLC

Data DLC 自有：

```text
ConnectionProfile
  ├─ provider / network coordinates
  ├─ CredentialRef / SSH / TLS
  ├─ environment / read-only policy
  └─ connection_generation

DatabaseResource
  ├─ connection_profile_id
  ├─ provider-owned database/catalog identity
  ├─ resource_generation
  └─ catalog_revision

Provider objects
  └─ schema / table / column / relation / query history / backup / restore
```

Provider adapter 决定层级：

- MySQL：server connection → databases（MySQL schema 即 database）→ tables；
- PostgreSQL：server profile → databases；每个 DatabaseResource 使用对应 database connection，内部再有 schemas → tables；
- SQLite：file-backed profile/resource → tables。

该差异来自数据库官方模型，Core 不统一成固定 `Connection → Database → Schema → Table` 深度。SQLAlchemy Engine/URL 继续负责 dialect 与连接池，不代替 durable 产品模型。

Data DLC 继续维护唯一 SQL 链：

```text
sql_validate
→ immutable validation Artifact
→ sql_execute_readonly
```

Catalog、backup/restore、completion、Data context、Data connector，以及 SQL/Table/Result 的 Artifact/View
均归 Data DLC。声明式图形创建和 Visualization View 归独立 `dbfox.visualization`；它只消费公开
Representation，不依赖 Data 私有服务。

Completion 已先完成所有权切换：Kernel 只提供按 Tool semantic capability 聚合 Artifact 与要求
inline citation 的通用原语，`RuntimeContributionSnapshot` 保存带 owner 的 constraint/support；
`dbfox.data` 通过 `host.completion` 声明 `query_result` 规则。禁用 Data package 时规则随同一快照
原子消失，冲突会拒绝整个 package，不保留半激活状态。Core 不再 import Data completion 模块。

### 8.1 执行代码迁移决策

> 状态：历史。本节保留切换期的决策与每批证据；当前生产状态以 11.1 和第 12 节为准。

现有 `engine.connectivity`、`engine.sql` 与 Data Tool 已有成熟的凭据、SSH/TLS、pool、SQL
guardrail、不可变 validation Artifact、只读执行和大结果边界；迁移必须复用这些行为与测试，
不能重写第二套实现。评估结果：

- 不采用 DLC 私下 import `engine.*`：这会形成未声明的私有 ABI，使 Data 仍是 Core 领域代码；
- 不采用 Core `DataExecutionService`/service locator：它只是把领域泄漏包进一层转发接口；
- 不复制现有模块到 DLC：会产生两条安全链、双重修复和不可证明的行为漂移；
- 采用源代码所有权移动：按 `dialect/connection primitives → safety → execution/result →
  catalog/backup → tools/context/completion` 的依赖顺序，将现有实现与测试移动到
  `dlcs/dbfox_data/backend`，调用方直接改用新权威模块。

迁移期间 release bundle 中 Data 保持安装但 disabled，Core legacy Data 是唯一生产执行链，
不双写 DLC state。只有 package 自包含全部执行族、旧 API endpoint 已改为调用 DLC operation、
完整 SQL 安全/恢复/多库回归通过后，才把 `dbfox.data.default_enabled` 设为 true；同一提交删除
legacy Data registrar/provider/resolver、Core Data composition import 与开关。若某一步需要临时 import
alias，它只能存在于 import-site 迁移提交内，不能承载逻辑、不能进入 release，并以零调用点为删除条件。

**实施状态（2026-08-23）：阶段 E 的目标耐久模型与 staging import 已落地，执行链迁移中。**
`dbfox.data/state.sqlite3` 已直接拥有 `ConnectionProfile → DatabaseResource(s)`，只有
DatabaseResource 会贡献 `dbfox.data.database` authority。Profile generation 会 fence 全部子数据库；
数据库 identity 变化另有 resource generation。普通网络 profile 必须完整包含 host、username
与 opaque password credential ref；SQLite profile 禁止混入网络、SSH、TLS 或 credential 配置。
历史 `DataSource.id` 在单向、可重放 import 中原样成为 DatabaseResource id，Core 与 DLC 不双写。
Data System DLC frontend 已贡献 hosted Resource Connector：第一层只展示 ConnectionProfile，第二层
展示 DatabaseResource；展开/聚焦只改变 UI browse state，不会改变下一次 Input 或 Invocation authority。
用户从 Table Workbench 发起“询问 DBFox”时，Reference 携带 parent Database identity、Table object 与
locator，由 Backend 在消息 admission 时校验。

执行迁移的第一条垂直链已经完成：Catalog、Preview、SQL validate/execute 的输入使用显式
`database_id` 选择 frozen `(kind,id)`；SQL validation Artifact 与审批能力都绑定完整
`ResourceScopeRef`，不再只绑定一个整数 generation。Artifact envelope 新增通用
`resource_refs_json`，写入时必须是 Run authority 的精确子集；Result/Visualization 可据此在同一 Run
含多个数据库时恢复来源。Resource version 保持 `str | int` 原值，Core 不解析 Data DLC 的
复合 generation，也不把它强转成整数。

Run/Memory 的旧 datasource compatibility 存储也已完成物理清理。历史迁移
`c0d1e2f3a4b7` 删除 `agent_runs.datasource_id/datasource_generation` 及
`agent_session_memories.datasource_id`、对应 FK 与索引；公共 Run projection 同步删除
`datasource_id`。`resource_refs_for_run()` 对缺少冻结 refs 的历史输入 fail closed，不再从 Run 行
恢复或扩大 authority。Extension API v2 进一步把 Memory JSON 内的 Data Catalog scope 改为
canonical `ResourceScopeRef`，不再镜像 `datasource_id/datasource_generation`。Alembic
`c0d1e2f3a4ba` 只移除可重建的旧 Catalog projection，保留 Memory Core 与其他 DLC projection；
该历史投影随后整体退役，不引入双读或长期兼容解析。Alembic
`d1e2f3a4b5c7` 随后把 Conversation intent、Input、Artifact 与 Memory 中旧的裸 `database`
resource kind 单向改写为 `dbfox.data.database`；运行时代码不保留 alias、mapper 或双读协议。

同一原则已延伸到 Tool execution context：`ToolRequest`、`AttemptInvocationRequest` 与
`ToolRunContext` 不再镜像 `datasource_id`、`datasource_generation` 或 `db_dialect`。Tool 只能通过
`scope/scopes/resource/resources/require_one` 读取冻结资源；查询取消注册也直接从唯一 database
scope 取 id。多 database scope 不会被压成一个隐式 active datasource。

Alembic `c0d1e2f3a4b8` 进一步把 `agent_session_inputs.resource_refs_json` 收敛为 NOT NULL：
历史 NULL 在迁移中一次性写成 `[]`，之后空数组是零 authority 的唯一耐久表示。Codec 因此只返回
`tuple[ResourceScopeRef, ...]`，不再用 `None` 表示另一种“未指定”状态。

Core `Project` 与当前 ORM 已完全删除 DataSource、Catalog、Backup 和 Workspace domain state。历史表只由
Alembic cutover migration 读取；生产 Kernel 不保留 legacy provider、metadata resolver、HTTP route、
旧 import path、开发 fallback 或领域 ORM。Data 的唯一权威源码树是 `dlcs/dbfox_data/backend`，其中
拥有 inventory、tool contracts、Artifact payload、SQL primitives、guardrail、execution、result view、
backup 和 Workbench contribution。

这一步同时修正了 Artifact contribution 的 snapshot lifecycle：DLC payload validator 只存在于
不可变 `RuntimeContributionSnapshot.artifact_contracts`，编译器不再把它写入可冻结的进程全局
registry。Artifact 写入从当前 active snapshot 精确解析 namespaced type/version；DLC 被禁用后新写
立即失去该合同，历史读取仍按 unknown historical payload fail-soft。Core 全局 registry 只保留
Kernel-owned type，因此 package 可重复编译，也不会在 Core freeze 后因动态注册而失败；不同
active owner 的 type 冲突仍在单次 snapshot 编译中原子拒绝。

第四步已迁出 SQL guardrail、bound-parameter rendering/fingerprint、identifier/query builder 与
`ExecutionSafetyDecision`/approval policy 纯合同。Guardrail 继续使用原 SQLGlot AST 和 hard-cap
算法；参数 fingerprint 增加固定向量测试，确保 validation Artifact 与执行参数的绑定没有漂移。
Kernel Extension API 新增的只有严格 JSON dumps 与安全诊断两个通用 primitive：DLC diagnostic 必须
使用 namespaced operation code，Host 只记录 code、异常类型与进程内 opaque fingerprint，不记录
SQL 或异常正文。`TrustGate` 已迁入 Data DLC，并只消费不可变 `DatabaseSafetyScope` 及显式注入的
schema validation / EXPLAIN 边界函数；它不持有 Core ORM Session。Data 方言值对象统一使用
`DatabaseDialectContext(resource_id, dialect)`。Core 不再包含 SQL safety、dialect loader 或 Data
policy engine，也没有从 Core 指向 `dlcs.dbfox_data` 的反向 import。

第五步已建立第一条由 System Data package 自己注册的真实 Tool 垂直链。`sql_validate` v2 只从
frozen `dbfox.data.database` scope 解析 `DatabaseHandle`；多数据库 Run 未显式提供 `database_id`
时直接拒绝，不读取 active datasource 或 Project membership。SQLite/MySQL/PostgreSQL direct profile
通过真实只读 EXPLAIN 校验 guardrail 产出的 `safe_sql`，并原子产生 namespaced
`dbfox.data.safety → dbfox.data.sql` Artifact drafts；每个 draft 都绑定完整 `ResourceScopeRef`。
SSH profile 当前明确返回 explain unavailable，不会退回 direct host。System Data 在签名发行 bundle 中
默认启用；package 缺失或未激活时 Runtime fail closed，不组合 legacy Tool。

第六步已把 `sql_execute_readonly` v2 接到同一条 System Data 垂直链。Kernel 的 `ToolPolicy` 不再
包含 `requires_validated_sql` 或任何 SQL 字段；它只提供通用 `requires_admission`。声明该策略的
DLC Tool 必须实现纯 admission：从 exact current-Run Artifact loader 读取输入，返回
`allowed / blocked / approval_required`、可选完整 `ResourceScopeRef` 与有界 approval subject。
PolicyGate 在 invocation admission 和进入 Tool leaf 前都会重新执行该判断，独立验证 resource ref
属于 frozen Run，并把 approval subject 的 canonical hash 与 invocation/input/policy/resource version
一起持久化。Tool leaf 只能通过 `context.approval_authorizes(subject, ref)` 消费这一能力，拿不到
Approval repository 或全局 authority service。

SQL/Safety payload、唯一 `validated_by` 关系、重复 `derived_from` Result 检查与多数据库选择全部由
`dbfox.data/backend/sql_admission.py` 解释；Core `ArtifactRepository` 已删除
`require_validated_sql()` 与 `result_for_sql_artifact()`。Repository 新增的只有通用
`artifacts_relating_to_for_run(id, relation)`，并先证明 relation source 也属于同一 Session/Run。
Data Tool 随后以只读事务直接执行 Artifact 中的 `safeSql`：SQLite 使用 read-only URI、`query_only`
和 progress deadline；MySQL 使用 `START TRANSACTION READ ONLY`；PostgreSQL 使用 readonly session 与
transaction-local statement timeout。所有路径再次解析单条 side-effect-free query，SSH 未完成时
继续 fail closed；结果行数、列数、cell 与 byte 上限的既有 tested serializer 已从 Core 物理迁到
Data source tree，legacy driver 暂时直接复用同一实现，没有第二套 serializer 或结果 mapper。

Tool cancellation 也已从 Data 特判改成 provider-neutral lifecycle。`ToolRunContext.invocation_id` 是
Host 生成的稳定执行 identity；`ToolExecutor` 在 timeout/user cancel 时调用 Tool 的 best-effort
`cancel(invocation_id)` hook。`ToolDispatcher` 已删除 `DATABASE_RESOURCE_KIND` 与 `QUERY_REGISTRY`
import，不再猜测资源种类或数据库连接。Legacy Data Tool 暂时在自己的实现内把 invocation id 绑定到
旧 QueryRegistry；System Data 的 `DataConnectionBoundary` 则自行维护 invocation→active connection，
SQLite 调用 interrupt、PostgreSQL 调用 driver cancel、MySQL 关闭当前只读连接。取消前已排队但尚未
attach 的 invocation 会保留 cancel flag，连接建立时立即中止并关闭，不会错过竞态窗口。

第七步已把 Catalog 的新权威实现落入 System Data package。`DataStateStore` 的 schema v2 迁移在
`dbfox.data/state.sqlite3` 内直接拥有 `catalog_tables / catalog_columns / catalog_foreign_keys`；一次
refresh 先完成远端全量反射，再在一个本地事务中替换指定 `DatabaseResource` 的 catalog，只有成功
提交才递增该资源自己的 `catalog_revision`。表 identity 由
`(database_resource_id, schema_name, table_name)` 确定，因此分页 cursor 在无结构变化的 refresh 之间
稳定；ConnectionProfile 下的多个数据库不会共享 revision 或 catalog rows。

`catalog_overview / catalog_refresh / schema_list / schema_search / schema_inspect` v2 现在全部由
`dbfox.data` 注册。每个 Tool 都从 frozen Run scope 显式选择 `database_id`，多数据库 Run 省略选择时
直接拒绝；刷新、实时检查和取消只经过 Data-owned connection boundary。Core 不提供 Catalog Session、
DataSource mapper 或 requested-resource fallback。`SchemaInventory` 与 `SyncResult` 的 identity 字段也已
单向收敛为 `database_resource_id`，不保留双字段。

实现复用项目既有 SQLAlchemy 2 Inspector 及其 dialect-specific `get_multi_columns`、
`get_multi_pk_constraint`、`get_multi_foreign_keys`，避免为 SQLite/MySQL/PostgreSQL 重写三套 metadata
协议。这个选择与 [SQLAlchemy 官方 Reflection API](https://docs.sqlalchemy.org/en/20/core/reflection.html)、
[SQLite PRAGMA metadata](https://www.sqlite.org/pragma.html)、
[PostgreSQL Information Schema](https://www.postgresql.org/docs/current/information-schema.html) 和
[MySQL INFORMATION_SCHEMA](https://dev.mysql.com/doc/refman/8.4/en/information-schema.html) 一致。
未引入新的 reflection/search 依赖；当前 catalog search 是 Data state 上有界、确定性的名称/注释
检索，不复制 legacy FTS fallback 链。Legacy Core Catalog 暂时只服务默认启用的旧 Data composition，
删除条件是 Preview/Result/Backup/Restore 完成迁移并切换 production snapshot。

第八步已迁移结构化 `data_preview`。System Data Tool 先从 Data-owned catalog 精确解析表与列，未初始化、
未知或歧义对象直接拒绝；projection/filter/order identifier 必须属于同一 DatabaseResource 的 catalog。
SQL 只由 Data-owned `build_select` 生成，operator 来自封闭枚举，value 只以 `dbfox_pN` 参数进入现有
DB-API renderer，且输入合同强制 `IN / NOT IN` 使用非空 list、其他 operator 使用 scalar。执行继续经过
同一 read-only connection/cancellation boundary，`LIMIT` 由合同限制为 20，模型窗口再次受 column/cell/
byte cap 约束。

默认敏感字段模式也已物理迁入 `dbfox.data/backend/sensitivity.py`；legacy Core executor 与 streaming
executor 直接消费该单一规则源，不保留镜像 pattern list。Preview 默认 projection 避开敏感列；用户
显式选择敏感列时仍允许验证结构，但值在进入 Observation 前替换为 `[REDACTED]`。Preview 产生
namespaced SQL → ResultView Artifact drafts，query fingerprint 同时绑定 ResourceRef、参数化 SQL 与
canonical parameter fingerprint，因此不同 filter value 不会共享结果 identity。

第九步已经收敛为 reference-only Result、显式 Snapshot 和通用 Representation。普通
`dbfox.data.result_view` 保存已校验 SQL Artifact、ResourceRef、generation、指纹和有界执行摘要，不保存
完整结果行；分页、筛选、排序、profile 和 export 通过 Data 的只读执行边界实时重查，返回
`live_reexecution`。用户或 Agent 明确冻结值时才创建 `dbfox.data.snapshot`，其读取返回
`durable_snapshot`。两者是不同 Artifact，不存在失败时静默回退。

Core 只实现 `ArtifactRepresentationContribution` 的发现、JSON read、stream、预算、错误和 frozen Runtime
snapshot 分派；公共第一种合同是 `dbfox.dataframe.v1`。Data 独占 SQL、generation fence、字段和操作符
校验、稳定排序、筛选、CSV spreadsheet-formula escaping 与查询取消。Core 不保存 Data rows，不提供
`/page`、`/chart-data` 或 chart-specific Provider。独立 `dbfox.visualization` 通过公开 Representation 读取
兼容 Artifact，生成带 `derived_from` 血缘的 Visualization Artifact；Data 不再注册 `chart_create`。
历史 `dbfox.data.chart` 仅由 Visualization DLC 精确只读渲染，不能创建或成为新依赖。

第十步已建立 Data-owned Backup/Restore 的第一条安全垂直链。`DataStateStore` schema v4 直接拥有
`backups / restore_operations`，备份 payload 只写入 DLC 私有 data path；记录保存相对 file name、SHA-256、
DatabaseResource id 与完整 resource version，不写 credential、DSN 或 Core DataSource id。
`backups.create/list/restore` 是 typed project-scoped DLC operations，restore 输入必须同时携带固定 confirmation
literal 和 expected resource version。SQLite 创建使用 Python 标准库对官方 Online Backup API 的封装，先写
唯一 staging file、执行 `PRAGMA integrity_check`、flush/fsync 后原子 rename。恢复不会覆盖原数据库，而是先
在 DLC 私有 `restores/` 下构建隔离数据库、校验完整性/表数，再在一个 Data state 事务中切换
DatabaseResource identity、递增 resource generation、清空旧 catalog revision 并写 restore audit；旧 frozen
Run 因 version fence 立即失效。

方案调查采用 [SQLite Online Backup API](https://www.sqlite.org/backup.html)；未采用普通文件 copy，因为官方
文档明确指出 live database copy 的锁与崩溃一致性问题。也未用 `VACUUM INTO`，其优势是压缩/清除删除痕迹，
但 CPU 更高且意外中断可能留下不完整文件；当前目标是低干扰一致快照。网络 provider 不自行拼接 SQL dump：
PostgreSQL 应复用官方 [pg_dump/pg_restore](https://www.postgresql.org/docs/current/app-pgdump.html)，MySQL 应复用
官方 [MySQL Shell dump/load utilities](https://dev.mysql.com/doc/mysql-shell/8.0/en/mysql-shell-utilities-dump-instance-schema.html)。
Frozen Sidecar 尚未固定、签名并随包提供这些 native clients，因此 MySQL/PostgreSQL backup 当前明确 fail
closed；后续只有在工具版本、checksum、credential handoff、进程取消和 restore code-execution 风险合同
冻结后才启用，不增加私有 dump format 或不受控 PATH fallback。Data typed Operation 声明的
`filesystem_write` manifest permission 只覆盖该私有 payload 边界，不授权 model Tool；它不是 OS
sandbox，目录约束仍由不可注入的 Host data path 与生成式文件名保证。

该拆分参考 Kubernetes 将 authorization 与 admission controller 分开的官方边界，以及 VS Code
Workspace Trust 对 capability enablement 的 Host-owned 决策：Kernel 决定“调用是否拥有执行能力”，
DLC 决定“领域对象是否满足执行前置条件”。没有采用通用字段路径/表达式 DSL，因为它会把领域 payload
结构复制进 Kernel 并形成第二份规则事实；也没有引入第三方 policy engine，因为当前变化轴只有 typed
Tool hook，现有 Pydantic/Artifact/approval 合同已经覆盖持久化、版本 fence 与审计需求。

为避免迁移期间形成第二套连接安全规则，TLS 参数、embedded database 文件校验与 network driver
参数构造已物理收敛到 `dlcs/dbfox_data/backend/connection_primitives.py`。System Data 的直接连接
边界和 legacy `engine.connectivity.ConnectionFactory` 都调用这一个源实现；Core 只在自己的 HTTP/
legacy error boundary 做一次异常语义转换。没有 driver 参数 mapper、双写配置或 fallback endpoint。
剩余 SSH、pool、generation lifecycle 继续由 legacy 路径单独持有，删除条件是这些实现完成源码所有权
移动并由 Data package conformance tests 覆盖。

Extension API 同时增加了通用、只读的 Run-scoped Artifact seam：DLC Tool 可通过
`context.artifact(id)` 读取当前 invoking Run 内的 immutable Artifact；Host loader 同时校验
`session_id + run_id + artifact_id`，跨 Run/Session 返回不可用。Artifact relation/visibility draft
类型也属于公开 envelope contract。这个 seam 不暴露 ORM Session、ArtifactRepository 或全局查询，
isolated worker 未获得相同宿主绑定时 fail closed。它是后续迁移只读执行所需的真实平台边界，不是
Data service locator。

通用 `ContributionCompiler` 也已删除 `include_legacy_domain_builtins` 和七组无 owner 的 built-in
参数，改为只接收不可变 `BuiltinContributionSet`。Tool、resolver、completion、credential probe
在进入编译器前就携带权威 owner，seed identifiers 参与 snapshot hash；因此启用 System Data DLC
时不会再生成一个声称含有 `builtin.data` 的虚假 composition identity。签名 System Data 已在发行
bundle 中默认启用，正式发行只组合 platform primitives 与已验证 DLC。源码直接运行时的临时 Data
组合只存在于 `runtime_composition._source_development_product_builtins()`；它不会进入 generic
compiler，也不会与激活的 System Data 同时加载。删除条件是开发启动脚本能够生成并固定本地签名包；
在此之前会记录明确 warning，避免把开发便利误认为正式发行合同。generic compiler 已有工程合同禁止
任何 Data import、id 或布尔分支回流。

Data capability 的 Resource kind 已统一冻结为 namespaced `dbfox.data.database`。Legacy execution
与 System DLC 在 staged activation 中互斥，但现在共享同一个 canonical resolver key；耐久旧值由
`d1e2f3a4b5c7` 一次性迁移，Conversation intent、Run authority、Artifact provenance 与 Tool context
不再存在第二种 Data resource identity。

现有 `engine.connectivity.ConnectionFactory` 已覆盖凭据解析、SSH、连接池与 generation fence，
属于必须迁移复用的成熟实现；TLS、SQLite 文件校验及 direct driver 参数 primitive 已先迁至 Data
唯一权威树并由双方直接复用，不在 DLC 内另造第二套连接栈。
但它当前的 `ConnectionProfile` 是“单数据库执行快照”，不是新的服务器级耐久 Profile。迁移时只允许在
真正的 driver 边界把 `ConnectionProfile + DatabaseResource` 单向组合成执行快照，随后将 connectivity
实现整体归入 Data DLC；不在 Core 增加 `DatabaseManager` 或数据库专用 service locator。

## 9. Workspace System DLC

Workspace DLC 自有 Project workspace binding、Resource Provider/Resolver、file read/search/write tools、Workspace Context、File/Patch Artifact、Connector 和 File/Patch Dock。Core `Project` 已不再包含 Workspace 字段。

**实施状态（2026-08-22）：阶段 D 已完成 cutover 与物理清理。** Project 创建合同已只接受名称与可选描述；
历史 `workspace_root` 通过可重放、验证后清源的 Alembic import 进入
`dbfox.workspace/state.sqlite3`；最终 Alembic cutover 会再次幂等导入初次迁移后由旧版本写入的目录，验证后删除 `projects.workspace_root`。默认 Core snapshot 不再注册 Workspace Tool、Provider、Resolver
或 Context contributor；`engine.workspace`、Core Workspace builtin、Core Workspace Context contributor
与专属旧测试文件已删除；混合回归文件中的历史用例标记为 retired，Runtime 有效测试改用不含领域逻辑的 Resource probe。官方签名包的启用/禁用、路径 containment、二进制拒绝、Artifact freshness 与状态保留已有 conformance proof。前端 Connector
通过 generic `nativeDialogs.pickFolder` 工作，Workbench 引用通过正式 `DockRenderContext.onAsk` 合同进入 Composer。
Workspace 新写入的 File/Patch Artifact 同样使用 Core Artifact envelope 的 `resource_refs`；Context
contributor 优先按该通用绑定校验 frozen Workspace authority。payload 内旧 workspace identity 只用于
读取迁移前历史 Artifact，不再是新 authority 的事实源。

Extension API v2 当前只允许 installable DLC Tool 使用 in-process backend，而 Tool Runtime 又要求
`filesystem_write` 使用 isolated process。Compiler 因此明确只接受 DLC Tool 的 `network` 与
`filesystem_read` capability；即使 manifest 声明 write permission，模型 Tool 注册仍会 fail closed。
System Workspace DLC 当前正式注册 file read/search，不注册 file write；已删除未注册的 write Tool 与
私有 patch service，避免源码/API 暗示一条不存在的执行链。typed Workbench Operation 的 manifest
permission 是另一条 Host operation 边界，不会使模型 Tool 获得 write。删除该限制的条件是 isolated worker 能按
冻结的 package digest 装载签名 DLC Tool，并通过 frozen Sidecar 与 package mismatch 回归。

Native file/folder picker 与 Credential Broker 属于 Electron/Core OS boundary；DLC 通过窄 Host service 使用，不能获得 application container、任意 Session 或全局 credential vault。
Backend Extension Host 已提供无枚举能力的 `credentials.get(opaque_ref, kind=...)`；每次读取都要求
签名 manifest 精确声明 `credentials:<kind>`，并再次校验 credential id 的 kind。它只面向 trusted
publisher in-process DLC，不构成恶意代码沙箱。凭据创建/lease adoption/delete 的跨 Core/DLC
写事务不能用 SQLite `ATTACH` 或 SQLAlchemy two-phase commit 伪装成单事务：Core 与 DLC state
均使用 WAL，而 SQLite 官方明确说明 WAL 下 attached databases 只保证各文件独立原子；SQLAlchemy
2PC 也只适用于底层数据库提供 two-phase operation 的后端（[SQLite ATTACH](https://sqlite.org/lang_attach.html)、
[SQLite WAL](https://www.sqlite.org/wal.html)、[SQLAlchemy transactions](https://docs.sqlalchemy.org/en/21/orm/session_transaction.html#enabling-two-phase-commit)）。
因此继续采用可恢复 saga，不切换 journal mode，也不引入双写 mapper。

**实施状态（2026-08-23）：owner-bound adoption 与恢复闭环已完成。** `CredentialLeaseSaga` 不再 import
或查询领域表，只执行 immutable Runtime snapshot 中 capability-owned 的只读 reference probe。签名
`dbfox.data` package 通过 `host.credentials.register_reference_probe(...)` 查询自身 `state.sqlite3`。Probe 注册要求 manifest
至少声明一个 `credentials:<kind>` 权限，并随 package activation 原子加入/移出 snapshot。这样崩溃后
已进入 `claimed` 的 lease 可以在 active capability 的 durable state 已落盘时安全收敛为 `committed`。

Alembic `c0d1e2f3a4b9` 为 claim 持久化 `owner_id / owner_operation / owner_project_id`；generic operation
Host 在调用 handler 前提交 Core ownership intent，再让 DLC 在自己的 SQLite 中完成单库事务，最后用
该 owner 的 probe 验证**全部** leased refs 已耐久归属后才提交 lease。handler 抛错、output 合同失败或
probe 不承认完整集合时立即走同一恢复判断；owner 暂时未激活则 fail closed 保留 claim，等待下次启动，
不猜测秘密已无主。Frontend Extension Host 的 operation options 只透传 opaque `credentialLeaseId`，
不暴露 vault、secret enumeration、Core Session 或 store/delete。需要凭据 adoption 的 operation 必须声明
reference extractor，且同一签名 package 必须注册唯一 owner probe，否则整个 package 激活失败。

Frontend DLC 创建 secret 时也不直接调用产品 API：`host.credentials.enrollBatch(...)` 自动绑定当前
`dlc_id`，Engine 只允许 active snapshot 中该签名 manifest 已声明的 `credentials:<kind>`。Secret 仅存在于
这次本机 HTTP request 与 OS vault write；返回给 package 的仍只有 opaque refs 和 server-owned lease。
Manifest 未授权的 kind 在写 vault 之前以 403 拒绝。Runtime activation projection 不向前端公开其他 DLC
的权限集合，Host 也不提供任意 owner 参数。

这不是通用分布式事务或自动重试协议：DLC handler 仍必须把自身领域写入做成单库原子事务；Core 不会
自动重放 handler。Saga 只解决“秘密已经写入 OS vault，而 owner durable state 与 Core lease finalize
分属两个 SQLite 事务”的已知崩溃窗口。

## 10. DLC durable state

Capability DLC 在自身 data directory 保存 durable state，并只把 `project_id` 当外部 identity：

```text
Core DB
  Project / Conversation / Run / Artifact envelope / ...

dbfox.data/state.sqlite3
  ConnectionProfile / DatabaseResource / Catalog / Query / Backup / ...

dbfox.workspace/state.sqlite3
  ProjectWorkspaceBinding / ...

dbfox.github/state.sqlite3
  RepositoryBinding / ...
```

不建立 Core 万能 `ProjectResourceBinding(config_json)`，不跨 SQLite 建 FK，不双写长期事实。迁移复用 `dbfox.github` 已证明的一次性 import 模式：幂等 staging、冲突拒绝、失败保留、验证后切换读写权威、最后证明 Core absence。

## 11. Workbench 交互合同

```text
single click resource/object → UI focus；必要时打开 Dock
double click / Enter         → inspect/open
Ask DBFox                    → 写入当前 Conversation-scoped composer reference
Pin / explicit attachment   → 可选写入 durable intent 或 one-shot requested_resource
remove reference chip       → 只从当前待发送消息移除
Send                        → message + typed reference + optional authority 原子提交
```

左侧结构：

```text
Project
├─ Conversations
└─ Resources
   ├─ Data
   │  └─ Connection
   │     └─ DatabaseResource
   │        └─ provider objects
   ├─ Workspace
   └─ GitHub
```

Host 拥有 section chrome、overflow、focus、keyboard、Conversation workbench scope 与 selection visual
contract；DLC 提供 typed tree data/action，不直接控制 Sidebar 外层布局。每个 Conversation（以及尚未
创建 Conversation 的 Project draft）只有一份 `workbenchByConversation` 事实源；Tabs 和 DLC view
state 都使用同一个稳定 `workbenchScopeId`，draft 创建 Conversation 时整体迁移，不双写第二份 dock
state。实现遵循 WAI-ARIA Tree View 中 focus 与 selection 分离的语义，并参考 VS Code contribution
points 的 Host-owned Workbench 原则，但不引入完整 IDE framework。

### 11.1 最终切换状态（2026-08-23）

- `dbfox.data`、`dbfox.workspace` 与 `dbfox.music` 均以签名 System DLC 默认启用；Kernel-only 启动仅是包不可用时的明确 fail-closed 状态，不会注册领域 fallback。
- Core HTTP 不再注册 DataSource、Schema、Query、Backup 业务路由；Data Workbench 通过 typed DLC operations 和 Artifact views 工作。
- Alembic `e2f3a4b5c6d8` 将历史 Connection/DataSource identity 与 opaque credential refs 幂等导入 `dbfox.data/state.sqlite3`，验证后删除 Core Data 表和 Data FTS；当前 head `f3a4b5c6d7e9` 又移除最后的 Run/Data compatibility columns。Catalog 与显式 Snapshot 是 capability-owned 领域状态；普通 Result rows 不进入 Core 或 Data 元数据存储。
- Project 当前模型只保留 identity/metadata；Conversation 只保留 Project 归属和 generic resource intent；Run 只从 frozen refs 获得权限。
- Data Connector 以 `ConnectionProfile → DatabaseResource → provider objects` 展示资源；左侧 focus 只导航，Workbench Reference 才把对象与 locator 交给 Composer。
- Dock collapsed state 使用独立 rail layout，不压缩 expanded tab strip；Composer 与 Conversation content column 共用版心，不作为 footer panel。
- 迁移没有引入新依赖、双写、通用 `ProjectResourceBinding(config_json)`、service locator 或 Data 兼容 API；SQLite/Alembic、现有 DLC verifier/compiler、Credential Broker、Tool Runtime 与 Artifact envelope 被直接复用。

## 12. 分阶段迁移与删除条件

| 阶段 | 状态 | 新事实 | 旧事实删除条件 |
| --- | --- | --- | --- |
| A | 已完成 | ResourceKey + multi-resource Tool context | 所有内置工具和 bundled DLC 不再调用单值 `require_resource(kind)` |
| B | 已完成 | typed Workbench Reference + backend-derived initial explicit authority | 手工 `contextSelection`/`composerContext` Host 和 stores 已删除；浏览资源不改变 Input/Invocation authority |
| C | 已完成 | Session/Run 只从 frozen refs 工作；Conversation API/UI 已删除 datasource/table context 合同；`agent_sessions.datasource_id/context_tables_json` 已物理删除 | 无 |
| D | 已完成 | Project v2 + Workspace DLC binding；`projects.workspace_root` 已物理删除 | 无 |
| E | 已完成 | ConnectionProfile + DatabaseResource、显式多数据库 Tool selection、generic Tool Admission、Artifact/approval ResourceRef fence、System Data `sql_validate → sql_execute_readonly`、Database-scoped Catalog、结构化/遮罩 Preview、reference-only Result、显式 Snapshot、`dbfox.dataframe.v1` Representation，以及 SQLite online backup + isolated restore | 旧 DataSource HTTP/Workbench 管理面、Core Data tables、旧 Artifact page/chart-data API 与源码开发 fallback 已删除；网络 backup 未在官方 client 固定前不以私有 dump format 扩大范围 |
| F | 已完成 | Frozen Sidecar 已内嵌官方 publisher key 与 Data/Workspace exact package pins；Electron Resources 只承载包字节，启动走 verify → content-addressed install → selected snapshot；源码开发 bundle 使用内容指纹 prerelease version 并有界轮换旧开发 package bytes；Data/Workspace 均默认启用 | 无 |
| G | 已完成 | Conversation legacy API、implicit datasource authority fallback、Session 历史物理列、Core Data tables 与 `projects.workspace_root` 已删除 | 无 |

临时兼容代码只能存在于明确阶段，必须有调用量或 characterization test，不承载新业务逻辑，也不能被新模块依赖。

## 13. 非目标

- 不把 Core 自身 DLC 化；
- 不把 trusted DLC 宣称为安全 sandbox；
- 不建设 Marketplace、远程 extension host 或通用 Service Locator；
- 不建设万能 Resource payload/mapper 表；
- 不让 Project 自动授予所有资源；
- 不让 table/file/object 成为海量粗粒度 ResourceRef；
- 不为迁移长期维持 Core 与 DLC 双写。

## 14. 参考依据

- [VS Code Contribution Points](https://code.visualstudio.com/api/references/contribution-points)
- [VS Code Extending Workbench](https://code.visualstudio.com/api/extension-capabilities/extending-workbench)
- [VS Code Extension Host](https://code.visualstudio.com/api/advanced-topics/extension-host)
- [VS Code Workspace Trust / Extension Runtime Security](https://code.visualstudio.com/docs/configure/extensions/extension-runtime-security)
- [VS Code SecretStorage](https://code.visualstudio.com/api/references/vscode-api#SecretStorage)
- [WAI-ARIA Tree View Pattern](https://www.w3.org/WAI/ARIA/apg/patterns/treeview/)
- [PostgreSQL Schemas and database connection boundary](https://www.postgresql.org/docs/18/ddl-schemas.html)
- [MySQL INFORMATION_SCHEMA SCHEMATA](https://dev.mysql.com/doc/refman/8.4/en/information-schema-schemata-table.html)
- [SQLite Single File Database](https://www.sqlite.org/onefile.html)
- [SQLAlchemy Engine Configuration](https://docs.sqlalchemy.org/en/20/core/engines.html)
- [Pydantic JSON Schema](https://docs.pydantic.dev/latest/concepts/json_schema/)
