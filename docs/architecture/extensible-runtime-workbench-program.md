# DBFox 可扩展 Runtime 与 Workbench 架构计划

> 文档类型：Umbrella RFC / Architecture North Star
>
> 状态：已接受
>
> 最后核验：2026-08-16
>
> 基线：`main@641ddf98a962189f0a2959e6b752533087c2cd65`
>
> 适用范围：Agent Runtime、工具扩展、Session 状态投影、Artifact/Evidence、Context/Prompt、Completion、桌面 Workbench Shell

## 1. 最终评审结论

本 RFC 是 Context/Memory、Tool/Compatibility 和 Frontend Shell 三份 review 的最终收敛。历史 review 继续保留问题发现价值；如与本 RFC 或配套 ADR 冲突，以本 RFC 和 ADR 为准。

DBFox 后续统一目标是：

> **稳定的 Agent Runtime Kernel + 稳定的 Workbench Shell Kernel + 有边界的内置扩展 + 可重建状态投影。**

这不是一次整体重写，也不是第三方插件市场。它首先解决已经发生的问题：

| 层 | 当前问题 | 目标方向 |
| --- | --- | --- |
| Context / Memory | completed、failed、cancelled Run 中已完成的 Catalog/Schema 工作没有可靠进入跨 Run Working State | Memory v4、类型化 Effect、确定性 Projection |
| Tool Runtime | Tool 定义已接近通用，但执行上下文、Backend、Artifact、Semantic/Completion 仍偏 Data Agent | Runtime Extension Contract、Execution Environment、Capability Grant |
| Frontend | Global Tabs、Conversation、ArtifactDock、ContextDrawer 和 Datasource Tree 多套所有权叠加 | Project Sidebar、Conversation Main、注册式 Workspace Dock |

共同根因是：领域能力与 Kernel 之间还缺少稳定贡献边界。未来增加 File、Patch、Terminal、GitHub、Browser 或 Search，不应再给 RunLoop、ContextSnapshot、Memory 根模型、Completion Core 或 WorkspaceDock 增加领域分支。

## 2. 文档事实层级

本 RFC 描述**接受后的目标架构**，不虚构尚未完成的实现。

1. 当前源码、迁移和协议测试描述系统今天实际如何运行；
2. 现有 `docs/architecture/` 实现合同继续描述当前行为；
3. 本 RFC 和配套 ADR 描述迁移完成后必须达到的目标边界；
4. 实施指南规定 PR 切片、依赖、测试、回退和验收；
5. 每个阶段合入后，必须同步更新对应当前状态文档。

## 3. 五条共同原则

1. **Canonical State belongs to the Runtime Kernel.** `Message`、`Run`、`Turn`、`ToolInvocation`、`Observation`、`Artifact`、`Evidence`、`Plan` 是领域事实。Memory、Context、Prompt、Event UI projection 都不能替代它们。
2. **Domain capabilities enter through contracts, not Kernel branches.** 扩展通过 Tool、Observation、Artifact、Semantic Proof、Session Effect、Projection Module 和必要的 Completion Rule 参与 Runtime。
3. **Session is the continuity boundary; Run is the execution boundary.** Run 是事务、预算、恢复和授权边界；Session 是跨 Run 工作连续性边界。
4. **Presentation is a projection of resources and Artifacts.** 模型生成或引用 Artifact，不生成 React Component、Dock Tab 或前端路由。
5. **Extensibility means adding capability without rewriting the Kernel.** 第一阶段只支持受信任、编译期内置扩展；成功标准是新增完整能力时不再向 Kernel 添加领域特例。

`AgentEventRecord` 是已提交公共变化的权威事件流，用于 SSE replay、客户端投影和审计交付；它不是领域实体表的替代事实源，也不是 Memory rebuild 的输入捷径。

## 4. 两个 Kernel

Python Runtime 和 React Workbench 生命周期、安全边界、版本和持久化方式不同，必须分开定义。

```text
AGENT RUNTIME KERNEL
Session / Run / Turn / Lease
Invocation / Policy / Authority / Recovery
Observation / Artifact / Evidence envelopes
Effect settlement / Projection lifecycle
ContextSnapshot / Budget / PromptBundle
Core Completion / Event stream

        │ stable wire IDs and envelopes
        ▼

WORKBENCH SHELL KERNEL
Project Sidebar / Conversation Main
Workspace Dock / canonical view identity
View lifecycle / Shell state
Unknown-view and unknown-artifact fallback
```

二者共享 namespaced ID 和 wire contract，例如 `extension_id`、Artifact `type_id/schema_version`、Semantic capability ID、Dock `view_type` 和 Resource reference schema；二者不共享同一个运行时 Registry 实例。

## 5. 保留的健康主干

以下设计不推倒：

- Session、Run、Turn、lease/fencing 和显式 RunLoop；
- provider-neutral native function calling；
- ToolInvocation/Observation 耐久结算；
- `ToolObservationProjection(summary, facts, provider_payload)`；
- durable facts 排除 rows/results/series/previewRows；
- transient provider payload 独立限额；
- 当前 Run function call/output 成对保留并按完整 Turn batch 淘汰；
- Artifact/Evidence、Result Gateway 和 SQL authority；
- PreviousRunOutcome 的 immediate-continuation 职责；
- Conversation archive、SSE replay 和 AgentBench；
- 已工作的 Conversation、SQL Console、Table、Artifact renderer、Datasource 和 Settings。

未来扩展不得增加 `ContextSnapshot.file_context`、`github_context`、`browser_context` 等领域字段。扩展内容只能通过 Kernel 允许的 Context lane、Observation、Artifact reference 和 Session Projection 进入模型上下文。

## 6. Extension contribution 与 Tool execution source

第一阶段采用内部、编译期扩展：

```text
register_builtin_extensions()
  → validate IDs, versions, dependencies and conflicts
  → register contributions deterministically
  → freeze registries before accepting Runs
```

后端和前端分别使用 Manifest，避免隐式耦合：

```text
BackendExtensionManifest
  tools / artifact contracts / semantic capabilities
  session effect contracts / projection modules / completion rules

FrontendContributionManifest
  dock views / artifact renderers / commands
```

Manifest 冻结贡献点命名和所有权，但不要求 Phase 1 一次实现七套复杂 Registry。Memory v4 先启用 Effect/Projection；Artifact、Completion、Dock/Renderer 按实际阶段迁移。

Tool 是 DBFox 的**逻辑能力合同**，不是某种固定技术实现。一个 Tool 可以由不同 Binding 执行：

```text
DBFox Tool Contract
  ├── NativeBinding
  ├── ApiBinding
  ├── McpBinding
  └── CommandBinding
```

Native Tool 用于 DBFox correctness 核心能力；稳定官方 API/SDK 可用 ApiBinding；可信、成熟 MCP Server 可作为受策略控制的 External Tool Provider；只有稳定官方 CLI 时可用结构化 CommandBinding。Generic Terminal 是长尾 coding/build/test/排障能力，不是所有第三方集成的默认万能胶。

无论 Binding 类型，最终结果都必须回到 DBFox 的 Policy/Authority、ToolInvocation、Observation、Artifact、Effect、Completion 和 Memory pipeline。MCP 不成为第二套 Runtime，CLI stdout 也不能直接变成 Memory/Prompt。

## 7. 信任、安全与缺失扩展

扩展不能拥有 Prompt 权限。Kernel 固定 lane 和优先级：SYSTEM_POLICY、CURRENT_USER_REQUEST、RUNTIME_GUIDANCE 仅由 Kernel 产生；DERIVED_WORKING_STATE、RESOURCE_CONTEXT、ARTIFACT_REFERENCE 只能作为有界、不可信数据进入。

Tool 声明 capability 不等于获得 capability。Kernel 根据 Policy、Approval、当前 scope/version 和 authorized input 铸造 Capability Grant；Secret 只通过 opaque reference 和 broker 使用，不进入 Prompt、Observation、Artifact、Effect 或普通 invocation JSON。

`isolated_process` 是故障、取消、资源和生命周期边界，不是运行恶意第三方代码的完整安全沙箱。第一阶段 Extension 是受信任产品代码。

缺失扩展分三种模式：

1. **Degraded read**：未知 projection/Artifact envelope 原样保留，不进入 Prompt、不参与 Completion，UI 显示扩展不可用；
2. **Strict rebuild**：缺少必需 Projector 时标记 incomplete，不覆盖现有 Memory，不声称 hash equivalent；
3. **Explicit migration/drop**：只有显式迁移才能丢弃 namespace，并记录 migration/tombstone。

## 8. 迁移顺序

```text
Phase 0  RFC / ADR / characterization
Phase 1  minimal Extension bootstrap
Phase 2  Memory v4 P0 in shadow mode
Phase 3  Artifact envelope + Data Completion Rule
Phase 4  Workbench Shell V2 behind feature flag
Phase 5  InvocationContext / ExecutionEnvironment
Phase 6  isolated_process protocol
Phase 7  Workspace read-only vertical slice
Phase 8  Patch write with CAS
Phase 9  Terminal / Tests
Phase 10 second Extension proves stable seams
```

P0 是跨 Run Working State，不是通用 Tool Cache。第一种非 DB Extension 可以补充通用 seam，但不得增加 `if tool == file_read` 等领域分支；第二种完整 Extension 必须只通过 contribution registration 接入。

API/MCP/Command Binding 的**架构合同现在冻结**，实现则按真实集成需求进入后续 Phase；本轮不为了理论完整性先写通用 MCP client 或任意 Terminal execution layer。

## 9. 全局验收

- 新增 Extension 不向 RunLoop 增加具体 Tool 名分支；
- filesystem/network/subprocess 不进入 `in_process`；
- SQL authority 不跨 Run，recovery 遵守 retry/reconcile/unknown；
- External Provider 不绕过 Tool materialization、Policy、Observation/Artifact/Effect；
- MCP Tool 不自动无审查透传给模型，CommandBinding 不执行 model-authored 任意 shell 字符串；
- incremental Memory projection 与同版本 full rebuild hash 相等；
- stale Catalog revision 不作为当前 knowledge；
- Memory 删除不损坏 canonical correctness，rows/完整 Schema/文件/长日志不进入 Memory；
- ContextSnapshot 是 pre-budget candidate projection，PromptBundle/Provider Input 才是实际模型输入；
- 新增 Dock View/Artifact renderer 通过 registration 完成；
- 相同 canonical resource 不创建重复 Tab；
- ShellStore 只保存 UI identity/layout，具体 View state 有独立 owner；
- Unknown Extension/Artifact 不破坏 Conversation、Evidence 和历史读取。

## 10. 本轮非目标

不做 Marketplace、动态第三方 Python/React bundle、在线安装、Remote Extension Host、Vector Memory、Generic Tool Cache、Knowledge Graph、外部 Workflow Engine、跨 Session User Memory、通用 Task Requirement DSL、完整 Project multi-resource aggregate，也不把普通子进程宣称为恶意代码安全沙箱。

MCP 不是架构禁区：允许未来以 `McpBinding` 形式接入受信任 Server。本轮明确不做的是“通用 MCP Marketplace/自动发现任意 Server/把所有 Tool 无审查透传给模型”的兼容层。

## 11. 配套文档

1. [Runtime Extension Contracts](./runtime-extension-contracts.md)
2. [Runtime Extension 安全与兼容规范](./runtime-extension-security-compatibility.md)
3. [Session Memory v4 与跨 Run 工作连续性](./session-memory-v4.md)
4. [Session Memory v4 Projection 实施合同](./session-memory-v4-projection-contract.md)
5. [Workbench Shell 与 Workspace Dock](./workbench-shell-workspace-dock.md)
6. [Workbench Shell 迁移规范](./workbench-shell-migration-guide.md)
7. [分阶段实施指南](./extensible-runtime-workbench-implementation-guide.md)

## 12. 外部设计参考

外部框架只验证边界原则，不替代 DBFox 自身实现和测试：

- [OpenAI Agents SDK Context](https://openai.github.io/openai-agents-python/context/)、[Sessions](https://openai.github.io/openai-agents-python/sessions/) 和 [Tool Output Trimmer](https://openai.github.io/openai-agents-python/ref/extensions/tool_output_trimmer/)
- [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [AutoGen Managing State](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/state.html)
- [VS Code Contribution Points](https://code.visualstudio.com/api/references/contribution-points)、[Custom Editor](https://code.visualstudio.com/api/extension-guides/custom-editors) 和 [Extension Host](https://code.visualstudio.com/api/advanced-topics/extension-host)

DBFox 继续拥有自己的 Session、Run、Tool dispatch、Artifact/Evidence、SQL authority、SQLite transaction、SSE replay 和 AgentBench，不引入第二套事实源。
