# 可扩展 Runtime 与 Workbench 分阶段实施指南

> 文档类型：跨 ADR 开发计划 / 实施指南
>
> 状态：已接受
>
> 最后核验：2026-08-16
>
> 基线：`main@daa99d048decd7f5f8dc010cbe5465f332686a3c`
>
> 上位 RFC：[DBFox 可扩展 Runtime 与 Workbench 架构计划](./extensible-runtime-workbench-program.md)

## 1. 目标

把 Runtime Extension、Memory v4、Artifact/Completion、Workbench Shell 和后续 capability family 拆成小 PR，并确保开发者不需要在实现中重新发明关键架构决定。

每个 PR 必须：

- main 可运行；
- 先有 characterization/contract test；
- 新抽象说明至少两个真实变化点，或明确是短期 migration facade；
- canonical state 与 derived projection 分离；
- 不新增无必要 DTO/Mapper/Manager；
- 数据结构的 identity/order/bounds/freshness 先于 Service class；
- transaction、recovery、compatibility owner 明确；
- 同步更新受影响的当前实现文档；
- feature flag/compat path 写清删除条件。

本指南的目标不是预建万能 Framework，而是保证后续 Database、Workspace、Terminal、API/MCP、Remote Job、Data Engineering、ML 等能力可以沿同一 Kernel 生命周期演进。

## 2. 总体顺序

```text
P0.5 implementation refinement / characterization
  ↓
P1 minimal Extension ownership
  ↓
P2 Memory v4 P0 + catalog_revision
  ↓
P3 Artifact open type + Completion constraint
  ↓
P4 Workbench Shell V2
  ↓
P5A Workspace resource substrate
  ↓
P5B Database + Workspace resource seam
  ↓
P6 serializable attempt request + isolated runner
  ↓
P7 Workspace read-only vertical slice + Context fragment seam
  ↓
P8 Patch write with CAS
  ↓
P9 Terminal / external binding / Remote Job pattern
  ↓
P10 second materially different capability-family proof
```

P2 是跨 Run 连续性的产品 P0，不被完整扩展框架、isolated process 或前端迁移阻塞。

P5 拆为 A/B 是为了避免“P5 需要 File prototype，而 File Tool 又依赖 P5/P6”的依赖环：先建立真实 Workspace resource service，再用 Database + Workspace 两个真实资源提炼 seam，最后才把 File 暴露成 model-visible Tool。

## 3. P0.5 — 实现前 characterization

### Backend 必须冻结

- `register_dbfox_tools()` 当前注册集合和 materialization hash；
- Tool input/output/Policy/Execution/Semantics parity；
- ToolExecutor deadline/retry/cancel/quarantine；
- completed/failed/cancelled terminal transaction；
- Memory v3 当前 write/read；
- Catalog search/inspect facts bounds；
- Artifact batch prepare-before-write；
- Completion query-result citation behavior。

### Frontend 必须冻结

- Conversation stream/cancel/approval/question；
- SQL draft/execute/result/error；
- Table Preview/Schema/ER；
- MultiTable；
- Artifact open/render；
- Project list/create；
- Datasource create/edit/test/sync；
- Settings / command palette / shortcuts。

### 退出条件

- correction ADR/实施合同合入；
- characterization tests 绿色；
- baseline AgentBench continuity 记录 commit/model/provider/dataset；
- 团队确认以下内容不是实现前置：Session Effect P0、Extension dependency graph、万能 Environment、第二套 Tool fingerprint、Project≈Datasource adapter。

## 4. P1 — 最小 Extension ownership

### PR 1：注册所有权拆分

把现有组合注册拆成：

```text
register_core_functions
register_conversation_functions
register_data_extension
```

保留 `register_dbfox_tools()` facade 作为短期组合入口。

要求：

- Control/Conversation 不误归 `dbfox.data`；
- Tool 真实对象直接进 Registry；
- 不创建 ToolContribution DTO → Mapper → Adapter 链；
- existing Tool materialization hash parity 100%。

### PR 2：owner / duplicate / freeze

只为实际已经存在的 Registry 增加：

- owner ID；
- duplicate contribution ID check；
- deterministic registration；
- `freeze()`；
- freeze 后 mutation test。

P1 不实现 dependency graph。第二个真实 Extension 出现依赖时才增加 `requires`，并使用稳定拓扑排序；简单 extension-ID 排序不能代替依赖解析。

### 回滚

新组合入口删除后，旧 facade 仍能构建原 Tool Registry。所有调用点迁完且 parity 稳定后删除 facade。

## 5. P2 — Memory v4 P0

P2 解决真正的 Context continuity，同时保持 Memory 的 derived/non-authoritative 身份。

### 5.1 PR：Catalog publication transaction + revision

先修正 transaction ownership，再加 revision：

- `DataSource.catalog_revision` migration；
- Catalog authoritative publication 与 SearchDoc publication 同一短事务；
- AI enrichment 不在外层 sync transaction 中自行 commit/rollback；
- LLM call 放在数据库写 transaction 外；
- enrichment 写入前 re-check schema hash / connection generation；
- DB atomic `catalog_revision = catalog_revision + 1`；
- Catalog Tool output/Observation 冻结 execution-time revision。

测试：

- successful refresh bumps；
- failed publication no bump；
- AI enrichment publication bumps；
- concurrent publication revision monotonic；
- observation revision 不在 terminal 时倒填。

### 5.2 PR：typed Memory v4 + Catalog reducer

新增最小模型：

```text
SessionMemoryStateV4
SessionMemoryCore
SessionProjectionEnvelope
CatalogProjectionScope
CatalogWorkingState
CatalogObjectKey
CatalogObjectState
SearchFootprint
```

实现 pure Data-owned Catalog reducer，输入直接来自 canonical Invocation/Observation。

**不新增 Session Effect storage/registry。**

算法必须满足：

- temporary object hash map，candidate merge average O(1)；
- searches <= 12；
- objects <= 32；
- deterministic eviction；
- deterministic canonical serialization/hash；
- incremental 与 rebuild 调同一 fold function。

### 5.3 PR：terminal projection + fail-soft catch-up

completed/failed/cancelled 都触发同一个 projection boundary，但 **Memory projection failure 不能阻止 canonical Run terminalization**。

责任：

```text
canonical terminal state / Event
  authoritative

Memory v4
  derived / rebuildable
```

正常路径：

```text
stage canonical terminal state
→ read Memory watermark
→ compute projection candidate through current session_sequence
→ if projection succeeds: upsert Memory + advance watermark
→ append canonical terminal Event
→ commit
```

如果 reducer、projection contract 或 derived-state validation 失败：

```text
DO NOT mutate Memory
DO NOT advance watermark
record fixed/redacted telemetry/log
commit canonical terminal state + terminal Event
```

这不是 silent best-effort：每个 Projection 的 lag 由 `latest terminal session_sequence - 该 Projection envelope 的 projected_through_session_sequence` 明确观测；不维护全局第二份水位。

下一次 projection 不能直接跳到当前 Run；必须从 `watermark + 1` 开始按 session_sequence 连续 catch up。若中间 sequence 尚未形成可归约 terminal Run，则停在 gap 前，不虚假推进 watermark。

普通数据库 transaction/commit 本身失败仍按现有 canonical persistence failure 处理；这里的 fail-soft 只针对 derived projection 计算/合同失败，不能吞掉数据库基础设施故障。

测试至少包括：

- projector exception 不阻止 completed/failed/cancelled terminal settlement；
- projection failure 后 watermark 不变；
- 后续 terminal callback 从旧 watermark catch up；
- catch-up 与 full rebuild hash 相等；
- gap 不被跨越。

### 5.4 PR：shadow + rebuild

- v3 保持当前写入；
- v4 shadow incremental/catch-up；
- full rebuild 调**同一 reducer**；
- compare hash telemetry；
- strict/compare/repair modes；
- missing projector incomplete semantics。

禁止写第二套 rebuild merge 算法。

### 5.5 PR：Context rehydration

- typed context-facing Memory；
- datasource/generation/revision read fence；
- deterministic prior Observation selection；
- <= 8 object digest；
- `SESSION_WORKING_STATE` / `SESSION_EVIDENCE_INDEX`；
- <= 2,000 estimated token working-state budget；
- feature flag 切 v4 Context。

第一版不使用 LLM/embedding 做 prior digest selection。Memory 有 projection lag 时可以少提供新工作，但不能伪装成 complete；resource revision/generation fence 仍优先阻止 stale knowledge 注入。

### 5.6 P2 cutover gate

- incremental/catch-up/full rebuild hash match 100% in deterministic suite；
- failed/cancelled continuity scenarios pass；
- projection failure does not block canonical terminalization；
- no rows/full schema/secret in Memory；
- 10/50/100 Run state bytes/tokens 达平台期；
- AgentBench 无理由 exact Catalog duplicate 显著下降；
- rollback 可切回 v3 Context。

达到稳定窗口后停止 v3 write，再删除 raw dict compatibility。

## 6. P3 — Artifact 与 Completion

### 6.1 PR：Artifact open type + expand migration

当前 DB column `type` 保留，增加独立 payload schema version：

```text
ArtifactType enum → validated string boundary
schema_version INTEGER NOT NULL DEFAULT 1
validator[(type, schema_version)]
```

迁移合同冻结为：

- 现有数据库行 backfill/default 为 `schema_version = 1`；
- existing `sql/safety/result_view/chart/markdown/error/...` ID 保持不变并定义为 schema v1；
- `Artifact.version` 继续表示 semantic-key work-product version，绝不复用为 payload schema version；
- 兼容读取旧 snapshot/wire 时，**只有已知 legacy type 缺少 `schema_version` 才按 v1 处理**；
- unknown historical type/version 保留 metadata/envelope 并 fallback，不猜 schema；
- compatibility window 内 built-in producer 可由 boundary 补 v1，cutover 后新 Extension write 必须显式提供 schema_version；
- unknown new write reject；
- current relations、payload aliases、batch prepare-before-write algorithm 保持。

不建立 `type → type_id → legacy mapper` 双字段长期兼容。

### 6.2 PR：frontend compatible read

Wire 入口变为：

```text
type: string
schema_version: number
payload: object
```

已知 renderer 根据 `(type, schema_version)` 严格 parse；unknown 使用 metadata fallback。现有业务 View 可以继续保留 typed local model，不要求所有 React 内部都变成 `unknown`。

### 6.3 PR：Completion constraint

保持 Completion Core 的 lifecycle/pending work/answer/citation ownership/budget 逻辑，只抽：

```text
DataResultCitationConstraint
```

使用 immutable tuple composition，不建 RuleManager。现有 Completion decision 与 evidence Artifact IDs 必须 parity。

### 6.4 Semantic capability

Registry/Observation 接口从 closed enum 放宽到 validated string，但 legacy IDs 原样保留；新 capability ID 使用 namespace。不在 P3 批量 rename 已参与 materialization/history 的 ID。

## 7. P4 — Workbench Shell V2

详细阶段见 [Workbench Shell 迁移规范](./workbench-shell-migration-guide.md)。

约束：

- 使用真实 Project model/list/create API；
- `Project != Datasource`；
- current Conversation 仍 datasource-bound；
- Project Edit 若进入范围，先补独立最小 backend update contract；
- Main Surface 固定显式，不 Registry 化；
- Dock View / Artifact Renderer 才是开放 registry；
- ShellStore 只保存 identity/layout；
- SQL state project-keyed；
- Dock canonical key 不使用递增 counter；
- 小规模 views 优先单一数组，不维护双索引 truth；
- Navigation facade 有删除条件。

Gate：

- Conversation/SQL/Table/MultiTable/Artifact/Project/Datasource/Settings parity；
- Project switch restore；
- same canonical target dedup；
- no business payload in ShellStore；
- no central Dock domain switch；
- legacy `openXxxTab()` 在删除阶段归零。

## 8. P5A — Workspace resource substrate

P5A **不创建 model-visible File Tool**。先建立第二种真实执行资源本身，使 P5B 可以基于真实代码而不是 mock/猜测抽象。

实现：

```text
WorkspaceRoot / WorkspaceIdentity
canonical relative path
path normalization policy
symlink/reparse-point policy
bounded file-read service
file version/hash function
platform contract tests
```

要求：

- service 输入/输出是普通 typed domain value；
- 不依赖 Agent RunLoop、Tool Registry 或 Prompt；
- 不绕过 workspace root；
- 不写文件；
- 不建立通用 FilesystemManager/ResourceManager。

Gate：Database resource 和 Workspace read service 都是可运行真实实现。

## 9. P5B — 从 Database + Workspace 提炼 execution resource seam

此时才提炼最小公共边界：

```text
ToolInvocationContext
ResourceScopeRef(kind, id, version)
minimum resource resolver
immutable resource authorization value（仅在现有 ExecutionAuthority 不足时）
```

`ToolInvocationContext` 初始上限：

```text
session_id
run_id
turn_id
invocation_id
idempotency_key
deadline_at
scope_refs
```

除非 Database + Workspace 两个真实实现证明必要，不增加 `project_id`、DB-only `execution_id`、arbitrary metadata bag、authority_ref 或 grant-id lookup 链。

Gate：

- current DB Tool behavior/materialization parity；
- Workspace read service 可通过同一 scope/resolver boundary 获取授权资源；
- Tool/handler 看不到 global service container；
- execution resource object/Secret 不进入 durable invocation JSON。

## 10. P6 — Serializable Attempt Request + isolated runner

现有 `ToolExecutor` 继续拥有 retry、overall deadline、scope concurrency、attempt accounting 和 recovery decision。新的 Strategy 只决定“一次 attempt 在哪里执行”。

### 10.1 PR：定义 serializable ToolAttemptRequest

**不要把 Python callable/closure 作为 AttemptRunner contract。** closure 捕获的 SQLAlchemy Session、request、authority 等无法成为稳定 worker wire。

最小概念模型：

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

`ExecutionResourceGrant` 只在 P5B 证明需要时存在；否则 request 使用 scope refs + 现有 authority 能表达的最小值。

父进程的 `ToolExecutor` 仍是 deadline authority；`attempt_timeout_ms` 是给 attempt/worker 的相对上限，不能反向延长父级 deadline。

### 10.2 PR：共享 ToolAttemptHandler

建立一个内部 handler：

```text
ToolAttemptRequest
→ verify frozen Tool contract
→ resolve authorized resources
→ ToolRuntime.execute/reconcile
→ ToolResult
```

In-process 与 isolated worker 调**同一个 handler 语义**，避免两套 Tool execution contract。

### 10.3 PR：InProcessAttemptRunner extraction

InProcess runner 接受 `ToolAttemptRequest`，在当前 executor-owned thread 中调用 handler；保留现有 stuck-thread quarantine/retired pool 行为，确保 parity。

### 10.4 PR：worker protocol + IsolatedProcessAttemptRunner

Wire 只发送 serializable request/result：

```text
protocol version
ToolAttemptRequest
heartbeat/cancel channel
ToolResult / bounded diagnostics
worker exit status
```

Worker 不接收 Python closure、SQLAlchemy Session、HTTP client 或 application container。

必须：

- protocol/schema handshake；
- worker current Tool contract 与 frozen version 校验；
- heartbeat；
- parent→worker cancel；
- process group/tree kill；
- frame/stdout/stderr limits；
- malformed result rejection；
- late result suppression；
- worker crash → fixed runtime error/UNKNOWN semantics；
- Windows/macOS/Linux contract tests。

Gate：

- current in-process parity；
- isolated crash/timeout/cancel/late result；
- executor saturation/cleanup；
- retry/reconcile loop 仍只有 ToolExecutor 一个 owner；
- no hostile-code sandbox claim。

## 11. P7 — Workspace read-only vertical slice + Context contribution seam

### 11.1 File vertical slice

```text
file_read / file_search
→ Workspace resource seam
→ strict Tool output
→ Observation + FileSnapshot Artifact
→ Workspace reducer/projection
→ next Run bounded Context
→ File Dock View
```

P7 验证：

- 不允许 `ContextSnapshot.file_context`；
- 不允许 RunLoop `if tool == file_read`；
- 不允许 Artifact Core `if type == code_file`；
- 不允许 Dock Kernel `if viewType == file`。

Workspace projector 可以理解自己拥有的 Tool/Observation，但 Kernel 不理解 Workspace Tool name。

### 11.2 从 Catalog + Workspace 提炼最小 Context fragment seam

只有现在两个真实跨 Run Context 来源都存在，才允许抽最小接口。不要建立万能 Context Plugin Framework。

概念合同：

```python
class ContextFragment(BaseModel):
    source_id: str
    source_version: str
    lane: ContextLane
    content: str
    provenance: dict[str, JsonValue]
```

```python
class ContextContributor(Protocol):
    id: str
    def build(self, input: ContextContributionInput) -> tuple[ContextFragment, ...]: ...
```

约束：

- `ContextLane` 由 Kernel 定义并 allowlist，例如 working-state/resource/evidence；
- contributor **不能**指定 system role、最终 priority、token budget 或 Provider wire；
- Kernel 把非系统 fragment 统一当作 bounded/untrusted data 包装；
- fragment 有 item/byte/token 上限；
- provenance/source version/freshness fence 必须可审计；
- contributor 不能把 rows、完整文件、完整 Schema、长日志或 Secret 放入 Context；
- budget planner / Prompt assembler 是唯一 Provider-input owner；
- 初版可使用启动时 immutable tuple，不建 ContextManager。

Catalog 的现有 renderer 和 Workspace renderer 在该 PR 迁入同一 fragment seam，并保持模型可见内容 parity。

## 12. P8 — Patch write with CAS

```text
file_write_patch
→ authorized workspace root
→ expected file hash/version CAS
→ write temp sibling
→ flush/fsync where applicable
→ atomic replace
→ CodePatch Artifact
→ Workspace projection
→ Diff View
```

必须：

- path canonicalization；
- symlink/reparse defense；
- CAS conflict；
- bounded patch；
- no silent overwrite；
- crash/reconcile/unknown；
- platform-specific atomic-replace contract tests。

## 13. P9 — Terminal / external binding / Remote Job pattern

只在有真实 use case 时实现，不预建 universal provider framework。

### 13.1 Command-backed Tool

固定 executable + fixed/allowlisted operation + structured argv + versioned parser。禁止 model-authored shell string 直接 `shell=True`。

### 13.2 Generic Terminal

独立高风险 Tool，用于 coding/build/test/排障；不成为 API/MCP/CLI 的万能 fallback。

### 13.3 API/MCP

第一个真实平台接入时再抽最小 Binding Strategy。MCP 必须 admission/allowlist/materialization；API/MCP/Command 都复用同一 Tool settlement/recovery。

### 13.4 Remote Job / long-running resource

Spark、Flink、Airflow、Kubernetes Job、ML training 等长任务禁止通过一个长挂 ToolInvocation 维持生命周期。

统一语义：

```text
submit Tool
→ bounded submission Observation
→ durable RemoteJobRef
→ Run 可以正常 terminal

later Run
→ status/read/cancel Tool(RemoteJobRef)
→ Observation
→ optional Result/Report/Model/Dataset Artifact
→ capability-owned Projection / Context fragment
```

`RemoteJobRef` 是逻辑稳定引用，不要求现在建立通用 RemoteJob table：

```text
provider/capability ID
resource kind
external job/resource ID
submission provenance
contract/schema version
resource scope/version when applicable
```

第一个真实集成可以把它放在 capability-owned Artifact payload 或该 capability 已经需要的 canonical record 中。只有两个真实 provider 都证明需要独立可变 job aggregate 时，才评审通用 Remote Job persistence。

不变量：

- Run lifetime != Remote Job lifetime；
- ToolInvocation lifetime != Remote Job lifetime；
- 不把 credential、完整 logs 或远程大结果放进 RemoteJobRef；
- status/result freshness 由 provider/capability 自己的 version/fence 表达；
- RemoteJobRef 可以通过 Projection/Context 暴露“当前有哪些相关工作”，但不能成为执行 authority。

P9 不实现 universal MCP marketplace 或 generic external-provider meta-runtime。

## 14. P10 — 第二个 materially different capability-family proof

P10 不是多一个相似 Tool demo，而是验证 capability-family 模型没有退化成 Tool-only。

在 Data + Workspace 已存在后，选择一个形态明显不同的真实能力，例如 Remote Job、GitHub external resource 或 ML deployment，按实际需要贡献其子集：

```text
Tool(s) optional
Resource reference(s) optional
Artifact(s) optional
Projection optional
Context contributor optional
Completion constraint optional
Workbench contribution optional
```

它不需要为了“完整”实现全部 contribution。

必须证明：

- 不修改 RunLoop 领域 branch；
- 不给 ContextSnapshot 增 `github_context/spark_context/ml_context/...`；
- 不修改 Completion Core lifecycle；
- 不修改 Artifact Core central type switch；
- 不修改 Dock Kernel domain switch；
- 若是长任务，不长挂 ToolInvocation；
- 若需要跨 Run Context，通过同一 bounded ContextFragment/lane/budget seam；
- 若需要外部执行，复用 Tool materialization/Policy/Attempt/Observation/Artifact/recovery。

任一条件失败，暂停该功能，回到 seam review；不得用新的 Mapper/Manager/Kernel `if` 掩盖边界错误。

## 15. PR 设计检查表

每个实现 PR 在 description 回答：

1. 当前真实问题是什么？
2. 最小改动是什么？
3. 新抽象有几个真实使用者？
4. 是否新增第二份 identity/state/hash？
5. 是否引入 DTO/Mapper 只为字段搬运？
6. identity/key/order/bounds/eviction/freshness 是什么？
7. canonical transaction owner 是谁？derived failure 如何处理？
8. incremental/catch-up/rebuild 是否同一算法？
9. fail/cancel/recovery 的 owner 是谁？
10. 跨进程边界传的是 serializable value 还是 Python object/closure？
11. Context contributor 是否试图控制 role/priority/budget/Prompt？
12. compatibility path 什么时候删除？

## 16. Rollback 原则

每个兼容路径在对应 PR description 中指定负责人；删除条件必须包含可观察证据和期限，不能只写“稳定后删除”。

| 兼容路径 | 负责模块 | 删除条件（可观察） | 期限 |
| --- | --- | --- | --- |
| P1 `register_dbfox_tools()` facade | Agent Runtime / Tool Registry | 所有生产组合调用点迁到 owner-scoped 注册函数；反向 grep/import 测试证明旧 facade 无新增调用；materialization parity 测试绿色 | P1 合入后的下一个 PR |
| P2 v3 Memory + v4 shadow | Agent Runtime / Memory | v4 Context flag 连续稳定窗口无回归；incremental/catch-up/full rebuild hash 一致；failed/cancelled continuity 场景通过；切回演练成功 | 稳定窗口结束后一个版本内删除 v3 写入 |
| P3 legacy Artifact 缺省 v1 | Artifact / API | 不再有 built-in producer 写入缺 `schema_version` 的新记录；unknown legacy 只读兼容保留，不新增双 schema 写路径 | cutover 后一个版本 |
| P4 Navigation facade | Frontend Shell | 所有 `openXxxTab()` callsite 迁完；反向 import/grep 测试证明归零；WorkspaceTabs/Router 旧分支删除 | 入口 cutover 完成后下一个 PR |
| P5/P6 旧 in-process DB path | Agent Runtime / Tool Execution | 新 resource seam + AttemptRunner parity 与平台合同测试全绿；isolated runner 故障矩阵通过；旧路径无新增调用 | P6 gate 通过后一个版本 |
| P7 旧 Catalog renderer | Agent Context | Catalog + Workspace 两个真实 contributor 通过同一 fragment seam，模型可见内容 parity；旧 renderer 无新增调用 | P7 gate 通过后一个版本 |

禁止长期双写/双事实源。Rollback window 结束必须删除兼容路径；逾期未删的路径按技术债进入下一迭代，不静默续期。

## 17. 最终完成定义

只有同时满足以下条件才算这轮架构实施成功。

### Context

- completed/failed/cancelled 中 succeeded work 跨 Run 连续；
- derived projection failure 不阻止 canonical terminalization，且 watermark/catch-up 可证明；
- stale generation/revision/resource version 不误用；
- Memory bounded/rebuildable/non-authoritative；
- Catalog 与 Workspace 通过统一 bounded fragment seam 进入 Context；
- prior digest/fragment 有 canonical provenance；
- 新 capability 不扩张 ContextSnapshot 领域根字段。

### Runtime capability

- Database/File/Terminal/API/MCP 使用同一 durable Tool lifecycle；
- Remote Job 使用 durable ref + 后续 Run 查询，不长挂 Invocation；
- execution resource boundary 来自 Database + Workspace 两个真实案例；
- isolated attempt 使用 serializable request，不序列化 closure/application object；
- retry/recovery orchestration 只有 ToolExecutor 一个 owner；
- materially different capability family 可只贡献所需子集，不被迫变成 Tool-only。

### Artifact / compatibility

- legacy Artifact v1 可读；
- `Artifact.version` 与 `schema_version` 含义不混淆；
- unknown historical type/version fail-soft；
- new type/schema strict validation；
- frozen Tool/materialization/reconcile/UNKNOWN 语义保留。

### Frontend

- Project/Datasource ownership 真实；
- Shell/Main/Dock/Settings 边界明确；
- ShellStore 无业务事实；
- new View/Renderer registration 不改 central domain switch。

### Design quality

- 没有为了对称性存在的空抽象；
- 没有长期 Mapper/Adapter 链；
- 没有重复 fingerprint/identity/state；
- reducer、dedup、eviction、catch-up、CAS、Remote Job lifecycle 算法确定、有界、可测试。
