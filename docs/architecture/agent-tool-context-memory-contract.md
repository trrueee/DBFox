# Agent Tool、Context 与 Memory 边界合同

状态：Accepted
日期：2026-08-05

## 1. 目标

DBFox 使用 SQL 后端计算数据，模型负责提出问题、选择工具、解释有界结果。完整数据集不是 Prompt，也不是 Memory。

```text
数据库 -> 只读 SQL/结果服务 -> Result Artifact（权威引用）
                              -> 有界观察窗口（当前 Run 的 provider output）
                              -> 耐久摘要（恢复、审计、UI）
```

必须同时满足：

- 模型能够看到它刚刚请求的少量、脱敏、可解释的数据；
- 大结果由 SQL 聚合、筛选、排序、分页和 profile 处理；
- 任何行值都不进入 Artifact 元数据、Observation、Session Memory 或错误消息；
- function call 与 function call output 使用同一 `call_id`；
- 进程恢复后不伪造丢失的瞬时行值，而是通过 Artifact 和 `result_inspect` 重新读取；
- Provider Adapter 只忠实转换标准事件，不按提供商名称修补工具语义。

## 2. 三个数据平面

### 2.1 数据平面

SQL 执行器、ResultViewService 和数据库是完整结果的权威来源。分析优先使用 SQL：聚合、分组、排名、比例、分布和钻取。`SELECT *` 的大批行只用于显式预览，不作为分析策略。

Result Artifact 保存查询指纹、列、行数、截断状态和来源关系，但禁止保存 `rows`、`series` 或其他结果值。完整结果由结果服务按 Artifact 引用重新读取。

### 2.2 当前 Run 的观察平面

每次成功的数据工具调用产生一个有界 `provider_payload`：

- 查询执行：Artifact 引用、列、少量脱敏预览行、行列计数、耗时和截断原因；
- 结果查看：用户明确请求的有界页、分页信息和 Artifact 引用；
- Schema 查看：目标对象以及每个对象的有界字段清单，不允许因总输出过大而退化成只有对象数量；
- 失败：固定公开错误码、固定公开消息、可重试性和下一步能力，不包含内部异常文本。

该 payload 只存在于一次 RunLoop 的内存中。PromptAssembler 在生成 provider input 时，以相同 `call_id` 覆盖耐久的摘要 output。它可以跨同一 Run 的多个模型轮次复用，但不得写入 Turn snapshot、Observation、Artifact、事件、日志或 Session Memory。

每个表格观察窗口必须有独立硬上限；达到上限时返回结构化截断原因，而不是截断 JSON 文本。模型需要更多数据时必须调用 `result_inspect`、`result_profile` 或编写更精确的聚合 SQL。

### 2.3 耐久控制与记忆平面

Observation 只保存：工具状态、公开摘要、Artifact IDs、能力、固定错误码和少量非结果事实。它用于审计、UI 和崩溃恢复，不承诺保留行值。

Session Memory 只保存：

- 当前 datasource 与 generation；
- 工作集和选中的 Artifact；
- 已引用的证据 Artifact 元数据；
- 用户明确确认或 Runtime 能够证明的稳定上下文。

模型生成的自然语言结论即使带 Artifact 引用，也不得命名或存储为 `verified_claims`。引用证明来源存在，不证明模型措辞本身正确。

## 3. Run 恢复与跨 Run 上下文

- 同一 Run 正常执行：使用内存中的有界 provider payload。
- 同一 Run 进程恢复：只恢复耐久摘要；若需要值，模型使用 Artifact ID 调用结果工具重新读取。
- 下一 Run：不携带上一次的瞬时行值；使用已完成 assistant answer、工作集和证据引用。
- 上一 Run 失败或取消：下一 Run 注入一个 Runtime 生成的 `previous_run_outcome`，包含状态、固定公开错误、最近工具结果摘要和恢复提示；不得注入失败 assistant 草稿。

## 4. 失败语义

工具失败 output 必须是机器可判定的封闭合同：

```text
status, error_code, public_message, retryable, artifact_ids, recovery
```

`DBFoxError.message` 默认不可信。只有显式允许公开的输入错误可以携带受控文本；其他错误只通过已注册的固定错误码取得公开消息。未知错误统一为通用错误。

Turn 终止使用封闭枚举 `completed | incomplete | failed | cancelled`。只有 `completed` 可以提交无 phase 的最终文本。

## 5. 复用决策

- 继续复用 OpenAI Responses 的原生 function call/function call output 和 `call_id` 合同，不建立第二套工具协议；
- 继续复用现有 SQL guardrail、脱敏、Result Artifact、ResultViewService、行序列化上限和 Context Budget；
- 仅在 ToolObservationProjection 中增加真实边界所需的瞬时 payload，不新增 provider mapper、DTO 镜像或 fallback 链；
- 不引入新的第三方依赖。现有组件已覆盖执行、分页、序列化和持久化，问题在边界组合而非缺少库。

## 6. 验收不变量

1. 工具返回 `42` 时，下一模型轮能够实际看到 `42`。
2. 同一行值不出现在 Observation、Artifact、Session Memory、RunItem 和 Turn context snapshot。
3. 大结果只提供有界窗口，并明确说明剩余数据如何读取。
4. 失败 Run 的下一条用户消息能够获得失败原因与最近工具状态。
5. 失败 assistant 草稿不会进入后续上下文。
6. 记忆不再新增模型生成的 `verified_claims`。
7. Schema 宽对象不会被压缩成只有 `itemCount`。
8. 带工具调用、取消、流失败和未完成 Turn 不会被误判为最终回答。
