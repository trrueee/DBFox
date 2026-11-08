# Agent 连续执行上下文与进度判定

> 文档类型：架构说明
>
> 状态：当前
>
> 最后核验：2026-11-08

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
