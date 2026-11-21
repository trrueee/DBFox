# Agent 连续执行上下文与进度判定

> 文档类型：架构说明
>
> 状态：当前
>
> 最后核验：2026-11-21

本次属于 Kernel 内部正确性修复，不新增 Runtime、领域控制流或公开 API。真实客户端 Run `run_f0270941f2114ce7a11aafb50028af56` 在 17 个 Turn 中执行了 17 次场景检查、6 次计划更新，只创建空场景和两个材质，随后被人工取消。该记录消耗 534020 个输入/输出 token；没有 Provider 重试或协议修复。不能把这些空转记作创作完成。

## 已确认的原因

- 52 个原生工具定义约占 24259 token。旧 32768 输入上限下，第 10 个 Turn 将 9 个完整原生历史 batch 全部丢弃，`response_item_tokens=0`；这不是模型没有收到工具输出，而是后续模型请求不再携带完整的调用连续性。
- 进度指纹包含可随时重写的计划目标、步骤文案、状态和摘要。没有新增工具事实的改写也会改变指纹、重置停滞计数。计划仍是耐久控制状态，但它自身不证明任务有实际推进。

## 修复后的实际结果

同一隔离客户端、相同 `deepseek-v4-flash` 与凭据，用户级续作请求触发 `run_f05d55ba437441e99d8288ac16121b37`，耐久状态为 `completed`：21 Turn、23 次工具调用（22 成功、1 次输入拒绝后自行改正），产出 35 对象 / 6 材质的固定 Scene v10，以及通过该公开成果绑定 `clock.pendulum` 的 Animation v8。Agent/Prompt 版本均为 4.1；最后请求估计 55284 token，其中原生历史 24164、schema 24259，未省略历史 batch。人工仅提交需求、观察、下载和播放，没有补建内容。

这不是低成本或视觉质量已通过的证明：本次续作累计消耗 936215 token，Agent 没有渲染截图/播放回执能力，完整三维动画还没有实际播放验收。64K 是明确的容量与成本权衡，不能替代工具发现能力或宣称所有扩展可同时运行。显式 32K 组合回归确认在最近完整历史无法保留时耐久失败，不自动放大预算。

核心确定性集合 375 passed / 2 deselected，Scene/Animation 与注册合同 12 passed，额外三/四工作室、Story/Comic、Pixel/Game 和 Animation 红队集合 19 passed。原始失败、真实 Run 与下载审计见[连续产品使用第六阶段](../quality/continuous-product-use-20261107.md)。

## 决策与边界

1. **正确性与通用变化轴。** 上下文预算和进度保护属于已有 Core 职责；相同缺陷影响任何多能力、长响应或重复规划任务，与 Scene/Animation 类型无关。
2. **复用调查。** 沿用 `ContextBudgetPlanner`、完整 `ResponseItemBatch`、已有 native tool search、`ProgressGuard` 和耐久 `record_progress`。参考 OpenAI 官方原生 reasoning/function calling 上下文要求，以及 LangGraph/AutoGen 的有界终止设计；不引入这些框架作为新依赖。
3. **owner 源头。** DLC 无法控制 Core 在预算时删除原生调用历史，也不能决定哪些通用记录重置停滞计数。因此不在每个 DLC 增加重试、隐藏写入或“直接完成”提示来掩盖问题。
4. **最小修复。** 仍只从最旧的完整 Turn 淘汰历史，但不能清空最新完整 Turn。其与当前请求无法同时放入预算时，复用现有 `AGENT_CONTEXT_BUDGET_EXCEEDED` 耐久失败路径。默认单次输入上限从 32768 调到 65536，以容纳已实测的两能力完整工具集和最近调用；调用数、轮数、超时、单独配置的 token/cost 上限继续生效。显式设置的小输入上限不会被自动提高。支持 native search 的模型继续使用现有按需加载；未知模型名仍发送完整 schema，不替换模型或猜测端点能力。
5. **进度唯一事实。** 指纹继续由已持久化的规范 Artifact 和贡献进展的 Observation 组成。计划的文字或状态变化不再独立重置停滞保护；计划依赖的实际工具结果仍会贡献进展。计划本身、UI 和完成约束继续保留。
6. **兼容性与债务。** 不改 authority、审批、取消、幂等、公开工具合同、Artifact envelope、API v2、数据库 schema 或 Provider 原生 item。没有新增 mapper、fallback、镜像状态或迁移。版本化 Agent 定义和 Prompt 标识随默认策略/装配修复递增；已取消的真实 Run 不自动恢复或重放写入。成本风险是允许更长的单次输入，收益与限制通过真实 Run 的预算遥测和调用数检查，不宣称已经解决任意数量扩展的上下文容量。
7. **验证与退出。** 三条改前失败反例覆盖计划空转、最新 native batch 不可静默丢失，以及大型能力清单下的连续性。另跑 Core、原生 Provider/取消/完成合同和 Scene/Animation 组合；实际客户端后续请求继续操作 Agent 已创建的作品，禁止人工补内容。没有临时层需要退出。

参考：[OpenAI reasoning items](https://developers.openai.com/cookbook/examples/responses_api/reasoning_items)、[LangGraph recursion boundary](https://reference.langchain.com/python/langgraph/errors/GraphRecursionError)、[AutoGen termination](https://microsoft.github.io/autogen/dev/user-guide/agentchat-user-guide/tutorial/termination.html)。官方资料支持保留原生上下文及有界运行原则；具体预算和进度指纹规则来自本项目的真实失败与本地合同。

## 运行反馈与最终整理（2026-11-21）

前述记录保留 11 月 8 日的历史测量。本次使用部署中的本地 4B 复现了另一处通用缺陷：
Runtime 的引用修复要求出现在当前请求和原生历史之前，末尾却是刚被拒绝的 Assistant
回答。真实模型反复只补引用或产生空输出；更长的格式说明也未证明更可靠。

首个增量 Prompt 4.7 的规范顺序为：预算规划后的上下文、Evidence ledger、完整原生响应
batch、当前 Runtime completion feedback、已消费的用户 steer。反馈仍来自唯一耐久
`Run.focus`，只在 Prompt 中表达一次，不提升为 system 指令或修改原生响应。其 tokens
作为必需项预留并记录 `run_focus_tokens`；预算不足明确失败，不静默丢弃反馈。

有可核验成果但回答未满足引用合同，与没有成果是不同状态。现有 CompletionSupport
继续决定是否存在可用耐久工作；Core 不检查领域 payload。到停滞边界时：

1. 合法回答可按既有规则交付；不合法回答只返回 `REPAIR`，不能成为 bounded partial。
2. 尚未最终整理且原预算仍有剩余时，进入已有 `synthesize` 阶段，保留具体拒绝原因、
   缺失项与真实引用 ID。该阶段不物化新的能力工具，不重跑已有查询。
3. 最终整理后仍不合法就失败；预算用尽不能将 `REPAIR` 当作成果发布。不存在增加轮次、
   重置停滞计数、拼接引用或自动生成结论的兜底路径。

最终整理中的后续反馈保留 `Run.focus.kind=synthesize`，只更新缺失项和原因。恢复 worker
仍从同一耐久事实得到最终整理阶段，不能因修复反馈覆盖标记而重新开放能力工具。

这是 Kernel 正确性修复：停滞、Prompt 顺序和终结资格属于既有 Core；DLC 不能修复
Runtime 提前拒绝整理的分支。复用 `Run.focus`、CompletionSupport、`CompletionKind.REPAIR`
与既有最终整理物化限制，不增加 API、schema、第二套状态、兼容层或领域关键词。
变更既适用于文本分析，也适用于有工件的其他能力。安全依据仍是原有引用/授权校验；
进入修复阶段不构成发布许可。测试覆盖修改前失败、正确修复、修复仍失败、引用独存、
精确一次工具结算与工件保留；本地模型效果单独记录于
[Phase 0 质量记录](../quality/local-data-phase0.md)，不把脚本模型通过视为真实模型可靠。

## 计划与完成合同（首次落地于 Agent 4.3 / Prompt 5.0）

代码审查确认另两个通用缺口：当前 `agent_task_plans` 没有独立进入 Context，模型只能从
可能被淘汰的 `update_plan` 历史中找计划；`Terminalizer` 则会在结束 Run 时把未执行步骤
自动改为 skipped，并把计划标为 completed。后者把“模型文本结束”变成了计划完成依据。

当前实现复用现有 TaskPlan、PlanRepository 和完成链：

1. `PlanRepository.current` 是同一计划表的规范读取，`ContextSnapshot.task_plan` 是带版本的
   冻结投影。它不增加计划数据库或第二份状态权威。
2. Prompt 在原生历史之后呈现最新计划、随后呈现 Runtime feedback 和用户 steer。计划
   全量计入必需预算，不能靠丢弃计划来放入更多历史；预算不足走既有明确失败路径。
3. CompletionPolicy 拒绝未结清计划的完整交付；预算结束时也不能把不合格正文提升为
   部分成功。Terminalizer 的最终事务重新检查当前计划，PlanRepository 自身还禁止完整
   结束操作代替生产者跳过未执行步骤。完成要求由实际计划更新及原有证据规则满足。
4. 无计划的直接回答保持原行为，不要求所有问题都调用工具或生成计划。显式修订、明确
   跳过不再需要的步骤，以及失败、取消、bounded partial 的既有终结语义保留。

`is_settled` 只表示生产者显式结清了这份计划，不证明计划正确覆盖用户目标，也不证明
某个 Artifact 支持全部业务结论。没有声明计划、事后补写计划或错误解释用户目标，仍须
由任务验收和领域完成约束发现，不能用 SQL/文件关键词或每个测试 case 的特例掩盖。

### Kernel 变更依据

1. 计划上下文和终结完整性是已有 Core 正确性职责，同时影响数据、开发、内容等能力。
2. 既有 DLC CompletionConstraint 无法阻止 Core 在最后事务里把未执行步骤自动跳过，也
   无法补回未送入模型的 Core 计划，因此不能逐个 DLC 加补丁。
3. 在 Plan owner 和既有 Context / Completion / Terminalizer 修复，不新增任务编排器。
4. 没有业务类型、模型名称或供应商判断；SQL、文件和其他领域内容仍由 owner 校验。
5. 无新依赖、映射、兼容层或镜像存储。一次额外模型自评实验因未达标已从产品撤回；
   实验记录不构成默认 Runtime 能力。
6. 不改工具输入、公开 SDK 表面、HTTP API 或数据库 schema。新 Snapshot 字段可选，历史
   记录保持原样；重启从同一计划表恢复，不自动重放任务。新策略用版本标识区分。
7. 验证包括改前失败反例、真实事务保护、跨任务脚本模型、当前计划顺序/预算、生产
   解释器、现有组合场景和真实本地模型；具体结果和未通过项见 Phase 0 质量记录。

复用调查参考 [Pydantic AI 输出验证](https://pydantic.dev/docs/ai/core-concepts/output/#output-validators)
与 [OpenAI Agents 输出 guardrails](https://openai.github.io/openai-agents-python/guardrails/#output-guardrails)。
本项目采用可程序验证的状态约束，没有引入其框架，也没有把另一次模型判断当作正确性证明。

## 结构化答案提交（Agent 4.4 / Prompt 5.1）

本节记录首次落地版本；当前输入准入合同见下节。

模型可以通过原生 `submit_answer` 函数提交完整 Markdown 及其来源。输入只有有界的
`parts: [{text, citations: [artifact_id]}]`：片段按原样连接，调用者显式保留换行；引用附在
对应片段后。引用片段应是可以独立阅读的结论，先闭合 Markdown 代码、链接等结构，
再引用。模型不能传入 Evidence、来源位置、授权、完成状态或限制代码。

`AnswerSubmission` 是这一条模型到 Runtime 边界的规范输入，不是另一份答案事实源。
Registry / Policy / Invocation / Observation 仍先验证并结算。该控制命令必须单独调用，
不能与尚待执行的工具或计划更新混在同一响应中；输入不合法、来源不可用或内部工件
引用，均通过现有工具错误反馈修正。命令成功只表示候选被接收。

RunLoop 从成功结算的 Core Invocation 读取候选，继续走原有 CompletionPolicy、DLC
CompletionConstraint、TaskPlan 和 Terminalizer。持久 Invocation 参数是候选的唯一来源；
原始 Responses function_call 不改写为伪造的 assistant message。恢复时同一 Repository
可重新读取已结算候选，不重放副作用，也不直接批准成功。新模型轮次仍受原预算控制。

Terminalizer 根据实际可访问工件再次校验身份，生成原有正文引用标记和服务端 Evidence。
结构化引用的 label 来自明确提交的片段，定位仍为 Artifact 级，不猜测页、行或单元格。
无法解析的来源不再被悄悄从最终正文删掉。后续仍使用原有 ComposedResponse、RunItem、
SSE、历史 snapshot 和 Dock 入口。普通无来源解释可以直接输出文本；已有正文引用格式
也是现行输出合同，历史记录无需迁移。

### 调查与 Kernel 变更依据

1. 来源交付是数据、文件、代码执行和内容成果共同需要的边界。特殊引用标记由模型直接
   书写，易与自由 Markdown 混淆；DLC 无法为所有最终答案统一修复该 Core 表达问题。
2. 复用现有严格 Pydantic 输入、原生函数调用、控制命令、完成约束和 Evidence。对照
   [Pydantic AI Tool Output](https://pydantic.dev/docs/ai/core-concepts/output/#tool-output)
   的类型输入验证，以及 [Ollama 工具调用](https://docs.ollama.com/capabilities/tool-calling)。
   只借鉴边界模式，不引入这些框架，也不要求 Provider 额外实现 JSON response format。
3. 能力 owner 继续负责计算和领域正确性；此改动不增加 SQL、文件类型或模型名称分支。
4. 结构合法、来源身份真实与任务语义正确分开验证。链接并不证明被引用工件支持该句
   结论；新入口不替代业务 oracle 或未声明的自然语言目标验收。
5. 无新增依赖、答案表、兼容映射、自动引用修补、额外模型审核或第二套 RunLoop。
   输入与可信 Evidence 是不同信任边界，并非镜像持久模型。
6. 唯一新增模型可见入口为 `dbfox.core/submit_answer@1`；内置注册指纹相应更新。
   无公开 API v2 导出、HTTP、前端 SDK 或数据库 schema 变更。旧 DLC 无需修改；冻结的
   历史 Turn 保留原工具物化，不因新入口而重放。
7. 验证覆盖真实结算、原生记录保留、引用 claim 与位置、非法来源、混合批次、计划门禁、
   恢复、取消，以及原有 Core / composition / 前端引用导航。真实本地模型结果单独记录
   于 [Phase 0 质量记录](../quality/local-data-phase0.md)，不以类型检查代替产品验收。

## 输入准入时冻结的答案要求（Agent 4.5 / Prompt 5.2）

`ConversationInputRequest.answer_requirements` 是可选的用户任务合同。当前只有一个字段：
`evidence = when_observed | required`。它要求需要证据的答案使用原生 `submit_answer`，在
明确片段上给出实际已观察的公开 Artifact ID。`when_observed` 在未观察到公开工件时允许
直接回答；`required` 即使暂时没有来源也不能完成，必须先取得已授权证据。两者都不
扩张资源权限，不要求普通解释创建工具结果，也不证明用户的业务目标已实现。

当前桌面在新建/替换任务时发送 `when_observed`；steer / respond 保留原任务合同。旧客户端
不传该字段、历史 Run 没有该字段时保留原语义，已有 DLC 的完成约束始终继续生效。
显式尝试在 steer 中改变当前合同会被拒绝；不能通过计划、工具输出、来源文字或答案
参数放宽合同。省略合同不是对已有合同的撤销。新客户端遇到不认识该字段的旧 Engine
会得到正式请求失败，不自动删字段重发。

### 唯一事实源与完成路径

1. API 用同一 Pydantic 模型校验，SessionRepository 把规范值纳入输入幂等指纹并保存到
   原有 `AgentRun.request_json`；没有新需求表或第二份耐久状态。
2. ContextAssembler 从该 Run 读取合同，快照同时包含已观察公开工件的事实和当前实际
   可引用 ID。候选来自成功 Observation，并复用现有 Artifact/Resource 权限证明。
   内部工件不要求用户引用；选中但未实际观察的历史工件不自动成为证据。
3. 已观察与当前可访问是两件事。撤销访问后，来源可能不再可引用，但不能因此把原有
   交付要求抹掉。完整 Observation 历史是依据，模型的历史窗口裁剪不是权限边界。
4. Prompt 在原生历史之后给出合同与至多八个来源示例，单独预留必需预算并记录
   `answer_requirements_tokens`。示例是有界提示，完整验证仍使用规范来源索引。
5. CompletionPolicy 根据合同与真实来源检查结构化候选。原始 ID、伪工具文本、普通引用
   标记或 Artifact embed 不代替结构化交付。缺失时在原有修复/整理预算内纠正；预算耗尽
   不能把不合格答案或自动生成的部分摘要改称成功。
6. Terminalizer 的原有最终写事务再次读取合同、来源及已成功结算的 Core 提交。提交正文
   必须与待发布正文相同，服务端 Evidence 必须包含对应来源；入口校验通过后换正文、
   缺失 Evidence 或绕过完成判断的其他调用路径不能发布成功。

合同检查的范围是结构与来源身份。可点击引用不能证明数值、因果推断、测试充分性或
全部自然语言要求正确；这些仍由相应能力 owner 和独立验收验证。没有额外模型裁判，
也没有根据 SQL、语言、文件名或测试题目推断新的完成条件。

### Kernel / API 变更依据

1. 文件、数据和生成成果都存在“内容已产生，交付未完成”的共同边界；这是实际通用
   变化轴，不是为某个任务增加专用执行规则。
2. 既有 CompletionConstraint 可表达能力规则，但没有正式的输入合同来源；纯提示词
   和模型声明无法成为可信完成依据。复用完成链，不新增任务框架或审核 Agent。
3. 能力 owner 继续拥有领域事实。公共合同只表达结构化来源交付，不进入任何业务领域。
4. 合同由已认证的输入准入产生，当前可引用来源继续经过原有 ResourceRef / Artifact
   权限证明；无来源、无权限与未观察到的工件不靠模型补全。
5. 没有新依赖、mapper、兼容映射、双写或永久 fallback。Context 与 UI 仍只是投影；
   `observed_artifacts_for_run` 在原有 Repository 复用相同解析和权限规则。
6. HTTP 输入增加一个可选字段，按正式流程重新生成 API client；无数据库 schema、
   API v2 导出或前端 SDK 变化。旧记录不回填新要求，旧 DLC / 冻结 Tool 合同不改写。
7. 回归覆盖输入冻结/steer、无来源直接回答、来源已观察但撤销、历史裁剪、内部工件、
   预算/部分交付、真实工具结算、最后事务正文替换，以及 API/前端入口。真实模型固定
   任务与尚未通过项见 [Phase 0 质量记录](../quality/local-data-phase0.md)。

调查复用原有准入、Context、完成约束、Artifact Repository 和 Terminalizer。对照
[Pydantic AI 输出验证与校验上下文](https://pydantic.dev/docs/ai/core-concepts/output/#output-validators)
及 [Anthropic 对清晰验收条件的说明](https://www.anthropic.com/research/building-effective-agents)，
采用确定性的合同检查，不引入其框架或新的推理循环。
