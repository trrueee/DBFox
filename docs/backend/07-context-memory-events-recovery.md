# 卷七：Context、Memory、Recall、事件与恢复

> 文档类型：实现指南
>
> 状态：当前
>
> 最后核验：2026-08-12
>
> 适用范围：当前上下文、工作记忆、历史查找、事件和恢复
>
> 权威合同：[Tool、Context 与 Memory 边界](../architecture/agent-tool-context-memory-contract.md)、[Conversation Recall 合同](../architecture/agent-conversation-recall-contract.md)、[Runtime Item 协议](../architecture/agent-runtime-item-protocol.md)
>
> 核心入口：[`engine/agent/context.py`](../../engine/agent/context.py)、[`engine/agent/conversation_recall.py`](../../engine/agent/conversation_recall.py)、[`engine/agent/repositories/events.py`](../../engine/agent/repositories/events.py)

## 1. 四种“记忆”不能混为一谈

用户通常把“AI 记不记得”统称为记忆，但实现上有四层：

| 层 | 保存什么 | 生命周期 | 进入 Prompt 的方式 |
| --- | --- | --- | --- |
| Canonical messages | 用户与 completed assistant 原文 | 耐久、可归档 | 最近窗口自动注入；较早内容通过 Recall |
| Run/Turn/RunItem | 执行、工具、reasoning summary、状态 | 耐久、审计/恢复 | 选择性摘要，不全量注入 |
| Session Memory | 工作集合、最近结论、Evidence 引用 | 有界派生状态 | ContextAssembler 按预算注入 |
| Result Artifact | 查询结果或可回源引用 | 受保留策略管理 | 先给引用，按需通过结果工具读取 |

缺少任何一层都会出问题，但把四层合并成一个 JSON 也会造成上下文爆炸、事实冲突和无法恢复。

## 2. ContextAssembler 的职责

[`engine/agent/context.py`](../../engine/agent/context.py) 在每个 Turn 构造确定性 Context snapshot。它组合：

- 当前原始请求；
- 本 Run 已消费 steer；
- 最近 canonical history；
- archive/recall 可用性摘要；
- 最近 response/tool batches；
- selected artifact；
- 有界 observations；
- Session Memory；
- workspace/context tables；
- Run focus/plan；
- previous outcome；
- datasource/generation 来源信息；
- hash 和预算统计。

Context 是本 Turn 的输入快照，不是实时读取视图。Turn 持久化 snapshot/hash 后，后续状态变化不应悄悄改变“模型当时看到了什么”。

## 3. 当前请求与 consumed steer

### 3.1 原始请求

Run 的原始 Input 是本次任务的稳定目标，只出现一次，不能在 history 和 current request 中重复。

### 3.2 consumed steer

Run 进行中用户补充的信息，在被当前 Run 明确消费后作为 `consumed steer` 单独进入 Context。这样可以表达：

- 原始任务是什么；
- 用户后来补充/纠正了什么；
- 哪些后续输入还没被消费。

### 3.3 必须排除未来输入

同一 Session 中排队的下一条 Input 不能提前进入当前 Run，否则会：

- 打乱用户意图顺序；
- 同一输入被两个 Run 消费；
- 恢复后无法解释上下文；
- 形成“模型知道未来消息”的假象。

## 4. canonical history

自动历史窗口只选择：

- 当前请求之前的用户消息；
- status=completed 的 assistant 消息；
- Session 内按 sequence 排序；
- 在 Context Budget 允许范围内的最近窗口。

排除：

- pending assistant 占位；
- cancelled/failed 的部分输出；
- reasoning；
- 工具状态文案；
- 未来 queued input；
- 被删除/归档策略排除的消息。

这避免把内部协议内容伪装成用户对话。

## 5. Context Budget

[`engine/agent/context_budget.py`](../../engine/agent/context_budget.py) 负责有界选择，不只是最后粗暴截字符串。

预算需要按语义优先级分配：

1. 系统/AgentDefinition 必需规则；
2. 当前请求和已消费 steer；
3. 未完成工具闭环所需 call/output；
4. 最新 Observation；
5. 当前计划/工作状态；
6. 最近 completed messages；
7. Memory/Evidence 引用；
8. 较旧历史摘要。

不能截断：

- function call 与对应 output 的配对；
- JSON Schema；
- 当前请求关键字段；
- artifact id；
- approval/取消控制语义。

可以压缩/减少：

- 较旧历史；
- 重复工具状态；
- 大样本；
- 可通过 Recall/Result 工具回源的内容。

## 6. Session Memory

### 6.1 Memory 保存什么

Memory 应是经过完成事务派生的工作记忆：

- 最近完成 Run 的有界摘要；
- 已验证 Evidence/Artifact 引用；
- 当前 working set；
- 用户已明确的稳定偏好（若产品合同允许）；
- datasource identity/generation。

### 6.2 Memory 不保存什么

- 全量聊天原文；
- 完整查询结果；
- 未完成的部分文本；
- Provider reasoning 原文；
- 未验证主张；
- secret；
- 跨 datasource generation 仍假装有效的数据结论。

### 6.3 `_write_memory`

Run 完成时，`RunRepository._write_memory` 在终态事务中更新 Memory。它与最终 Message、Evidence 和 Run 状态同一提交，防止记忆了一个随后回滚的答案。

## 7. Conversation Recall

### 7.1 为什么 Recall 是工具

完整对话可以很长。自动注入全部历史会：

- 超出 token；
- 稀释当前任务；
- 重复发送敏感内容；
- 增加费用和延迟；
- 让模型难以区分当前与历史指令。

因此较旧历史通过受控检索工具按需找回，类似“先搜索，再读取”。

### 7.2 `ConversationRecallService.search`

[`engine/agent/conversation_recall.py`](../../engine/agent/conversation_recall.py) 的搜索合同：

- 只在当前授权 Session；
- 只搜 canonical message projection；
- FTS5 支持时使用受控索引；
- 不支持/不适合时使用确定性 literal fallback；
- 结果分页、数量和 snippet 长度有界；
- 返回 message sequence/id/role/摘要；
- 不把搜索结果直接永久写入 Memory。

### 7.3 `ConversationRecallService.read`

read 接收明确的消息 sequence/range，返回：

- canonical completed content；
- 稳定顺序；
- 受控最大条数/字节；
- 归属验证；
- 对不存在、未完成或越界消息的稳定错误。

模型应先 search 定位，再 read 所需内容；不能用 read 一次拉取整个 Session。

### 7.4 Recall 的耐久 Observation

工具返回给当前 Turn 的文本是瞬时上下文；耐久记录应保存结构性信息，例如查询、命中 message ids/sequences 和数量，而非再次复制所有原文。

## 8. RunItem 与 Event

### 8.1 RunItem

RunItem 是运行过程的规范项目，例如：

- user/assistant message；
- plan step；
- function call；
- function output；
- approval/question；
- status/progress；
- artifact/evidence reference。

它服务持久化与投影，不依赖某个前端组件形状。

### 8.2 Event

Event 表达“规范状态发生了什么变化”，带 Session 内单调 sequence。它用于：

- SSE replay；
- UI 增量更新；
- cursor 恢复；
- 运行审计。

Event 不是唯一事实源：当前状态仍从 Session/Run/RunItem 等 canonical 表读取。

## 9. 写入、提交和发布顺序

```text
business state mutation
  → canonical RunItem upsert
  → Event append(sequence++)
  → transaction commit
  → SQLAlchemy after_commit
  → LiveStreamHub publish
  → SSE subscribers receive
```

如果进程在 commit 后 publish 前崩溃，客户端重连后从数据库 replay。若事务 rollback，`after_rollback` 清掉 pending notification，UI 不会看到幽灵事件。

## 10. SSE snapshot/replay/live

[`engine/api/conversation_stream.py`](../../engine/api/conversation_stream.py) 的安全连接顺序：

1. 验证 Token 和 Session；
2. 先订阅 commit/live hub，避免 replay 与 live 间出现窗口；
3. 从客户端 cursor 开始读取数据库事件；
4. 若 cursor 早于 floor，要求 snapshot；
5. replay 到当前 high-water；
6. 接收 live 有界队列；
7. 定期 keepalive；
8. 客户端断开时关闭订阅，但不取消 Run。

### 10.1 为什么先订阅再 replay

若先查询 DB 再订阅，查询结束和订阅建立之间提交的事件可能永久丢失。先订阅后 replay 允许按 sequence 去重和衔接。

### 10.2 背压

每客户端 live queue 有界。消费者过慢时不能无限吃内存；应关闭/标记 gap，让客户端通过 snapshot/cursor 恢复，而不是丢事件后继续假装连续。

## 11. Snapshot

Snapshot 从 canonical Session/Run/RunItem/Message 状态构建，返回：

- 当前投影；
- 可继续的 cursor；
- event floor/high-water；
- 当前 Run/等待态；
- 必需选择和 Artifact 引用。

Snapshot 不是把所有历史 Event 重放到内存后得到；它应直接读取当前规范状态，因此事件压缩后仍可工作。

## 12. 崩溃恢复

### 12.1 Sidecar 崩溃

重启后：

1. Host 建立新 runtime generation/Token/port；
2. FastAPI 完成数据库初始化和 Saga reconciliation；
3. Coordinator 扫描 queued/recoverable Run；
4. 旧 Session lease 到期或被安全接管；
5. pending ToolInvocation 按 recovery policy 处理；
6. UI 获取新 runtime config；
7. SSE 用 snapshot/cursor 恢复；
8. 非幂等未知结果不自动重放。

### 12.2 SSE 断开

SSE 断开只表示观察通道断开，不表示用户取消。Run 继续在服务端执行，UI 重连后 replay。

### 12.3 Provider 流中断

Provider 流中断属于当前 Turn 失败/不完整：

- 关闭流；
- 部分文本不提交为最终 message；
- 根据分类和 budget 决定 retry/fail；
- 事件说明阶段和公开错误；
- 不污染 Memory。

### 12.4 工具执行中崩溃

依赖持久化 Invocation 状态和 recovery policy：

- 未执行可重新调度；
- 已完成有 output 则复用；
- 幂等可按策略重试；
- 非幂等未知结果等待人工/明确失败。

## 13. “本轮所有对话说了什么”如何回答

理想链路不是依赖当前 Prompt 恰好还装得下全部历史：

1. Agent 识别这是历史回忆任务；
2. `conversation_search` 用宽查询/分段定位；
3. `conversation_read` 按 sequence 分页读取；
4. 必要时继续读取下一段；
5. 在 Context Budget 内逐段归纳；
6. 引用消息范围或稳定序列；
7. 不把全部原文永久写入 Memory。

这使“找回”依赖数据库 canonical messages，而非模型隐式记忆。

## 14. 数据源隔离

Memory、Artifact、Observation 和旧 Run 都要记录 datasource id/generation。切换数据源后：

- 对话原文仍属于 Session 历史；
- 旧数据结论不能默认作为新数据源证据；
- Artifact 回源必须验证归属；
- ContextAssembler 过滤不兼容 working set/evidence；
- 模型可描述历史讨论，但不能把旧指标声称为当前库事实。

## 15. 常见症状定位

### 15.1 Agent 忘了刚才工具结果

检查：ToolInvocation output → Observation → response batch → 下一 Turn Context snapshot；不是先扩大 Memory。

### 15.2 Agent 忘了很早的对话

检查：canonical messages 是否 completed；SearchDoc 是否同步；Recall 工具是否物化；search/read 是否受错误 scope 限制；Prompt 是否告诉模型可用 Recall。

### 15.3 UI 重连后重复节点

检查：Event sequence 去重；snapshot cursor；RunItem stable id；live/replay 重叠处理；前端是否按 append 而非 upsert canonical item。

### 15.4 UI 永久重连

检查：Token/generation 是否刷新；cursor 是否早于 floor；错误分类是否把 401/404/contract error 当瞬时网络错误；backoff 是否有最大值和终止类别。

### 15.5 最终答案出现未验证主张

检查：Evidence 引用；Artifact 是否 observed；CompletionPolicy 的 citation validation；Memory 是否混入未完成输出。

## 16. 关键测试

| 合同 | 测试 |
| --- | --- |
| Context 组成 | [`test_context_assembler.py`](../../engine/agent/tests/test_context_assembler.py) |
| Context 预算 | [`test_context_budget.py`](../../engine/agent/tests/test_context_budget.py) |
| Memory 过滤 | [`test_context_memory.py`](../../engine/agent/tests/test_context_memory.py) |
| Recall service | [`test_conversation_recall.py`](../../engine/agent/tests/test_conversation_recall.py) |
| Recall 完整 Harness | [`test_conversation_recall_harness.py`](../../engine/agent/tests/test_conversation_recall_harness.py) |
| Conversation projection | [`test_conversation_projection.py`](../../engine/agent/tests/test_conversation_projection.py) |
| Event 合同 | [`test_event_contracts.py`](../../engine/agent/tests/test_event_contracts.py) |
| Live hub | [`test_live_stream_hub.py`](../../engine/agent/tests/test_live_stream_hub.py) |
| SSE 背压 | [`test_conversation_stream_backpressure.py`](../../engine/tests/test_conversation_stream_backpressure.py) |
| Search index | [`test_search_index_service.py`](../../engine/tests/test_search_index_service.py) |
| SQLite 恢复场景 | [`harness/test_sqlite_scenarios.py`](../../engine/agent/tests/harness/test_sqlite_scenarios.py) |

## 17. 修改检查表

- [ ] current request 不在 history 重复；
- [ ] consumed steer 与 future queued input 分离；
- [ ] 只注入 completed canonical assistant message；
- [ ] Context Budget 保持 call/output 配对；
- [ ] Memory 有界、可重建且仅来自已完成事实；
- [ ] Recall 只在授权 Session，结果分页有界；
- [ ] 大结果仍用 Artifact 回源；
- [ ] Event 与业务状态同事务；
- [ ] publish 只在 commit 后；
- [ ] SSE 背压产生可恢复 gap，不无限缓存；
- [ ] SSE 断开不取消 Run；
- [ ] 不兼容 datasource generation 的证据不进入当前分析。
