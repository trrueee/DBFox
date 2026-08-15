# Session Memory v4 Projection 实施合同

> 文档类型：Memory v4 ADR 附录 / 实施合同
>
> 状态：已接受
>
> 最后核验：2026-08-16
>
> 关联 ADR：[Session Memory v4 与跨 Run 工作连续性](./session-memory-v4.md)

## 1. Projection envelope

```python
class SessionProjectionEnvelope(BaseModel):
    extension_id: str
    projection_id: str
    schema_version: int
    projector_version: int
    policy_version: int
    contract_fingerprint: str
    projected_through_session_sequence: int
    state_hash: str
    scope: dict[str, JsonValue]
    state: dict[str, JsonValue]
```

第一版：

```text
extension_id = dbfox.catalog
projection_id = dbfox.catalog.working_state
```

核心集合使用 tuple 和严格嵌套模型，不能只靠 `frozen=True` 包裹可变 list/dict。

## 2. Catalog state model

```python
class CatalogProjectionScope(BaseModel):
    datasource_id: str
    datasource_generation: int
    catalog_revision: int

class CatalogWorkingState(BaseModel):
    catalog_orientation: CatalogFootprint | None = None
    searches: tuple[SearchFootprint, ...] = ()
    candidate_objects: tuple[WorkingObjectRef, ...] = ()
    inspections: tuple[InspectionFootprint, ...] = ()
    referenced_artifacts: tuple[ArtifactFootprint, ...] = ()
```

建议 policy v1：

```text
searches              <= 12
candidate_objects     <= 32
inspections           <= 24
referenced_artifacts  <= 24
advisory questions    <= 8
runtime evidence refs <= 32
```

所有集合和单项字段必须显式 bounded。排序/淘汰使用稳定键：

```text
(run.session_sequence, observation.sequence, observation.id)
```

禁止依赖 reducer 执行时的 wall clock、random 或未排序数据库结果。

## 3. Footprint models

```python
class SearchFootprint(BaseModel):
    run_id: str
    invocation_id: str
    observation_id: str
    tool_version: str
    input_hash: str
    queries: tuple[str, ...]
    candidate_object_keys: tuple[str, ...]
    returned_count: int
    catalog_revision: int
    observed_at: datetime

class InspectionFootprint(BaseModel):
    run_id: str
    invocation_id: str
    observation_id: str
    tool_version: str
    targets: tuple[str, ...]
    observed_at: datetime
```

同一 terminal Run 重复 apply 必须幂等。推荐以 source Observation ID 去重，并以稳定 semantic key 合并近期状态。

## 4. Session Effect contracts

首批 Effect：

```text
dbfox.catalog.oriented
dbfox.catalog.refreshed
dbfox.catalog.search_performed
dbfox.catalog.objects_inspected
dbfox.data.result_artifact_referenced
```

示例：

```json
{
  "extension_id": "dbfox.catalog",
  "effect_type": "dbfox.catalog.search_performed",
  "effect_version": 1,
  "payload": {
    "input_hash": "...",
    "queries": ["refund"],
    "candidate_object_keys": ["public.refunds"],
    "catalog_revision": 19
  }
}
```

Effect 不重复 enclosing provenance。Effect payload 必须比完整 Observation output 小，不保存 score、aliases、完整 search detail 或 Schema。

Tool settlement 应先校验 output/Artifact draft，再校验 Effect；任一合同失败时按 Tool output contract 失败处理，不能留下半批 Artifact/Effect。

## 5. Projector ownership

建议结构：

```text
engine/agent/memory/models.py
engine/agent/memory/projector.py
engine/agent/memory/rebuild.py
engine/agent/memory/service.py
engine/agent/repositories/memory.py
engine/extensions/data/catalog_projection.py
```

职责：

- Repository：锁定和持久化；
- Projector：纯 reducer；
- Service：terminal transaction 编排；
- Rebuilder：扫描 canonical history、compare 和 repair；
- Catalog Projection Module：Effect/Observation 的领域归约。

`RunRepository` 不理解 Memory JSON、Catalog merge 或 Tool-specific reducer。

Projector 禁止调用：LLM、embedding、random、Tool reexecution、当前 Prompt wording、`datetime.now()` 作为排序输入或未排序查询结果。

Reducer 选择至少感知：

```text
extension_id
effect_type/effect_version
或 tool_name/tool_version
projection policy version
```

未知版本跳过并记录 telemetry，不猜测兼容。

## 6. Terminal fold policy

| Tool/Effect | Fold 行为 |
| --- | --- |
| catalog overview/search/inspect | 进入 Catalog Working State |
| catalog refresh | 更新 revision 并失效旧 active Catalog state |
| SQL execute result Artifact | 只记录可用 Result Artifact ref |
| result inspect/profile | 可更新 Artifact recent-use，不保存 rows |
| sql validate | 不形成跨 Run execution authority |
| unknown/rejected/failed/cancelled | 不写为完成工作 |

`contributes_progress` 不能作为唯一全局门槛。例如 result_inspect 可以不推进计划，但其 Result Artifact 使用状态仍可能被特定 reducer 接受。

## 7. Full rebuild

```python
rebuild_session_memory(
    session_id,
    *,
    mode: Literal["strict", "compare", "repair"],
) -> RebuildResult
```

算法：

```text
read Session/current scopes
→ iterate terminal Runs by session_sequence
→ load settled Invocation + Observation + Artifact/Evidence
→ validate effects/contracts
→ apply same Projectors and policies
→ produce canonical Memory JSON and hashes
```

等价条件：

```text
same canonical records and cutoff
same Memory schema/core policy version
same per-projection schema/projector/policy version
same effect/reducer contract fingerprint
→ same canonical Memory hash
```

Policy/Projector 升级后执行新版本 rebuild；不同版本 hash 不要求相等。

Modes：

- `compare`：只比较，不写入；
- `strict`：缺 Projector 或合同则 incomplete；
- `repair`：只有 strict complete 且用户/运维显式请求时覆盖。

## 8. Context rehydration

ContextAssembler 对 active footprint 做 read-time fence：

```text
datasource ID
datasource generation
catalog revision
```

然后按当前请求选择有限 Observation，生成 prior digest。Digest 不复制全部 facts，优先：

- exact object identity；
- bounded key columns；
- primary key；
- bounded related objects；
- observed_at；
- source Observation ID；
- freshness warning。

建议上限：

```text
prior digest objects <= 8
columns per object    <= 12
digest facts bytes    <= 16 KiB
rendered working state<= 2,000 estimated tokens
```

Prompt renderer 不暴露 Memory 内部 schema/projector/version 字段，只渲染任务相关状态和 provenance/freshness。

## 9. v3 shadow migration

建议数据库/代码步骤：

1. 新增 `catalog_revision`；
2. 新增 Effect storage；
3. 新增 Memory v4 row metadata 或 v4 envelope；
4. terminal transaction 双算 v3/v4；
5. v4 暂不进入 Context；
6. 每次或抽样执行 full rebuild compare；
7. telemetry 达标后 feature flag 切 v4 Context；
8. 停止写 v3；
9. 回退窗口后删除 raw dict compatibility。

推荐 Memory row 增加可查询 metadata：

```text
schema_version
core_policy_version
projected_through_session_sequence
state_hash
updated_at
```

避免每次为 repair/lag 检查解析整段 JSON。

## 10. 功能测试

至少覆盖：

- completed schema-only continuation；
- failed Run 中 succeeded search/inspect；
- cancelled Run 中 succeeded inspect；
- unknown outcome exclusion；
- topic switch/topic return；
- Catalog revision invalidation；
- AI enrichment/search-doc invalidation；
- connection generation invalidation；
- negative search 语义；
- prior Observation digest；
- Result Artifact continuation；
- selected Artifact 单一所有者；
- 100 Run boundedness；
- delete/rebuild；
- incremental/full rebuild equality；
- missing Projector strict/degraded/migration。

## 11. AgentBench

扩展现有 continuity dataset，不建第二套评测系统。

Exact unnecessary duplicate 只有以下条件全部相同才计数：

```text
tool name/version
normalized input hash
datasource generation
catalog revision
no explicit refresh request
no recorded freshness reason
```

`schema_inspect` 分别统计有/无 freshness reason 的 reinspection，不设零重复目标。

先记录 baseline，目标优先使用“Catalog exact duplicate 相对降低 >= 70%”；稳定后再冻结绝对 SLO。

## 12. Telemetry

```text
session_memory_schema_version
projection_id/version/fingerprint
working_set_bytes
working_set_context_tokens
working_set_search_count
working_set_inspection_count
catalog_revision
projection_source_run_sequence
projection_lag
unsupported_effect_count
strict_rebuild_incomplete_count
incremental_rebuild_hash_match
cross_run_duplicate_tool_calls
catalog_reexploration_count
result_artifact_reuse_count
prior_observation_digest_count
```

## 13. 性能

增量路径复杂度必须是：

```text
O(current terminal Run observations/effects)
```

不能每次 terminal 扫描整个 Session。Full rebuild 可以是 `O(Session total canonical records)`，仅用于 migration、repair、debug 和 projection upgrade。

## 14. 非目标

不做 Generic Tool Cache、Vector Memory、完整 Schema Memory、统一 live-state TTL、LLM 长期总结或 PreviousRunOutcome 扩容。
