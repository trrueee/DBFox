# 卷五：Agent Harness 与 Provider

> 文档类型：实现指南
>
> 状态：当前
>
> 最后核验：2026-08-12
>
> 适用范围：Agent 调度、运行循环、模型服务和完成判断
>
> 权威合同：[Agent Runtime](../architecture/agent-runtime.md)、[Runtime Item 协议](../architecture/agent-runtime-item-protocol.md)、[Agent 规范](../specs/agent.md)
>
> 核心入口：[`engine/agent/coordinator.py`](../../engine/agent/coordinator.py)、[`engine/agent/loop.py`](../../engine/agent/loop.py)、[`engine/agent/providers/openai.py`](../../engine/agent/providers/openai.py)

## 1. 什么是 Harness

这里的 Agent Harness 不是一个 Prompt 文件。它是保证模型可以稳定工作的完整运行系统：

- 接收并持久化用户输入；
- 调度 Run；
- 组装每个 Turn 的 Context 和工具合同；
- 调用 Provider；
- 翻译 provider-neutral response items；
- 执行/恢复工具；
- 处理审批、提问、取消、重试和预算；
- 决定继续还是完成；
- 原子写入最终消息、Evidence、Memory 和 Event；
- 让 UI 断线后恢复。

模型能力上限很大程度取决于 Harness 是否提供正确状态、工具反馈和恢复边界。

## 2. 领域对象关系

```text
AgentSession
  ├─ AgentSessionInput 1..n
  ├─ AgentMessage 1..n
  ├─ AgentRun 1..n
  │    ├─ AgentTurn 1..n
  │    ├─ AgentToolInvocation 0..n
  │    ├─ RunItem 1..n
  │    ├─ Evidence 0..n
  │    └─ Artifact ref 0..n
  ├─ AgentEventRecord 1..n
  └─ AgentSessionMemory 0..1
```

一个用户 Input 通常对应一个 Run；一个 Run 可以包含多个 Turn；一个 Turn 可以发出多个工具调用。

## 3. 输入 admission

### 3.1 API 命令边界

对话输入由 [`engine/api/conversation_commands.py`](../../engine/api/conversation_commands.py) 接收，先校验：

- Session 存在且未删除；
- datasource 归属/可用；
- 模型配置和 credential 引用；
- 输入大小与格式；
- 幂等/admission 标识。

然后调用 `SessionRepository.admit`。

### 3.2 `SessionRepository.admit`

在一个事务中创建或复用：

1. `AgentSessionInput`；
2. canonical user message；
3. pending assistant message 占位；
4. queued AgentRun；
5. 初始 RunItem/Event；
6. 单调 sequence。

重复 admission 应返回稳定 ids，不应创建两次 Run。commit 后 API 调用 `coordinator.wake(session_id)`；即使 wake hint 丢失，数据库 queued Run 仍是耐久事实。

## 4. Coordinator：有界内存，数据库耐久队列

[`engine/agent/coordinator.py`](../../engine/agent/coordinator.py) 的 `SessionCoordinator`：

- worker 数有上限；
- 内存只保存有界、可合并的 Session wake hints；
- 从数据库发现 queued/recoverable Run；
- 同一 Session 通过 lease 串行拥有；
- heartbeat 续租；
- 进程重启后可从数据库继续；
- stop 时停止调度并有界等待。

### 4.1 为什么数据库才是队列

如果内存 queue 是唯一事实：

- Sidecar 崩溃会丢任务；
- 多实例无法正确竞争；
- API commit 和 enqueue 之间存在丢失窗口；
- 无法审计“输入已收但为何没运行”。

DBFox 的 wake 只是降低扫描延迟。真正可运行工作由持久化状态决定。

### 4.2 `_drain_session`

worker 的典型流程：

1. claim Session lease；
2. 启动 heartbeat；
3. 找到下一条可执行 Run；
4. 调用 `RunLoop.execute`；
5. 正常完成、等待或失败后更新状态；
6. 异常经过 Terminalizer 形成稳定失败；
7. 停止 heartbeat，释放/让 lease 到期；
8. 若 Session 还有工作则再次调度。

## 5. RunLoop 总体状态机

[`engine/agent/loop.py`](../../engine/agent/loop.py) 是显式循环，而不是隐藏在某个框架 checkpoint 中。

```text
queued
  → running
  → prepare turn
  → call provider
       ├─ tool calls → persist invocations → execute → next turn
       ├─ clarification → waiting_question
       ├─ approval → waiting_approval
       ├─ final text → completion policy → complete
       ├─ repairable contract issue → repair → next turn
       ├─ cancelled → cancelled
       └─ provider/protocol failure → failed
```

循环每个阶段都检查：

- Session lease 是否仍有效；
- cancel 是否请求；
- Turn/工具/repair/token/cost 预算；
- 是否有待恢复 ToolInvocation；
- 是否已经进入终态。

## 6. Turn 准备

`RunLoop._prepare_turn` 在短事务中：

1. 消费符合条件的 steer 输入；
2. 调用 `ContextAssembler`；
3. 构造 WorkingState；
4. 根据 AgentDefinition、mode、tool group 物化工具；
5. 调用 `PromptAssembler`；
6. 记录 Context snapshot/hash；
7. 记录 Tool materialization/hash；
8. 创建 AgentTurn；
9. 提交后才调用 Provider。

Provider 网络流期间不持有 metadata 写事务。

## 7. AgentDefinition 与 Prompt

[`engine/agent/definition.py`](../../engine/agent/definition.py) 定义当前 Agent 的：

- tool groups；
- mode/capability；
- Turn/repair/retry/工具预算；
- Prompt/definition version；
- 完成所需输出；
- 领域安全约束。

[`engine/agent/prompt.py`](../../engine/agent/prompt.py) 与 [`engine/agent/model/system_prompt.py`](../../engine/agent/model/system_prompt.py) 负责组装稳定 Prompt。

Prompt 不是事实源：

- 工具权限由 PolicyGate 强制；
- SQL 只读由 Safety Service 强制；
- 完成由 CompletionPolicy 判断；
- Evidence 由 Terminalizer/Repository 校验；
- Prompt 只是把这些能力和规则告诉模型。

## 8. Provider Adapter 边界

### 8.1 `OpenAIModelAdapter`

[`engine/agent/providers/openai.py`](../../engine/agent/providers/openai.py) 对 OpenAI Responses API 和兼容实现做真实外部边界适配：

- 把 provider-neutral Turn request 转成 SDK 请求；
- 保留可选 message `phase`；
- 翻译流式 response item；
- 聚合展示文本、reasoning summary、tool call；
- 保持 function `call_id`；
- 将终止原因映射为 provider-neutral 枚举；
- 分类取消、incomplete、failed、协议错误和 transport error；
- 在所有退出路径关闭流；
- 记录 usage，不泄漏 secret。

这是允许存在 Adapter 的地方，因为它是真实第三方协议边界。内部不应继续围绕 Provider 名称增加 mapper。

### 8.2 Provider-neutral response items

Harness 关心的是规范语义：

- assistant display text；
- reasoning summary（不可当最终展示文本）；
- function call；
- function output；
- usage；
- terminal status；
- protocol/provider error。

未来增加 Provider 时，应忠实映射到同一语义，而不是伪造 `phase="final_answer"` 或根据文本内容猜终态。

## 9. 流式生命周期

### 9.1 必须关闭

Provider 流在以下所有路径都必须关闭：

- 正常 completed；
- function call 提前形成完整响应；
- 用户取消；
- deadline；
- SDK 异常；
- 协议解析异常；
- Run lease 丢失；
- 调用方任务被取消。

否则会泄漏 HTTP 连接、占用 pool，并导致后续请求表现为随机失败。

### 9.2 可取消等待

异步读取流和 retry backoff 需要同时监听：

- Provider 数据；
- cancel signal；
- deadline；
- transport close/error。

不能用长时间不可中断 `sleep`。取消发生后，部分文本只能作为诊断/临时 item，不能提交为正常最终答案。

## 10. CompletionPolicy

[`engine/agent/completion.py`](../../engine/agent/completion.py) 在 provider-neutral Turn 边界决定 complete/continue/repair/fail。

### 10.1 优先级

典型判断顺序：

1. 有待执行工具调用：必须继续，不能因同时有文本而完成；
2. 工具失败且没有可展示文本：根据预算 repair 或 fail；
3. 没有非空可展示文本：continue/repair/fail；
4. terminal status 不是 `completed`：不能提交最终答案；
5. 显式 `phase=final_answer` 是正向提示；
6. `phase=None` 但正常 completed、无工具、无控制继续信号时，文本可成为最终候选；
7. 验证引用 Artifact 已被观察且 Evidence 合法；
8. 多结果回答满足 inline evidence 要求；
9. 预算耗尽时按策略 partial/fail；
10. 返回 synthesize/complete 决策。

### 10.2 `phase` 不是必要条件

合法 Provider 可以返回：

```text
display_text = "这是最终答案。"
phase = None
terminal_status = completed
tool_calls = []
```

它应完成。Adapter 必须保留 `None`，CompletionPolicy 使用完整 Turn 语义判断，不能要求所有 Provider 伪造 phase。

### 10.3 terminal status 必须枚举化

只有 provider-neutral `completed` 可以形成最终候选。以下状态即使有部分文本也不能完成：

- `incomplete`；
- `failed`；
- `cancelled`。

任意非空字符串不能被当成 truthy 完成信号。

## 11. 工具调用回路

一个完整 function calling 闭环：

```text
Provider function_call(call_id, name, arguments)
  → persist canonical ToolInvocation
  → PolicyGate
  → approval if needed
  → ToolExecutor
  → ToolResult/Observation
  → persist function_output(same call_id)
  → next Provider request contains matched call + output
```

不能：

- 改写 call_id；
- 只把工具结果作为普通 assistant/user 文本；
- 工具失败后丢失 function_output；
- 同时执行两次同一 idempotency key；
- 为某个 Provider 添加 UI mapper 修补协议。

## 12. Steer、取消与等待态

### 12.1 steer

用户在 Run 过程中追加的输入分为：

- 当前 Run 可消费的 steer；
- 仍排队等待后续 Run 的原始 Input。

Context 必须把“原始当前请求”和“本轮已消费 steer”分开，不能重复注入，也不能提前消费未来输入。

### 12.2 cancel

取消是持久化命令：

1. API 写 cancel requested；
2. Coordinator/RunLoop/Provider stream/ToolExecutor 都可观察；
3. 执行边界尝试中止；
4. 进入 cancelled 终态；
5. 部分文本不成为最终答案；
6. 事件通知 UI。

### 12.3 waiting approval/question

等待审批或澄清不是失败，也不应占用 worker 无限轮询。状态和关联记录落库，用户动作到达后重新 wake Session。

## 13. Terminalizer

[`engine/agent/terminalizer.py`](../../engine/agent/terminalizer.py) 将运行结果收敛为耐久终态：

- complete：合成/验证最终回答、Evidence、Message、Run、Memory、Event；
- fail：固定公开错误 + 内部诊断；
- cancel：明确 cancelled 语义；
- 遵守 lease fencing；
- 使用单一事务提交终态。

RunLoop 不应在多个分支各自手写一半终态逻辑。

## 14. 预算与进度保护

Harness 需要多维预算：

- max turns；
- provider retries；
- contract repairs；
- tool attempts；
- token/cost；
- wall-clock deadline；
- repeated no-progress observations。

[`engine/agent/progress_guard.py`](../../engine/agent/progress_guard.py) 防止重复调用同一失败工具而无新证据。预算耗尽要形成可解释终态，不能只抛出通用 500。

## 15. 真实 Provider 与确定性测试

两类测试职责不同：

- 确定性 fake/SQLite Harness：覆盖状态机、失败注入、幂等、恢复；
- opt-in 真实 Responses 合同：验证 SDK 事件、`phase=None`、tool call/output、流关闭与 Provider 兼容。

真实测试不能成为默认离线单测，也不能用 fake 声称外部 Provider 已通过。

## 16. 常见症状定位

### 16.1 模型已经输出文本但 UI 没答案

检查：terminal status、display text、phase、pending tool calls、CompletionDecision、assistant message status、RUN_COMPLETED event。

### 16.2 工具调用一次后不停重复

检查：function output 是否用同一 call_id 回送；ToolInvocation status/idempotency；Observation 是否进入下一 Turn；ProgressGuard；Provider 是否收到上一轮完整 items。

### 16.3 达到最大轮次

不要先提高轮数。检查：完成语义是否错误依赖 phase；工具失败是否给出可行动错误；Catalog/Result 工具是否返回真实引用；Context 是否丢掉最新观察；模型是否被迫重复无效步骤。

### 16.4 Sidecar 重启后 Run 丢失

检查：Input/Run 是否在 wake 前 commit；数据库是否仍 queued/running；lease 是否过期可接管；pending ToolInvocation recovery policy；Coordinator 是否从 DB 扫描，而非只等内存 hint。

## 17. 关键测试

| 合同 | 测试 |
| --- | --- |
| RunLoop 多分支 | [`test_run_loop.py`](../../engine/agent/tests/test_run_loop.py) |
| Coordinator 有界调度 | [`test_session_coordinator.py`](../../engine/agent/tests/test_session_coordinator.py) |
| Provider Adapter/流 | [`test_openai_model_adapter.py`](../../engine/agent/tests/test_openai_model_adapter.py) |
| Prompt/Completion | [`test_prompt_and_completion.py`](../../engine/agent/tests/test_prompt_and_completion.py) |
| Run control/取消 | [`test_run_control.py`](../../engine/agent/tests/test_run_control.py) |
| Progress guard | [`test_progress_guard.py`](../../engine/agent/tests/test_progress_guard.py) |
| Terminalizer 取消 | [`test_terminalizer_cancellation.py`](../../engine/agent/tests/test_terminalizer_cancellation.py) |
| 真实 Responses（opt-in） | [`test_real_responses_contract.py`](../../engine/agent/tests/test_real_responses_contract.py) |
| SQLite Harness | [`harness/test_sqlite_scenarios.py`](../../engine/tests/test_dbfox_data_domain_model.py) |

## 18. 修改检查表

- [ ] Input/Run 在 wake 前耐久提交；
- [ ] Coordinator 内存有界且不是唯一队列；
- [ ] Provider 调用不持有 metadata 写事务；
- [ ] Adapter 只位于外部协议边界；
- [ ] phase 保持可选，不伪造；
- [ ] terminal status 使用枚举，只有 completed 可最终提交；
- [ ] 待执行工具优先于文本完成；
- [ ] function call/output 保持同一 call_id；
- [ ] 所有流退出路径关闭资源；
- [ ] 取消与退避可中断；
- [ ] 终态由 Terminalizer 原子收敛；
- [ ] 默认测试确定性，真实 Provider 测试显式 opt-in。
