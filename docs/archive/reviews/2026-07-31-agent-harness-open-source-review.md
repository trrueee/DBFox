# DBFox Agent Harness 开源对标与剪枝审查

> **状态：历史归档。** 本文绑定原设计、计划或评审基线，仅用于追溯；当前事实见[架构导航](../../architecture/README.md)。下方原状态只代表当时。

> 审查日期：2026-07-26  
> 范围：Context、Memory、Model/Tool Loop、Completion、Artifact/Evidence、Event/SSE、前端交互与可观测性

## 1. 结论

DBFox 不需要再增加 Intent Router、Planner Graph 或关键词分类器。合适的主干是：

```text
Session → Run → Turn → typed items
                    ├─ reasoning_summary（可选）
                    ├─ plan（复杂任务可选）
                    ├─ tool_call → observation → artifact
                    ├─ approval / question
                    └─ final_answer
```

模型在统一的 model/tool loop 中决定是否使用工具；Runtime 只执行确定性的安全、
预算、状态和证据规则。产品 UI 投影 typed items，不从 Turn 数量或工具数量猜测
“思考阶段”和“完成进度”。

这与 Codex 的 Thread → Turn → Item、OpenCode 的 Session/Message/Part 和显式
tool part 状态机一致，同时保留 DBFox 的数据库安全链、generation-aware Memory、
Reference-only Artifact、Evidence 引用和动态 `plan_update`。

## 2. 对标依据

- [Codex app-server](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md)：
  Thread、Turn、Item 是公开协议；plan、reasoning、command、file change 和 agent
  message 是不同 item，started/delta/completed 有稳定身份。
- [Codex protocol](https://github.com/openai/codex/blob/main/codex-rs/docs/protocol_v1.md)：
  UI submission 与 Agent event 使用独立队列，Turn start/complete、approval、
  plan delta 和 agent message delta 是不同事件。
- [Codex compaction](https://github.com/openai/codex/blob/main/codex-rs/core/src/compact.rs)：
  长上下文压缩围绕 canonical history 进行，并保持真实用户消息的顺序和身份。
- [OpenCode prompt loop](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/prompt.ts)
  与 [processor](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/processor.ts)：
  模型、工具和终止在显式循环中处理；tool part 有 pending → running →
  completed/error 状态，循环保护是安全网，不是业务意图分类器。
- [OpenCode run UI](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/cli/cmd/run.ts)：
  text、reasoning、tool、step start/finish 分开渲染，Session idle/terminal 决定结束。

## 3. 本轮已执行的剪枝

| 问题 | 处理 |
|---|---|
| 用户文本关键词决定 TaskKind 和 Completion 证据要求 | 删除分类器和 TaskKind 路由；Completion 只读真实模型输出、Observation、Artifact 和预算 |
| canonical history 与 Session Memory 重复注入最近回答 | 模型 Context 不再注入 `recent_runs` / `conversation_summary`；仅保留 generation 匹配的工作集和已验证事实 |
| 每个 Turn 自动生成“正在理解/已完成分析” | 删除 synthetic Turn Activity；只有真实 reasoning summary 才生成 reasoning Activity |
| 任意 Activity 显示 `X/Y`，冒充任务进度 | 删除；只有 versioned `plan_update` 展示步骤进度 |
| 固定工具顺序、至少两次搜索、30 表阈值、强制 review | 从 Prompt 删除；改为最小充分工具使用和结果驱动继续 |
| `escalate_tool_group` | 删除；生产 Registry 已包含全部实际工具组，升级工具没有可升级目标 |
| `ArtifactSpec` | 删除；该声明未被 Runtime 使用，且 `table` 声明与真实 `result_view` 产物不一致 |

## 4. 应保留的 DBFox 特色

- Session 单写者 lease、取消传播、短事务和可恢复等待状态；
- immutable Tool Materialization、canonical input、SQL validate → execute 绑定；
- typed Observation capability，而不是从工具名或用户关键词猜任务类型；
- Reference-only Artifact、Result Gateway、Artifact Relation 和 claim-level Evidence；
- 动态 `plan_update`：模型仅在真实多步骤任务中创建，稳定 step ID，版本化持久化；
- committed event + cursor replay + bounded live delta 的 SSE 恢复模型；
- Run → Turn → Model/Tool → Policy/Approval 的开发者 Trace。

## 5. 仍需收敛的设计

### P0：最终回答与工具轮 commentary 的流语义

当前 OpenAI-compatible Chat Completions adapter 把所有 `delta.content` 都标为
answer。Runtime 在流结束前不知道该 Turn 是否还会产生 tool call，因此可能先把
工具轮文字显示成回答，再在下一 Turn 清空。这正是“偶尔出现一段不知道做什么的
文字”的根因。

目标不是增加文本启发式，而是升级 provider-neutral item 协议：

```text
reasoning_summary.delta  → Activity（可选）
tool_call.delta          → Tool item
agent_message.delta      → Final/committed answer item
```

支持 typed provider event 的 adapter 应直接映射；只提供 Chat Completions 的
adapter 必须把混合 text/tool-call Turn 标为 ambiguous，不能把它当 final answer。
前端只对 `agent_message` item 做回答流式渲染。不得用延迟毫秒数、字符数或关键词
猜测“这是不是最终答案”，也不得在完成后重播假流式动画。

### P1：Artifact 投影所有权

当前 Artifact 真实投影集中在 `ArtifactRepository.project_tool_result`，其中包含
核心 SQL/Result/Chart 工具分支。这对封闭的内置工具是可控的，但不适合作为插件
扩展边界。

下一步应让工具定义拥有 typed artifact projector，并由 Runtime 调用该 projector；
ArtifactRepository 只负责 payload 校验、关系、版本、事务和事件。只保留一个
projector 注册来源，不能同时维护 `ArtifactSpec`、Repository 工具名分支和前端映射。

### P1：长历史压缩

当前 bounded canonical history 是正确的，但超过窗口的旧消息只是被丢弃。需要
长会话时，应新增“仅覆盖被淘汰历史”的 compaction record，记录 source range、
版本和 hash。compaction 不得复制仍在窗口内的最近问答，也不得保存数据库结果行。

### P2：清理未接入的设计草稿

未接入 RunLoop 的 `engine/agent/planning/AgentPlanDirective` 和内部 skill
registry 已删除。评测目录里的旧 Planner expectation 仍是非生产兼容字段，不应被
描述为现有 Agent 能力；迁移评测数据后可继续删除。不要为了让旧字段“有用”而重新
增加 Planner Router。

## 6. 产品展示规则

- 活跃 Run 无 typed item 时，只显示真实 lifecycle 状态“正在分析”，不生成阶段名称；
- reasoning summary 只有 provider 明确提供时才展示，完成后保持稳定摘要；
- tool item 展示用户能理解的动作、状态、耗时、失败原因和恢复动作；
- plan item 是唯一可展示步骤完成比例的对象；
- safety Artifact 默认 internal，SQL 默认 supporting，Result/Chart 默认 primary；
- 最终回答与 Activity 分离；Run terminal 不等于最后一个 Turn completed；
- 默认展示稳定摘要，完整 raw event/trace 只进入开发者诊断页。

## 7. 完成语义

CompletionGate 只允许以下确定性输入：

1. 是否仍有待结算 tool call / approval / question；
2. 是否存在非空 answer candidate；
3. 当前 Run 的成功 Observation 与 Artifact；
4. 引用是否来自本 Run 已观察到的 Result Artifact；
5. Turn/Tool/Token/Cost/Deadline/No-progress 预算。

它不得读取自然语言关键词，不得按“分析/结构/环境”分类，不得要求一个模型自报的
review 或 provider finish reason 来证明完成。`analysis_review` 可以提高 Evidence
定位质量，但不能决定 Run 是否完成。
