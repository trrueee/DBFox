# Runtime Extension 安全与兼容规范

> 文档类型：Runtime Extension ADR 附录 / 实施合同
>
> 状态：已接受
>
> 最后核验：2026-08-16
>
> 关联 ADR：[Runtime Extension Contracts](./runtime-extension-contracts.md)

## 1. 目的

本规范定义 ExecutionBackend、Capability Grant、isolated worker、External Tool Provider、Artifact envelope、wire compatibility 和缺失 Extension 的实施边界。它不授权运行任意第三方代码，也不把普通子进程称为安全沙箱。

## 2. ExecutionBackend

```python
class ExecutionBackend(Protocol):
    id: str
    protocol_version: str

    def execute(
        self,
        *,
        tool: FrozenToolContract,
        invocation: ToolInvocationContext,
        grants: tuple[CapabilityGrant, ...],
        control: ExecutionControl,
    ) -> ToolExecutionResult: ...
```

Backend 负责：

- 在本执行位置 materialize Environment；
- timeout、heartbeat 和 cancellation；
- output byte limit；
- transport/exit error 映射；
- 返回严格结构化 envelope；
- 阻止 late result 提交；
- 不绕过 durable Tool settlement。

### 2.1 `in_process`

只允许 Kernel 明确 allowlist 的 capability，例如 metadata read/write 和 database read。Tool 仍在 executor-owned thread 中创建自己的数据库 Session，不跨线程复用 caller Session。

### 2.2 `isolated_process`

父子协议至少包含：

```text
protocol version
extension/tool ID and version
input/output schema hash
invocation context
capability grant references
authorized input
heartbeat/cancellation channel
structured Tool result
Artifact drafts
Session Effects
bounded diagnostics
exit/timeout/cancel status
```

必须实现：

- environment allowlist；
- workspace root grant；
- stdout/stderr 和 structured output 限额；
- process group/tree termination；
- deadline、heartbeat 和 cancellation；
- child/parent crash 映射；
- malformed/version-mismatched result 拒绝；
- late success 不提交；
- Secret 只通过 broker reference 使用；
- recovery 遵守 retry/reconcile/unknown；
- Windows、macOS、Linux 平台测试。

`isolated_process` 主要是故障、资源和生命周期隔离。以当前用户身份运行的子进程默认仍可能访问用户可读资源；第一阶段 Extension 必须是受信任产品代码。

## 3. External Tool Provider / Binding

外部服务或 CLI 不能绕过 DBFox Tool Contract。无论 Native、API、MCP 还是 Command Binding，最终都必须回到：

```text
DBFox ToolSpec/materialization
→ Policy / Approval / Capability Grant
→ Provider/Backend
→ strict Tool output validation
→ Observation + Artifact + optional Session Effect
→ durable Tool settlement
```

### 3.1 API Provider

- endpoint、method、pagination、rate limit 和 timeout 由 adapter 合同控制；
- 认证由 SecretResolver/credential reference 注入；
- 外部错误映射为固定安全错误；
- raw response 不直接进入 Memory/Prompt；
- adapter/protocol/schema 语义变化必须反映在 Tool version/materialization fingerprint 中。

### 3.2 MCP Provider

MCP 仅作为受策略控制的 External Tool Provider。DBFox 不自动把任意 MCP Server 的 `tools/list` 全量暴露给模型。

MCP connection 必须绑定：

- trusted server identity；
- transport kind（stdio / network transport）；
- adapter/protocol version；
- allowed tool IDs；
- Tool schema hash；
- capability/risk mapping；
- credential reference；
- timeout/output limits。

Admission：

```text
connect/discover
→ verify server/config policy
→ validate tool names/input schema
→ allowlist requested tools
→ map capabilities/risk/approval
→ adapt to DBFox ToolSpec
→ freeze Turn materialization
```

如果 server/tool schema 在 pending 调用期间变化：未执行调用返回 version changed 并要求 replan；已经执行且不能证明 outcome 时结算 `UNKNOWN`。

MCP result 必须经过 DBFox output schema、secret scan、byte limit 和 Artifact/Effect validation。MCP Server 不能直接：

- 写 Session Memory；
- 写 Evidence；
- 决定 Completion；
- 获得 SYSTEM_POLICY/RUNTIME_INSTRUCTION lane；
- 绕过 Approval/Authority；
- 把 credential 返回给模型。

stdio MCP 可以由 isolated worker 托管；HTTP/网络 MCP 通过 Network Gateway/Secret broker。两种 transport 共享同一 Tool settlement 和 recovery contract。

### 3.3 Command Provider

官方 CLI 可作为一等 Binding，但必须结构化：

```text
validated input
→ fixed executable
→ fixed/allowlisted subcommand
→ structured argument builder
→ isolated execution
→ bounded stdout/stderr
→ versioned parser
→ strict Tool output
```

禁止：

```python
subprocess.run(model_generated_string, shell=True)
```

对于稳定重复能力（例如 dbt run、git status、某平台 job submit/status），优先封装 Command-backed Tool；Generic Terminal 仅用于长尾 coding/build/test/排障。

## 4. Filesystem capability

Workspace File Tool 必须绑定：

- canonical workspace root；
- normalized relative path；
- read/write capability；
- expected workspace/file version；
- size/line/window limit；
- deadline 和 invocation ID。

拒绝：

- absolute path；
- `..` escape；
- Windows device path；
- 未授权 root；
- 不符合 symlink/reparse-point policy 的目标；
- 超限文件；
- 未声明编码或不支持的 binary write。

写入合同：

```text
read current version
compare expected hash/revision
return conflict if changed
write temp file
flush/fsync where supported
atomic replace
preserve permitted metadata
publish Observation/Artifact/Effect
```

不得静默覆盖。File write 必须有 expected hash/version CAS，并明确 crash/reconcile/unknown 语义。

## 5. Network capability

未来 Network Extension 至少处理：

- allowed scheme/domain/port；
- DNS/redirect 后重新验证；
- loopback、link-local、private range 和 metadata-service policy；
- response size、content type、decompression limit；
- pagination 和 bounded preview；
- credential injection 由 broker 完成；
- raw credential 不进入 invocation、Prompt、Observation、Artifact 或 Effect。

Browser/Web/MCP 网络内容只能进入 Kernel 指定的不可信 Context lane。

## 6. Process capability

Terminal/Test Tool 必须声明：

- command policy 或 registered operation；
- cwd/workspace scope；
- argument contract；
- environment allowlist；
- timeout；
- output limit；
- recovery policy；
- 是否允许子进程；
- changed-files detection policy。

非幂等命令不能使用 `RETRY_SAFE`。worker 丢失且无法证明结果时必须结算 `UNKNOWN`，不能根据 exit log 猜测成功。

## 7. Secret boundary

Secret 永远不作为普通 JSON value 传输。Kernel/Policy 产生 opaque reference，ExecutionEnvironment 的 SecretResolver 在授权执行位置解析。

禁止持久化或发送给模型：

```text
API keys
passwords
Authorization headers
plaintext DSN
SSH private keys
session cookies
temporary access tokens
```

Artifact、Observation、Effect、Event、diagnostic、MCP adapter 和 worker output 在写入前都执行固定 secret scan/redaction。错误消息只允许固定公开 catalog 或经过边界声明的安全文本。

## 8. Artifact envelope

```python
class ArtifactEnvelope(BaseModel):
    id: str
    session_id: str
    run_id: str
    turn_id: str | None
    type_id: str
    schema_version: int
    title: str
    summary: str | None
    status: str
    visibility: str
    payload: dict[str, JsonValue]
    payload_ref: str | None
    provenance: dict[str, JsonValue]
    relations: tuple[ArtifactRelation, ...]
```

写入顺序：

```text
Kernel envelope validation
→ registered type-specific payload validation
→ persistence
```

Kernel 始终负责：

- payload/provenance/relations byte limit；
- 禁止 rows、previewRows、series 等大结果复制；
- secret scan；
- `payload_ref` 安全格式和访问网关；
- Session/Run ownership；
- type ID namespace/schema version；
- relation target 可见性。

Extension validator 只负责领域 payload。

未知类型：

```text
write unknown type       → reject
read historical unknown  → preserve envelope
render unknown           → fallback
Evidence relation        → preserve
```

首阶段保留少量 Kernel relation primitives：`derived_from`、`supports`、`validated_by`、`executed_as`、`visualized_as`。不提前建立 relation registry。

## 9. Wire contract

后端和前端必须从封闭 enum/union 迁移为稳定 envelope：

```text
type_id: string
schema_version: integer
payload: JSON object
```

已知类型由 Registry 二次验证；未知类型保留 metadata。迁移采用 expand/compatible-read/switch/delete，不允许一次性破坏旧 Conversation snapshot。

Backend manifest 与 Frontend contribution manifest 通过共享 namespaced IDs 配对，但后端注册 Tool 不会隐式注册 React Renderer。

## 10. Fingerprint

分别计算：

```text
runtime_contract_registry_fingerprint
state_projection_registry_fingerprint
presentation_registry_fingerprint
```

每个 Projection Module 自带：

```text
schema_version
projector_version
policy_version
contract_fingerprint
projected_through_session_sequence
state_hash
```

只有影响该 Projection 的 effect/reducer contract 才进入其 fingerprint。新增 Renderer、Command 或外部 endpoint 配置不得导致 Catalog Memory 重建。

External Provider 的 server identity/endpoint/credential identity 属于 runtime configuration；会改变 Tool schema、输入/输出解释、权限或 recovery 语义的 adapter/protocol/schema contract 必须进入 frozen materialization。

## 11. Version mismatch 与缺失能力

- pending Tool 使用 Turn 冻结的 Tool version/materialization；
- 实现/Binding 缺失且尚未执行时返回 version changed，要求模型规划新调用；
- 已开始但结果无法证明时结算 `UNKNOWN`；
- 历史 unknown Artifact envelope 可读取；
- 缺 Renderer 显示 fallback；
- 缺 Projector 时 strict rebuild 不覆盖 Memory；
- 普通启动不得静默 drop namespace。

## 12. Completion Rule 安全

Extension Rule 只能返回 `PASS`、`MISSING` 或 `VETO`。聚合顺序：

```text
Core VETO > Extension VETO > MISSING > PASS
```

Rule 不得：

- 强制 completed；
- 绕过 active Tool/Approval/Question；
- 绕过 citation/Artifact ownership；
- 重建执行授权；
- 修改 Run budget；
- 把 failed/unknown Observation 当 success；
- 降低其他 Rule 要求。

Rule exception 必须 fail-closed，并记录固定公开错误和 rule ID。

## 13. 测试矩阵

### Contract

- duplicate ID/dependency mismatch；
- schema hash/version mismatch；
- Registry freeze；
- unknown Artifact read/write；
- Effect size/type validation；
- capability-grant binding；
- MCP admission/allowlist/schema drift；
- Command argument builder forbids arbitrary shell string。

### Backend

- timeout/cancel；
- process-tree kill；
- worker crash/parent crash；
- malformed result；
- late result；
- output limit；
- Secret leak scan；
- retry/reconcile/unknown；
- stdio/network provider disconnect。

### Filesystem

- path traversal；
- symlink/reparse-point escape；
- CAS conflict；
- atomic replace；
- permission/encoding behavior；
- external modification race。

### Compatibility

- old Conversation snapshot；
- unknown Artifact fallback；
- missing Renderer；
- missing Projector strict rebuild；
- missing MCP/Command Binding；
- explicit namespace drop/tombstone；
- Data Tool behavior parity。

## 14. 非目标

不做 hostile-code sandbox、动态 Extension Host、在线安装、任意网络代理、任意命令执行、Secret 直传、通用 Artifact relation graph、自动兼容未知 schema，或将任意 MCP Server 的所有 Tool 自动透传给模型。
