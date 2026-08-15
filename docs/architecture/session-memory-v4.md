# Session Memory v4 与跨 Run 工作连续性

> 文档类型：ADR
>
> 状态：已接受
>
> 最后核验：2026-08-16
>
> 基线：`main@daa99d048decd7f5f8dc010cbe5465f332686a3c`
>
> 上位 RFC：[DBFox 可扩展 Runtime 与 Workbench 架构计划](./extensible-runtime-workbench-program.md)

## 1. 决策

将当前 `AgentSessionMemory` v3 演进为 typed、bounded、deterministically rebuildable 的 Memory v4，首先解决 Catalog/Schema 工作跨 Run 丢失的问题。

Memory v4 第一版只实现 Catalog Projection，直接从 canonical `ToolInvocation + Observation + Artifact references + Run` 归约。

**P0 不增加 Session Effect storage/registry。** 当前 durable Invocation/Observation 已经保存 search/inspect/refresh 归约所需的信息，再写一份 Effect 会复制事实。

Memory 不是事实源、执行恢复状态、Tool Cache 或模型自由书写的长期记忆。

## 2. 当前真实问题

当前 Memory v3 主要在 successful completion path 更新；failed/cancelled Run 不会得到等价的 Session Memory consolidation。

因此下面这种 Run：

```text
schema_search     succeeded
schema_inspect    succeeded
later provider failure / user cancel
```

下一 Run 仍可能重新 overview/search/inspect。

目标不是把更多历史文本塞进 Prompt，而是保存**已经完成工作的有界 footprint 和 provenance**，后续再按需回 canonical Observation。

## 3. 四层边界

```text
1. Canonical durable state
   Message / Run / Turn / Invocation / Observation
   Artifact / Evidence / Plan

            ↓ pure reducer

2. Session Memory v4
   bounded cross-Run working-state projection

            ↓ bounded rehydration

3. ContextSnapshot
   frozen provider-neutral candidate state

            ↓ budget / render

4. Prompt / Provider input
   actual model-visible input
```

删除 Memory 不得删除事实，也不得影响同 Run crash recovery。

## 4. Memory envelope

第一版使用：

```python
class SessionMemoryStateV4(BaseModel):
    schema_version: Literal[4] = 4
    core_policy_version: int
    projected_through_session_sequence: int
    core: SessionMemoryCore
    projections: tuple[SessionProjectionEnvelope, ...]
```

不保存全局 `state_projection_registry_fingerprint`。每个 Projection 自己拥有 compatibility contract；新增无关 Projection 不应使已有 Catalog projection 失效。

Core：

```python
class SessionMemoryCore(BaseModel):
    referenced_artifact_ids: tuple[str, ...] = ()
    runtime_evidence_references: tuple[EvidenceReference, ...] = ()
    advisory_open_questions: tuple[str, ...] = ()
```

`selected_artifact_id` 仍由 Session aggregate / admitted input 所有，不复制到 Memory。

Artifact reference 只属于 Core，不再在 Catalog projection 保存第二份 `referenced_artifacts`。

## 5. Projection envelope

每个 Projection 只保留真正影响兼容性的维度：

```python
class SessionProjectionEnvelope(BaseModel):
    extension_id: str
    projection_id: str
    schema_version: int
    contract_fingerprint: str
    projected_through_session_sequence: int
    state_hash: str
    scope: JsonObject
    state: JsonObject
```

`contract_fingerprint` 已经覆盖 reducer/policy/schema contract，不再单独持久化 `projector_version` 和 `policy_version` 形成额外迁移轴。

内部实现必须在序列化前先验证成对应 projection 的 typed scope/state；通用 envelope 的 dict 只是 JSON persistence boundary，不是业务层裸 dict API。

## 6. Catalog revision

新增：

```text
DataSource.catalog_revision
```

语义：DBFox 本地 Catalog/Search Surface 的发布版本。

区别：

```text
connection_generation
  connection metadata / credential profile generation

catalog_revision
  search-visible local catalog publication generation
```

任何改变下列 Tool 可见结果的成功 publication 都 bump：

- Catalog authoritative sync；
- SearchDoc rebuild；
- AI enrichment 对 search-visible metadata 的发布；
- 未来用户修改 search-visible metadata。

失败 mutation 不 bump。

### 6.1 事务原则

`catalog_revision` 与对应 search-visible publication 必须由**同一个短事务**提交。

现有 AI enrichment 有内部 commit/rollback 行为，实施 `catalog_revision` 前必须先把 transaction ownership 收敛为 caller-owned publication boundary。

LLM enrichment 不应持有一个长写事务。推荐：

```text
read canonical schema snapshot/hash
→ transaction ends
→ call LLM
→ begin short write transaction
→ re-check expected schema hash/generation
→ write enrichment + SearchDoc
→ atomic catalog_revision = catalog_revision + 1
→ commit
```

这样不会在远程模型等待期间长期占用写事务，也不会把旧 schema 的 enrichment 发布到新 catalog。

`catalog_revision` bump 使用数据库原子 update，不使用无锁 Python read-modify-write。

### 6.2 Observation 必须冻结执行时 revision

Catalog Tool 在执行时读取与其结果一致的 `catalog_revision`，并把 revision 写入 Tool output/Observation facts。

禁止在 Run terminal 时读取“当前 revision”再倒填旧 Observation。

## 7. Catalog Working State

第一版持久状态收敛成两个主要集合：

```python
class CatalogWorkingState(BaseModel):
    orientation: CatalogOrientation | None = None
    searches: tuple[SearchFootprint, ...] = ()
    objects: tuple[CatalogObjectState, ...] = ()
```

而不是分别维护 searches / candidates / inspections 三套相互引用的集合。

### 7.1 Stable object key

沿用当前 Catalog search 已使用的 canonical identity 思路：

```python
class CatalogObjectKey(BaseModel):
    kind: Literal["table", "column"]
    schema_name: str
    table_name: str
    column_name: str = ""
```

不为 projection 生成新的 UUID。

### 7.2 Object state

```python
class CatalogObjectState(BaseModel):
    key: CatalogObjectKey
    first_seen_observation_id: str
    last_seen_observation_id: str
    last_inspected_observation_id: str | None = None
    last_source_sequence: int
    catalog_revision: int
```

这里只保存 footprint/provenance，不复制完整 columns/indexes/FK/search score/aliases。

Search query 保存在 `SearchFootprint`，并从 Invocation authorized input 读取；候选对象只保存 canonical key。

## 8. Catalog reducer

Reducer 是纯函数，同一实现同时服务 terminal incremental fold 和 full rebuild。

概念接口：

```python
def fold_catalog(
    state: CatalogWorkingState,
    *,
    scope: CatalogProjectionScope,
    invocation: CatalogInvocationRecord,
    observation: CatalogObservationRecord,
) -> CatalogWorkingState:
    ...
```

只处理 `Observation.status == succeeded`。

### 8.1 增量算法

Terminal Run 的 Observation 按 durable sequence 升序处理：

```text
for succeeded observation in terminal Run:
    read observation execution-time catalog_revision
    if revision/generation/datasource differs from active scope:
        reset revision-scoped Catalog state
    dispatch by registered catalog reducer semantics
    merge searches / object footprints
trim to policy bounds
canonical sort
hash
persist
```

Reducer 可以按 Tool name/version 识别现有 built-in Catalog Tool，但该识别只存在于 **Data-owned projector**，不进入 Kernel。

内部 merge 使用临时：

```python
objects_by_key: dict[CatalogObjectKey, CatalogObjectState]
```

这是 O(1) merge 的数据结构，不是第二个持久模型。

### 8.2 Eviction

Policy v1：

```text
searches <= 12
objects  <= 32
advisory questions <= 8
runtime evidence refs <= 32
```

Object 超限时稳定排序优先保留：

1. 有 live inspection provenance 的对象；
2. `last_source_sequence` 更新较新的对象；
3. canonical object key 作为稳定 tie-breaker。

然后保留前 32。

Search 只保留最新 12，按 source sequence + observation ID 稳定排序。

最终持久化 tuple 使用稳定顺序；不能依赖 dict insertion、wall clock、random 或未排序 SQL query。

## 9. 哪些 Run 被归约

所有 terminal Run：

```text
completed
failed
cancelled
```

都调用同一个 Session Memory projection service。

基础规则：

- 只 fold succeeded Observation；
- unknown/failed/cancelled/rejected Observation 不记为完成工作；
- SQL execution authority / Approval grant / Safety capability 不进入跨 Run Memory；
- Result Artifact 只在 Core 保存 reference；
- 模型自然语言 claim 不直接进入确定性 Working State。

同一 terminal Run 重复 apply 必须幂等。水位线使用 `projected_through_session_sequence`；同一个 sequence 不重复 fold。

## 10. Terminal transaction

目标 transaction：

```text
settle active durable children
→ stage terminal Run/Plan/Message/Evidence state
→ load current Memory row under lock
→ apply same pure reducers for this Run
→ upsert Memory v4
→ append terminal Event
→ commit
```

Memory update 与 Run terminal publication 处在同一个 application transaction。

如果 Memory projection 失败，terminal transaction 回滚，而不是提交 Run terminal 后留下 projection gap。

同 Run recovery 仍只依赖 Run/Turn/Invocation/Observation/Approval/Question/Plan/lease，不依赖 Memory。

## 11. Full rebuild

Full rebuild 只用于：

- migration；
- compare；
- repair；
- projection contract upgrade；
- debug。

算法：

```text
read Session scope
→ iterate terminal Runs by session_sequence
→ for each Run load canonical Invocation + Observation + Artifact refs
→ call the same reducer used by incremental fold
→ canonical serialize/hash
```

复杂度：

```text
incremental: O(current terminal Run canonical tool records + bounded state)
full rebuild: O(Session canonical tool records)
```

不能让每次 terminal Run 扫描整个 Session。

## 12. Prior Observation digest

Memory footprint 只说明“哪些工作做过”，不复制 Schema facts。

ContextAssembler 在构建下一 Run 时：

```text
read active Catalog projection
→ fence datasource / connection_generation / catalog_revision
→ select <= 8 relevant object footprints deterministically
→ fetch canonical Observation by ID
→ build bounded digest
```

第一版不使用 embedding/LLM 选择 prior Observation。

优先级：

1. admitted workspace/current resource 明确引用的 object；
2. 当前 request 明确包含 canonical object identity 或 prior search query 的对象；
3. 最近有 live inspection provenance 的对象；
4. stable key tie-breaker。

没有相关 footprint 时宁可不注入，也不“智能猜”。

Digest 可包含：

- canonical object identity；
- bounded key columns；
- primary key；
- bounded related object identity；
- observed_at；
- source Observation ID；
- freshness warning。

限制：

```text
prior digest objects <= 8
columns per object    <= 12
digest serialized facts <= 16 KiB
rendered Session Working State <= 2,000 estimated tokens
```

## 13. Context integration

`ContextSnapshot.session_memory` 从 raw dict 迁为 typed context-facing model，但不把 persistence envelope 原样 dump 进 Prompt。

渲染分为：

```text
SESSION_WORKING_STATE
SESSION_EVIDENCE_INDEX
```

当前 Run native function-call/output transcript 与跨 Run Memory 分开预算，避免同一 observation 重复进入多个 lane。

## 14. Result / Evidence / selected Artifact

保持：

- selected Artifact owner 仍是 Session aggregate / admitted input；
- runtime Evidence references 在 Memory Core 只保存 bounded provenance ref；
- Result Artifact 可跨 Run 引用，但 rowset 不进入 Memory；
- SQL validation/Safety/Approval/ExecutionAuthority 不跨 Run。

## 15. Migration

采用 shadow migration：

```text
add catalog_revision
fix Catalog publication transaction ownership
add Memory v4 storage metadata
keep v3 current path
terminal path compute v4 shadow with canonical reducer
compare incremental vs full rebuild
v4 not yet injected into Prompt
cut Context read path behind flag
stop writing v3
remove compatibility after rollback window
```

**不增加 Effect storage 作为 migration prerequisite。**

推荐 Memory row metadata：

```text
schema_version
core_policy_version
projected_through_session_sequence
state_hash
updated_at
```

用于 lag/repair 检查，不必每次解析整个 JSON。

## 16. 验收

必须覆盖：

- completed schema-only continuation；
- failed Run 中 succeeded search/inspect；
- cancelled Run 中 succeeded inspect；
- unknown outcome exclusion；
- exact duplicate Catalog calls 降低；
- catalog revision invalidation；
- AI enrichment publication invalidation；
- connection generation invalidation；
- negative search 语义不夸大；
- prior Observation digest；
- Result Artifact continuation；
- selected Artifact 单一所有者；
- 100 Run boundedness；
- delete/rebuild；
- incremental/full rebuild equality；
- missing Projector strict/degraded/migration。

真正的成功标准是：**下一 Run 能继续已经成功完成的工作，同时 stale work 会可靠失效；不是仅仅新增了一张 Memory 表。**
