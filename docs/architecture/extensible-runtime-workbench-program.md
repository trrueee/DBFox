# DBFox 可扩展 Runtime 与 Workbench 架构计划

> 文档类型：Umbrella RFC / Architecture North Star
>
> 状态：已接受
>
> 最后核验：2026-08-16
>
> 基线：`main@daa99d048decd7f5f8dc010cbe5465f332686a3c`
>
> 适用范围：Agent Runtime、跨 Run Context/Memory、Tool 执行、Artifact/Completion、桌面 Workbench Shell

## 1. 决策

DBFox 后续统一目标保持不变：

> **稳定的 Agent Runtime Kernel + 稳定的 Workbench Shell Kernel + 有边界的内置扩展 + 可重建的跨 Run 工作状态。**

本次实现前复核不改变原目标，只修正已经被当前代码证明会造成过度设计、重复事实源或错误所有权的实现路径。

三个最终必须解决的问题是：

1. **Context continuity**：Run 结束不能等于已经成功完成的工作被遗忘；completed、failed、cancelled Run 中已成功结算的 Observation 都能在后续 Run 有界复用。
2. **Tool extensibility**：Database、File、Terminal、API、MCP 等 Tool 不要求 RunLoop、ContextSnapshot、Completion Core 或 Artifact Core 持续增加领域分支。
3. **Workbench extensibility**：Project、Conversation、Dock、Settings 所有权清晰；新增资源 View 不再扩张中央 Workspace Router。

## 2. 实现前复核原则

后续实现必须遵守以下约束：

- **先有真实变化点，再抽象。** 一个抽象至少要由两个真实实现证明；只为对称性存在的 `NativeBinding`、万能 Environment、依赖图或 Registry 不提前实现。
- **单一事实源。** Message、Run、Turn、Invocation、Observation、Artifact、Evidence、Plan 是 canonical state；Memory、Context、Prompt、UI 只做投影。
- **少层级、少转换。** 能直接注册真实 Tool/Validator/Constraint/View 就不创建 Contribution DTO → Mapper → Adapter 链。
- **兼容层短命。** Facade/adapter 只用于迁移，并在实施指南中写明删除条件。
- **数据结构先于 Service。** 先确定 identity、稳定 key、所有权、排序、容量和失效条件，再决定类与模块。
- **一套算法服务增量与重建。** Memory incremental fold 与 full rebuild 必须调用同一 reducer，只允许输入区间不同。
- **不为了“可扩展”隐藏真实边界。** 如果新增第二种能力仍要求 Kernel 写领域 `if`，应重新审查 seam，而不是继续加 wrapper。

## 3. 当前实现中应直接复用的健康主干

以下能力已经存在并应保持：

- Session / Run / Turn / lease/fencing 和显式 RunLoop；
- durable ToolInvocation / Observation settlement；
- Tool input/output schema、Policy、Approval、timeout/retry/recovery/concurrency；
- `ToolMaterialization` 对完整 Tool contract 的 content-addressed hash；
- `ToolExecutor` 的 deadline、retry、scope concurrency、cancel 和 stuck-thread quarantine；
- Observation durable facts 与 transient provider payload 分离；
- Artifact batch 先完整解析/验证再写入；
- Result Artifact / Evidence / SQL authority 和跨 Run authority 禁止复用；
- PreviousRunOutcome 的 immediate-continuation 职责；
- Conversation archive、SSE replay 和 AgentBench；
- 已工作的 Conversation、SQL Console、Table、Artifact renderer、Datasource、Project 和 Settings。

重构首先复用这些主干，不重新实现第二套 Runtime。

## 4. 两个 Kernel

```text
AGENT RUNTIME KERNEL
Session / Run / Turn / Lease
Tool admission / Policy / Authority / Recovery
Observation / Artifact / Evidence
Session projection lifecycle
ContextSnapshot / Budget / Prompt
Core completion
Event stream

        │ stable IDs / wire envelopes
        ▼

WORKBENCH SHELL KERNEL
Project navigation
Conversation Main Surface
Workspace Dock
View identity / lifecycle
Unknown-view / unknown-artifact fallback
```

两个 Kernel 共享稳定 ID 和 wire contract，不共享同一个运行时 Registry。

## 5. Extension 的最小定义

第一阶段 Extension 是**编译期所有权边界**，不是插件框架。

P1 只需要：

```text
register built-in core functions
register built-in data extension contributions
validate owner/ID duplicates
freeze registries
accept Runs
```

注册直接接收真实对象，例如：

```python
registries.tools.register(tool, owner="dbfox.data")
registries.artifacts.register(contract, owner="dbfox.data")
```

不建立只用于再映射一次的 `ToolContribution` DTO。

当前 `register_dbfox_tools()` 同时包含 Control、Conversation 和 Data 能力，因此不能整体包装成 Data Extension。迁移时拆分注册所有权，但保留一个组合入口作为短期 facade。

P1 不实现：

- 第三方动态加载；
- Extension Host；
- 通用 dependency graph；
- 全套七种 Registry；
- 第二份 Tool Registry fingerprint；
- 通用 MCP client / Terminal runtime。

只有出现真实扩展依赖时才引入依赖声明；届时必须使用依赖拓扑排序，而不是把“按 ID 排序”当作依赖解析。

## 6. Tool 与执行来源

Tool 是 DBFox 的逻辑能力合同。执行来源可以是：

```text
Native implementation
API/SDK adapter
MCP adapter
Command/CLI adapter
```

但 Native Tool 不为了形式对称被包进一个空的 `NativeBinding` 对象。第一个真实非 Native 集成出现时，再抽最小 Binding Strategy。

无论来源如何，结果必须回到同一条链：

```text
Tool contract
→ Policy / Approval
→ execution attempt
→ strict output validation
→ Observation / Artifact
→ optional projection input
→ Context / Completion
```

MCP 不成为第二套 Agent Runtime；Generic Terminal 仍是高自由度 fallback，不是所有外部平台的默认集成层。

## 7. Context / Memory 的最终边界

```text
Canonical durable records
        ↓ deterministic reducer
Session Memory v4
        ↓ bounded rehydration
ContextSnapshot
        ↓ budget / render
Prompt / Provider input
```

Memory v4 的 P0 直接从 canonical Invocation + Observation + Artifact references 归约，不为 Catalog 再保存一份 Session Effect。

如果未来某个真实 Extension 产生了 canonical records 无法稳定表达、且又必须跨 Run 归约的领域变化，再评审是否增加 Effect。Effect 不是 P0 前置条件。

最终验收不是“Memory schema 存在”，而是以下行为成立：

- failed/cancelled Run 中已经成功的 search/inspect 可在下一 Run 继续使用；
- `catalog_revision` 或 datasource generation 变化后旧 working state 不作为 current knowledge；
- Memory 删除不影响审计、Artifact、Evidence 或 Run recovery；
- Memory 有界，长期 Session 达到容量平台期；
- prior digest 每次从 canonical Observation 生成，不保存第二份完整 Schema。

## 8. Artifact 与 Completion

Artifact 持久层已有 string `type`，目标是把运行时封闭 enum 打开，而不是做一次大规模 ID 改名。

第一阶段：

- 保留现有 `type` 字段和现有 `result_view/chart/sql/...` ID；
- 新增独立 `schema_version`；
- 新 Extension type 必须 namespaced；
- Validator Registry 按 `(type, schema_version)` 注册；
- `Artifact.version` 继续表示同一 semantic key 的业务版本，不与 payload schema version 混用；
- unknown historical Artifact 保留 envelope 并 fail-soft 渲染。

Completion Core 保留 lifecycle、pending work、answer candidate、citation syntax/ownership 和 budget。第一阶段只把 Data result citation 这种领域约束抽成 immutable `CompletionConstraint` 列表，不建立复杂 Rule Manager。

现有 semantic capability ID 参与 Tool materialization。为避免无意义的历史迁移和 pending Tool mismatch，已有 ID 暂不批量重命名；新 Extension capability 才强制 namespace。

## 9. Workbench Shell 的真实 Project 边界

仓库已经有真实 `Project` 模型、Project API，且 `DataSource.project_id` 是真实关系。因此：

- Project 使用真实 `Project.id`；
- DataSource 是 Project 子资源；
- 不允许 `project_id = datasource_id` adapter；
- 当前 AgentSession 仍然 datasource-bound，Conversation 通过 datasource 所属 Project 被归组；
- 无 datasource Session 是未来独立数据模型迁移，不在 Shell 重构中伪造。

目标 UI：

```text
Project Sidebar | Conversation Main | optional Workspace Dock
```

ShellStore 只拥有 UI identity/layout。Dock View 和 Artifact Renderer 是开放贡献点；Main Surface（Conversation/New Conversation/Project form/Empty）是固定 Kernel 状态，不为“统一 Registry”再注册一遍。

## 10. Execution 的责任分层

当前 `ToolExecutor` 已经负责总体 deadline、retry、scope concurrency 和 cancellation。后续 isolated process 不重新实现一套外层策略。

目标责任：

```text
ToolDispatcher
  durable admission / settlement

ToolExecutor
  overall deadline / retry / concurrency / recovery loop

AttemptRunner Strategy
  one execution attempt
  - InProcessAttemptRunner
  - IsolatedProcessAttemptRunner

ToolRuntime
  input/output validation and Tool call
```

`IsolatedProcessAttemptRunner` 负责 worker transport、heartbeat、process-tree kill、frame/output limit 和 worker crash；不重复拥有 ToolExecutor 的 retry policy。

`ToolExecutionEnvironment` 和通用 Capability Grant 不在只有 Database 一种真实资源时提前实现。等 Workspace/File 成为第二种真实执行资源后，再从 DB + Workspace 两个案例提炼最小公共接口。

## 11. 实施顺序

```text
P0.5  implementation refinement + characterization
P1    minimal extension ownership / direct registrar
P2    Memory v4 P0 + catalog_revision + canonical reducer
P3    open Artifact type + schema_version + Data completion constraint
P4    Workbench Shell V2 using real Project model
P5    second real resource boundary from Database + Workspace
P6    isolated execution attempt runner
P7    Workspace read-only vertical slice
P8    Patch write with CAS
P9    Terminal / external binding as real use cases require
P10   second Extension proves stable seams
```

P2 是产品连续性的最高优先级，不被后端扩展框架或前端迁移阻塞。

## 12. 全局验收

- Run boundary 不再导致成功工作被遗忘；
- Memory incremental fold 与同版本 full rebuild 使用同一 reducer 并得到相同 hash；
- 新 File/Terminal/API/MCP Tool 不要求 RunLoop 增具体 Tool 名分支；
- 新 Extension 不要求 `ContextSnapshot.file_context/github_context/...`；
- 新 Artifact type 不要求修改中央 enum/switch；
- 新领域 completion constraint 不修改 Completion Core 的生命周期判断；
- 新 Dock View 不修改中央 Workspace Router；
- Project 和 Datasource 不再混同；
- ShellStore 不保存 SQL Result、Artifact payload、Table metadata 或 File content；
- filesystem/network/subprocess 不进入当前 `in_process` 高权限路径；
- isolated process 不被宣传为 hostile-code sandbox；
- 兼容层有删除条件，不长期双写/双路由。

如果第二种完整 Extension 接入时仍需要修改 RunLoop、Context 根模型、Completion Core 或 Dock Kernel 的领域分支，则本架构未达到目标，应重新审查 seam。

## 13. 配套文档

1. [Runtime Extension Contracts](./runtime-extension-contracts.md)
2. [Runtime Extension 安全与兼容规范](./runtime-extension-security-compatibility.md)
3. [Session Memory v4 与跨 Run 工作连续性](./session-memory-v4.md)
4. [Session Memory v4 Projection 实施合同](./session-memory-v4-projection-contract.md)
5. [Workbench Shell 与 Workspace Dock](./workbench-shell-workspace-dock.md)
6. [Workbench Shell 迁移规范](./workbench-shell-migration-guide.md)
7. [分阶段实施指南](./extensible-runtime-workbench-implementation-guide.md)

## 14. 非目标

不做 Marketplace、动态第三方 Python/React bundle、在线安装、Remote Extension Host、Vector Memory、Generic Tool Cache、Knowledge Graph、外部 Workflow Engine、跨 Session User Memory、通用 Task Requirement DSL、完整 Project multi-resource aggregate，也不把普通子进程宣称为恶意代码安全沙箱。
