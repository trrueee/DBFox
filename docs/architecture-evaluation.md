# DataBox 架构评价：ReAct / Graph / Memory / Environment / Context / Frontend

## 1. ReAct 循环

```
START → model → policy → tools → observe → progress → model/repair/finalize
```

**设计判断：纯 ReAct，模型是唯一的决策者。**

没有独立的 Planner 节点。模型在每一轮看着完整的 state（messages、tool_results、
environment_profile、schema_context、execution、progress_decision）自己做决定。
Progress Judge 的 fast path 是确定性的——tool_results 到了就 continue，模型输出文本
就 complete——只在 ambiguous 情况调 LLM judge。这是一个"模型驱动 + 状态机兜底"
的设计。

**优点：**
- 单一决策源。模型不会和另一个"Planner"冲突。
- `escalate.tool_group` 让模型可以自己扩展工具权限，不需要外部重新规划。
- Progress Judge 的 fast path 覆盖了 90% 的常见路径，LLM judge 只用于恢复。

**风险点：**
- 初始 tool scope 给了全部 12 个 group。模型可能在简单对话（"你好"）中看到
  不需要的 SQL 工具。但如果 prompt 足够好，模型会选择不调用。
- `execution_mode` 是唯一的安全阀（suggest_only 会阻止 SQL 执行），
  但它现在来自 request 层，不是 agent 自己决定的。


## 2. Graph 状态机

**设计判断：Graph 提供纯状态机保证，不做流程编排。**

```
Nodes:  model, policy, tools, observe, progress, repair, approval, finalize
Edges:  条件路由 → policy (有 tool_calls) / progress (无 tool_calls) / model (继续) / finalize (结束)
```

**状态机保证：**

| 保证 | 实现 | 位置 |
|---|---|---|
| 步数上限 | `max_steps` 在 model_node 和 progress_node 双重检查 | `model_node.py:20-37`, `progress_node.py:325-341` |
| Checkpoint | LangGraph SQLite / InMemory checkpointer | `checkpointer.py` |
| Resume | `interrupt()` + `Command(resume=...)` | `approval_node.py`, `service.py:186-297` |
| Anti-loop (replan) | `replan_count` budget (max 2-4) | `replan_policy.py` |
| Anti-loop (blocks) | `consecutive_blocks` limit (max 2) | `policy_node.py:157-183` |
| Human-in-the-loop | Approval interrupt for risky SQL | `approval_node.py` |

**评价：每个 node 都映射到一个真实的运行时关注点。没有为了"画图好看"加的节点。**

`policy` 是安全边界。`tools` 是执行。`observe` 是状态更新。`progress` 是完成判断。
`repair` 是恢复子路径。`approval` 是人机交互。`finalize` 是终态。

**风险点：**
- `observe` 和 `progress` 之间是硬边 (`graph.add_edge("tools", "observe")`,
  `graph.add_edge("observe", "progress")`)，意味着每次工具执行后必然经过 progress
  judge。对于简单的 schema 查询这种 1-tool 任务，多了一轮判断开销。
  但这是 ReAct 的结构性成本，不是设计缺陷。


## 3. 记忆系统

**设计判断：三层记忆 + 自动注入，不依赖模型"记得去查记忆"。**

```
Layer 1: Short-Term   → LangGraph checkpoint（thread state，瞬态）
Layer 2: Session      → 进程内 dict（跨 run 上下文：last question, SQL, artifacts）
Layer 3: Long-Term    → LongTermMemoryStore（持久化：偏好、规则、轨迹、失败经验）
```

**记忆类型（9 种）：**
user_preference, project_rule, metric_definition, schema_alias, join_path,
successful_trajectory, failure_learning, artifact_reference, conversation_summary

**命名空间隔离：** 层级 tuple `("user", uid, "project", pid, "datasource", did)`，
前缀匹配检索。同一个查询能拿到 user 级偏好 + project 级规则 + datasource 级 schema alias。

**注入点：**
1. **Planning**（已移除，但 bridge 代码仍在）— 自动注入偏好、规则、历史成功轨迹
2. **Progress Judge（恢复时）** — 自动注入过去的失败经验
3. **Finalize** — 自动写入轨迹、join path、语义映射

**安全策略：** `is_safe_for_long_term()` 阻止 password / token / PII 进入长期记忆。
agent_inferred 类型的 schema/rule 记忆需要 confidence ≥ 0.8 或进入 pending_review。

**评价：记忆系统是最完整的子系统。** 它做到了 memory 不应只是 agent 可选的 tool call，
而是系统自动在关键决策点注入上下文。写入是 best-effort（不阻塞 finalize），
检索是 namespace-scoped（多租户安全）。

**风险点：**
- `LongTermMemoryStore` 当前是内存 dict。生产部署需要换成 SQLite/Postgres 后端。
  API 设计已为此做好准备（`put/upsert/search/delete/get`）。
- `memory_bridge.search_memory_for_planner()` 仍存在但 planner 已删除。
  它的逻辑应该迁移到首次 model 调用的 context builder 中。
- 两个并行写入路径（`MemoryWriter` + `memory_bridge.write_trajectory`）
  可能产生重复轨迹。去重依赖 store 的 upsert key 匹配。


## 4. 环境 / 数据源系统

**设计判断：确定性的 fact layer，零 LLM 输出。所有数据来自配置或实时 introspection。**

**解析管线：**
```
DataSource (DB row)
  → resolve_datasource()        # dialect, connection_kind, host/port
  → SchemaIntrospector.inspect() # tables, columns, FKs, samples
  → SchemaCatalogSync.sync()     # upsert 到 SchemaTable/SchemaColumn
  → EnvironmentService           # 统一的查询 API
  → Tool: environment.get_profile → state["environment_profile"]
```

**DatabaseMap（Agent v2 世界模型）6 层：**
1. Catalog — TableProfile + ColumnProfile，启发式分类（fact/dimension/bridge）
2. Profiles — 可选实时列分析（null rate, distinct count, sample values）
3. Relationships — FK + 命名约定推断 join（`account_id` → `accounts.id`）
4. Semantics — 业务术语到列的映射（来自长期记忆）
5. Usage — 查询频率和成功 join path（来自记忆轨迹）
6. Risk — 敏感列检测、大表警告、PROD 标记

**评价：这是 DataBox 真正区别于通用 agent 框架的地方。** DatabaseMap 提供了
SQL agent 最需要的东西——结构化的数据库世界知识。6 层模型中，前 3 层是确定性
的（来自 introspection），后 3 层是 learned（来自使用历史和记忆）。

**风险点：**
- 启发式 join 推断（`_build_relationships`）confidence 只有 0.5，可能产生错误连接。
- PostgreSQL/DuckDB 的 introspection 是 stubbed，需要实现。
- `database_map` 目前只在 `environment.get_profile` 工具中构建。其他工具看不到它。


## 5. 上下文管理

**设计判断：多层上下文注入，从 system prompt 到结构化 ContextPack。**

**上下文层次：**

| 层次 | 注入方式 | 内容 |
|---|---|---|
| System Prompt | `model_node.py` → `build_system_prompt()` | 角色定义、工具使用规则、escalation 指导 |
| Context Block | `model_node.py` → `build_context_message()` | workspace、environment、schema、SQL、execution、result profile |
| Progress Guidance | `model_node.py` → `build_progress_guidance_message()` | 上轮 progress judge 的判定：next action、missing evidence、recovery strategy |
| Memory Context | `memory_bridge.search_memory_for_*()` | 偏好、规则、历史轨迹、失败经验 |
| ContextPack | `observe_node.py` → `build_context_pack()` | 结构化状态摘要：run_state、skill、intent、recent activity |

**ContextPack** 是 Agent v2 的核心创新——把分散的 state 字段压缩成结构化摘要。
`render_for_model()` 产生 ~500 token 的紧凑上下文块，替代了 ad-hoc 的 state 拼接。

**评价：上下文注入点设计得当。** System prompt 是静态规则层，Context Block 是
动态事实层，Progress Guidance 是 supervisor 指令层，Memory 是经验层。
每一层都有清晰的职责边界。

**风险点：**
- 如果所有层都满载，首次 model 调用的 token 消耗可能很大。
  `memory_compactor.py` 提供了消息和 schema 的压缩策略，但缺少全局 token 预算控制。
- `follow_up_context` 通过 `parent_run_id` 传递，但只在 `service.py` 的 `run_iter`
  中处理。纯 session 连续性的逻辑分散在多处。


## 6. 前端

**技术栈：Tauri 2 (Rust) + React 19 + TypeScript + Vite 8 + Tailwind 3**

**桌面壳层：** Tauri 提供原生窗口（自定义标题栏）、本地 SQLite 持久化、
外部 engine binary 管理。前端通过 `http://127.0.0.1:{port}/api/v1` 与 engine 通信。

**状态管理：无外部状态库。** 所有状态在 `App.tsx` 中用 `useState` hooks 管理，
通过 props 向下传递。`tabsRef` / `conversationsRef` 用 ref 镜像关键状态
供异步回调访问。

**Tab 系统（9 种工作区类型）：**

| Tab | 组件 | 职责 |
|---|---|---|
| smart-query | SmartQueryHome | NL 问答入口 |
| query-result | QueryResultWorkspace | Agent 聊天结果 |
| sql | SqlConsoleWorkspace | SQL 控制台 |
| table | TableWorkspace | 单表浏览（5 个子视图） |
| multi-table | MultiTableWorkspace | 多表联合 |
| conversation-history | ConversationHistoryPanel | 历史对话 |
| llm-config | LlmConfigPanel | LLM 配置 |
| datasource-settings | DataSourcesPage | 数据源管理 |
| agent-eval | AgentEvalPage | Agent 评测 |

**评价：前端严格遵循"本地优先"原则。** 不依赖云端服务。Tauri 提供原生性能，
React 19 的并发特性可以用于流式渲染。Tab 系统将每个工作区类型封装为独立组件。

**风险点：**
- 无状态管理库在 tab 数增多时可能变得难以维护。`patchTab()` 模式是手写的
  immutable update，容易出错。
- SSE 流解析是手写的（`response.body.getReader()` + 行分割），
  没有使用 EventSource API。这可能是为了支持 POST 请求的自定义 header。
- Monaco Editor 和 ECharts 是重型依赖，影响 bundle 大小和首屏加载。


## 7. 渲染

**Artifact 渲染管线：**
```
API AgentArtifact → agentBridge.toViewArtifacts() → View Artifact → ArtifactRenderer → 具体 View
```

**7 种 Artifact 类型映射：**

| API 类型 | View 类型 | 渲染器 |
|---|---|---|
| sql | SqlArtifact | `<pre>` 代码块 + Copy/Download/Open-in-SQL-Console |
| chart (line/bar) | ChartArtifact | 内联 SVG 图表（toggle line/bar） |
| table | TableArtifact | `<table>` + Copy/Export CSV |
| insight | MarkdownArtifact | 文本 + Copy |
| recommendation | MarkdownArtifact | 文本 + Copy |
| error | MarkdownArtifact | 文本 + Copy |
| agent_plan / query_plan / safety | (隐藏) | 不渲染给用户 |

**DataTable 渲染：** 功能最丰富的组件——客户端 sort/filter/hide、列菜单、
右键上下文菜单（Copy Cell / Row JSON / INSERT SQL / Filter）、
GSAP 行动画、JSON tree inspector、密度切换。

**ER Diagram 渲染：** `@xyflow/react` + 自定义节点（TableCardNode）+ 自定义边（ErEdge）。
3 种布局模式：radial（单表焦点）、grid（模块/全图）。虚线表示推断关系。

**Chart 渲染：** ECharts 封装，支持 bar/line/pie。从执行结果自动提取 series 数据。

**评价：Artifact 类型系统是 clean 的 discriminated union。** 每种 artifact
有明确的渲染策略。内部 artifact（plan/safety）不暴露给用户。DataTable 的
交互密度远高于典型的"表格展示"组件——它是一个迷你数据分析 IDE。

**风险点：**
- ChartArtifact 只支持 line/bar 切换，不支持 pie/scatter 等 chart.suggest 推荐的类型。
- 没有流式 artifact 渲染——artifact 只在 `agent.artifact.created` 事件时完整出现。
  大表或复杂图表可能出现"突然弹出"的效果。
- MarkdownArtifact 没有真正渲染 Markdown（只是纯文本 + Copy 按钮）。
  这可能是为了安全（避免 XSS），但限制了表达力。


## 8. 交互

**Agent 交互循环（从 UI 视角）：**

```
用户输入问题
  → SmartQueryHome / FollowUpInput
  → runAgentForTab(tabId, question)
    → SSE stream 开始
      → 每收到 event: 更新进度文案（"正在构建 Schema 上下文…"）
      → 每收到 artifact: 追加到 tab.artifacts
      → 每收到 approval: 暂停，显示 Approve/Reject 按钮
    → 流结束
    → finishAgentRun()
      → 成功: 显示 answer + suggestions + artifacts
      → 等待审批: 显示审批卡片
      → 失败: 显示错误
  → persistTabConversation() 保存到 SQLite
```

**多轮对话：** `sendFollowUp()` 带上 `sessionId` 和 `parentRunId`，
后端通过 `follow_up_context` 传递上一轮的 schema/execution/sql 状态。

**Approval 交互：** `agentApproval` 作为 tab 状态的一部分存储。
用户 Approve/Reject → `handleApprovalDecision()` → `streamResumeAgentRun()`。
审批卡片显示 risk_level、reason、SQL 预览。

**进度反馈：** `describeRuntimeEvent()` 将 SSE 事件映射为人可读的进度文案。
例如 `agent.tool.started` + `sql.generate` → "正在生成 SQL 查询语句…"。

**评价：交互设计抓住了一个关键洞察——agent 交互不是聊天，是异步任务执行。**
进度文案、artifact 增量追加、审批暂停/恢复，都是在传达"agent 在工作"。
QueryResultWorkspace 的布局（问题 → 进度 → artifacts → answer → 追问输入）
反映了这个任务导向的设计。

**风险点：**
- 取消 Agent Run 没有实现。如果用户输入了错误的问题，必须等待超时或完成。
- 流式 artifact 渲染缺失——用户在等待 artifact 时只能看到进度文案。
- 进度文案映射（`describeRuntimeEvent`）是 hardcoded 的中文文案，
  国际化需要重构。
- 没有"重新生成"按钮——用户不能要求 agent 对同一问题给出不同答案。


## 总结

| 维度 | 成熟度 | 关键设计 |
|---|---|---|
| ReAct | ★★★★☆ | 纯模型驱动，Progress Judge 确定性 fast path |
| Graph | ★★★★★ | 每个节点有明确运行时职责，状态机保证完整 |
| Memory | ★★★★★ | 三层记忆 + 自动注入 + 命名空间隔离 + PII 防护 |
| Environment | ★★★★☆ | 确定性 fact layer，DatabaseMap 6 层世界模型，Postgres/DuckDB stub |
| Context | ★★★★☆ | 多层注入（system/context/progress/memory），缺全局 token 预算控制 |
| Frontend | ★★★★☆ | 本地优先，9 种工作区类型，无状态库可能成为瓶颈 |
| Rendering | ★★★★☆ | Artifact discriminated union 清晰，DataTable 交互密度高，缺流式渲染 |
| Interaction | ★★★★☆ | 任务导向交互（非聊天），缺取消和重新生成 |

**整体评价：DataBox 是一个在 SQL agent 领域做了深度垂直整合的系统。**
它不是 LangChain/LangGraph 的薄封装——它在环境系统、记忆系统、渲染系统上
做了大量原创设计。ReAct 循环本身保持简洁（模型决策 + 状态机保证），
复杂度被正确地放在了"数据库世界知识"和"用户体验"这两层。
