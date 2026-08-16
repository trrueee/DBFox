# Session Memory v4 Projection 实施合同

> 文档类型：Memory v4 ADR 附录 / 实施合同
>
> 状态：已接受
>
> 最后核验：2026-08-16
>
> 基线：`main@daa99d048decd7f5f8dc010cbe5465f332686a3c`
>
> 关联 ADR：[Session Memory v4 与跨 Run 工作连续性](./session-memory-v4.md)

## 1. 目标

本合同把 Memory v4 约束成一个小而确定的状态投影：

- 输入只来自 canonical durable records；
- incremental、lag catch-up 和 full rebuild 使用同一 reducer；
- 所有集合有硬上限；
- identity、merge、eviction、排序和 hash 都确定；
- P0 不增加 Session Effect；
- Context 按 footprint 回 canonical Observation，不复制完整事实；
- derived projection failure 不阻止 canonical Run terminalization。

## 2. Projection envelope

```python
class SessionProjectionEnvelope(BaseModel):
    extension_id: str
    projection_id: str
    schema_version: int
    contract_fingerprint: str
    projected_through_session_sequence: int
    state_hash: str
    scope: dict[str, JsonValue]
    state: dict[str, JsonValue]
```

第一版：

```text
extension_id = dbfox.data
projection_id = dbfox.catalog.working_state
```

`scope/state` 只在 persistence envelope 是 JSON object。Projector 内部必须使用 typed model，禁止业务代码直接读写裸 dict。

不保存：

```text
projector_version
policy_version
state_projection_registry_fingerprint
```

这些兼容信息统一进入 `contract_fingerprint`。

## 3. Catalog scope

```python
class CatalogProjectionScope(BaseModel):
    datasource_id: str
    datasource_generation: int
    catalog_revision: int
```

Scope 任一字段变化，旧 Catalog state 都不能作为 current knowledge。

## 4. Catalog state

```python
class CatalogWorkingState(BaseModel):
    orientation: CatalogOrientation | None = None
    searches: tuple[SearchFootprint, ...] = ()
    objects: tuple[CatalogObjectState, ...] = ()
```

Catalog 不保存 Artifact references；Artifact refs 属于 Session Memory Core。

### 4.1 Object key

```python
class CatalogObjectKey(BaseModel):
    kind: Literal["table", "column"]
    schema_name: str
    table_name: str
    column_name: str = ""
```

canonical tuple：

```text
(kind, schema_name, table_name, column_name)
```

与当前 Schema Search candidate dedup 思路一致，不生成 projection-only UUID。

### 4.2 Search footprint

```python
class SearchFootprint(BaseModel):
    invocation_id: str
    observation_id: str
    input_hash: str
    queries: tuple[str, ...]
    candidate_keys: tuple[CatalogObjectKey, ...]
    returned_count: int
    catalog_revision: int
    source_sequence: int
```

Query 来自 Invocation authorized input；Observation 不需要再复制 query。

### 4.3 Object footprint

```python
class CatalogObjectState(BaseModel):
    key: CatalogObjectKey
    first_seen_observation_id: str
    last_seen_observation_id: str
    last_inspected_observation_id: str | None = None
    last_source_sequence: int
    catalog_revision: int
```

不保存：

- full columns；
- indexes；
- FK detail；
- comments；
- aliases；
- score/reasons；
- Tool output copy；
- rows/series。

## 5. Projector 输入

P0 读取：

```text
AgentRun.session_sequence
AgentToolInvocation.tool_name / tool_version
AgentToolInvocation.authorized input / input_hash
AgentObservationRecord.status / facts / artifact refs / sequence
```

Catalog Tool 必须在 Observation facts 中冻结执行时 `catalog_revision`。

Reducer 不读：

- 当前 wall clock；
- Prompt wording；
- LLM；
- embedding；
- live Tool reexecution；
- 当前 datasource catalog 状态来“修正”历史 Observation。

## 6. Reducer dispatch

Kernel 不理解 Tool name。Data-owned Catalog projector 可以对自己拥有的 built-in Catalog Tool 做明确 dispatch：

```text
catalog_overview
catalog_refresh
schema_list
schema_search
schema_inspect
```

dispatch 必须同时验证 Tool contract/version compatibility；未知版本不能猜兼容。若该输入不能被当前 projector 解释，projection attempt 失败并保持 watermark，不得把 canonical Run 变回非 terminal。

未来若 Data Tool 改名或拆分，由 Data projector 自己升级 contract fingerprint / rebuild，不修改 Kernel reducer。

## 7. Fold 算法

### 7.1 单个 terminal Run fold

输入是一个 terminal Run 中的 settled canonical records：

```text
decode typed projection
→ iterate Run observations by durable sequence ASC
→ fold succeeded eligible observations
→ trim bounded collections
→ canonical sort
→ canonical serialize + hash
```

只有整个 candidate 通过 typed validation 后才允许写 Memory row / watermark。

### 7.2 Revision transition

对每个 eligible Observation：

```text
obs_scope = datasource_id + datasource_generation + observation.catalog_revision
```

如果 `obs_scope != current projection scope`：

- 清空 revision-scoped orientation/search/object state；
- 切到该 Observation scope；
- 再 fold 当前 Observation。

这样同一个 Run 内 `catalog_refresh → search → inspect` 可以自然切换到新 revision，不需要 terminal 时读取当前 revision 猜测。

### 7.3 Search merge

`schema_search`：

1. 从 authorized input 读取 queries；
2. 从 succeeded Observation facts 读取 bounded candidates；
3. candidate 转 canonical `CatalogObjectKey`；
4. 追加 SearchFootprint；
5. 对每个 candidate upsert ObjectState。

内部临时结构：

```python
objects_by_key: dict[tuple[str, str, str, str], CatalogObjectState]
```

每个 candidate merge 是均摊 O(1)。

### 7.4 Inspect merge

`schema_inspect`：

1. 从 authorized input / succeeded facts 获取 inspected target；
2. target canonicalize 为 ObjectKey；
3. upsert object；
4. 更新 `last_inspected_observation_id` 和 `last_source_sequence`。

完整 inspection detail 仍留在 canonical Observation。

### 7.5 Overview / list / refresh

- overview：只更新 bounded orientation provenance；
- schema_list：可将返回对象作为 seen object，但不保存完整 table summary；
- refresh：记录新 revision orientation，并使旧 revision working state 失效；
- result/profile Tool 不进入 Catalog projection。

## 8. Bound 与 eviction

Policy v1：

```text
searches              <= 12
objects               <= 32
core artifact refs    <= 24
advisory questions    <= 8
runtime evidence refs <= 32
```

### 8.1 Search eviction

排序：

```text
(source_sequence DESC, observation_id ASC)
```

保留前 12；持久化时按 `(source_sequence, observation_id)` ASC 输出。

### 8.2 Object eviction

候选排序用于决定保留集合：

```text
has_inspection DESC
last_source_sequence DESC
canonical_object_key ASC
```

保留前 32。

最终持久化按 canonical object key ASC 排序，保证相同逻辑集合得到相同 JSON/hash。

## 9. Watermark、幂等与 catch-up

`projected_through_session_sequence` 表示**已经成功通过当前 projection contract 归约的连续 terminal prefix**。

规则：

- `run.session_sequence <= watermark`：no-op；
- 健康路径下当前 terminal Run 应为 `watermark + 1`；
- watermark 落后时，从 `watermark + 1` 开始按 Session sequence catch up；
- 每个 sequence 都调用与正常增量完全相同的 fold；
- 遇到未 terminal/missing sequence，停止在 gap 前；
- projection 计算/validation 失败，整个 candidate 丢弃，watermark 不变；
- 绝不因为“当前 Run 已 terminal”就把 watermark 跳过中间 gap。

Object merge 本身还以 canonical key + Observation ID 保持幂等。

正常复杂度：

```text
O(current terminal Run records + bounded state)
```

存在 lag 时：

```text
O(records in catch-up gap + bounded state)
```

## 10. Full rebuild

```python
rebuild_session_memory(
    session_id,
    *,
    mode: Literal["strict", "compare", "repair"],
) -> RebuildResult
```

算法：

```text
empty typed Memory v4
→ terminal Runs by session_sequence ASC
→ load each Run canonical Invocation + Observation + Artifact refs
→ call EXACT SAME fold functions as incremental/catch-up
→ canonical serialize/hash
```

禁止实现另一套 `rebuild_catalog_from_history()` merge 逻辑。

Modes：

- `compare`：只比较，不写；
- `strict`：缺 projector/contract 时 incomplete；
- `repair`：仅 strict complete + 显式运维请求时覆盖。

相等条件：

```text
same canonical records + cutoff
same memory schema/core policy
same projection contract_fingerprint
→ same canonical state_hash
```

Catch-up 到相同 cutoff 也必须满足同一等价条件。

## 11. Contract fingerprint

Fingerprint 只包含会改变该 projection state 解释的内容，例如：

```text
projection schema version
eligible Tool contract/version set
canonicalization rules
merge rules
eviction/bounds policy
```

不包含：

```text
frontend renderer
Tool title/presentation
external endpoint
credential identity
unrelated Extension
```

Tool materialization 的整 Tool hash 不能直接作为 fingerprint，因为其中包含 title/presentation/description，UI 文案变化会错误触发 Memory rebuild。
fingerprint 只能取与 Projection 解释相关的字段子集：Tool name/version、input/output schema、execution、policy、semantics 中会影响 reducer 解释的字段。实现上复用 `MaterializedTool` 已经暴露的合同字段做 canonical hash 输入，不复制第二套 schema-hash 算法；presentation 类字段明确排除。

## 12. Context rehydration

ContextAssembler 先做 read-time fence：

```text
datasource ID
datasource generation
catalog revision
```

不匹配则整个 Catalog working state 不进入 current Prompt。

Projection lag 表示可能缺少较新的 working-state，并不授权使用 stale scope；revision/generation fence 始终优先。

### 12.1 Prior digest selection

第一版不使用 LLM/embedding。

选择最多 8 个对象：

1. admitted workspace/resource context 明确引用的 canonical object；
2. current request 明确命中 object identity 或 prior search query；
3. 最近有 `last_inspected_observation_id` 的对象；
4. canonical key 稳定 tie-breaker。

选中后按 Observation ID 回源 canonical facts，生成 bounded digest。

### 12.2 Digest bounds

```text
objects <= 8
columns/object <= 12
related objects/object <= 8
serialized digest facts <= 16 KiB
rendered session working state <= 2,000 estimated tokens
```

Digest 必须标注：

- source Observation；
- observation time（如果 canonical record 有）；
- datasource generation；
- catalog revision；
- freshness note。

Digest 不持久化为第二事实源。

## 13. Canonical transaction / derived projection boundary

Run terminal state 与 Memory 不具有相同权威性。

推荐实现顺序：

```text
stage canonical terminal records
→ load Memory/watermark
→ compute catch-up candidate in memory
→ validate complete candidate
→ success: stage Memory upsert
→ projection error: leave Memory untouched, record lag/error
→ append terminal Event
→ commit canonical transaction
```

### 13.1 Fail-soft 范围

以下错误不能阻止 canonical terminalization：

- reducer exception；
- unsupported projection input/contract；
- projection typed validation failure；
- state hash/canonicalization contract error。

它们必须：

```text
no Memory mutation
no watermark advance
visible telemetry/logging
later catch-up or rebuild
```

### 13.2 不吞数据库基础设施错误

如果 SQLite/ORM transaction/commit 本身失败，仍按 canonical persistence failure 处理。Projection service 应先纯计算/验证 candidate，再修改 ORM row，避免 derived bug 污染 transaction。

## 14. Migration

步骤：

```text
1. catalog_revision + publication transaction contract
2. Memory v4 typed models/storage metadata
3. pure Catalog reducer
4. completed/failed/cancelled projection boundary
5. v4 shadow incremental/catch-up
6. compare-mode full rebuild sampling
7. Context typed read + prior digest behind flag
8. cutover
9. stop v3 write
10. rollback window 后删除 raw dict compatibility
```

不增加 Effect storage。

## 15. AgentBench

扩展现有 continuity dataset，不建第二套评测系统。

Exact duplicate 只在以下全部相同才计数：

```text
tool name / compatible contract
normalized input hash
datasource generation
catalog revision
no explicit refresh request
no recorded freshness reason
```

`schema_inspect` 分别统计有 freshness reason 与无 reason 的重复。

先记录 baseline；目标优先使用“无理由 exact Catalog duplicate 相对降低 >= 70%”，稳定后再冻结长期 SLO。

## 16. Telemetry

最小 telemetry：

```text
memory_schema_version
projection_id
projection_fingerprint
projection_watermark
projection_lag
projection_failure_count
projection_catchup_run_count
working_state_bytes
working_state_context_tokens
catalog_revision
unsupported_projection_input_count
strict_rebuild_incomplete_count
incremental_rebuild_hash_match
cross_run_duplicate_tool_calls
prior_observation_digest_count
```

不要为了 telemetry 建第二套 state model。

## 17. 性能

```text
normal incremental = O(records in current terminal Run + bounded object state)
lag catch-up       = O(records in catch-up gap + bounded object state)
full rebuild       = O(total canonical records in Session)
lookup/merge       = average O(1)
```

P0 不引入 vector index、graph、generic cache 或健康路径全 Session terminal scan。

## 18. 功能测试

至少覆盖：

- completed search/inspect continuation；
- failed Run succeeded observation continuation；
- cancelled Run succeeded observation continuation；
- unknown/failed exclusion；
- refresh revision transition within one Run；
- Run 外 catalog revision invalidation；
- connection generation invalidation；
- negative search 不夸大；
- object merge/eviction determinism；
- duplicate terminal apply no-op；
- projection exception keeps canonical terminal state；
- projection failure keeps watermark unchanged；
- lag catch-up from watermark + 1；
- gap not crossed；
- prior digest deterministic selection；
- 100 Run boundedness；
- incremental/catch-up/full rebuild hash equality；
- missing projector strict/repair semantics。

## 19. 非目标

不做 Session Effect P0、Generic Tool Cache、Vector Memory、完整 Schema Memory、统一 live-state TTL、LLM 长期总结、跨 Session 用户记忆、PreviousRunOutcome 扩容或为 fail-soft 预先建设通用 Outbox Framework。
