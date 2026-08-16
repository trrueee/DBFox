# Runtime Extension 安全与兼容规范

> 文档类型：Runtime Extension ADR 附录 / 实施合同
>
> 状态：已接受
>
> 最后核验：2026-08-16
>
> 基线：`main@daa99d048decd7f5f8dc010cbe5465f332686a3c`
>
> 关联 ADR：[Runtime Extension Contracts](./runtime-extension-contracts.md)

## 1. 目的

本规范定义扩展执行、安全、Artifact/wire compatibility 和缺失能力语义。目标是在不复制当前 ToolExecutor/ToolRuntime 职责的前提下，支持未来 isolated process、File、Terminal、API、MCP、Remote Job 等能力。

第一阶段 Extension 仍是受信任产品代码；普通子进程不是 hostile-code sandbox。

## 2. 当前执行责任必须保留

当前代码已经形成三层有效边界：

```text
ToolDispatcher
  durable request / policy / approval / settlement

ToolExecutor
  overall deadline / retry / concurrency / cancel

ToolRuntime
  input/output validation / Tool call / reconciliation
```

后续不建立另一个 `ExecutionBackend` 再重复拥有 deadline、retry、output limit 和 recovery policy。

### 2.1 AttemptRunner Strategy 使用 serializable request

`isolated_process` 不能以 Python `Callable`/closure 作为 Runner contract，因为 closure 会捕获 SQLAlchemy Session、request、authority 或其他进程内对象，无法形成稳定 worker wire。

P5B resource seam 完成后定义最小 attempt value：

```python
class ToolAttemptRequest(BaseModel):
    mode: Literal["execute", "reconcile"]
    tool_name: str
    frozen_tool_version: str
    invocation: ToolInvocationContext
    authorized_input: dict[str, JsonValue]
    resource_grants: tuple[ExecutionResourceGrant, ...] = ()
    attempt_timeout_ms: int
```

`ExecutionResourceGrant` 只有在 Database + Workspace 两个真实资源证明现有 ExecutionAuthority 不足时才存在；否则不为字段对称性创建空 Grant 层。

Runner 接口概念上是：

```python
class ToolAttemptRunner(Protocol):
    def run(
        self,
        *,
        request: ToolAttemptRequest,
        control: ToolExecutionControl,
    ) -> ToolResult: ...
```

实现：

```text
InProcessAttemptRunner
IsolatedProcessAttemptRunner
```

父进程 `ToolExecutor` 仍是 deadline authority；`attempt_timeout_ms` 是基于剩余 deadline 产生的相对上限，worker 不能通过自己的时钟延长父级 deadline。

### 2.2 Shared ToolAttemptHandler

In-process 与 isolated worker 必须复用同一 handler 语义：

```text
ToolAttemptRequest
→ verify frozen/current Tool contract
→ resolve authorized resources
→ ToolRuntime.execute / reconcile
→ strict ToolResult
```

不允许实现一套 `run_in_process_tool()` 和另一套具有不同 validation/reconcile 语义的 `run_worker_tool()`。

责任分配：

| 层 | 负责 |
| --- | --- |
| ToolDispatcher | durable admission、Policy/Approval、running/settlement、UNKNOWN 语义 |
| ToolExecutor | overall deadline、retry loop、scope concurrency、cancel decision、attempt accounting |
| AttemptRunner | 单次 attempt 的 thread/process transport 与强制停止能力 |
| ToolAttemptHandler | Tool contract verification、resource resolution、调用 ToolRuntime |
| ToolRuntime | Tool input/output contract、implementation、reconcile output contract |

这样 retry/recovery 只有一个 owner，execute/reconcile 也只有一条语义链。

## 3. In-process

当前 in-process 继续只允许 Kernel allowlist capability。数据库 Session 在 worker attempt 内创建，不跨线程复用 caller Session。

Python 无法安全杀死已经运行的线程，因此当前 stuck-thread quarantine / retired pool 行为应保留；late result 不得提交成功状态。

InProcessAttemptRunner 可以在 executor-owned thread 中调用 `ToolAttemptHandler(request)`，但 Runner 的公开 seam 仍然是 serializable request，而不是 closure。这保证后续 isolated runner 不要求再改 ToolExecutor API。

## 4. Isolated process

`IsolatedProcessAttemptRunner` 负责本地 worker transport，不负责 Agent orchestration。

父子协议最小包含：

```text
protocol version
ToolAttemptRequest
heartbeat / cancellation channel
structured ToolResult
bounded diagnostics
worker exit status
```

Worker 启动后：

```text
decode request
→ validate protocol/schema
→ verify current Tool contract == frozen_tool_version
→ materialize only authorized resources
→ invoke shared ToolAttemptHandler
→ validate/encode ToolResult
```

禁止跨进程传输：

- Python callable/closure；
- SQLAlchemy Session；
- DB connection；
- HTTP client；
- global application container；
- plaintext Secret。

如果未来真的引入 Session Effect，再在协议版本中增加，不为 P0 Catalog Memory 预留空字段。

必须实现：

- protocol/schema handshake；
- heartbeat；
- parent→worker cancel；
- process group/tree termination；
- stdout/stderr 和 frame size limit；
- malformed result rejection；
- worker crash / parent crash 的确定语义；
- late result suppression；
- Windows/macOS/Linux contract tests；
- Secret 只通过受控 opaque reference 使用。

`isolated_process` 的产品承诺是故障、资源、取消和生命周期隔离，不是防御同用户权限下恶意代码的完整沙箱。

## 5. Resource / capability boundary

不要在只有 Database 一种真实资源时建设万能 Service Locator。

实施顺序：

```text
P5A real Workspace resource substrate
→ P5B extract Database + Workspace common seam
→ P6 use that seam in ToolAttemptRequest / worker
→ P7 expose File Tool
```

这样避免“resource seam 等 File Tool，而 File Tool 又等 resource seam/isolated runner”的循环。

要求：

- invocation 中只保存 serializable scope identity；
- execution resource object 不进入 durable JSON/wire；
- Tool/handler 只能解析已授权 scope；
- Secret 不作为普通 JSON 字段；
- 没有 authorization 时资源解析失败；
- 不注入整个 application container。

如果引入 resource grant，使用 immutable value，直接绑定 invocation/input/scope/version/policy/approval/expiry。第一版不建立独立 grant table 或 `grant_id → lookup → materialize` 链。

## 6. API / MCP / Command 外部执行

外部执行来源仍然是 Tool contract 背后的实现策略，不能绕过 DBFox durable Tool lifecycle：

```text
frozen Tool materialization
→ Policy / Approval
→ ToolAttemptRequest
→ one execution attempt
→ strict output validation
→ durable Observation / Artifact settlement
```

### 6.1 API

API adapter 必须控制：

- endpoint/method contract；
- timeout/pagination/rate limit；
- redirect policy；
- credential injection；
- response size/content-type；
- fixed safe error mapping。

Raw response 不直接进入 Prompt/Memory。

### 6.2 MCP

MCP connection 必须绑定：

- trusted server identity；
- transport kind；
- adapter/protocol version；
- allowed tool IDs；
- input/output schema hash；
- risk/capability policy；
- credential reference；
- timeout/output limit。

Admission：

```text
connect/discover
→ validate server config
→ allowlist tool
→ validate schema
→ materialize DBFox Tool contract
→ freeze Turn
```

MCP server/tool schema 变化：

- pending、未执行：version changed / replan；
- 已执行且 outcome 无法证明：UNKNOWN；
- 不自动兼容未知 schema。

stdio MCP 可以由 isolated attempt 托管；network MCP 仍需 network/secret policy。二者不能创建平行 Session/RunLoop。

### 6.3 Command

Command-backed Tool 必须：

```text
validated input
→ fixed executable
→ fixed/allowlisted operation
→ structured argv
→ bounded process attempt
→ versioned parser
→ strict Tool output
```

禁止：

```python
subprocess.run(model_generated_string, shell=True)
```

Generic Terminal 是独立高风险能力，不能伪装成“CommandBinding 的自由模式”。

## 7. Remote Job / long-running resource

Runtime compatibility 不等价于所有任务都在一个 ToolInvocation 生命周期内完成。

Spark/Flink/Airflow/Kubernetes/ML training 等长任务采用：

```text
submit Tool
→ bounded submission Observation
→ durable RemoteJobRef
→ ToolInvocation settles
→ Run may terminal

later Run
→ status/read/cancel Tool(RemoteJobRef)
→ new Observation/Artifact
```

`RemoteJobRef` 是稳定引用 value，不自动成为通用 global table。至少包含：

```text
provider/capability ID
resource kind
external resource ID
submission provenance
contract/schema version
resource scope/version if applicable
```

第一种 provider 可以把它放入 capability-owned Artifact payload 或已经必要的 provider-owned canonical state；只有至少两个真实 provider 证明需要统一可变 job aggregate 时，才评审通用 RemoteJob persistence。

禁止在 RemoteJobRef 中保存 credential、完整 log、大结果或 execution authority。

## 8. Filesystem

Workspace File Tool 真正进入实现时必须绑定：

- canonical workspace root；
- normalized relative path；
- read/write permission；
- expected file/workspace version；
- size/window limit；
- deadline/invocation identity。

拒绝：

- absolute path；
- `..` escape；
- Windows device path；
- 未授权 root；
- symlink/reparse-point escape；
- 超限文件；
- 不支持的 binary write。

写入算法：

```text
open under authorized root
→ read current version/hash
→ compare expected CAS value
→ write temp sibling
→ flush/fsync where supported
→ atomic replace
→ publish Tool result
```

不得静默覆盖。worker crash 后如果无法证明 replace 是否完成，按 recovery contract reconcile/unknown。

## 9. Network

Network Tool/adapter 至少处理：

- allowed scheme/domain/port；
- DNS 和 redirect 后重新验证目标；
- loopback/link-local/private/metadata-service policy；
- response/decompression limit；
- pagination bound；
- credential 注入不返回给模型。

网络返回内容只能进入 Kernel 指定的不可信 Context lane。

## 10. Secret

Secret 永远不作为普通 JSON value 跨 Runtime 边界传播。

禁止进入：

```text
Prompt
Observation facts
Artifact payload
Session Memory
Event payload
ToolAttemptRequest plain fields
worker diagnostics
MCP raw model-visible result
```

执行位置通过 opaque credential reference/resolver 使用 Secret。写入持久化边界前执行固定 redaction/secret scan。

## 11. Artifact compatibility

Artifact wire 第一阶段保持字段名 `type`，新增独立 `schema_version`：

```text
id
session_id
run_id
turn_id
type: string
schema_version: integer
version: integer        # semantic work-product version, 不是 schema version
title / summary / status / visibility
payload
payload_ref
provenance
relations
```

数据库 expand migration 冻结为：

```text
schema_version INTEGER NOT NULL DEFAULT 1
```

已有行视为 schema v1；`Artifact.version` 不改语义。

兼容读取规则：

- 已知 legacy type 的历史 snapshot/wire 缺 `schema_version` → 仅按 v1 读取；
- unknown historical type/version → preserve metadata/envelope + fallback；
- 绝不把 unknown missing version 猜成 v1 的某个 payload contract；
- compatibility window 内 built-in write boundary 可补 v1；
- cutover 后新 Extension write 必须显式 schema version；
- unknown new write reject。

写入顺序：

```text
Kernel envelope checks
→ validator[(type, schema_version)]
→ persistence
```

Kernel 固定负责：

- ownership；
- payload/provenance/relations byte limit；
- result rows/series 等禁止复制；
- secret scan；
- payload_ref policy；
- relation target visibility。

新 Extension type 使用 namespaced ID。已有 `sql/result_view/chart/...` 继续作为 schema v1，避免纯命名迁移。

## 12. Completion safety

Extension completion constraint 只读 durable/context input，并只能返回：

```text
PASS
MISSING
VETO
```

顺序：

```text
Core lifecycle/citation eligibility
→ extension VETO
→ union MISSING
→ PASS
```

Constraint 不得：

- 强制 completed；
- 绕过 pending Tool/Approval/Question；
- 绕过 citation ownership；
- 生成 execution authority；
- 修改 budget；
- 把 failed/unknown Observation 当 success。

第一阶段使用 immutable constraint tuple；只有真实动态启停需求出现后才需要独立 Registry。

## 13. Projection / Context compatibility

Memory compatibility 是 per-projection contract，不是全局 Tool Registry hash。

每个 Projection 保存：

```text
projection_id
schema_version
contract_fingerprint
projected_through_session_sequence
state_hash
```

`contract_fingerprint` 的输入包括会改变该 projection 解释的 reducer/policy/schema contract。UI Renderer、Tool presentation、外部 endpoint/credential identity 不得触发 Catalog Memory rebuild。

缺 Projector 时：

- normal read：现有 projection 可保留；只有通过当前 resource fence 的已成功 state 才能参与 Context；
- strict rebuild：incomplete，不覆盖；
- drop：必须显式 migration/tombstone。

当 Catalog + Workspace 两个真实 Context 来源都存在后，提炼 bounded Context fragment seam。Fragment 只能选择 Kernel allowlist lane，不能控制 system role、最终 priority、budget 或 Provider wire；PromptAssembler 仍是唯一 Provider-input owner。

## 14. Version mismatch

- Turn 使用 frozen Tool materialization；
- 未执行时实现/contract 变化 → version changed；
- 已开始且 outcome 无法证明 → UNKNOWN；
- reconcile 只证明旧 action outcome，不隐式授权 replay；
- historical unknown Artifact/Projection 保留 envelope；
- 不猜测未知 schema compatibility；
- worker 必须在执行 request 前验证 frozen/current Tool contract。

## 15. 测试矩阵

### Runtime

- Tool registry freeze / duplicate owner；
- materialization parity；
- timeout/cancel；
- retry/reconcile/unknown；
- late result；
- stuck-thread quarantine；
- AttemptRequest serialization；
- in-process/isolated shared handler parity；
- isolated worker crash / malformed frame / process-tree kill；
- worker contract mismatch。

### External

- MCP allowlist / schema drift；
- API redirect/network policy；
- Command argv 不接受 arbitrary shell string；
- stdout/stderr/output size bound；
- Secret 不泄露；
- Remote Job submit settles invocation and later status reuses durable ref。

### Filesystem

- traversal；
- symlink/reparse escape；
- CAS conflict；
- atomic replace；
- external modification race。

### Compatibility

- legacy Artifact v1 without wire schema_version；
- unknown Artifact fallback；
- missing Projector strict rebuild；
- existing Tool materialization parity；
- legacy semantic capability compatibility；
- new Context contributor cannot choose privileged role/priority。

## 16. 非目标

不做 hostile-code sandbox、动态 Extension Host、任意网络代理、任意命令执行、Secret 直传、通用 Artifact relation graph、自动兼容未知 schema、第二套 retry engine、第二套 Agent Runtime、预先建设通用 Remote Job database 或万能 Context plugin framework。
