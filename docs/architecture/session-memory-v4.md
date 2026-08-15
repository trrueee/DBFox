# Session Memory v4 与跨 Run 工作连续性

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

将当前 `AgentSessionMemory` v3 演进为 typed、versioned、bounded、deterministically rebuildable 的 Memory v4。

Memory v4 使用 namespaced Projection Module 保存跨 Run 工作连续性。第一版只实现 `dbfox.catalog`，解决 Catalog/Schema 探索在 completed、failed 和 cancelled Run 之间丢失的问题。

Memory 不是事实源、执行恢复状态、Tool Cache 或模型自由书写的长期记忆。

## 2. 当前缺陷

当前 Memory v3 的 `working_set` 主要保存 selected/referenced Artifact 和开放问题。普通 completed Run 若只执行 `catalog_overview`、`schema_search`、`schema_inspect` 并正常回答但没有 Result Artifact，下一 Run 的 `PreviousRunOutcome` 不会包含这批探索工作。failed/cancelled Run 中已经成功结算的 metadata Observation 也不会经过成功完成路径的 Memory consolidation。

因此下一 Run 主要依赖自然语言历史，模型可能重新 overview/search/inspect。P0 是 State Continuity，不是 Prompt 扩张或 Generic Tool Cache。

## 3. 四个层次

```text
1. Canonical Durable State
   Message / Run / Turn / Invocation / Observation
   Artifact / Evidence / Plan

            ↓ deterministic projection

2. Session Memory v4
   bounded cross-Run working-state projections

            ↓ context projection and rehydration

3. ContextSnapshot
   frozen provider-neutral pre-budget candidate state

            ↓ budget / render / transient overlay

4. PromptBundle / Provider Input
   actual model-visible items
```

`ContextSnapshot` 不是模型实际看到的完整内容。它保存候选状态和 provenance；预算器和 PromptAssembler 还会处理 Tool Schema、当前 Run native response items、steer 和 transient output。最终 Provider request 才是实际模型输入。

## 4. 职责

| 对象 | 回答的问题 |
| --- | --- |
| Canonical tables | 实际发生了什么，如何恢复和审计？ |
| PreviousRunOutcome | 紧邻上一 Run 如何结束，当前请求需要什么 immediate continuation？ |
| Session Memory | 当前 Session 最近完成过哪些相关工作？ |
| Observation | 某次 Tool 实际观察到了什么？ |
| Artifact | 已产生什么可复用工作产品？ |
| Evidence | 当前回答 claim 由什么 Artifact 支持？ |
| ContextSnapshot | 本 Turn 有哪些冻结候选状态？ |
| PromptBundle | 模型这次实际收到了什么？ |

`PreviousRunOutcome` 继续只覆盖 failed、cancelled、bounded_partial 和 completed-with-result 等 immediate continuation，不扩展成上一 Run 完整工具历史。

## 5. Memory envelope

```python
class SessionMemoryStateV4(BaseModel):
    schema_version: Literal[4] = 4
    core_policy_version: int
    state_projection_registry_fingerprint: str
    projected_through_session_sequence: int
    core: SessionMemoryCore
    projections: tuple[SessionProjectionEnvelope, ...]
```

```python
class SessionMemoryCore(BaseModel):
    referenced_artifact_ids: tuple[str, ...] = ()
    runtime_evidence_references: tuple[EvidenceReference, ...] = ()
    advisory_open_questions: tuple[str, ...] = ()
```

`advisory_open_questions` 是有界建议，不是 Runtime 事实。

`selected_artifact_id` 不再复制到 Memory。其 owner 是 `AgentSession.selected_artifact_id` 和 admitted input selected IDs；Run 外用户选择也不能只通过 terminal Runs 重建，继续复制会制造第二所有者。

每个 Projection envelope 独立保存 extension/projection ID、schema/projector/policy version、contract fingerprint、watermark、state hash、scope 和 state。增加前端 Renderer 或无关 Extension 不能改变 Catalog projection hash。

## 6. Catalog revision

新增：

```text
DataSource.catalog_revision
```

不用 `catalog_generation` 或 `catalog_epoch`，避免与 `connection_generation` 混淆。

```text
connection_generation
    连接配置、凭据和 connection profile 的代际

catalog_revision
    DBFox 本地 Catalog/Search Surface 的发布版本
```

任何会改变 `catalog_overview`、`schema_list`、`schema_search` 可见结果的 local-catalog mutation 都必须明确 BUMP/NO-BUMP，包括：

- authoritative SchemaCatalogSync；
- SchemaSearchDoc rebuild；
- AI enrichment 对 description/alias/tag/business term/subject area/search docs 的发布；
- 未来用户对搜索可见 metadata 的编辑。

失败 mutation 不递增。Catalog mutation、SearchDoc publication 和 revision bump 同事务提交。初版允许每次成功 refresh 都递增，即使内容相同；这只会保守失效旧 footprint。

Catalog Tool 必须在执行时读取一致 revision 并写入 Observation/Effect，不能在 Run terminal 时读取当前 revision 倒填旧 Observation。

失效采用双层保障：Projector 在新 revision 时清理/降级旧 active state；ContextAssembler read-time 再次比较当前 revision，处理 Run 外 refresh。

## 7. Working State 与事实

第一版 Catalog state 包含：

```text
catalog orientation
recent searches
candidate objects
inspection footprints
referenced Result Artifacts
```

Memory 保存 footprint 和 provenance，例如 Tool version、input hash、queries、candidate keys、source invocation/observation、catalog revision、observed_at；不复制完整 columns、indexes、foreign keys、comments、search score、aliases、Tool output、rows 或 series。

Search query 需要从 canonical Invocation authorized input 获取；Projector 输入是：

```text
ToolInvocation + Observation + Artifact references + enclosing Run
```

若采用 Session Effect，Effect 提供严格验证的 projection input，但不替代 enclosing canonical records。

空搜索只表达：在 Tool version、input hash 和 catalog revision 下，本次有界搜索返回零候选。它不能证明远程数据库不存在对象，也不能渲染成“表一定不存在”。

## 8. Prior Observation digest

只有 `observation_id` 仍不足以让下一 Run 使用此前工作。ContextAssembler 应根据少量 active footprint，按预算读取 canonical Observation，生成 deterministic bounded digest：

```text
orders
- previously live-inspected at 2026-08-16T01:30:00Z
- key columns: id, customer_id, status, total_amount, created_at
- primary key: id
- related objects: customers
- source observation: observation_x
- freshness: prior live observation; revalidate when current schema matters
```

Digest 每次从 canonical Observation 生成，不持久化为第二份完整事实；有 item/byte/token 上限，只选择与当前请求相关的 footprint，并明确 freshness。

`schema_inspect` 是 live introspection。`catalog_revision` 不能证明外部数据库当前仍与 prior inspection 一致。不在初版引入统一 TTL，也不把 reinspection 机械设为零。

## 9. 哪些 Run 被归约

Run terminal path 全部调用同一 Memory Projection Service：

```text
completed
failed
cancelled
```

`bounded_partial` 是 completed Run 的 disposition。

基础规则：

- 只 fold `Observation.status == succeeded`；
- unknown/failed/cancelled/rejected Observation 不进入“已完成工作”；
- Effect/reducer 必须注册且版本受支持；
- Tool-specific policy 决定是否进入 Working State；
- SQL validation/Safety/Approval authority 不进入跨 Run Memory；
- Result Artifact 可作为引用，但 rows 不进入 Memory。

Stable Evidence 只来自已持久化 Evidence/Artifact provenance。模型自然语言 claim 不直接进入 stable state。

## 10. 写入事务与恢复

```text
settle active children
→ stage terminal Run/Plan/Message/Evidence state
→ load eligible succeeded effects/observations
→ SessionMemoryProjectionService.apply_terminal_run()
→ upsert Memory v4
→ append terminal Event
→ commit
```

Tool settlement 只写 canonical Observation、Artifact 和 Effect，不立即更新 Session Memory。

同 Run crash recovery 继续只依赖 Run、Turn、Invocation、Observation、Approval/Question、Plan 和 lease/fencing。Memory 不参与正确性恢复。

## 11. Context projection

`ContextSnapshot.session_memory` 从裸 dict 改为 typed context model。内部存储 schema 不直接 dump 到 Prompt，分别渲染：

```text
SESSION_WORKING_STATE
SESSION_EVIDENCE_INDEX
```

Working State 推荐硬限制 `<= 2,000` estimated tokens。优先级：System、Current Request、Run Focus、PreviousRunOutcome、Selected Artifacts、Session Working State、Workspace/Factual Context、Evidence Index、Archive Metadata、Recent History。

当前 Run native function call/output 继续使用完整 Turn batch 淘汰和 Evidence ledger，不与跨 Run Projection 混合。

## 12. Result 与 SQL authority

保持现有边界：Tool rows 只进入 transient bounded provider payload；Observation 无 rows；Result Artifact 保存安全 source/fingerprint/metadata；Result Gateway 按需 bounded live reexecution/inspection。

跨 Run 复用 Result Artifact 是复用安全查询合同和 provenance，不是冻结 rowset。绝对禁止跨 Run 复用 SQL validation authority、Safety execution capability、Approval grant 或 ToolInvocation authority。

## 13. 迁移

采用 shadow migration：

```text
新增 revision/effect/storage
保持 v3 当前行为
terminal path 同时计算 v4 shadow
v4 暂不注入 Prompt
持续比较 incremental/full rebuild hash
稳定后切 Context read path
停止写 v3
回退窗口后删除兼容代码
```

v3 和 v4 都是可删除派生状态，shadow 双投影不是双领域事实源。

## 14. 不变量与验收

- 删除 Memory 不得导致 Message、Observation、Artifact、Evidence 丢失或 Run recovery 失败；
- 相同 canonical cutoff 和版本下 incremental hash 等于 full rebuild hash；
- 模型文本不能直接成为确定性 Working State；
- Memory 中 rows、previewRows、series、完整 Schema、完整文件、长日志为零；
- datasource/connection generation 变化后旧 Data state 不进入新上下文；
- catalog revision 变化后旧 orientation/search/candidate/negative state 不作为 current knowledge；
- Result Artifact 可复用，execution authority 不可复用；
- 10/50/100 Runs 达到 policy 上限后 Working State bytes/tokens 进入平台期。

实现模型、Effect、Projector、rebuild、bounds、AgentBench 和 telemetry 细节见[Session Memory v4 Projection 实施合同](./session-memory-v4-projection-contract.md)。
