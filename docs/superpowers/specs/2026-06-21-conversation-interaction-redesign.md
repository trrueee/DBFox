# DBFox 对话交互端到端重构设计

> 日期：2026-06-21
> 状态：待用户 review
> 范围：前端对话页、后端会话模型、运行事件、SQL/Chart artifact 归属、历史会话恢复

## 背景

当前 DBFox 的对话交互存在两个层面的问题。

第一层是可见体验问题：对话区空旷，消息、失败提示、执行过程和追问输入之间缺少稳定层级；失败态会与主消息流割裂；SQL、表格和图表证据容易把回答挤散。

第二层是结构问题：前端仍在多个 tab 字段上拼接会话事实，旧 `ChatConversation.messages_json` 和 `artifacts_json` 只是扁平 JSON 快照；消息 id 会被转换成数字；运行过程、最终回答、SQL、表格和 Chart 的归属关系不够明确。这会导致用户消息被覆盖、多 SQL 只显示最后一条、Chart 绑定错误、刷新恢复不完整等风险。

本设计选择端到端重构，而不是继续在旧 UI 和旧 JSON 快照上打补丁。

## 已确认决策

- 产品形态采用 ChatGPT / Claude 式问答流：消息是主线，执行过程和证据默认收起。
- 允许同时重构前端、后端、数据库 schema 和 API。
- 新结构化 Conversation / Message / AgentRun / Artifact 是唯一主路径。
- 不做旧 `ChatConversation.messages_json` / `artifacts_json` 迁移。
- 接受重构后旧历史对话不可见，新版本从空历史开始。
- 可以通过 migration/drop 清理旧 `ChatConversation` JSON 路径和相关前端 repository。

## 目标

1. 对话页形成稳定、清晰、可复用的 Chat 流体验。
2. 消息更新遵循 append-only + targeted update，避免 AI 回复覆盖用户消息。
3. 每轮用户问题对应一个 AgentRun，运行状态、trace、审批、错误和 artifacts 都归属于该 run。
4. 多 SQL、多表格、多 Chart 通过 artifact sequence 和 `depends_on` 稳定展示，不再互相覆盖。
5. 刷新或重新打开会话时，从新结构化 API 恢复完整消息、运行状态和证据。
6. 后端 runtime events 成为前端会话状态的事实来源。

## 非目标

- 不迁移旧 JSON 会话历史。
- 不保留旧 `ChatConversation` API 作为新 UI 的兼容数据源。
- 不把对话页改成 Notebook 或数据库 IDE 形态。
- 不在本次设计中重构无关设置页、数据源树或 SQL 控制台。

## 数据模型

### Conversation

长期会话实体，保存会话元信息。

实现上复用现有 `AgentSession` 作为 Conversation 的数据库主表，对外 API 使用 conversation 命名。

字段：

- `id`
- `title`
- `datasource_id`
- `context_tables_json` 或结构化上下文表关联
- `created_at`
- `updated_at`
- `archived_at`
- `deleted_at`

### Message

聊天流里的可见消息。所有 message 使用稳定字符串 id。

新增 `AgentMessage` 表。

字段：

- `id`
- `conversation_id`
- `role`: `user` | `assistant` | `system`
- `content`
- `status`: `created` | `streaming` | `completed` | `failed`
- `created_at`
- `updated_at`

规则：

- 用户消息只 append，不被后续事件覆盖。
- Assistant 消息由 `assistant_message_id` 定位更新。
- 前端禁止用数组下标或最后一条消息作为更新目标。

### AgentRun

一次用户提问触发的一轮 Agent 执行。

实现上复用并扩展现有 `AgentRun` 表。

字段：

- `id`
- `conversation_id`
- `user_message_id`
- `assistant_message_id`
- `parent_run_id`
- `status`: `queued` | `running` | `waiting_approval` | `completed` | `failed` | `cancelled`
- `error_code`
- `error_message`
- `started_at`
- `completed_at`

规则：

- trace、approval、artifacts、错误都归属于 run。
- 取消和失败保留已经产生的 trace 和 artifacts。
- 追问创建新的 run，但仍属于同一个 conversation。

### Artifact

回答证据，支持 SQL、table、chart、markdown 等类型。

实现上复用并扩展现有 `AgentArtifactRecord` 表。Artifact payload 继续使用 JSON 字段，以适配 SQL、table、chart 等异构内容；类型级契约由后端 schema 和前端 TypeScript 类型约束。

字段：

- `id`
- `conversation_id`
- `run_id`
- `message_id`
- `type`: `sql` | `table` | `chart` | `markdown`
- `sequence`
- `title`
- `payload_json`
- `depends_on_json`
- `status`: `created` | `running` | `completed` | `failed`
- `created_at`

规则：

- 多 SQL 按 `sequence` 展示。
- table artifact 依赖对应 SQL artifact。
- chart artifact 依赖 SQL 或 table artifact。
- 前端只根据 `run_id`、`message_id`、`depends_on` 和 `sequence` 分组，不再猜测 artifact 归属。

## API 设计

### 会话 API

- `GET /conversations`
  - 返回会话摘要列表。
  - 包括标题、更新时间、数据源、最后消息摘要、当前运行状态和 artifact 计数。

- `POST /conversations`
  - 创建新会话。
  - 可带 `datasource_id` 和上下文表。

- `GET /conversations/{id}`
  - 返回完整会话详情。
  - 包括 messages、runs、artifacts、approvals。

- `PATCH /conversations/{id}`
  - 重命名、更新上下文表、归档。

- `DELETE /conversations/{id}`
  - 删除会话，并级联清理 messages、runs、events、artifacts。

### 消息与运行 API

- `POST /conversations/{id}/messages`
  - 发送用户消息并启动 run。
  - 后端创建 user message、assistant placeholder message 和 AgentRun。
  - 返回 `conversation_id`、`user_message_id`、`assistant_message_id`、`run_id`。

- `GET /runs/{run_id}/events/stream`
  - SSE 输出运行事件。

- `POST /runs/{run_id}/cancel`
  - 取消运行。

- `POST /approvals/{approval_id}/resolve`
  - 处理审批。

## Runtime Events

后端 runtime events 是前端状态更新的事实来源。建议事件类型：

- `conversation.created`
- `message.created`
- `assistant.delta`
- `assistant.completed`
- `run.started`
- `run.trace.appended`
- `artifact.created`
- `artifact.updated`
- `approval.required`
- `approval.resolved`
- `run.completed`
- `run.failed`
- `run.cancelled`

事件必须携带足够的定位信息：

- `conversation_id`
- `run_id`
- `message_id` 或 `assistant_message_id`
- `artifact_id`
- `sequence`

前端 reducer 只按 id 更新对应对象，不使用 `messages[messages.length - 1]` 或 tab 上的临时字段作为事实来源。

## 前端架构

### Store 边界

`WorkspaceTab` 只保存打开了哪个 conversation 和当前 UI tab 状态，不再保存完整聊天事实。

会话事实进入新的 conversation store：

- conversations summary
- active conversation detail
- messages by id
- runs by id
- artifacts by id
- ordered ids
- streaming run subscriptions

### 组件拆分

`ConversationWorkspace`

- 加载会话详情。
- 订阅 run events。
- 汇总运行状态。
- 向子组件传入结构化 view model。

`ConversationHeader`

- 显示标题、数据源、状态。
- 提供重命名、删除、历史入口。

`MessageList`

- 渲染消息流。
- 处理自动滚动。
- 用户手动上滚时暂停自动跟随。

`MessageBubble`

- 渲染 user、assistant、system 消息。
- Assistant 消息内挂回答正文、错误卡片、trace summary 和 evidence summary。

`RunTracePanel`

- 默认折叠。
- 展开后显示 timeline、tool call、审批记录。

`ArtifactEvidencePanel`

- 展示 SQL/table/chart 证据。
- 按 run 和 sequence 分组。
- SQL 下方展示对应 table 和 chart。

`Composer`

- 固定在对话容器底部。
- 支持发送、运行中取消、禁用原因提示。
- 保持和消息流同一视觉系统。

## UI 设计

对话页采用三层结构。

顶部是轻量会话栏：显示会话标题、数据源、运行状态和必要操作。

中间是消息流主列：宽度约 `760px` 到 `880px`，居中但不空旷。用户消息右侧气泡，assistant 回答左侧正文。执行过程默认显示为一条 summary，例如“已分析 3 步，执行 2 条 SQL，用时 8.4s”。

回答下方是证据摘要和可展开详情：默认只显示“2 条 SQL，2 张表，1 个图表”。展开后每个 SQL group 按顺序展示 SQL、状态、结果表、关联 Chart、复制和打开控制台操作。

底部是固定输入区：运行中显示取消按钮；失败后允许继续追问；没有数据源或 LLM 配置缺失时显示明确禁用原因。

失败态作为 assistant 消息里的错误回答卡片出现，不再漂浮在页面角落。

## 错误处理

- 网络或 API 超时：run 进入 `failed`，assistant 消息显示超时错误和重试入口。
- 模型或 API key 错误：显示配置错误，提供打开 LLM 配置入口。
- SQL 执行失败：失败信息挂在对应 SQL artifact 下，不让整轮对话布局崩掉。
- 用户取消：run 进入 `cancelled`，保留已产生的 trace 和 artifacts。
- 审批拒绝：run 进入终态，显示拒绝原因并允许继续追问。

## 数据库与清理策略

本次重构不迁移旧会话历史。

迁移策略：

1. 复用 `AgentSession` 作为 Conversation 主表。
2. 新增 `AgentMessage` 表。
3. 扩展 `AgentRun`，增加 `user_message_id`、`assistant_message_id`、更明确的终态字段和错误字段。
4. 复用并扩展 `AgentArtifactRecord`，补齐 `message_id`、`conversation_id` 和稳定 sequence 约束。
5. 保留 `AgentRuntimeEventRecord` / `AgentTraceEventRecord` 作为 run 事件记录。
6. 移除新 API 对旧 `ChatConversation.messages_json` 和 `artifacts_json` 的读取。
7. 删除旧 `/conversations` JSON 快照保存逻辑。
8. 通过 migration/drop 清理旧 `ChatConversation` 表。
9. 前端删除旧 `conversationRepository` JSON record 路径。

## 测试计划

### 后端

- 创建 conversation、message、run、artifact 的完整流程。
- `POST /conversations/{id}/messages` 能创建 user message、assistant message 和 run。
- SSE events 携带稳定 id，能按顺序输出 run trace、assistant delta、artifact created 和 final event。
- 多 SQL artifact sequence 稳定。
- Chart artifact `depends_on` 指向正确 SQL 或 table。
- 删除 conversation 会级联清理 messages、runs、artifacts、events。
- 旧 JSON conversation 路径不再被新 API 使用。

### 前端

- 连续多轮提问时用户消息不会被覆盖。
- Streaming delta 只更新对应 assistant message。
- 失败、取消、审批状态都显示在对应 assistant 消息中。
- 多 SQL、多 table、多 chart 按顺序归属到同一 run。
- 刷新后通过新 API 恢复完整会话。
- 大屏和窄屏下消息列、证据面板、输入区不重叠。

### 端到端验收场景

1. 新建会话，发送普通问题，得到稳定回答。
2. 连续发送两轮追问，消息顺序保持正确。
3. 一轮回答产生两条 SQL，每条 SQL 都显示独立结果。
4. Chart 绑定到对应 SQL 或 table，不使用最后一个结果集。
5. 运行中取消，页面保留已产生内容并显示取消状态。
6. 模型超时或 API key 错误显示在 assistant 消息内。
7. 刷新页面后，新会话历史能从结构化 API 恢复。

## 实施顺序

1. 后端 schema 与 API：建立结构化会话主路径，废弃旧 JSON conversation 路径。
2. 前端类型、API client 和 store：让 tab 打开 conversation，而不是保存聊天事实。
3. 对话 UI 重建：替换 `AgentTaskView`、`AgentTurnItem`、`FinalAnswerCard` 为新的消息流组件。
4. Runtime event 接入：用 SSE events 驱动 message、run、artifact 更新。
5. 验证与清理：覆盖多轮、失败、多 SQL、Chart、刷新恢复，删除旧 repository 和无用样式。

## 实现决策

- 数据库主路径复用 `AgentSession`、`AgentRun`、`AgentArtifactRecord`、`AgentRuntimeEventRecord` 和 `AgentTraceEventRecord`，新增 `AgentMessage`。
- Artifact payload 保持 JSON 存储，SQL/table/chart 的字段约束放在后端 Pydantic schema 和前端 TypeScript 类型中。
- 历史入口保留现有“对话历史”tab，但数据源切换到新的 `GET /conversations` 摘要 API；对话页顶部增加打开历史的轻量按钮。
