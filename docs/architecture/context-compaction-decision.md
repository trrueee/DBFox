# 上下文压缩决策

> 文档类型：架构决策
>
> 状态：当前
>
> 最后核验：2026-11-24
>
> 适用范围：`engine/agent/context.py`、`engine/agent/prompt.py`、`engine/agent/conversation_recall.py`

## 1. 问题

长会话和多次工具调用会超出模型输入预算。候选方案有三类：

1. **确定性裁剪**：按预算淘汰最旧的完整 Turn，保留证据账本、Artifact 引用与会话检索工具；
2. **LLM 摘要**：调用模型把旧 Turn 压缩成摘要，再注入后续 Prompt；
3. **Provider 原生 compaction**：使用 Responses 等协议提供的服务端压缩项。

## 2. 决定

DBFox Core 采用 **方案 1**，不引入 LLM 摘要，也不依赖 Provider 原生 compaction。

理由：

- **Provider-neutral**：摘要调用会绑定某一家模型、额外计费并引入新的失败路径；Core 的 Turn/预算/结算语义不应因此增加第二个模型调用生命周期。
- **事实可追溯**：被淘汰的是“原始 transcript 片段”，但 Observation、Artifact、Evidence 仍在 SQLite；模型可以通过 `artifact_read`、`conversation_search`、`conversation_read` 重新取得证据，而不是信任一段不可核验的摘要。
- **已有合同**：`agent-tool-context-memory-contract.md` 已明确选择确定性裁剪；本轮不反向修改已接受合同。
- **可预测成本**：每个 Turn 的输入预算由 token 估算与模型窗口决定，不因摘要调用的重试、超时或质量波动而变化。

## 3. 当前实现

- `PromptAssembler` 在预算不足时以完整 Turn 为单位淘汰 `response_batches`，不拆散 function call 与 output（`prompt.py`）。
- 原始请求和已生效的补充指令按顺序完整进入模型。补充指令单独读取，历史消息的窗口只限制历史。必需内容装不下时，Run 以 `AGENT_CONTEXT_BUDGET_EXCEEDED` 停止，并保留已结算成果。
- 被淘汰 Turn 的 Observation 通过证据账本注入（最多 8 条、每 facts 512 字符），并标明“Runtime-authored ledger”。
- `ContextAssembler` 注入有界的 Session Memory（working set + 最近证据引用，总大小 ≤4 KiB）。
- 长历史消息由 `conversation_archive` 计数暴露给模型，需要原文时调用检索工具。
- 当前 Run 的上下文窗口按模型能力收紧（`engine/llm/model_capabilities.py`），未知模型保留定义中的显式预算。

## 4. 不采用 LLM 摘要的原因

摘要会带来以下新增责任，当前没有对应合同：

- 摘要失败时是否阻断 Run、是否回退到裁剪、是否计入 Token/费用预算；
- 摘要内容与仍在窗口内的原文重复，导致同一事实出现两份；
- 摘要丢失 Artifact ID、限制条件或失败原因，模型据此作出错误结论；
- 摘要模型与主模型不同，需要额外 Provider 路由与凭据边界。

在这些责任被明确写入合同之前，Core 不增加摘要调用。

## 5. 重新评估条件

满足任一条件时重新评审：

1. 真实长会话评测显示“检索工具无法在可接受轮次内找回证据”；
2. 产品明确接受摘要的额外模型调用、成本与失败语义；
3. 出现必须依赖 Provider 原生 compaction 才能支持的模型；
4. 上下文窗口显著增大后，淘汰频率下降到可忽略，压缩不再是瓶颈。

## 6. 验证

- `verification/tests/agent_core/test_context_budget.py`：预算、Turn 整批淘汰、证据账本。
- `verification/tests/agent_core/test_conversation_recall_harness.py`：窗口外历史通过检索工具恢复。
- `verification/tests/agent_core/test_session_memory_context.py`：Session Memory 有界投影。
- `verification/tests/agent_core/test_model_capabilities.py`：模型窗口收紧与未知模型回退。
