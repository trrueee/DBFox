# Runtime Extension Contracts

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

DBFox 建立受信任、编译期的 Backend Extension Contract，使 Data、Workspace、Terminal、GitHub 和 Web 能力通过注册贡献进入 Runtime，而不是通过 RunLoop、ContextSnapshot、CompletionPolicy 或 Artifact switch 中的领域分支进入。

第一阶段不支持第三方动态代码。现有 Data Agent 能力首先迁移为内置 Data Extension，用它证明新合同不改变当前产品行为。

一个重要边界是：

> **Tool 是 DBFox 的逻辑能力合同；Native API、HTTP/SDK、MCP 和 CLI/Command 只是这个 Tool 背后的执行 Binding。**

因此 MCP 不成为第二套 Agent Runtime，CLI/Terminal 也不绕过 DBFox 的 Tool/Policy/Observation/Artifact/Memory 生命周期。

## 2. 当前边界

现有 Tool 定义已具有严格 input/output model、Tool version、Policy/Approval、timeout/retry/recovery/concurrency、Backend 名称、capability、Tool-owned Observation projection、Artifact draft 和冻结 Tool materialization。

缺口是：

- `ToolRunContext` 直接携带 datasource、dialect、SQLAlchemy Session 和数据库导向 request；
- Registry 已禁止 filesystem/network/subprocess 进入 `in_process`，但 executor 对 `isolated_process` 仍返回 unavailable；
- Semantic capability 是封闭 Data enum；
- Completion Core 直接理解 `QUERY_RESULT`；
- Artifact type/payload map 和前端 wire union 是封闭集合；
- 外部 API、MCP Server 和官方 CLI 尚无统一 Binding/admission 语义。

## 3. Extension bootstrap

```python
class BackendExtensionManifest(BaseModel):
    id: str
    version: str
    api_version: str
    dependencies: tuple[ExtensionDependency, ...] = ()
    tools: tuple[ToolContribution, ...] = ()
    artifact_contracts: tuple[ArtifactContractContribution, ...] = ()
    semantic_capabilities: tuple[SemanticCapabilityContribution, ...] = ()
    session_effect_contracts: tuple[SessionEffectContribution, ...] = ()
    projection_modules: tuple[ProjectionModuleContribution, ...] = ()
    completion_rules: tuple[CompletionRuleContribution, ...] = ()
```

启动规则：

```text
load built-in manifests
→ validate IDs / API versions / dependencies
→ validate namespaced contribution IDs and duplicates
→ register in deterministic extension-ID order
→ compute relevant fingerprints
→ freeze before accepting Runs
```

Manifest 是贡献声明，不要求 Phase 1 一次实现所有 Registry。每个贡献点按实际阶段启用。

ID 必须稳定、命名空间化，例如：

```text
dbfox.data
dbfox.catalog.search_performed
dbfox.data.query_result
dbfox.workspace.file_snapshot
dbfox.workspace.code_patch
```

用户可见标题不是稳定 ID。

## 4. Logical Tool 与 Execution Binding

Agent、RunLoop 和 durable ToolInvocation 只识别 DBFox Tool Contract。一个 Tool 的具体执行来源由 Binding 决定：

```text
                    DBFox Tool Contract
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
   NativeBinding       ExternalBinding     CommandBinding
                         │
                  ┌──────┴──────┐
                  ▼             ▼
              ApiBinding     McpBinding
```

### 4.1 NativeBinding

用于 DBFox correctness 核心能力和与内部状态深度耦合的能力，例如 Catalog、SQL safety、Result Gateway、Workspace CAS write。它可以调用 DBFox 内部 Python service，但仍遵守 Tool input/output、Policy、Artifact、Observation 和 recovery contract。

### 4.2 ApiBinding

用于具有稳定官方 API/SDK 的外部平台。Adapter 负责：

- 将 DBFox Tool input 映射为外部请求；
- 通过 SecretResolver 注入凭据；
- timeout/pagination/rate-limit/retry；
- 将外部错误映射为固定安全错误；
- 将结果规范化为 DBFox Tool output/Artifact/Effect。

外部 API response 不能直接成为 Session Memory 或模型长期上下文。

### 4.3 McpBinding

MCP 是可选的 External Tool Provider，不是第二套 Runtime。DBFox 不把远端/stdio MCP Server 的 `tools/list` 原样暴露给模型。

MCP Tool 进入 Turn 前必须经过：

```text
MCP discovery
→ trusted-server / allowlist policy
→ tool/input schema validation
→ risk/capability mapping
→ DBFox ToolSpec adaptation
→ frozen materialization
→ model-visible Tool definitions
```

冻结 materialization 至少绑定：

```text
mcp_server_id
mcp protocol/adapter version
external tool name
input schema hash
structured-output/adapter contract hash
DBFox ToolSpec version
```

如果 MCP schema 在 pending 调用期间变化：尚未执行则按 Tool version changed 重新规划；已经开始且 outcome 无法证明则结算 `UNKNOWN`，不能用新 schema 猜测旧调用结果。

MCP output 仍必须经过 DBFox output schema、size/secret 校验，然后投影为 Observation、Artifact 和可选 Session Effect。MCP Server 不能直接写 Session Memory、Evidence、Completion state 或 Prompt policy lane。

### 4.4 CommandBinding

当平台没有合适 API/MCP，但存在稳定官方 CLI 时，CLI 是一等合法 Binding。Command Tool 必须使用固定 executable/operation 和严格参数 builder：

```text
validated Tool input
→ approved executable + approved subcommand + structured args
→ isolated process
→ bounded stdout/stderr + structured parser
→ strict Tool output
```

禁止把 model-authored 任意字符串直接传给 `shell=True`。CommandBinding 负责稳定解析 job ID/status/result，而 Generic Terminal Tool 不应承担所有第三方集成。

### 4.5 Generic Terminal

Generic Terminal 是更自由的 Agent 能力，主要用于 coding/build/test/排障和没有稳定封装的长尾操作。它不是默认 Integration Binding。若一个 CLI 操作会重复使用、需要权限/恢复/语义证明，应升级为 Command-backed Tool。

### 4.6 Binding 选择原则

```text
DBFox correctness 核心能力          → Native Tool
稳定官方 API/SDK                    → ApiBinding
成熟、可信、维护良好的 MCP Server   → McpBinding
稳定官方 CLI                        → CommandBinding
无稳定合同的长尾操作                → Generic Terminal / Browser fallback
```

API 与 MCP 的优先顺序按具体平台成熟度决定。无论 Binding 类型，上层 Tool ID、Policy、Observation、Artifact、Effect、Completion 和 Memory 生命周期保持一致。

## 5. Tool execution 分层

```text
ToolInvocationContext
        ↓
ExecutionBackend
        ↓ materialize authorized grants
ToolExecutionEnvironment
        ↓
Tool implementation / Binding adapter
```

### 5.1 ToolInvocationContext

描述“这一次调用是什么”，必须可序列化、backend-neutral，不携带数据库 Session、文件 handle、HTTP client 或 Secret object。

```python
class ToolInvocationContext(BaseModel):
    session_id: str
    run_id: str
    turn_id: str
    invocation_id: str
    execution_id: str
    idempotency_key: str
    deadline_at: datetime | None
    project_id: str | None
    scope_refs: tuple[ResourceScopeRef, ...]
    authority_ref: str | None
    capability_grant_ids: tuple[str, ...]
```

统一 Scope ref，避免持续增加 `datasource_ref/workspace_ref/repository_ref`：

```python
class ResourceScopeRef(BaseModel):
    kind: str
    id: str
    project_id: str | None = None
    version: str | int | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
```

Scope metadata 必须有大小限制并由对应 kind 合同验证。当前 `AgentSession.datasource_id` 仍是非空约束，UI 可暂用 `project_id = datasource_id` adapter；真正支持无数据库 Session 仍需数据模型迁移。

### 5.2 ToolExecutionEnvironment

描述“本 backend 中真正能访问什么”，由 Backend 基于 Kernel 授权在执行进程内创建：

```python
class ToolExecutionEnvironment(Protocol):
    def require_database(self) -> DatabaseResource: ...
    def require_workspace(self) -> WorkspaceResource: ...
    def require_filesystem(self) -> FilesystemResource: ...
    def require_process_runner(self) -> ProcessRunner: ...
    def require_network_gateway(self) -> NetworkGateway: ...
    def require_secret_resolver(self) -> SecretResolver: ...
```

Environment 不是全局 Service Locator：只暴露本 invocation 已授权能力；缺少 Grant 时 `require_*` 必须失败；不得注入整个应用容器。现有 DB Tool 迁移期继续通过 `require_database()` compatibility facade 使用。

## 6. Capability Grant

Tool 的 `execution.capabilities` 是需求声明，不是授权。Kernel 根据 ToolSpec、Policy、Approval、authorized input、scope 和 generation/version 铸造 Grant。

Grant 至少绑定：

- invocation ID；
- Tool name/version；
- authorized input hash；
- capability kind；
- resource scope/version；
- policy fingerprint；
- approval ID（如适用）；
- deadline/expiry。

Environment 只能 materialize Grant 中列出的资源。Tool 或 Binding 不能自行扩大目录、域名、命令、MCP Server、数据源或凭据范围。

## 7. Session Effect

Session Effect 是 Projection 的类型化输入，不是新的领域事实源。

```python
class SessionEffectEnvelope(BaseModel):
    extension_id: str
    effect_type: str
    effect_version: int
    payload: dict[str, JsonValue]
```

Effect payload 不重复 run/observation/timestamp provenance；这些来自 enclosing Observation。

Effect 必须：

- 由已注册 Tool/Extension 产生；
- 与 Observation 在同一 Tool settlement 事务持久化；
- 按 `(extension_id, effect_type, effect_version)` 严格验证；
- 使用 canonical JSON，并有 item/byte 上限；
- 只有 enclosing Observation `succeeded` 时可 fold。

Effect 禁止保存 rows、series、完整 Schema、完整文件、长日志、Secret、DSN、Token 或 execution authority；不能影响当前 Run recovery、进入系统指令 lane 或覆盖 Observation/Artifact/Evidence。

推荐作为 Tool outcome 的独立贡献：

```python
ToolOutcome(output=..., artifacts=(...), session_effects=(...))
```

如果 Catalog 实现证明 Effect 只是 Invocation/Observation 的完全重复，应通过实现评审改为 extension-owned reducer 直接读取 canonical records；无论哪条路径，Kernel 都不能按具体 Tool 名写 reducer。

## 8. Semantic capability

Semantic capability 改为 namespaced string contract：

```text
dbfox.data.environment_profile
dbfox.data.schema_metadata
dbfox.data.query_result
dbfox.workspace.file_content
dbfox.workspace.modified
dbfox.tests.result
```

它表达成功 Observation 能证明什么，不是 Tool 名别名，也不授予执行权限。注册时验证 ID 唯一、所属 Extension 和版本；Tool 只能声明已注册 capability。

## 9. Completion composition

Completion 拆为 Core 和 Domain rules。

Core 负责 Tool 是否 settled、pending Approval/Question、Run/cancel、answer candidate、citation 基础有效性、Artifact ownership 和 budget。

Extension Rule 只能增加约束：

```text
PASS
MISSING(requirements)
VETO(reason)
```

组合顺序：

```text
Core VETO > Extension VETO > union(MISSING) > PASS
```

Extension Rule 可以要求 Semantic Proof、Artifact、引用或测试结果；不能强制 completed、绕过 pending work/citation/authority、修改预算、把失败 Observation 当成功或降低其他 Rule 要求。Rule 抛异常时 fail-closed。

当前 `QUERY_RESULT → inline Result Artifact citation` 机械迁移为 DataCompletionRule，现有测试必须保持 decision 和 Evidence artifact IDs 等价。

## 10. Fingerprint 与缺失扩展

不能使用覆盖前后端所有贡献的单一 `extension_registry_hash`。分别计算：

```text
runtime_contract_registry_fingerprint
state_projection_registry_fingerprint
presentation_registry_fingerprint
```

Memory 使用 per-projection `contract_fingerprint`；增加前端 Renderer 不得改变 Catalog projection hash。

External Binding 的 endpoint、credential identity 等运行配置不进入 Tool semantic version；但能改变输入/输出解释、权限或恢复语义的 adapter/protocol/schema contract 必须进入 materialization/fingerprint。

缺失扩展遵守：

- degraded read：保留 envelope，不进入 Prompt/Completion；
- strict rebuild：缺 Projector 则 incomplete，不覆盖 Memory；
- explicit migration/drop：显式 tombstone 后才可丢弃 namespace。

缺 Renderer 只影响呈现；缺 Tool/Binding 只影响未来调用；缺 Projector 影响 rebuild；缺 Artifact validator 拒绝新写入但不能破坏旧 envelope 读取。

## 11. Data Extension 迁移

现有 `register_dbfox_tools()` 先包装为：

```python
register_builtin_data_extension(registries)
```

第一步只改变注册所有权，不改变 Tool 名、版本、Schema、Policy、Observation、Artifact 或用户行为。随后按阶段迁移 Catalog Projection、Data Artifact contract、namespaced semantics、DataCompletionRule 和前端 Result/Table/Chart contributions。

## 12. 验收

- 注册顺序确定，duplicate/dependency mismatch 拒绝，serving 后 Registry 冻结；
- 当前 Data Tool schema/materialization 在预期迁移点外不变化；
- DB Tool 无回归，高权限 capability 不能进入 `in_process`；
- Grant 与 invocation/input/scope/version 绑定；
- MCP Tool 经过 allowlist/admission/materialization，不直接透传给模型；
- CommandBinding 不执行 model-authored 任意 shell 字符串；
- 不同 Binding 的 output 都进入相同 DBFox Observation/Artifact/Effect pipeline；
- 未注册 Artifact 写入失败，历史未知 Artifact envelope 可读取；
- DataCompletionRule 与迁移前行为一致，Rule exception fail-closed；
- 第一个 Workspace Extension 不添加 Tool-name/domain switch；
- 第二个完整 Extension 只通过 contribution registration 接入，不修改 RunLoop、ContextSnapshot 根字段、Memory 根模型、Completion Core 或 WorkspaceDock dispatch。

## 13. 非目标

不做动态第三方 Extension、Marketplace、任意 Service Locator、通用任务 DSL、通用 Tool Cache、外部 Workflow Engine，或“自动发现任意 MCP Server 并把所有 Tool 无审查透传给模型”。Generic MCP Marketplace/compatibility layer 不属于初始实施范围；MCP 作为受策略控制的未来 Tool Binding 是架构允许且明确支持的方向。

隔离执行、安全协议、MCP/Command provider、Artifact envelope 和 wire compatibility 的细节见[Runtime Extension 安全与兼容规范](./runtime-extension-security-compatibility.md)。
