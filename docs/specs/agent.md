# DBFox Agent 产品与运行规范

状态：设计基线
适用范围：桌面端、Web、Agent Runtime、工具、持久化与评测

关联文档：

- [技术设计](../designs/agent.md)
- [实施任务](../plans/agent.md)
- [架构链路评审](../reviews/agent-architecture-review.md)
- [能力资产清单](../reviews/agent-capability-inventory.md)

## 1. 目标

DBFox Agent 是面向数据库工作的智能数据分析师。它不以“生成一条 SQL”作为默认终点，而应围绕用户目标主动完成理解、探索、验证、执行、修复、归纳和解释，直到取得足以支撑结论的证据，或明确说明仍缺少什么。

最终产品必须同时满足：

1. 过程可观察：用户能够理解 Agent 当前在做什么、为什么继续、使用了哪些工具，以及是否发生修复或等待批准。
2. 结果可解释：每个关键结论都能打开对应工件和证据。
3. 运行可恢复：页面刷新、网络重连或进程重启不会破坏已经确认的状态。
4. 权限可控制：工具在声明、物化和执行边界均受权限与策略约束，高风险动作主动请求批准。
5. 架构可扩展：模型、工具、记忆源、工件和前端展示通过稳定协议扩展，不依赖硬编码流程分支。

## 2. 最终架构决定

- 生产 Runtime 不使用 LangGraph、LangGraph Thread、Graph State 或 LangGraph Checkpointer。
- DBFox 自己拥有 Session、Run、Turn、ToolInvocation、Approval、QuestionRequest、Artifact、Evidence、Memory 和 Event 的领域模型。
- Agent 使用显式 ReAct 循环，但安全、事务、权限、恢复和完成判断由确定性 Runtime 控制。
- 只保留一条生产执行路径，不提供新旧 Runtime 切换开关。
- 现有能力不是废弃重做，而是提炼后纳入唯一实现。

## 3. 继承基础

实施必须复用已经验证的基础，而不是从零构造：

### 3.1 来自 1.0.1 的产品行为

- 数据分析 ReAct 闭环；
- Policy、Tool、Observe、Progress、Repair、Answer、Finalize 的业务语义；
- 工具输出摘要和回灌；
- SQL 自动修复；
- 独立最终答案合成；
- 多轮结果引用与会话记忆；
- SQL、Safety、ResultView、Chart 等工件链；
- 用户可见的分析过程。

### 3.2 来自当前代码的可靠性基础

- Run 状态转换和版本检查；
- Supervisor 与隔离数据库 Session；
- Approval 的原子消费；
- datasource generation fence；
- 事务事件与会话投影；
- 查询中断和结果服务；
- 错误脱敏和凭据边界。

### 3.3 来自 OpenCode 的运行思想

- Session 所有的显式循环；
- 每轮重新加载持久化消息和状态；
- Provider stream、tool call、tool result 组成自然 ReAct 循环；
- 同 Session 串行、不同 Session 并行；
- 工具按 Agent、模型、权限动态物化；
- 压缩后通过持久化历史继续，而不是依赖进程内思维状态。

### 3.4 DBFox 保留的核心设计

- 统一的 BaseTool、ToolPolicy、ToolExecutionSpec、ToolStateSpec 和 ArtifactSpec；
- 数据分析师 System Prompt：主动探索、交叉验证、尽可能发现更多有价值信息；
- 一等 Artifact/Evidence 模型；
- 数据库安全、只读、确认和敏感数据策略；
- 桌面端与 Web 使用相同协议。

## 4. 命名规则

生产代码使用稳定领域名，不使用阶段、替代或兼容语义命名。

禁止用于正式模块、类、接口和路由的词：

```text
new
next
legacy
compat
temporary
v2
v3
migration
bridge（仅在真正的外部协议桥接中允许）
```

推荐领域名：

```text
Session
SessionInput
Run
Turn
AgentDefinition
ContextSnapshot
ContextEpoch
ToolDefinition
ToolInvocation
Observation
Approval
QuestionRequest
Artifact
Evidence
ResponseComposition
RuntimeEvent
```

数据库 schema revision 仍可使用基础设施要求的 revision 文件，但领域代码不得出现过渡命名或双路径。

## 5. 领域词汇

### 5.1 Session

一次连续对话及其记忆、输入顺序、选中工件和上下文范围。产品中的 Conversation 与 Runtime Session 使用同一个聚合身份。

### 5.2 SessionInput

已经被系统接纳的用户输入。包含内容、幂等 ID、交付方式、显式选中工件和工作区上下文。

### 5.3 Run

处理一个 SessionInput 的完整执行。Run 是取消、终态、成本、恢复和产品结果的边界。

### 5.4 Turn

一次不可分割的模型请求与流式响应。每个 Turn 固定模型配置、Prompt、ContextSnapshot 和 ToolMaterialization。

### 5.5 ToolInvocation

一次具体工具调用。它在副作用前持久化，并独立记录权限、批准、执行、结果和恢复状态。

### 5.6 Observation

工具结算后提供给 Agent 的有界、结构化观察。Observation 同时引用工具结果、工件和诊断，但不内嵌大结果。

### 5.7 Artifact

用户可以查看、引用、操作和再次使用的工作成果，例如 SQL、查询结果、图表、安全报告、分析计划和说明文档。

### 5.8 Evidence

回答中一个结论与真实 Artifact 之间的可定位关系。Evidence 必须引用不可变 Artifact ID。

## 6. AgentDefinition 与 System Prompt

每个 Run 必须固定一个 AgentDefinition：

```text
agent_id
version
name
description
prompt_bundle
model_requirements
context_policy
tool_policy
completion_policy
permission_policy
response_schema
budgets
```

PromptBundle 必须包含稳定版本和内容哈希。System Prompt 至少表达：

- 身份是数据分析师，不是 SQL 自动补全器；
- 先理解业务目标，再选择必要的数据探索；
- 优先使用工具获取事实，不基于猜测生成数据结论；
- 一次查询不足以回答目标时应继续探索、验证或修复；
- 关键结论必须关联可验证 Evidence；
- 不泄露凭据、系统策略和敏感数据；
- 高风险动作必须遵循 ToolPolicy 和 Approval；
- 达到预算或无法继续时给出清晰的部分结果、限制和下一步建议。

历史消息、Schema、工具输出和用户内容均为非特权上下文，不得插入 System Prompt 权限层。

## 7. 输入接纳与交付

接纳请求必须原子完成：

- 创建或确认 SessionInput；
- 分配 Session sequence；
- 写入用户消息；
- 记录 delivery mode；
- 记录 selected_artifact_ids；
- 记录 reply_to_request_id（响应 Agent 提问时）；
- 创建 Run 或记录待创建关系；
- 追加 `session.input.admitted`；
- 提交后唤醒 Session。

支持：

- `queue`：当前 Run 结束后执行；
- `steer`：在下一个安全 Turn 边界注入当前 Run；
- `cancel_and_replace`：持久化取消当前 Run，结算后处理新输入。
- `respond`：原子回答一个仍有效的 QuestionRequest，并恢复原 Run。

输入接纳不等待模型首 token。调度失败不能丢失已接纳输入。

## 8. Session 并发

- 一个 Session 同时只有一个所有者可以修改对话状态。
- 不同 Session 可以并行。
- 所有权使用数据库 lease 和单调 fencing token；每次 Session/Run 写入都校验 token。
- lease 过期后旧 owner 的迟到提交必须失败，不能覆盖新 owner 状态。
- 重复 wake 合并。
- 进程重启后扫描未消费输入和可恢复 Run。
- 所有者只是进程内优化，数据库状态才是恢复依据。

## 9. ReAct Run 循环

唯一 Run 控制循环为：

```text
load durable state
→ assemble context
→ materialize tools
→ start Turn
→ stream model output
→ tool calls?
   yes → request/approve/execute/settle tools
       → project Observations and Artifacts
       → continue
   no  → evaluate completion
       → continue/repair/ask_user/synthesize/complete
→ compose terminal response
→ commit terminal projection
```

模型可以提出动作，但不得决定事务、安全或权限结果。

循环必须有：

- 最大 Turn 数；
- 最大工具调用数；
- 时间、token 和成本预算；
- 重复调用检测；
- 连续相同错误检测；
- SQL repair 预算；
- provider retry 预算；
- 明确终止原因。

## 10. 完成策略

CompletionPolicy 必须根据 AgentDefinition、用户目标、Observations、Artifacts 和 Evidence 判断：

- 是否已经回答用户目标；
- 声称的数据事实是否有结果工件支撑；
- 是否存在可修复的 SQL 或工具错误；
- 是否仍缺少关键表、字段或时间范围；
- Evidence 是否全部可解析；
- 是否需要继续探索以避免一次查询即结束；
- 是否达到预算并需要部分回答。

Provider finish reason 只是输入信号，不能单独决定 Run 完成。

当缺少必须由用户决定的信息时，Runtime 持久化 QuestionRequest，将 Run 置为 `waiting_input`。用户回答后从新的 Turn 继续；不得依赖进程内 future、Graph checkpoint 或重新猜测原问题。

## 11. Context 与分层记忆

### L0 Turn Buffer

token delta、reasoning summary delta、partial tool-call assembly。Turn 完成后只保留必要摘要。

### L1 Run Working Memory

目标、当前焦点、Observations、修复历史、工具调用、Artifact refs、缺失 Evidence 和预算使用。

### L2 Session Memory

消息历史、近期 Run 摘要、选中/固定工件、未解决任务和 ContextEpoch。

### L3 Datasource/Workspace Memory

验证 SQL、Schema 语义、业务别名、可靠 join path 和用户固定知识。必须携带 datasource generation、catalog version、provenance 和失效规则。

### L4 User Preference

回答语言、展示、安全和图表偏好。不得包含数据库事实或凭据。

每个 Turn 都记录 ContextSnapshot：来源 ID、版本、预算、包含/排除原因、Prompt 版本、工具物化哈希和最终 context hash。

ContextEpoch 用于压缩 L2 历史，保留摘要、近期尾部、选中工件、未解决任务、安全决策和 Schema 版本。压缩失败继续使用旧 Epoch。

## 12. 工具系统

内置、插件和 MCP 工具统一降低为 ToolDefinition。每个 Turn 得到按 Agent、模型能力、datasource、权限和执行模式过滤的 ToolMaterialization。

ToolInvocation 状态：

```text
requested
→ waiting_approval
→ running
→ succeeded | failed | unknown | cancelled | rejected
```

工具执行顺序：

1. 解析并校验输入；
2. 校验物化身份和版本；
3. 校验 datasource generation；
4. 计算权限与策略；
5. 持久化 ToolInvocation；
6. 必要时创建 Approval 并暂停；
7. 执行 leaf；
8. 限制、脱敏并持久化结果；
9. 生成 Observation 和 Artifact candidates；
10. 原子结算并通知。

工具必须声明恢复策略：`retry_safe`、`reconcile`、`never_retry` 或 `provider_owned`。

## 13. 权限与 Approval

权限同时在工具物化和 leaf 边界执行。Approval 必须包含：

- 工具名称与用途；
- 关键参数的安全摘要；
- 风险和可能影响；
- 数据源与环境；
- 请求原因；
- 允许、拒绝与可选的长期规则；
- expiration、Run version、Turn ID、Invocation ID 和 datasource generation。

Approval 只能消费一次。批准后从对应 ToolInvocation 继续；拒绝后产生结构化 Observation，Agent 可以调整方案或结束。

### 13.1 主动提问

QuestionRequest 是区别于 Approval 的通用用户决策：它可以请求业务口径、时间范围或方案选择，但不能用来绕过权限批准。

QuestionRequest 必须包含问题、原因、可选项、是否允许自由输入、Run/Turn/version、过期时间和恢复上下文引用。回答只能消费一次，并作为正式用户消息和 Observation 进入下一 Turn。

## 14. Observation

Observation 必须包含：

```text
observation_id
run_id
turn_id
tool_invocation_id
tool identity and version
status
model_visible_summary
structured_result_ref
artifact_ids
facts
error
retryability
sequence
```

下一 Turn 只接收有界摘要、关键事实、Artifact refs 和错误信息。大查询结果留在 ResultView/Query service。

## 15. Artifact 与 Evidence

Artifact 使用不可变 ID、稳定 semantic key、版本、状态、provenance、bounded preview 和 payload reference。

至少支持：

- analysis_plan；
- sql；
- safety；
- result_view；
- chart；
- markdown；
- error。

关系至少支持：

```text
validated_by
executed_as
visualized_as
derived_from
supports
```

Evidence 必须引用真实 Artifact ID，并可以定位到指标、列、行键、单元格范围或 SQL 片段。语义占位符和前缀猜测禁止进入完成回答。

## 16. 最终回答

FinalSynthesis 产生结构化 AnswerCandidate。ResponseComposer 只负责：

- 校验结构；
- 校验 Evidence；
- 确定 referenced artifacts；
- 生成完整回答文本和消息块；
- 生成建议、限制、安全与上下文摘要；
- 生成 Session memory delta；
- 生成 terminal event payload。

Answer、assistant message、Evidence、Run terminal state、Session memory delta 和 terminal event 必须原子提交。

## 17. 产品过程可观察性

产品展示的是可审计的工作叙事，不是隐藏 chain-of-thought。

用户可见阶段由语义事件驱动，可以动态出现，不使用固定步骤条强迫所有任务走同一路径：

- 理解目标；
- 读取上下文；
- 探索 Schema；
- 检查数据；
- 形成或调整分析计划；
- 生成与验证 SQL；
- 执行工具；
- 修复；
- 等待批准；
- 汇总证据；
- 形成回答。

每个 Activity 应包含状态、简洁说明、时间、关联 Tool/Artifact 和可展开的安全详情。Reasoning 只展示模型或 Runtime 生成的简短 reasoning summary。

## 18. 前端产品契约

会话工作区包含：

1. 消息与流式回答主区域；
2. 当前 Run Activity Feed；
3. 右侧 Artifact Dock；
4. Evidence chips/links；
5. Approval Card 与 Question Card；
6. Composer 和 queue/steer/cancel 控制；
7. 数据源、模型和上下文状态。

交互要求：

- 发送后 100ms 内产生已接纳反馈；
- 首 delta 前显示真实 Activity，不使用长时间纯 spinner；
- Answer delta 平滑合并，不逐 token 造成布局抖动；
- 新 ResultView 可自动选中，但用户显式选择优先；
- Evidence 点击打开精确 Artifact；
- Approval 在对话中显示原因，在需要时固定为主要操作；
- 刷新后 Activity、回答、Approval、Artifacts、Evidence 和选择状态一致恢复；
- 所有操作可键盘访问，动态状态使用 aria-live；
- 图标使用统一 SVG，不使用 emoji；
- 状态不能只靠颜色；
- 动画 150-300ms，并支持 reduced motion。

## 19. 事件与流式

权威事件使用 Session sequence，包含 event_id、event_type、event_version、conversation_id、run_id、turn_id、sequence、timestamp 和 payload。

事件族：

```text
session.input.admitted
session.input.promoted
session.context.updated
run.created
run.started
run.completed
run.failed
run.cancelling
run.cancelled
turn.started
turn.completed
activity.updated
reasoning.summary.delta
tool.requested
tool.running
tool.progress
tool.completed
tool.failed
approval.requested
approval.resolved
question.requested
question.resolved
observation.created
artifact.created
artifact.updated
artifact.selected
answer.delta
answer.completed
```

LiveStreamHub 提供低延迟 delta；RuntimeEventLog 提供权威 replay；SSE 先订阅通知再补历史，客户端按 sequence 和 offset 去重。

## 20. 错误、取消与恢复

- 错误使用稳定 code、产品消息和 diagnostic reference。
- 凭据、连接串和不受限结果不得进入事件、日志或 ContextSnapshot。
- 取消持久化且有版本检查；迟到 worker 不得覆盖 cancelled。
- Turn 中断且无工具副作用时可以在预算内重开 Turn。
- 工具执行中断按 recovery policy reconcile，不猜测成功。
- waiting approval 在进程重启后保留。
- terminal transaction 只能全部成功或全部不生效。

## 21. 性能与边界

- 已连接客户端的 provider delta 到 UI P95 小于 50ms。
- durable event commit 到通知 P95 小于 100ms。
- 主流式路径不使用固定轮询。
- Tool output、Event payload、Context source 和 Artifact preview 均有大小限制。
- 长 Activity 列表和大表格使用虚拟化或分页。
- 大结果有保留、清理和失效提示。

## 22. 验收场景

### 22.1 深入分析而非一次结束

用户提出需要数据支持的问题。Agent 至少完成必要的 Schema 探索、SQL 验证、执行和结果解释；如果第一次结果不足，会继续分析或明确询问，而不是直接结束。

### 22.2 工具 Observation 闭环

工具成功、失败和空结果都会生成 Observation，并实际进入下一 Turn 的 Context。

### 22.3 工件与证据

SQL 执行后右侧出现 SQL、Safety 和 ResultView。回答中的 Evidence 点击可打开准确 ResultView 或 SQL。

### 22.4 多轮记忆

下一轮询问“按地区拆分刚才结果”，后端从 Session History 和选中 Artifact 解析“刚才”，不依赖前端拼接隐藏上下文。

### 22.5 Approval

高风险工具主动暂停并展示批准卡。进程重启后仍可批准或拒绝，且只能消费一次。

### 22.6 过程体验

运行过程中实时显示理解、工具、修复和证据汇总等 Activity；不暴露隐藏 chain-of-thought；刷新后过程完整恢复。

### 22.7 主动提问

关键业务口径不明确时，Agent 持久暂停并展示 Question Card；刷新后仍可回答，回答只消费一次并恢复原 Run。

### 22.8 流式恢复

客户端在 answer delta 或 tool progress 中断线，使用 sequence 重连后无缺失、无重复文本、无重复 Artifact。

### 22.9 取消与替换

执行查询时 cancel_and_replace，旧 Run 被可靠结算，新输入在安全边界开始，旧 worker 不能迟到完成。

### 22.10 权限边界

未物化、无权限、过期 datasource generation 或未批准的工具都不能产生副作用。

### 22.11 统一产品行为

Web 与打包桌面端使用相同协议，能够完成输入、流式、工具、Artifact、Evidence、Approval、刷新恢复和下一轮引用。

## 23. 发布门槛

只有同时满足以下条件才允许发布：

- 生产依赖和代码中不存在 LangGraph；
- 不存在双 Runtime 或切换标志；
- 完整纵向 Golden Scenario 通过；
- 每个 Tool 有权限、恢复和输出边界；
- 每个完成 Evidence 可解析；
- Activity、Answer、Artifact 和 Approval 可刷新恢复；
- Session 并发、取消、重连和崩溃注入通过；
- 桌面端与 Web 行为一致；
- 文件、类型和路由没有阶段性命名；
- System Prompt 的数据分析师核心行为通过评测。

## 24. Reference-only Artifact 数据边界

Artifact 是可解析的持久引用，不是查询结果缓存。SQL 查询结果的唯一事实来源是数据源本身以及由后端校验、编译和执行的 SQL。

- Result Artifact 只持久化真实 Artifact ID、来源 SQL Artifact ID、查询指纹、datasource generation、列结构、执行统计、时间、关系和 provenance；禁止持久化 `rows`、`previewRows` 或任意单元格值。
- Chart Artifact payload 固定为 `sourceResultArtifactId`、`chartType`、`x`、`y`、`aggregation`、`title`；其中 `y` 是字段名数组。禁止持久化 `series`、样本行、展示标签或重复统计元数据。
- Artifact 分页、筛选、排序、导出和图表数据接口只接受目标 Artifact ID 与视图参数。datasource、SQL、generation、权限和来源关系由后端解析，客户端不得作为权威来源回传。
- 前端 Conversation Store、事件流和会话快照只保存 Artifact descriptor。按需取得的当前页数据只存在于视图组件生命周期，不进入持久 Store。
- Tool Result 可以在当前 ReAct 步骤中短暂提供给模型，但 Durable Observation 只保存状态、摘要、Artifact ID、计数、查询指纹和诊断，不保存结果行。
- Session History、Session Memory、selected Artifact context 和 Turn context snapshot 禁止包含结果行。模型需要具体数据时必须通过 Artifact/SQL 工具重新读取。
- Evidence 只保存支撑结论的最小事实、locator、Artifact ID、查询指纹和观测时间，不保存任意结果集。
- Result Gateway 的唯一公开资源接口是 `POST /api/v1/artifacts/{artifactId}/page`、`POST /api/v1/artifacts/{artifactId}/export` 和 `POST /api/v1/artifacts/{artifactId}/chart-data`；请求不得携带 datasource ID 或 SQL。
- Agent 需要读取已选中或恢复后的结果时必须调用 `artifact.inspect`。该工具只向当前 ReAct 回合暴露最多 50 行，持久 Observation 仅保留计数、耗时、指纹和 Artifact ID。
- datasource generation 变化时，旧 Artifact 必须明确变为不可重放或 stale，不能静默查询新连接并冒充旧证据。

验收必须证明：使用唯一敏感测试值执行查询后，该值不存在于 Artifact、Event、Observation、Turn、Memory 和前端 Conversation Store；只有按需结果响应与当前工具调用的瞬时内存可以包含它。
