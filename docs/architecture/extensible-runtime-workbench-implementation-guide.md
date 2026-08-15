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

把 Runtime Extension、Memory v4、Artifact/Completion 和 Workbench Shell 拆成小 PR，并确保实现不会为了未来完整性提前建立无真实使用者的层级。

每个 PR 必须：

- main 可运行；
- 先有 characterization test；
- 新抽象说明至少两个真实变化点，或明确是短期 migration facade；
- 不复制 canonical state；
- 不新增无必要 DTO/Mapper/Manager；
- 数据结构的 identity/order/bounds 先于 Service class；
- 同步更新当前实现文档；
- feature flag/compat path 写清删除条件。

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
P5 Database + Workspace resource boundary
  ↓
P6 isolated execution attempt runner
  ↓
P7 Workspace read-only vertical slice
  ↓
P8 Patch write with CAS
  ↓
P9 Terminal / real external bindings
  ↓
P10 second Extension proof
```

P2 是跨 Run 连续性的产品 P0，不被“先做完整 Extension Framework”阻塞。

## 3. P0.5 — 实现前纠偏与 characterization

本阶段就是实现前最后一道架构门。

### 必须固定的当前合同

Backend：

- `register_dbfox_tools()` 当前注册集合和 materialization hash；
- Tool input/output/Policy/Execution/Semantics parity；
- ToolExecutor deadline/retry/cancel/quarantine；
- completed/failed/cancelled terminal transaction；
- Memory v3 当前 write/read；
- Catalog search/inspect facts bounds；
- Artifact batch validation；
- Completion query-result citation behavior。

Frontend：

- Conversation stream/cancel/approval/question；
- SQL draft/execute/result/error；
- Table Preview/Schema/ER；
- MultiTable；
- Artifact open/render；
- Project list/create；
- Datasource create/edit/test/sync；
- Settings / command palette / shortcuts。

### 退出条件

- 本轮 correction ADR 合入；
- characterization tests 绿色；
- baseline AgentBench continuity 记录 commit/model/provider/dataset；
- 团队确认下列内容不作为实现前置：Effect P0、dependency graph、万能 Environment、第二套 Tool fingerprint、Project≈Datasource adapter。

## 4. P1 — 最小 Extension ownership

### 目标

只建立“谁拥有 contribution”和“serving 后不可变”的 seam，不改变 Tool 行为。

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
- 不创建 ToolContribution DTO；
- existing Tool materialization hash parity 100%。

### PR 2：owner/duplicate/freeze

为实际已启用 Registry 增加：

- owner ID；
- duplicate contribution ID check；
- `freeze()`；
- freeze 后 mutation test。

P1 不实现 dependency graph。出现第二个有真实依赖的 Extension 时另开 ADR/PR，使用拓扑排序。

### 回滚

删除新组合入口，旧 facade 仍可直接构建原 Registry。

## 5. P2 — Memory v4 P0

P2 解决真正的 Context continuity。

### 5.1 PR：Catalog publication transaction + revision

先修正 transaction ownership，再加 revision。

工作：

- `DataSource.catalog_revision` migration；
- Catalog authoritative publication 与 SearchDoc publication 同一短事务；
- AI enrichment 移除内部 commit/rollback 对外层 transaction 的破坏；
- LLM call 放在数据库写 transaction 外；
- enrichment 写入前 re-check schema/generation；
- DB atomic `catalog_revision = catalog_revision + 1`；
- Catalog Tool output/Observation 冻结 execution-time revision。

测试：

- successful refresh bumps；
- failed publication no bump；
- AI enrichment publication bumps；
- concurrent publication revision monotonic；
- observation revision 不在 terminal 时倒填。

### 5.2 PR：Memory v4 typed models + Catalog reducer

新增：

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

**不新增 Effect storage/registry。**

算法必须满足：

- temporary object hash map O(1) merge；
- search <= 12；
- objects <= 32；
- deterministic eviction；
- deterministic canonical serialization/hash。

### 5.3 PR：统一 terminal fold

completed/failed/cancelled 都在同一 terminal transaction 调用 projection service。

规则：

- only succeeded Observation；
- watermark by session_sequence；
- duplicate apply no-op；
- gap detection；
- projection failure 与 terminal transaction 一起失败，避免提交“terminal 已发布但 Memory 水位线假装已推进”的状态。

Memory 仍不参与 same-Run recovery correctness。若后续实践证明 derived projection failure 不应阻塞 terminal publication，必须通过独立 ADR 定义 catch-up/outbox 语义，不能在实现里临时 best-effort skip。

### 5.4 PR：shadow + rebuild

- v3 继续当前写；
- v4 shadow incremental；
- full rebuild 调**同一 reducer**；
- compare hash telemetry；
- strict/compare/repair modes；
- missing projector incomplete semantics。

禁止写第二套 rebuild merge 算法。

### 5.5 PR：Context rehydration

- typed context-facing Memory；
- datasource/generation/revision read fence；
- deterministic prior Observation selection；
- <=8 object digest；
- SESSION_WORKING_STATE / SESSION_EVIDENCE_INDEX；
- <=2,000 estimated token working-state budget；
- feature flag 切 v4 Context。

第一版不使用 LLM/embedding 做 prior digest selection。

### 5.6 P2 cutover gate

- incremental/full rebuild hash match 100% in deterministic suite；
- failed/cancelled continuity scenarios pass；
- no rows/full schema/secret in Memory；
- 10/50/100 Run state bytes/tokens 达平台期；
- AgentBench 无理由 exact Catalog duplicate 显著下降；
- rollback 可切回 v3 Context。

达到稳定窗口后停止 v3 write，再删除 raw dict compatibility。

## 6. P3 — Artifact 与 Completion

### 6.1 PR：Artifact open type

当前 DB column `type` 保留。

改：

```text
ArtifactType enum → validated string boundary
add schema_version
validator map[(type, schema_version)]
```

保持：

- existing `sql/safety/result_view/chart/markdown/error/...` ID；
- `Artifact.version` 的 semantic-key version 语义；
- current Artifact relations；
- current payload aliases；
- batch prepare-before-write algorithm。

unknown historical read fallback；unknown new write reject。

不做 `type → type_id → legacy mapper` 双字段长期兼容。

### 6.2 PR：frontend compatible read

前端 wire 从 closed union 的入口改为：

```text
type: string
schema_version: number
payload: object
```

已知类型 renderer 在 registry 中严格 parse；unknown metadata fallback。

现有已知类型业务 View 可继续保留 typed local models，不要求所有 React 代码变成 `unknown`。

### 6.3 PR：Completion constraint

保持 Completion Core 的 lifecycle/citation/budget 逻辑。

只抽：

```text
DataResultCitationConstraint
```

使用 immutable tuple composition；不建 RuleManager。

现有 decision/evidence artifact IDs 必须 parity。

### 6.4 Semantic capability

先把 Registry/Observation 接口从 closed enum 放宽到 validated string，但 legacy IDs 原样保留。新 Extension capability 使用 namespace。

不在 P3 批量 rename legacy capability。

## 7. P4 — Workbench Shell V2

详细阶段见 [Workbench Shell 迁移规范](./workbench-shell-migration-guide.md)。

### P4 约束

- 使用真实 Project model 和当前 list/create API；
- `Project != Datasource`；
- current Conversation 仍 datasource-bound；
- Project Edit 若是需求，先补最小 Project update backend contract，不能假设当前已有；
- Main Surface 固定显式，不 Registry 化；
- Dock View / Artifact Renderer 是开放 registry；
- ShellStore 只保存 identity/layout；
- SQL state project-keyed；
- Dock canonical key 不使用递增 counter；
- tab 小集合优先单一数组，不维护双索引真相；
- Navigation facade 有删除条件。

### Gate

- Conversation/SQL/Table/MultiTable/Artifact/Project list-create/Datasource/Settings parity；
- 若实现 Project Edit，其 backend update contract 独立有测试；
- Project switch restore；
- same canonical target dedup；
- no business payload in ShellStore；
- no central Dock domain switch；
- no legacy `openXxxTab()` after deletion phase。

## 8. P5 — 从两个真实资源提炼 execution resource boundary

P5 之前不要实现万能 `ToolExecutionEnvironment`。

先有：

```text
Database Tool
Workspace File read Tool prototype
```

然后对照两者提炼：

- serializable `ToolInvocationContext`；
- `ResourceScopeRef(kind,id,version)`；
- minimum resource resolver / execution resource interface；
- resource authorization value if current ExecutionAuthority insufficient。

### ToolInvocationContext 上限

只允许：

```text
session_id
run_id
turn_id
invocation_id
idempotency_key
deadline_at
scope_refs
```

除非第二资源证明必要，不增加 project_id、execution_id、metadata bag、authority_ref、grant IDs。

### Gate

- current DB Tool parity；
- File read prototype 能用同一 invocation/resource seam；
- Tool 看不到 global service container；
- no secret in invocation JSON。

## 9. P6 — isolated execution attempt runner

在现有 `ToolExecutor` 内抽 AttemptRunner Strategy。

### PR 1：InProcessAttemptRunner extraction

只移动当前 ThreadPool/quarantine 单次 attempt 逻辑，确保行为 parity。

`ToolExecutor` 继续拥有：

- retry；
- overall deadline；
- concurrency；
- attempts；
- recovery decision。

### PR 2：worker protocol

- protocol handshake；
- one attempt request/result；
- heartbeat；
- cancel；
- process-tree kill；
- output/frame/diagnostic bound；
- late result suppression；
- worker crash mapping。

### PR 3：IsolatedProcessAttemptRunner

接到同一个 ToolExecutor attempt seam。

不复制 retry/recovery loop。

### Gate

- Windows/macOS/Linux contract tests；
- executor saturation/cleanup；
- current in-process parity；
- isolated crash/timeout/cancel/late result；
- no hostile-code sandbox claim。

## 10. P7 — Workspace read-only vertical slice

目标链：

```text
file_read / file_search
→ strict Tool output
→ Observation + FileSnapshot Artifact
→ Workspace reducer/projection
→ next Run bounded Context
→ File Dock View
```

P7 是检验 Runtime seam 的关键：

- 不允许 `ContextSnapshot.file_context`；
- 不允许 RunLoop `if tool == file_read`；
- 不允许 Artifact Core `if type == code_file`；
- 不允许 Dock Kernel `if viewType == file`。

Workspace projector 可以像 Data projector 一样理解自己拥有的 Tool。

## 11. P8 — Patch write

```text
file_write_patch
→ authorized workspace root
→ expected file hash/version CAS
→ temp sibling write
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
- crash/reconcile/unknown；
- bounded patch；
- no silent overwrite。

## 12. P9 — Terminal / external binding

只在有真实 use case 时实现。

### Command-backed Tool

固定 executable + operation + structured argv + versioned parser。

### Generic Terminal

独立高风险 Tool；用于 coding/build/test/排障；不成为 API/MCP/CLI 的万能 fallback。

### API/MCP

第一个真实平台接入时再抽最小 Binding Strategy。

MCP 必须 admission/allowlist/materialization；API/MCP/Command 都复用 Tool settlement。

P9 不因为“支持未来”一次实现 universal MCP marketplace 或 generic external provider framework。

## 13. P10 — 第二 Extension proof

P10 的意义不是多一个 demo，而是证明 seam 稳定。

第二种完整 Extension 必须：

- 注册 Tool；
- 产生 Observation/Artifact；
- 如需跨 Run，注册自己的 Projector；
- 如有领域完成条件，注册 Constraint；
- 如有 UI，注册 Dock/Renderer contribution；
- 不修改 RunLoop 领域 branch；
- 不修改 ContextSnapshot 根模型领域字段；
- 不修改 Completion Core 领域逻辑；
- 不修改 Dock Kernel central switch。

如果为了第二 Extension 需要这些 Kernel 变化，暂停功能实现，回到 seam review。

## 14. PR 设计检查表

每个实现 PR 在 description 回答：

1. 当前真实问题是什么？
2. 最小改动是什么？
3. 新抽象有几个真实使用者？
4. 是否新增第二份 identity/state/hash？
5. 是否引入 DTO/Mapper 只为字段搬运？
6. identity/key/order/bounds/eviction 是什么？
7. transaction owner 是谁？
8. incremental 与 rebuild 是否同一算法？
9. fail/cancel/recovery 的 owner 是谁？
10. compatibility path 什么时候删除？

## 15. Rollback 原则

- P1：保留旧 Tool registry facade 到 parity 完成；
- P2：v4 shadow + Context flag，回退只切 read path；
- P3：compatible read，legacy Artifact schema v1 始终可读；
- P4：Shell V2 flag 到 entry parity；
- P5/P6：existing in-process DB path 在新 seam parity 前不删除；
- P7+：新 Extension 可独立 disable，不破坏 Data Agent canonical state。

禁止长期双写/双事实源。Rollback window 结束必须删除兼容路径。

## 16. 最终完成定义

只有同时满足以下条件才算这轮架构实施成功：

### Context

- completed/failed/cancelled 中 succeeded work 跨 Run 连续；
- stale generation/revision 不误用；
- Memory bounded/rebuildable/non-authoritative；
- prior digest 回 canonical source。

### Tool

- Database/File/Terminal/External provider 使用同一 durable Tool lifecycle；
- Kernel 不认识具体新 Tool；
- execution resource boundary 来自真实案例；
- isolated attempt 不复制 executor orchestration。

### Frontend

- Project/Datasource ownership真实；
- Shell/Main/Dock/Settings 边界明确；
- ShellStore 无业务事实；
- new View/Renderer registration 不改 central domain switch。

### Design quality

- 没有为了对称性存在的空抽象；
- 没有长期 Mapper/Adapter 链；
- 没有重复 fingerprint/identity/state；
- 关键 reducer、dedup、eviction、CAS 算法确定、有界、可测试。
