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

本规范定义扩展执行、安全、Artifact/wire compatibility 和缺失能力语义。目标是在不复制当前 ToolExecutor/ToolRuntime 职责的前提下，支持未来 isolated process、File、Terminal、API、MCP 等执行来源。

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

### 2.1 AttemptRunner Strategy

当 `isolated_process` 真正实现时，在 `ToolExecutor` 内部抽“一次 attempt 如何执行”的 Strategy：

```python
class ToolAttemptRunner(Protocol):
    def run(
        self,
        *,
        operation: ToolOperation,
        control: ToolExecutionControl,
    ) -> ToolResult: ...
```

实现：

```text
InProcessAttemptRunner
IsolatedProcessAttemptRunner
```

责任分配：

| 层 | 负责 |
| --- | --- |
| ToolDispatcher | durable admission、Policy/Approval、running/settlement、UNKNOWN 语义 |
| ToolExecutor | 总 deadline、retry loop、scope concurrency、cancel decision、attempt accounting |
| AttemptRunner | 单次 attempt 的线程/进程 transport 和强制停止能力 |
| ToolRuntime | Tool input/output contract、Tool implementation、reconcile output contract |

这样 retry/recovery 只有一个 owner。

## 3. In-process

当前 in-process 继续只允许 Kernel allowlist capability。线程执行保持现有原则：数据库 Session 在 worker attempt 内创建，不跨线程复用 caller Session。

Python 无法安全杀死已经运行的线程，因此当前 stuck-thread quarantine / retired pool 行为应保留；late result 不得提交成功状态。

## 4. Isolated process

`IsolatedProcessAttemptRunner` 负责本地 worker transport，不负责 Agent orchestration。

父子协议最小包含：

```text
protocol version
Tool ID / frozen contract version
invocation identity
validated authorized input
resource grant values or opaque references
attempt deadline
structured Tool result
Artifact drafts
bounded diagnostics
worker exit status
```

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

不要在 isolated backend 之前建设万能 Service Locator。

第一阶段保持现有 Database resource 方式。Workspace/File 作为第二种真实资源出现时再定义最小 resource resolver/grant contract。

要求：

- invocation 中只保存 serializable scope identity；
- 执行资源对象不进入 durable JSON；
- Tool 只能拿到被授权的 scope；
- Secret 不作为普通 JSON 字段；
- 没有 grant 时资源解析失败；
- 不注入整个 application container。

如果引入 execution grant，使用 immutable value，直接绑定 invocation/input/scope/version/policy/approval/expiry。第一版不建立独立 grant table 或 `grant_id` lookup 链。

## 6. API / MCP / Command 外部执行

外部执行来源仍然是 Tool implementation 的一部分，不能绕过 DBFox durable Tool contract：

```text
frozen Tool materialization
→ Policy / Approval
→ one execution attempt
→ output validation
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

## 7. Filesystem

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

## 8. Network

Network Tool/adapter 至少处理：

- allowed scheme/domain/port；
- DNS 和 redirect 后重新验证目标；
- loopback/link-local/private/metadata-service policy；
- response/decompression limit；
- pagination bound；
- credential 注入不返回给模型。

网络返回内容只能进入 Kernel 指定的不可信 Context lane。

## 9. Secret

Secret 永远不作为普通 JSON value 跨 Runtime 边界传播。

禁止进入：

```text
Prompt
Observation facts
Artifact payload
Session Memory
Event payload
worker diagnostics
MCP raw model-visible result
```

执行位置通过 opaque credential reference/resolver 使用 Secret。写入持久化边界前执行固定 redaction/secret scan。

## 10. Artifact compatibility

Artifact wire 第一阶段保持字段名 `type`，新增 `schema_version`：

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

写入顺序：

```text
Kernel envelope checks
→ validator[(type, schema_version)]
→ persist
```

Kernel 固定负责：

- ownership；
- payload/provenance/relations byte limit；
- result rows/series 等禁止复制；
- secret scan；
- payload_ref policy；
- relation target visibility。

新 Extension type 使用 namespaced ID。已有 `sql/result_view/chart/...` 继续作为 schema v1，避免纯命名迁移。

未知历史 Artifact：保留并 fallback；未知新写入：拒绝。

## 11. Completion safety

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

## 12. Projection compatibility

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

- normal read：现有 projection 可保留但不注入 Prompt；
- strict rebuild：incomplete，不覆盖；
- drop：必须显式 migration/tombstone。

## 13. Version mismatch

- Turn 使用 frozen Tool materialization；
- 未执行时实现/contract 变化 → version changed；
- 已开始且 outcome 无法证明 → UNKNOWN；
- reconcile 只证明旧 action outcome，不隐式授权 replay；
- historical unknown Artifact/Projection 保留 envelope；
- 不猜测未知 schema compatibility。

## 14. 测试矩阵

### Runtime

- Tool registry freeze / duplicate owner；
- materialization parity；
- timeout/cancel；
- retry/reconcile/unknown；
- late result；
- stuck-thread quarantine；
- isolated worker crash / malformed frame / process-tree kill。

### External

- MCP allowlist / schema drift；
- API redirect/network policy；
- Command argv 不接受 arbitrary shell string；
- stdout/stderr/output size bound；
- Secret 不泄露。

### Filesystem

- traversal；
- symlink/reparse escape；
- CAS conflict；
- atomic replace；
- external modification race。

### Compatibility

- legacy Artifact v1；
- unknown Artifact fallback；
- missing Projector strict rebuild；
- existing Tool materialization parity；
- legacy semantic capability compatibility。

## 15. 非目标

不做 hostile-code sandbox、动态 Extension Host、任意网络代理、任意命令执行、Secret 直传、通用 Artifact relation graph、自动兼容未知 schema、第二套 retry engine 或第二套 Agent Runtime。
