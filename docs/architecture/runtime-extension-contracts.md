# Runtime Extension Contracts

> 文档类型：ADR
>
> 状态：已接受
>
> 最后核验：2026-08-16
>
> 基线：`main@daa99d048decd7f5f8dc010cbe5465f332686a3c`
>
> 上位 RFC：[DBFox 可扩展 Runtime 与 Workbench 架构计划](./extensible-runtime-workbench-program.md)
>
> 2026-08-22 收敛说明：Project、Conversation authority、同 kind 多资源及 System DLC
> 所有权以 [Agent Core 与 Capability DLC 架构合同](./agent-core-capability-dlc-contract.md)
> 为准；本文保留其余 Extension 合同。

## 1. 决策

DBFox 建立受信任、编译期的 Runtime Extension ownership seam，使 Data、Workspace、Terminal、GitHub、Web 等能力通过**直接注册真实合同对象**进入 Runtime，而不是通过 RunLoop、ContextSnapshot、CompletionPolicy 或 Artifact switch 的领域分支进入。

第一阶段不是插件框架，也不为了未来对称性预先实现全部 Registry、依赖图、Environment 层或 Binding 对象。

核心原则：

> **Extension 是所有权边界；Tool 是逻辑能力合同；Native/API/MCP/Command 是执行来源。**

## 2. 当前实现事实

当前 Tool Runtime 已具备：

- 严格 input/output Pydantic model；
- Tool contract content hash / Turn materialization；
- Policy / Approval / ExecutionAuthority；
- timeout / retry / recovery / concurrency；
- in-process capability allowlist；
- durable ToolInvocation / Observation settlement；
- Tool-owned Observation projection；
- Artifact drafts；
- transient provider payload 与 durable facts 分离。

当前需要解决的真实缺口是：

- `ToolRunContext` 直接携带 datasource、dialect、SQLAlchemy Session 和 DB-oriented request；
- `isolated_process` 名称存在但 executor 尚不执行它；
- Semantic capability 是封闭 enum；
- Completion Core 直接理解 Data `QUERY_RESULT`；
- Artifact domain model / frontend union 是封闭集合；
- 外部 API/MCP/CLI 尚无统一受控接入路径。

这些缺口按真实阶段逐个打开，不一次建立一个“万能扩展框架”。

## 3. P1：最小 Extension ownership

P1 只引入 owner ID、直接注册和 freeze。

推荐组合入口：

```python
def register_builtin_functions(registries: RuntimeRegistries) -> None:
    register_core_functions(registries)
    register_conversation_functions(registries)
    register_data_extension(registries)
    registries.freeze()
```

注册 API 直接接收真实对象：

```python
registries.tools.register(CatalogOverviewTool(), owner="dbfox.data")
registries.tools.register(SchemaSearchTool(), owner="dbfox.data")
```

不建立：

```text
Tool → ToolContribution DTO → ToolAdapter → ToolRegistry
```

这种只为再映射一次存在的层级。

当前 `register_dbfox_tools()` 同时注册 Control、Conversation 和 Data 功能，因此不能整体归属 `dbfox.data`。迁移时拆注册所有权，保留原函数作为短期 facade，所有调用点迁完后删除。

### 3.1 ID

Extension owner ID 必须稳定，例如：

```text
dbfox.core
dbfox.conversation
dbfox.data
dbfox.workspace
```

新开放贡献 ID 使用命名空间，例如：

```text
dbfox.workspace.file_snapshot
dbfox.workspace.code_patch
dbfox.tests.result
```

现有 Tool 名和已有 Semantic/Artifact ID 不为形式统一而批量改名；这些值已经参与 durable materialization 或历史数据。

### 3.2 注册顺序与依赖

P1 没有真实 Extension dependency，因此只要求：

- duplicate owner / contribution ID 拒绝；
- 注册结果确定；
- serving 前 freeze；
- freeze 后拒绝 mutation。

不要在 P1 加 dependency graph。

以后出现真实依赖时再引入 `requires`，并用稳定拓扑排序；若存在 cycle 或 missing dependency 则启动失败。简单“按 extension ID 排序”不能代替依赖解析。

## 4. Tool contract 与执行来源

Agent、RunLoop 和 durable ToolInvocation 只识别 DBFox Tool contract。

执行来源概念上包括：

```text
Native implementation
API / SDK adapter
MCP adapter
Command / CLI adapter
```

Native Tool 继续直接实现 `BaseTool.run()`，不为了对称性包装空 `NativeBinding`。

当第一个真实非 Native 集成出现时，才抽最小 `ToolBinding` Strategy；它必须是 Tool implementation 内部的可替换执行策略，而不是第二套 Agent Runtime。

### 4.1 API

API adapter 负责：

- 将已经验证的 Tool input 组成外部请求；
- timeout / pagination / rate limit；
- 通过受控 secret resolver 使用 credential；
- 将外部错误归一为 DBFox 固定安全错误；
- 将结果验证为 Tool output / Artifact。

Raw response 不直接进入 Memory 或 Prompt。

### 4.1.1 Run-scoped Artifact access

需要消费前序 Tool 工作产品的 DLC Tool 只使用公开 `ExtensionToolRunContext.artifact(id)`。
Host 必须把读取限制在当前 invoking `session_id + run_id`，不得暴露 ORM Session、repository、全局
Artifact list 或跨 Run fallback。DLC 可使用公开 `ArtifactRelationDraft`、`ArtifactRelationType` 与
`ArtifactVisibility` 产出关系图；所有 draft 仍由 Kernel 在一次写事务前验证 payload contract、
relation target 与 frozen resource_refs。未配置宿主 loader 的执行 backend 必须 fail closed。

### 4.2 MCP

MCP 是 External Tool Provider，不是第二套 Runtime。

MCP Tool 在进入 Turn materialization 前必须完成：

```text
discover
→ trusted server/config policy
→ allowlist tool
→ validate input schema
→ risk/capability review
→ materialize DBFox Tool contract
→ freeze for Turn
```

至少冻结：

```text
server identity
transport/protocol adapter version
external tool name
input/output contract hash
DBFox Tool contract version
```

Server schema 变化时：

- 尚未执行的 frozen call：`TOOL_VERSION_CHANGED`，要求重新规划；
- 已经开始且 outcome 无法证明：结算 `UNKNOWN`；
- 不用新 schema 猜测旧调用结果。

MCP result 必须经过 DBFox output、size、secret、Artifact validation，不能直接写 Memory、Evidence、Completion 或 Prompt policy lane。

### 4.3 Command / CLI

稳定官方 CLI 可以封装成一等 Tool：

```text
validated Tool input
→ fixed executable
→ fixed / allowlisted operation
→ structured argv builder
→ one execution attempt
→ bounded stdout/stderr
→ versioned parser
→ strict Tool output
```

禁止 model-authored 字符串直接进入 `shell=True`。

Generic Terminal 用于 coding/build/test/排障和长尾探索，不作为所有平台集成的默认胶水。

## 5. Invocation：先保留最小稳定数据

当 Workspace 成为第二种真实执行资源时，当前 DB-oriented `ToolRunContext` 需要拆成“可序列化 invocation facts”和“执行位置资源”。

可序列化部分只保留执行身份和 scope：

```python
class ToolInvocationContext(BaseModel):
    session_id: str
    run_id: str
    turn_id: str
    invocation_id: str
    idempotency_key: str
    deadline_at: datetime | None
    scope_refs: tuple[ResourceScopeRef, ...]
```

```python
class ResourceScopeRef(BaseModel):
    kind: str
    id: str
    version: str | int | None = None
```

不放：

- SQLAlchemy Session；
- HTTP client；
- Secret object；
- arbitrary `metadata: dict`；
- `project_id` 与 scope 重复字段；
- `authority_ref` / `capability_grant_ids` 这种额外引用链；
- DBFox 当前仅用于 DB query cancellation 的 `execution_id`，除非第二种执行资源证明它是 universal identity。

真实 Project 若是 scope，就表示为 `ResourceScopeRef(kind="project", ...)`；Datasource、Workspace 等同理。

## 6. Execution resource boundary：延迟到第二个真实案例

`ResourceScopeRef` 的执行身份是 `(kind, id)`，不能以 `kind` 为字典 key。当前
`ToolRunContext` 提供：

```python
context.resource(ref)       # 精确 (kind, id)
context.resources(kind)     # 同 kind 的全部已授权 handle
context.scopes(kind)        # 同 kind 的全部 frozen refs
context.require_one(kind)   # 仅当恰好一个时成功
```

Extension API v2 已删除单资源兼容名 `require_resource(kind)`；v1 包会在安装兼容性检查时
被明确拒绝。DLC 必须选择 `require_one(kind)`，或使用 `(kind, id)` 精确访问多资源。

API v2 的通用低层 primitive 还包括严格 `json_dumps()` 与安全诊断入口
`log_extension_diagnostic()` / `log_extension_exception()`。它们用于跨真实 Host/DLC 边界保持
同一 JSON 与脱敏日志合同；不允许据此向 DLC 暴露 Core logger、JSON codec 对象或应用容器。

不要提前定义一个同时包含：

```text
require_database
require_workspace
require_filesystem
require_process_runner
require_network_gateway
require_secret_resolver
```

的万能 Environment。

Database + Workspace 已证明这个最小接口。后续资源继续遵守：

- Tool 只能看到本 invocation 被授权的资源；
- 不能拿到全局应用容器；
- Secret 仍通过 opaque reference 解析；
- 接口必须能解释现有 DB Tool，而不是迫使现有实现适配一个更复杂的抽象。

## 7. Capability / Authority

Tool `execution.capabilities` 继续表示需求声明，不等于授权。

现有 `ExecutionAuthority` 继续负责已存在的 Approval/safety binding，不因为 Extension 重构而复制一套 grant table。

Filesystem/Network/Process 第二类资源真正出现时，如现有 Policy/Authority 无法表达 resource scope，再引入 immutable execution grant value。Grant 直接随 attempt 传递，不先建立 `grant_id → lookup → materialize` 的额外持久引用层。

任何新 grant 都必须至少绑定：

- invocation；
- Tool contract；
- authorized input hash；
- resource scope/version；
- policy / approval fingerprint；
- expiry/deadline。

## 8. Session Projection input

P0 Catalog Memory **不实现 Session Effect storage/registry**。

理由：当前 canonical `AgentToolInvocation + AgentObservationRecord + Artifact references + Run` 已经包含 Catalog reducer 所需的稳定输入。再写一份 `search_performed/objects_inspected` Effect 会复制同一事实。

P0 Projector 直接读取 canonical records：

```text
Invocation authorized input
+ succeeded Observation facts / capabilities
+ Artifact refs
+ enclosing Run sequence
→ pure reducer
```

未来只有在真实 Extension 出现“canonical records 无法稳定表达、但必须跨 Run 归约”的信息时，才评审 Effect。若引入 Effect，它仍然只能是 projection input，不是事实、证据、授权或 Prompt 指令。

## 9. Semantic capability

Semantic capability 表达成功 Observation 能证明什么，不授予执行权限。

兼容策略：

- 现有 `environment_profile/schema_metadata/query_result/...` 保持不变；
- 新 Extension capability 使用 namespaced string；
- Runtime 接口从 enum 接受范围迁到受验证 string，但不做历史批量 rename；
- 若未来迁移 legacy ID，必须有独立 wire/materialization migration。

这样避免仅为命名统一触发全部 Tool materialization hash 变化。

## 10. Completion composition

Completion Core 保持：

- active/pending Tool、Approval、Question；
- answer candidate 是否完整；
- citation syntax；
- cited Artifact 是否属于已观察集合；
- Run budget / forced partial；
- cancel / failure lifecycle。

领域规则只实现为只读 Constraint Strategy：

```python
class CompletionConstraint(Protocol):
    id: str
    def evaluate(self, input: CompletionConstraintInput) -> ConstraintResult: ...
```

```text
PASS
MISSING(requirements)
VETO(reason)
```

组合：

```text
Core terminal eligibility
→ any VETO
→ union MISSING
→ PASS
```

第一阶段只有 Data result citation constraint。使用 immutable tuple 注册即可，不建立 Rule Manager/Service 层。

Constraint 只能增加要求，不能绕过 pending work、authority、citation ownership 或 budget。

## 11. Artifact contract

当前数据库 `AgentArtifactRecord.type` 已是 String；真正的封闭点在 Python enum、payload map 和前端 union。

迁移采用最小扩展：

```text
type: string            # 保留现字段/现 ID
schema_version: integer # 新字段
payload: JSON object
```

`Artifact.version` 保持现有含义：同 semantic key 的业务/工作产品版本。它不能复用为 payload schema version。

Validator Registry 只按 `(type, schema_version)` 保存 payload validator。Kernel 继续负责：

- ownership；
- payload/relations size；
- rows/series 等禁止复制；
- secret scan；
- relation target visibility。

Existing `result_view/chart/sql/...` 作为 schema v1 原样兼容；新 Extension type 必须 namespaced。

未知历史 type：保留 envelope，UI fallback；未知新写入：拒绝。

## 12. Fingerprint

不要再增加覆盖全部 Tool 的 `runtime_contract_registry_fingerprint`，因为当前 `ToolMaterialization` 已对完整 Tool contract content-address。

需要 fingerprint 的地方只保留本地问题域：

- 每个 Memory projection 自己的 `contract_fingerprint`；
- Artifact payload schema 由 `(type, schema_version)` 定位；
- 外部 MCP/API/Command adapter 若改变 schema/permission/recovery 语义，则进入该 Tool materialization。

Presentation registry 变化不得触发 Memory rebuild。

## 13. Data ownership 迁移

Data Extension 第一阶段只改变**所有权**：

```text
Core / Control functions     → dbfox.core
Conversation functions       → dbfox.conversation
Catalog / Query / Result     → dbfox.data
```

不要为了每个 owner 都建立独立 Extension class。注册函数足够。

迁移完成标准：

- existing Tool 名、schema、policy 和 materialization 在非预期点不变；
- Registry freeze 有 contract test；
- RunLoop 不知道 `dbfox.data`；
- 后续 Workspace Tool 可以通过同一直接注册机制进入。

## 14. 验收

- P1 无多余 Contribution DTO / Mapper；
- Control/Conversation 不被误归 Data；
- Tool materialization 仍是 Tool executable contract 的兼容性事实源；
- Catalog Memory P0 不写重复 Effect；
- 新 Extension Tool 不要求 RunLoop 添加 Tool-name branch；
- existing semantic/artifact IDs 不为命名统一产生无必要迁移；
- first external binding 复用同一 Tool settlement；
- second real resource 出现前不提前建设万能 Environment；
- second full Extension 接入后仍能保持 Kernel 无领域特例。
