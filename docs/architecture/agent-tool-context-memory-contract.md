# Agent 工具、上下文与记忆合同

> 文档类型：架构决定与实现合同
> 状态：已接受
> 最后核验：2026-08-28
> 适用范围：Agent Session、Run、Turn、工具、上下文预算、会话档案、工作记忆、历史查找、部分完成与恢复

## 1. 目标

DBFox 的 Agent 必须在长对话、长任务、工具调用、应用重启和模型上下文有限的条件下保持以下性质：

1. 当前用户请求始终是本次执行的最高优先级输入；
2. 完整会话、运行轨迹和查询结果不会因为 Prompt 裁剪而丢失；
3. 模型只接收完成当前决策所需的有界数据；
4. 已完成的 SQL 和工具工作可通过 Artifact ID 复用，不因“继续”而重复执行；
5. 部分完成、失败、取消、审批暂停和进程崩溃具有不同且明确的恢复语义；
6. Memory 不是模型自由书写的事实库，也不替代完整会话档案；
7. Provider Adapter 只转换协议，不决定 DBFox 的任务、记忆和恢复策略。

本合同优先保证长期可维护性和可恢复性，不以一次 Prompt 能容纳全部历史为目标。

## 2. 调研与复用决定

### 2.1 调研来源

- OpenAI Agents SDK Session：每次 Run 前读取同一 Session 的历史并与新输入合并；Run 后保存本次产生的 message、tool call 和 output；输入裁剪不改变完整 Session 档案。
- OpenAI Agents SDK RunState：只用于审批等真正中断的同一 Run 恢复，不把普通后续消息伪装成原 Run。
- OpenAI Responses conversation state：`conversation_id`、`previous_response_id` 是 Provider 侧延续机制，不能与本地 Session 状态无条件叠加。
- OpenAI Responses compaction：压缩项用于降低模型上下文占用，但不能成为 DBFox 业务事实的唯一来源。
- LangGraph：Checkpoint 负责线程内执行恢复，Store 负责跨线程长期信息；二者职责分开。
- AutoGen：显式保存 Agent/Team 状态用于恢复，但不替代应用自己的业务持久化。

### 2.2 采用的方案

继续使用 DBFox 已有的 SQLAlchemy + SQLite 耐久模型和显式 RunLoop：

- `AgentSession` 是对话、输入顺序和单写者租约聚合根；
- `AgentRun` 消费一条正式接纳的用户输入；
- `AgentTurn` 保存一次模型往返的可复现输入边界；
- `AgentMessage` 保存完整、规范的用户可见会话；
- `AgentToolInvocation`、`AgentObservationRecord` 保存工具轨迹；
- `AgentArtifactRecord` 保存可回源结果引用；
- `AgentSessionMemory` 保存有界、可重建的工作投影；
- `ConversationRecallService` 从完整会话档案按需查找早期内容。

### 2.3 不采用的方案

- 不引入 OpenAI Agents SDK Session 作为第二套 Session；
- 不引入 LangGraph Checkpointer 作为第二套 Run/Turn 存储；
- 不引入 Temporal、DBOS 等外部工作流引擎；
- 不让前端或用户选择“继续模式”；
- 不根据“继续”“重试”等字符串建立关键词分类器；
- 不把 Provider response ID 作为 DBFox 本地恢复的唯一权威；
- 不建立向量数据库保存未经验证的模型总结。

这些组件与当前 Runtime 的 Session、lease、fencing、Turn、Tool recovery 和 Artifact 边界高度重叠，直接引入会产生双事实来源和迁移负担。

## 3. 权威对象与关系

```text
AgentSession
├── AgentMessage[]               完整会话档案
├── AgentSessionInput[]          queue / steer / respond 输入
├── AgentRun[]                   每条正式用户请求的执行
│   ├── AgentTurn[]              模型请求与响应边界
│   ├── AgentTaskPlanRecord      当前 Run 的动态计划
│   ├── AgentToolInvocation[]    工具请求和恢复状态
│   ├── AgentObservation[]       有界、可持久的工具观察
│   ├── AgentArtifact[]          可回源结果、SQL、图表和证据来源
│   └── AgentRunItem/Event[]     UI 与 SSE 的规范事件
└── AgentSessionMemory           可重建的工作投影（version 3）
```

不变量：

- 一个 Session 同时最多只有一个活跃 Run；
- 一个 Run 可以有多个 Turn；
- 一个 Turn 可以包含多个 function call；
- function call 与 function call output 必须使用相同 `call_id`；
- 新用户消息在上一 Run 已终止后创建新 Run，但仍属于同一 Session；
- 审批、提问或崩溃导致的未终止执行恢复原 Run；
- SSE 断线只恢复事件流，不创建 Run 或 Turn。

### 3.1 实现索引

| 职责 | 权威实现 | 关键 Symbol |
| --- | --- | --- |
| 输入接纳、排队、steer、租约 | `engine/agent/repositories/session.py` | `SessionRepository.admit`、`consume_steering_inputs`、`claim`、`promote_next_input` |
| Run/Turn 状态与终态原子提交 | `engine/agent/repositories/run.py` | `RunRepository`、`complete`、`fail`、`cancel` |
| 上下文投影 | `engine/agent/context.py` | `ContextAssembler`、`ContextSnapshot`、`PreviousRunOutcome` |
| 上下文预算 | `engine/agent/context_budget.py` | `ContextBudgetPlanner`、`ContextPriority` |
| Prompt 组装 | `engine/agent/prompt.py` | `PromptAssembler` |
| Agent 主循环 | `engine/agent/loop.py` | `RunLoop` |
| 完成判断 | `engine/agent/completion.py` | `CompletionPolicy` |
| 终态回答、Evidence、Memory | `engine/agent/terminalizer.py` | `Terminalizer` |
| 历史召回 | `engine/agent/conversation_recall.py` | `ConversationRecallService` |
| 工具合同与结算 | `engine/agent/tool_dispatcher.py`、`engine/tools/runtime/` | `ToolDispatcher`、`ToolOutcome` |
| Provider 协议转换 | `engine/agent/providers/` | `OpenAIModelAdapter` 等协议边界 |

### 3.2 状态机

Run 状态：

```text
created -> queued -> running
                      ├──> waiting_approval -> running
                      ├──> waiting_input ----> running
                      ├──> cancelling -------> cancelled
                      ├──> completed
                      └──> failed
```

`completed | failed | cancelled` 是终态。`bounded_partial` 不是第四种 Run 状态，而是 `completed` Run 的 `completion_disposition`；它表示事务已完整结算，但业务目标只完成了一部分。

Input 状态：

```text
admitted -> promoted -> consumed
                    └-> cancelled
```

- `queue`：当前 Run 结束后提升为新 Run；
- `steer`：只在活跃 Run 的 Turn 边界消费；
- `cancel_and_replace`：请求取消旧 Run，再接纳新 Run；
- `respond`：回答等待输入的原 Run，不新建业务任务。

## 4. 四个不同的数据层

### 4.1 完整会话档案

权威来源：`AgentMessage`。

保存完整的已接纳用户消息和已完成 Assistant 消息。它用于历史页面、审计、FTS 召回和未来重新构建上下文。不得使用 Memory、摘要或 Provider conversation 替代。

失败或被取消的 Assistant 草稿不进入后续正常历史。

### 4.2 当前模型上下文

权威投影：`ContextSnapshot`。

它是某一 Turn 实际可发送给模型的有界输入，不是完整会话。每个 Turn 持久化 snapshot 和 hash，用于解释模型当时看到了什么。

### 4.3 工作记忆

权威投影：`AgentSessionMemory`。

只保存：

- 当前 datasource ID 与 generation；
- 当前选中和最近引用的 Artifact ID；
- 开放问题；
- 带来源的 Evidence 引用；
- 用户明确确认或 Runtime 能确定性证明的稳定偏好和工作状态。

禁止保存：

- 完整聊天历史；
- 大结果行；
- Provider SDK 对象；
- 未引用来源的模型结论；
- API Key、Token、DSN、Authorization；
- 将模型措辞命名为 `verified_claims`。

Memory 是可删除、可重建的投影。Message、Artifact、Evidence 才是事实来源。

`version 3` 起不再写入 `recent_runs` 或回答摘要。旧版本字段保持惰性并会在下一次成功结算时随投影重写而清除，不需要数据库双写或兼容读取。

### 4.4 执行恢复状态

权威来源：未终止 Run 的规范表状态，包括 Run、Turn、Invocation、Approval、Question、Plan 和 Event。

恢复不能依赖进程内 continuation、Assistant 草稿或 Memory 摘要。恢复 worker 取得新 fencing token 后，根据已持久化状态推进原 Run。

### 4.5 短事务边界

DBFox 不在模型或数据库工具 I/O 期间持有 SQLite 写事务：

1. 短事务接纳 Input、创建 Message 和 Run；
2. worker 通过 Session lease 与 fencing token 取得执行权；
3. 短事务冻结 Turn、ContextSnapshot、Prompt hash 和工具集合；
4. 事务外调用 Provider；
5. 短事务保存响应项或 ToolInvocation；
6. 事务外执行工具 I/O；
7. 短事务结算 Observation、Artifact 和 Invocation；
8. 终态短事务原子提交 Plan、Answer、Evidence、Memory、Run 状态和公共事件。

进程在第 4 或第 6 步崩溃时，恢复依据是已冻结的 Turn/Invocation 记录和幂等合同，不是重放整段聊天。非幂等工具没有可证明的结果时不得自动重放。

## 5. ContextSnapshot 合同

当前结构包含：

```text
session_id / run_id / context_epoch
current_request
consumed_steers
messages
response_batches
selected_artifacts
observations
workspace_context
session_memory
conversation_archive
run_focus
previous_run_outcome
sources / hash
```

### 5.1 优先级

从高到低：

1. System policy；
2. 当前用户请求；
3. Runtime completion guidance；
4. 紧邻失败、取消或有界部分完成的 Run outcome；
5. 用户明确选择的 Artifact；
6. 工作区上下文；
7. 事实上下文；
8. 会话档案元数据；
9. Session Memory；
10. 普通历史消息。

工具 Schema、当前 Run 的原生 response items、function outputs 和 steer 输入必须在预算中提前预留。

### 5.2 当前请求

当前请求不进入普通 history 数组，而以独立、必需的最后一条 user message 注入。旧用户消息只是历史，不能被解释为本次需要同时执行的任务。

当前请求超过预算时只允许在完整结构包裹内截断；不得为了保留旧 Turn 而优先丢弃当前请求。

### 5.3 同一 Run 的原生 Turn transcript

`response_batches` 按 Turn 保存 Responses 原生 items，并补入对应的 `function_call_output`。预算不足时，以完整 Turn batch 为单位从最旧开始移除，不能拆开 function call 和 output。

被移除的 Turn 只保留有界 Evidence ledger：工具、状态、Artifact ID 和进度事实，不保留完整结果行。

### 5.4 跨 Run outcome

紧邻的上一 Run 出现以下情况时，Runtime 生成 `previous_run_outcome`：

- `failed`；
- `cancelled`；
- `completion_disposition=bounded_partial`。
- 已完整完成，并保留至少一个可复用的 Result Artifact。

投影包含：

```text
run_id
status
completion_disposition
limitation_codes
固定公开错误
Plan objective / summary / steps
完成 Artifact 的 ID / type / title / summary
最近有界工具结果
固定恢复说明
```

不得包含失败 Assistant 草稿、Artifact payload、结果行、内部异常、Provider 原始错误或凭据。

该投影是背景，不是自动继续指令。当前用户请求始终拥有更高优先级。

Result Artifact 不因跨 Run 复用而复制。Data 的 `result_inspect`、`result_profile` 与独立
Visualization DLC 的 `visualization_create` 只能读取当前 Run 可观察、同一 Session 且仍满足 Resource
generation 约束的 Artifact。工具在当前 Run 的 Observation 中记录被引用的 Artifact ID；Terminalizer
仅允许这些已观察引用形成当前回答的 Evidence 或块级 Artifact embed。SQL Validation Artifact 和执行
授权仍限定在其原 Run，不能跨 Run 重放。Visualization 也可以使用有界的 `model_knowledge` 或
`user_provided` 数据集，但必须明确事实来源，不能伪装成数据库 Evidence。

`PreviousRunOutcome` 是冻结的 Pydantic 边界模型，`extra="forbid"`。新增字段必须同时修改类型、投影和测试，不能把任意 `result_json` 直接透传给模型。

### 5.5 预算算法

组装过程按以下顺序执行：

1. 预估 tool schema、当前 Run 原生 response items、steer 和 Evidence ledger 的保留量；
2. 将 System policy 与当前请求标记为必需段；
3. 按 `ContextPriority` 从高到低选择可选段；
4. 相同优先级的 history 优先保留 sequence 更新的消息；
5. 输出时恢复原始顺序，避免改变对话语义；
6. 若仍超预算，先按完整 Turn batch 移除最旧原生 transcript；
7. function call 与其 output 永远成对保留或成对移除；
8. 只有当前请求允许在完整 XML 包裹内截断，System policy 不静默截断。

当前 token 估算是 Provider-neutral 的保守 UTF-8 估算。Provider 返回的真实 usage 进入 Run 账本，用于评测估算误差，但不会在不同 Provider 之间伪造精确 tokenizer 一致性。

## 6. 普通后续消息、继续和恢复

### 6.1 普通后续消息

上一 Run 已终止后，任何新用户消息都创建新 Run。运行时不需要判断它叫“继续请求”还是“新任务请求”。同一 Session 的历史、工作集和上一 Run outcome 为模型提供语义背景。

示例：

- “继续”——新 Run 复用上一 Run 的计划与 Artifact；
- “为什么中断”——新 Run 解释 limitation/error，不重新执行；
- “改成只分析退款”——新 Run 以当前请求为准，复用仍相关 Artifact；
- “介绍一下自己”——新 Run 处理新问题，不自动推进旧计划。

### 6.2 同一 Run 恢复

以下情况恢复原 Run：

- 等待审批；
- 等待用户回答工具提出的问题；
- worker 崩溃或 lease 到期；
- Provider stream 中断且 Run recovery policy 允许重新生成；
- 幂等、可恢复的 ToolInvocation 尚未结算。

恢复时继续消费原 Run 的 Turn、Tool、Token、Cost 和 Deadline 预算，不获得新预算。

### 6.3 SSE 重连

客户端按 `snapshot -> cursor replay -> live` 恢复公共事件。重连不影响模型执行状态，不创建新 Run，不重放非幂等工具。

### 6.4 “继续”不需要分类器

| 前一状态 | 新输入如何处理 | 原因 |
| --- | --- | --- |
| 前一 Run 已完整完成 | 新 Run，同 Session | 普通多轮对话 |
| 前一 Run 为 `bounded_partial` | 新 Run，同 Session，并注入类型化 outcome | 取得新预算，同时复用已完成 Plan/Artifact |
| 前一 Run 失败或取消 | 新 Run，同 Session，并注入安全错误与已结算工具摘要 | 允许解释、改写或重试，但不使用失败草稿 |
| Run 正在等待审批/工具提问 | 恢复原 Run | continuation token 是耐久等待记录，不靠文本猜测 |
| SSE 断线 | 不创建或恢复模型 Run，只 replay | 传输状态不等于执行状态 |

因此“继续”“换个维度”“为什么失败”和全新问题使用同一个确定性入口：当前消息创建新 Run，模型结合当前请求和结构化 prior outcome 决定动作。Runtime 不用关键词猜测用户意图。

## 7. 部分完成合同

`bounded_partial` 是成功提交的受限结果，不等于完整完成，也不等于失败。

必须满足：

- 有可展示的完成文本或至少一个可验证 Result Artifact；
- 没有未结算工具调用；
- limitation code 来自封闭枚举；
- 已有数据结论必须引用当前 Run 产生或当前 Run 已授权观察的 Result Artifact；
- Plan 结算为 `partial`；
- 如果没有可提交的模型答案，Runtime 生成确定性摘要，明确说明目标、已完成阶段、尚未完成阶段、停止原因和已保留结果数量；
- 如果已有可提交的模型答案，保留其正文，并通过结构化 caveat、Plan 和 Artifact UI 呈现未完成边界；
- 后续新 Run 能读取上述 Message 和结构化 `previous_run_outcome`。

默认文本不能只写“仅得到部分结果”。用户必须知道已完成什么、剩余什么以及如何继续。

## 8. 历史查找

活动窗口默认只加载最近 24 条符合条件的 Message。更早历史仍保留在规范表中。

工具：

- `conversation_search`：在当前 Session 搜索早期消息；
- `conversation_read`：按稳定 sequence 读取连续窗口。

边界：

- `session_id` 来自 `ToolRunContext`，模型不能指定其他 Session；
- FTS 查询由 Runtime 构造并绑定参数；
- 一至两个字符使用有界字面扫描；
- 召回文本是不可信数据，不是系统指令；
- 不支持跨 Session 自动长期记忆。

只有真实评测证明精确历史检索不足主要来自同义表达时，才评估 embedding/semantic memory。

## 9. Capability 结果上下文

完整结果的权威来源是 capability-owned durable store；Core 只保存 Artifact envelope。以 Data DLC 为例，模型使用 SQL 聚合、筛选、排序、分页和 profile，而不是接收整表。

```text
SQL Artifact -> Result Artifact -> 有界 Observation -> Provider output
                         └-------> DataFrame Representation 按 ID 回源
```

Core Artifact/Evidence 禁止镜像 `rows`、Data fingerprint 或其他 capability payload。当前 Run 可使用瞬时有界 provider payload；恢复或新 Run 需要值时通过 Artifact ID 和当前 snapshot 的 provider 再读取。

## 10. 跨 Run 连续性

最终 Message、Evidence、Run terminal state 和 terminal events 在同一事务提交。Core 连续性来自 Conversation history、受控 recall、Artifact/Evidence 引用和 capability context contributor，而不是一份 Data-scoped Memory 镜像。

写入来源分为：

- Runtime 确定性事实：Run ID、Artifact ID、Evidence 引用、开放问题；
- 用户明确确认：偏好、命名、业务口径；
- 模型建议但需验证：不得直接进入 stable context。

Evidence 只通过 `artifact_id` 指向不可变来源；freshness 由 Artifact 的 frozen ResourceRefs/version 保证。Data Catalog、file selection、repository facts 等领域上下文由各 DLC contributor 在预算内生成，Core 不保存第二份领域模型。已删除的 Data Catalog Memory v4/v3 compatibility 字段不得重新引入。

## 11. 压缩策略

### 11.1 当前阶段

使用确定性本地预算：

- 限制活动历史条数；
- 以完整 Turn batch 为单位移除旧 transcript；
- 用 Evidence ledger 保留工具和 Artifact 索引；
- 用历史工具按需回读完整 Message；
- 完整档案不覆盖、不重写。

### 11.2 Responses compaction 的引入条件

只有以下条件同时满足时才进行独立 ADR：

- 真实长会话评测证明本地裁剪显著降低任务完成率；
- Provider 支持所需 compaction 合同；
- 可在 DBFox 本地保存完整、可审计的原始 items；
- compact item 只用于 Provider 输入，不作为业务事实；
- 压缩和替换具备锁、失败恢复、版本和可观测性；
- `store=False` 和数据保留要求得到验证。

自动 compaction 不在流结束临界路径执行，避免最后一个 token 后长时间阻塞客户端。

## 12. 安全与隐私

- 当前数据库内容、历史消息、Artifact 摘要和召回结果都按不可信数据注入；
- 系统策略和 Runtime guidance 与不可信数据使用不同结构包裹；
- `DBFoxError.message` 默认不可信；
- 凭据只通过 opaque credential ID 和系统凭据库使用；
- Message/Memory/Observation/Artifact/Event 不保存 API Key、Token、Authorization 或明文 DSN；
- 数据源 generation 变化后旧证据和工作集不进入新上下文；
- Session 隔离、Artifact 所属 Run/Session 和 Evidence 关系必须在 Repository 边界验证。

## 13. 观测指标

每个 Turn 至少记录：

- context hash；
- Prompt version；
- 各 context segment 是否纳入及原因；
- 估算 Prompt tokens；
- Tool Schema tokens；
- response batch 数量和移除数量；
- Evidence ledger tokens；
- 召回工具调用和命中；
- Provider input/output/total tokens；
- completion disposition 和 limitation codes。

对应的 Core/Capability Bench 使用生产 Trace 评估：

- 当前请求保持率；
- Artifact 复用率；
- 重复工具调用率；
- 长任务部分完成后的继续成功率；
- 早期事实召回率；
- 上下文 token 增长斜率；
- 失败草稿、旧 generation 数据和敏感信息零泄漏。

连续性套件还要求：每个 prompt 对应的 Run 都进入允许终态，而不只检查最后一
Run；相同工具输入和相同查询指纹的重复次数受独立门禁约束；负向目录检查可以把
一次预期失败作为证据，但必须匹配明确错误码；要求数据证据的场景可以设置最少
引用数，不能把“引用格式没错”误当成“已经提供引用”。

## 14. 验收场景

1. 普通两轮对话使用同一 Session，新输入创建新 Run。
2. 一个 Run 内多 Turn 的 function call/output 保持配对。
3. 24 条窗口外的精确历史可以通过会话工具找回。
4. `bounded_partial` 后输入“继续”，下一 Run 能看到 Plan、Artifact ID 和 limitation，不重跑已完成 SQL。
5. `bounded_partial` 后输入新问题，当前请求优先，不自动执行旧计划。
6. 失败 Run 的草稿不进入历史，但固定错误和最近工具状态可见。
7. 取消 Run 不提交半截回答。
8. 审批后恢复原 Run，不创建第二个工具调用。
9. SSE 断线重连只 replay 事件。
10. worker 崩溃后恢复时继续原预算和 fencing token。
11. 数据源 generation 改变后旧 Artifact 工作集和 Evidence 不进入上下文。
12. Prompt 超预算时先移除旧完整 Turn，当前请求和系统策略保留。
13. 大结果行只存在于瞬时有界 payload 或 DataFrame Representation response，不进入耐久控制面。
14. Memory 更新与 Answer、Evidence 和 Run completion 原子提交。
15. 删除 Session 后，Message、Memory、FTS 投影和相关运行记录按合同删除或不可访问。
16. 已完成 Run 的 Result Artifact 可由下一 Run 读取，但跨 Session、跨 generation、未来 Run 或未终态 Run 均拒绝。
17. 跨 Run 结果形成的 Evidence 属于当前回答，Artifact 身份与所有权仍属于原 Run。

## 15. 演进路线

### 当前收敛

- 保留现有 Session、Run、Turn 和本地 Memory；
- 将 `bounded_partial` 纳入上一 Run outcome；
- 投影 Plan 与 Artifact 索引，不复制 payload；
- 改善部分完成 Message，使普通 Session 历史足以支持继续；
- 增加跨 Run 连续性和不重复执行测试。

### 后续按证据推进

- 用真实长任务 Trace 建立 token 增长和 continuation 基线；
- 根据评测决定是否增加确定性本地摘要；
- 只有本地裁剪证据不足时评估 Responses compaction；
- 只有跨 Session 同义召回是主要缺口时评估 semantic memory；
- 只有运行形态变成多节点分布式服务时重新评估外部 durable workflow。

任何演进都不得增加第二份 Session、Artifact、Memory 或工具执行事实来源。

## 16. 参考资料

- [OpenAI Agents SDK：Sessions](https://openai.github.io/openai-agents-python/sessions/)
- [OpenAI API：Conversation state](https://developers.openai.com/api/docs/guides/conversation-state)
- [OpenAI API：Compaction](https://developers.openai.com/api/docs/guides/compaction)
- [LangGraph：Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [AutoGen：Managing State](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/state.html)
