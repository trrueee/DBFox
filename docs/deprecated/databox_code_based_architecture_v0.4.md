# DataBox 按实际代码梳理的领域与功能架构设计

> 版本：v0.4  
> 日期：2026-06-02  
> 写作依据：按当前仓库代码的真实模块、API、模型、前端交互和已有功能拆分，而不是预设为四个模块。  
> 核心目标：把 DataBox 的领域边界、功能边界、运行时边界和未来演进边界拆清楚，尤其明确 SQL 操作、`@` 注解、问数前置优化、Agent Runtime、数据源/工作区/备份/表设计/评测等真实代码域的关系。

---

## 1. 读代码后的核心结论

DataBox 不是一个单纯的 Text-to-SQL 工具，也不是一个单纯的 Agent 项目。按当前代码，它更接近：

```text
DataBox
  = 本地优先数据工作台
  + 数据源 / 项目 / 本地环境管理
  + Schema 元数据与 ER 管理
  + 可信 Text-to-SQL 问数管线
  + SQL Editor 与 @ 注解快捷操作
  + SQL 安全执行与历史审计
  + 表结构设计与测试数据生成
  + 备份 / 恢复高风险操作
  + 独立 Agent 分析运行时
  + Golden SQL 评测与诊断
```

所以架构文档不应该只写成：

```text
SQL / @ / Semantic / Agent
```

而应该按真实代码拆成多个领域层：

```text
[1] App Shell & API Gateway
[2] Project / Environment / Datasource Domain
[3] Schema Metadata & ER Domain
[4] Semantic Query Optimization Domain
[5] Text-to-SQL Generation Domain
[6] SQL Safety & Execution Domain
[7] SQL Editor & @ Annotation Domain
[8] Agent Runtime Domain
[9] Schema Design & Test Data Domain
[10] Backup / Restore Domain
[11] Evaluation & Diagnostics Domain
[12] Frontend Workbench / Presentation Domain
```

其中最重要的边界是：

```text
@ 注解：SQL Editor 的用户快捷操作，不是 Agent Tool。
Agent Tool：Agent Runtime 内部步骤调用，不是 SQL 文本注解。
Semantic Layer：问数前置优化基础设施，不属于 Agent 独占。
TrustGate / Guardrail / PolicyEngine / Confirmation：底层治理能力，可被多个领域复用。
```

---

## 2. 当前代码事实：主要目录与职责

### 2.1 后端入口

```text
engine/api/__init__.py
  -> projects_router
  -> datasources_router
  -> query_router
  -> ai_router
  -> backup_router
  -> table_design_router
```

这说明后端已经按功能路由做了拆分，架构文档应该跟随这些真实边界，而不是只围绕 Agent 写。

### 2.2 主要后端领域文件

```text
engine/models.py
  - Project
  - DatabaseEnvironment
  - DataSource
  - SchemaTable
  - SchemaColumn
  - QueryHistory
  - LLMLog
  - GoldenSQL
  - AgentSession
  - AgentRun
  - AgentArtifactRecord
  - AgentRuntimeEventRecord
  - AgentTraceEventRecord
  - BackupRecord
  - TableDesignDraft

engine/api/projects.py
  - project 管理
  - local mysql environment 管理
  - environment health / logs / lifecycle

engine/api/datasources.py
  - datasource create/list/delete/health
  - schema sync
  - schema tables / columns
  - ER diagram

engine/api/query.py
  - SQL validate
  - SQL execute
  - SQL explain
  - SQL cancel
  - query history

engine/api/ai.py
  - Text-to-SQL generation
  - Agent run / stream
  - Golden SQL benchmark
  - LLM stats

engine/api/table_design.py
  - AI schema modification
  - create table DDL
  - execute DDL
  - table design draft
  - AI table design
  - test data generation

engine/api/backup.py
  - backup list/create/detail
  - restore precheck
  - restore with confirmation

engine/semantic/
  - alias resolver
  - schema linker
  - schema context builder
  - query plan builder

engine/agent/
  - runtime
  - tools
  - types
  - persistence
  - artifacts
  - answer
  - narration
  - result profiler
  - recommendations

engine/policy/
  - PolicyEngine
  - ConfirmationManager
  - redactor

engine/guardrail.py
engine/trust_gate.py
engine/executor.py
engine/schema_sync.py
```

### 2.3 主要前端领域文件

```text
desktop/src/lib/api.ts
  - 前端 API client
  - domain types
  - agent SSE streaming reducer
  - dangerous operation confirmation result type

desktop/src/lib/query-actions/
  - @ 注解解析与执行计划
  - limit / timeout / explain / export / chart processors

desktop/src/pages/WorkbenchPage.tsx
  - 主工作台
  - tabs
  - datasources / schema tree / query / ER / agent panel

desktop/src/features/agent/
  - AgentWorkspace
  - AgentComposer
  - AgentNarrativeStream
  - ArtifactInspector
  - TraceDrawer
  - follow-up context
```

---

## 3. 领域一：App Shell & API Gateway

### 3.1 定位

App Shell 是所有前后端功能的装配层，不承载具体业务逻辑。

### 3.2 当前代码事实

后端 API 聚合在：

```text
engine/api/__init__.py
```

它统一挂载：

```text
/api/v1/projects
/api/v1/datasources
/api/v1/query
/api/v1/query/generate
/api/v1/query/agent-run
/api/v1/backups
/api/v1/schema/design
```

前端 API 聚合在：

```text
desktop/src/lib/api.ts
```

这里同时定义：

```text
Project
DatabaseEnvironment
DataSource
BackupRecord
SchemaTable
SchemaColumn
QueryPlan
TrustGateResult
GeneratedSqlResult
AgentRunResponse
AgentRuntimeEvent
QueryResult
QueryHistory
ERDiagramData
TableDesignDraft
```

### 3.3 架构建议

保留 `api.ts` 作为前端 HTTP client，但建议后续按领域拆分：

```text
desktop/src/lib/api/
  projects.ts
  datasources.ts
  schema.ts
  query.ts
  ai.ts
  agent.ts
  backup.ts
  tableDesign.ts
```

这样可以避免 `api.ts` 继续膨胀，也能让领域边界在前端更清晰。

---

## 4. 领域二：Project / Environment / Datasource Domain

### 4.1 定位

这一层是 DataBox 的工作空间、数据库环境、数据源连接和范围治理基础。很多文档里叫 Workspace，但当前代码里的真实对象叫 `Project`。

### 4.2 当前核心对象

```text
Project
DatabaseEnvironment
DataSource
```

`Project` 用于组织数据源和本地环境。  
`DatabaseEnvironment` 用于本地 MySQL 容器环境。  
`DataSource` 是实际数据库连接配置，包含：

```text
project_id
environment_id
db_type
host / port / database_name / username
password_ciphertext / password_nonce
ssh 配置
ssl 配置
connection_mode
is_read_only
env
status
last_test_xxx
last_sync_xxx
```

### 4.3 当前核心 API

```text
GET  /projects
POST /projects

GET  /projects/{project_id}/environments
POST /environments/local-mysql
POST /environments/{environment_id}/start
POST /environments/{environment_id}/stop
GET  /environments/{environment_id}/health
GET  /environments/{environment_id}/logs

POST /datasources/test
POST /datasources
GET  /datasources
POST /datasources/{id}/health
DELETE /datasources/{id}
```

### 4.4 这一层负责什么

```text
项目 / 工作空间组织
本地环境生命周期
数据源连接配置
连接健康检查
只读 / 环境属性标记
生产环境标记
SSH / SSL 连接属性
删除数据源前的二次确认
```

### 4.5 这一层不负责什么

```text
不负责生成 SQL
不负责 Agent 编排
不负责 @ 注解解析
不负责结果展示
不负责自然语言语义理解
```

### 4.6 设计建议

文档里可以使用“Workspace”作为产品概念，但代码层建议明确：

```text
Product term: Workspace
Current code entity: Project
```

后续如果要做真正的 Workspace Scope，建议新增：

```text
WorkspaceScope
WorkspaceTableScope
WorkspaceMetricScope
```

而不是把 `Project` 直接承担所有语义范围控制。

---

## 5. 领域三：Schema Metadata & ER Domain

### 5.1 定位

Schema Metadata 是问数、SQL 校验、ER 图、表设计、Agent 的共同基础设施。

### 5.2 当前核心对象

```text
SchemaTable
SchemaColumn
```

`SchemaTable` 存：

```text
data_source_id
table_schema
table_name
table_comment
table_type
row_count_estimate
engine_name
```

`SchemaColumn` 存：

```text
table_id
column_name
data_type
column_type
is_nullable
column_default
column_comment
is_primary_key
is_foreign_key
foreign_table_id
foreign_column_id
ordinal_position
```

### 5.3 当前核心流程

```text
datasource
  -> sync_schema
  -> introspect demo / sqlite / mysql / postgresql
  -> replace schema snapshot
  -> update datasource last_sync_at / last_sync_status
```

### 5.4 当前支持的数据源类型

代码里 schema sync 已经区分：

```text
demo db
sqlite
postgresql
mysql
```

### 5.5 ER 图能力

`build_er_diagram_data` 会基于已同步的 `SchemaTable` / `SchemaColumn` 生成：

```text
nodes
edges
real FK edges
inferred FK edges
module_tag
fields
```

其中推断边来自：

```text
xxx_id -> xxx / xxxs / xxxes 表名匹配
```

### 5.6 架构职责

```text
元数据快照
字段类型 / 注释 / 主外键
ER 图
真实关系 + 推断关系
Schema sync 状态
Schema context 的底层数据来源
SQL hallucination 校验的数据来源
```

### 5.7 不负责什么

```text
不决定用户意图
不生成 QueryPlan
不执行 SQL
不做 Agent 状态机
```

---

## 6. 领域四：Semantic Query Optimization Domain

### 6.1 定位

这是“问数前置优化”层。它不是 Agent 的一部分，而是 Text-to-SQL、Agent、SQL 辅助能力共用的问数基础设施。

### 6.2 当前核心模块

```text
engine/semantic/alias.py
engine/semantic/schema_linker.py
engine/semantic/semantic_context.py
engine/semantic/query_plan.py
```

### 6.3 当前能力

#### 6.3.1 SemanticAliasResolver

当前 alias 有默认映射：

```text
销售额 -> orders.total_amount
GMV -> orders.total_amount
订单金额 -> orders.total_amount
用户 -> users
客户 -> users
```

这说明当前语义层已经开始承载业务词和物理 schema 的映射。

#### 6.3.2 SchemaLinker

`SchemaLinker.link()` 会：

```text
读取 datasource 的所有 SchemaTable / SchemaColumn
可选使用 workspace_table_ids 限定候选表
用 alias resolver 匹配业务别名
按 table name / table comment / column name / column comment 打分
小 schema 直接 full context
大 schema 选 top tables
根据外键扩展相关表
返回 selected tables / columns / linking reasons
```

#### 6.3.3 SchemaContextBuilder

把 SchemaLinkingResult 渲染成 prompt 用的类 SQL DDL：

```text
CREATE TABLE table_name (
  column type PRIMARY KEY NOT NULL REFERENCES xxx COMMENT '...'
);
```

#### 6.3.4 QueryPlanBuilder

`QueryPlan` 当前包含：

```text
intent
tables
metrics
dimensions
filters
joins
order_by
limit
warnings
mode
```

它支持：

```text
online LLM query plan
offline heuristic query plan
schema validation for query plan
foreign key join inference
```

### 6.4 架构职责

```text
把自然语言问题映射到候选表/字段
把业务词映射到表/字段
生成可解释的 QueryPlan
压缩 prompt schema context
降低 SQL 幻觉
为 Text-to-SQL 和 Agent 提供前置计划
```

### 6.5 不负责什么

```text
不调用数据库执行 SQL
不处理 @ 注解
不生成最终用户回答
不做审批和恢复
```

### 6.6 建议补强

当前语义层是轻量规则 + alias。后续建议明确设计：

```text
SemanticAliasStore
MetricDefinition
DimensionDefinition
BusinessEntity
WorkspaceTableScope
SchemaLinkingEval
```

这样问数前置优化就不只是 heuristic，而是可配置、可评测的语义基础设施。

---

## 7. 领域五：Text-to-SQL Generation Domain

### 7.1 定位

负责把自然语言问题生成 SQL 候选。它依赖 Semantic Query Optimization，但不等于语义层本身。

### 7.2 当前核心模块

```text
engine/ai.py
```

### 7.3 当前生成链路

```text
question
  -> _build_schema_context_with_metadata
  -> SchemaLinker / full_context
  -> SchemaContextBuilder
  -> QueryPlanBuilder
  -> if no api_key: local heuristic fallback
  -> else: online LLM call
  -> parse SQL from response
  -> TrustGate.evaluate
  -> LLMLog
  -> return sql + model + latency + guardrail + trustGate + queryPlan + schema metadata
```

### 7.4 当前本地 fallback

代码内置大量 demo 规则，例如：

```text
用户数量 -> SELECT COUNT(*) AS total_users FROM users
订单数量 -> SELECT COUNT(*) AS total_orders FROM orders
销售最好的商品 -> join order_items/products
每日订单统计 -> DATE(created_at) group by
支付渠道统计 -> group by payment_method
```

这对本地 demo 和无模型配置场景很重要。

### 7.5 当前审计

`LLMLog` 记录：

```text
request_type
prompt_hash
model_name
latency_ms
status
error_message
prompt_version
prompt_template_hash
model_temperature
max_tokens
schema_validation_warnings
```

### 7.6 不负责什么

```text
不直接执行 SQL
不承担 SQL Editor @ 注解
不负责 Agent 多步状态
不负责高风险 DDL / Restore 操作
```

---

## 8. 领域六：SQL Safety & Execution Domain

### 8.1 定位

这是 DataBox 的安全执行核心，多个上层入口都应该复用：

```text
SQL Editor
Text-to-SQL
Agent
Golden SQL benchmark
Explain
History
```

### 8.2 当前核心模块

```text
engine/guardrail.py
engine/trust_gate.py
engine/policy/engine.py
engine/policy/confirmation.py
engine/executor.py
engine/query_registry.py
engine/policy/redactor.py
```

### 8.3 Guardrail

`guardrail_check` 基于 sqlglot 做 AST 安全分析，当前规则包括：

```text
SQL 不能为空
SQL 长度限制
多语句禁止
只允许 SELECT
禁止 DDL / DML / Command / Merge
禁止系统库 / 系统表
禁止危险函数
禁止系统变量
禁止 SELECT INTO OUTFILE / DUMPFILE
SELECT * warning
无 LIMIT 自动注入 LIMIT 1000
```

### 8.4 TrustGate

`TrustGate` 叠加：

```text
schema validation
guardrail result
risk level
requires confirmation
production datasource confirmation
can_execute
ExecutionSafetyDecision
agent_readonly policy
select_star block
scope_state
blocked_reasons
```

### 8.5 PolicyEngine

`PolicyEngine` 当前用于更广义的操作策略：

```text
query policy
DDL policy
test data policy
restore policy
```

它会基于：

```text
DataSource.is_read_only
DataSource.env == prod
SQL AST mutation detection
```

做拦截。

### 8.6 ConfirmationManager

`ConfirmationManager` 是高风险操作的二次确认机制，当前用于：

```text
delete datasource
execute DDL
generate test data
restore backup
```

它有：

```text
one-time token
TTL
expected action
expected datasource
expected details
expected confirm text
testing-only bypass
```

### 8.7 Executor

`execute_query` 负责：

```text
resolve ExecutionSafetyDecision
guardrail / trust gate block
connect sqlite / mysql / postgresql
timeout / cancellation
fetch rows
serialize values
truncate response
write QueryHistory
return QueryResult
```

### 8.8 QueryRegistry

用于取消正在执行的 SQL：

```text
execution_id
register connection
cancel
unregister
```

### 8.9 架构边界

```text
Guardrail: SQL AST 级安全规则
TrustGate: AI/Agent 生成 SQL 的执行前决策
PolicyEngine: 跨功能高风险操作策略
ConfirmationManager: 用户显式二次确认
Executor: 真实连接数据库执行
QueryHistory: 执行审计
```

这几个模块不要混为一个类，但要在架构图中明确它们是“治理与执行共同底座”。

---

## 9. 领域七：SQL Editor & `@` Annotation Domain

### 9.1 定位

这是 Workbench / SQL Editor 的快捷操作层。它面向的是“用户正在写 SQL 或编辑 SQL”的场景。

### 9.2 当前核心模块

```text
desktop/src/lib/query-actions/types.ts
desktop/src/lib/query-actions/registry.ts
desktop/src/lib/query-actions/index.ts
desktop/src/lib/query-actions/processors/
  limit
  timeout
  explain
  export
  chart
```

### 9.3 当前 Action Engine 抽象

Processor 有四个 phase：

```text
compile
beforeExecute
aroundExecute
afterExecute
```

`QueryExecutionPlan` 包含：

```text
sourceText
actions
pureSql
compiledSql
context
issues
```

`ExecutionContext` 包含：

```text
timeoutMs
exportConfig
chartConfig
extras
```

### 9.4 当前注册的注解

```text
@limit
@timeout
@explain
@export
@chart
```

### 9.5 最重要边界

`@` 注解不是 Agent Tool。

它是 SQL Editor 的：

```text
SQL text annotation
query action DSL
execution preference shortcut
front-end pipeline runtime
```

它不应该进入：

```text
Agent ToolRegistry
AgentPlan
AgentStep
Agent Trace
```

### 9.6 正确交互方式

允许：

```text
Agent 生成 SQL artifact
  -> 用户点击 Open in SQL Editor
  -> 用户在 SQL Editor 手动添加 @limit / @chart / @export
```

不建议：

```text
Agent 内部 tool 调用写成 @limit
AgentPlanStep 使用 @chart 表示 chart tool
把 @ processors 注册进 Agent ToolRegistry
```

---

## 10. 领域八：Agent Runtime Domain

### 10.1 定位

Agent Runtime 是独立 Agent 区域的任务级运行时。它不是 SQL Editor，也不是 `@` 注解层。

### 10.2 当前核心模块

```text
engine/agent/runtime.py
engine/agent/tools.py
engine/agent/types.py
engine/agent/persistence.py
engine/agent/artifacts.py
engine/agent/events.py
engine/agent/narration.py
engine/agent/answer.py
engine/agent/result_profiler.py
engine/agent/recommendations.py
```

### 10.3 当前 Agent 输入输出

当前主要对象：

```text
AgentRunRequest
AgentRunResponse
AgentStep
ToolObservation
AgentArtifact
AgentAnswer
AgentVisibleEvent
AgentTraceEvent
AgentRuntimeEvent
```

### 10.4 当前 Runtime 执行链

当前 `DataBoxAgentRuntime.run_iter()` 是固定管线：

```text
agent.run.started
  -> optional load_follow_up_context
  -> build_schema_context
  -> build_query_plan
  -> generate_sql_candidate
  -> validate_sql
  -> execute_sql or skipped_execute
  -> profile_result
  -> suggest_chart
  -> suggest_followups
  -> answer_synthesizer
  -> artifact events
  -> answer event
  -> agent.run.completed / failed
```

### 10.5 当前 Agent tools.py 中的 tool-like functions

```text
load_followup_context_tool
build_schema_context_tool
build_query_plan_tool
generate_sql_tool
validate_sql_tool
execute_sql_tool
revise_sql_tool
explain_result_tool
suggest_chart_tool
profile_result_tool
answer_synthesizer_tool
suggest_followups_tool
```

这些已经是 Agent Tool 的雏形，但还没有正式的：

```text
ToolSpec
ToolRegistry
ToolExecutor
ToolPolicyAdapter
```

### 10.6 当前持久化

`persistence.py` 支持：

```text
agent session
agent run
runtime events
artifacts
trace events
final response
follow-up context reconstruction
recent run
run events / trace / artifacts list
```

### 10.7 当前前端 Agent 区域

`AgentWorkspace` 已经拆出：

```text
AgentNarrativeStream
ArtifactInspector
AgentComposer
TraceDrawer
```

前端 API 支持：

```text
runAgentQuery
streamAgentQuery
getAgentRun
listAgentSessionRuns
getRecentAgentRun
getAgentRunArtifacts
getAgentRunEvents
getAgentRunTrace
```

### 10.8 这一层不负责什么

```text
不解析 @ 注解
不替代 SQL Editor
不直接管理 datasource 创建
不执行 backup / restore
不执行 DDL 表设计
```

### 10.9 建议补强

优先级从高到低：

```text
1. 把 tools.py 升级成正式 ToolRegistry / ToolSpec
2. 把 run_iter 固定大函数拆成 StepExecutor + EventEmitter + ArtifactEmitter
3. 引入 AgentPlan，但先保持固定模板，不做自由 ReAct
4. 接入 ApprovalGate，把 requires_confirmation 变成 waiting_approval
5. 新增 Checkpoint / Resume
6. 新增 Agent Eval
```

---

## 11. 领域九：Schema Design & Test Data Domain

### 11.1 定位

这是结构设计与数据库变更辅助域，和 Text-to-SQL 查询域不同。它会涉及 DDL 和写入风险，因此必须走 PolicyEngine 与 ConfirmationManager。

### 11.2 当前核心对象

```text
TableDesignDraft
```

### 11.3 当前核心 API

```text
POST /schema/design/ai-modify
POST /schema/design/create-table-ddl
POST /schema/design/execute-ddl
GET  /schema/design/drafts
GET  /schema/design/drafts/{draft_id}
POST /schema/design/drafts/save
DELETE /schema/design/drafts/{draft_id}
POST /schema/design/ai-generate
POST /schema/generate-test-data
```

### 11.4 当前治理

执行 DDL 前：

```text
PolicyEngine.enforce_ddl_policy
ConfirmationManager 二次确认
```

生成测试数据前：

```text
PolicyEngine.enforce_test_data_policy
ConfirmationManager 二次确认
```

### 11.5 与 SQL Query 的边界

```text
SQL Query: 只读 SELECT 问数
Schema Design: DDL / 结构变更 / 测试数据插入
```

这两类不能共用同一个“SQL 执行策略”。DDL 和测试数据属于更高风险域。

---

## 12. 领域十：Backup / Restore Domain

### 12.1 定位

备份恢复是独立的运维能力，不属于 Agent，不属于 SQL Editor，也不属于问数管线。

### 12.2 当前核心对象

```text
BackupRecord
```

### 12.3 当前核心 API

```text
GET  /projects/{project_id}/backups
POST /backups
GET  /backups/{backup_id}
POST /backups/{backup_id}/restore-precheck
POST /backups/{backup_id}/restore
```

### 12.4 当前治理

Restore 是覆盖数据库的高风险操作，当前已经有：

```text
precheck_restore
PolicyEngine.enforce_restore_policy
ConfirmationManager 二次确认
restore 后 sync_schema
```

### 12.5 架构边界

Backup / Restore 可以复用：

```text
Project
Datasource
PolicyEngine
ConfirmationManager
Schema Sync
```

但不应该被包装成 Agent Tool 的默认能力。后续如果 Agent 要建议备份，也应该只是建议，不应自动执行 restore。

---

## 13. 领域十一：Evaluation & Diagnostics Domain

### 13.1 当前能力

代码中已有：

```text
GoldenSQL
LLMLog
QueryHistory
/golden-sql
/golden-sql/run-benchmark
/llm-logs/stats
```

### 13.2 当前 benchmark 流程

```text
读取 GoldenSQL
  -> generate_sql
  -> lexical compare
  -> 如果不同，执行 golden SQL 和 generated SQL
  -> 比较 execution rows
  -> 输出 accuracy_rate / avg_latency_ms / details
```

### 13.3 当前 LLM stats

统计：

```text
total_calls
success_count
failed_count
success_rate
avg_latency_ms
guardrail_total
guardrail_blocked
guardrail_approved
guardrail_block_rate
chart_data
model_dist
```

### 13.4 建议补强

当前 eval 主要是 SQL 级。后续应新增 Agent 级：

```text
AgentGoldenTask
expected_steps
expected_tools
expected_artifacts
expected_tables
expected_final_contains
expected_approval_state
```

但不要替代 GoldenSQL。两套评测并存：

```text
GoldenSQL Eval: 衡量 SQL 生成质量
Agent Eval: 衡量任务完成质量
```

---

## 14. 领域十二：Frontend Workbench / Presentation Domain

### 14.1 定位

Workbench 是多个领域的前端组合，不是单一业务模块。

### 14.2 当前 Workbench 概念

`WorkbenchPage` 中的 tab 包含：

```text
query
table
er
datasources
history
diagnostics
```

这说明前端工作台实际承载：

```text
数据源树
表 / 列元数据
查询标签页
ER 视图
历史记录
诊断
Agent 区域
SQL 打开/编辑
```

### 14.3 Agent 前端区域

`AgentWorkspace` 由这些组件组成：

```text
AgentNarrativeStream
ArtifactInspector
AgentComposer
TraceDrawer
```

它说明 Agent 已经是独立区域，而不是 SQL Editor 的一个小插件。

### 14.4 `@` 注解前端区域

`query-actions` 是 SQL Editor 的内部 DSL，不应和 Agent UI 混在一起。

---

## 15. 全局关键链路设计

### 15.1 数据源初始化链路

```text
Project
  -> create local environment or create datasource
  -> test connection
  -> health check
  -> sync_schema
  -> SchemaTable / SchemaColumn
  -> ER diagram
  -> ready for query / agent / table design
```

### 15.2 普通 Text-to-SQL 问数链路

```text
User question
  -> /query/generate
  -> SchemaLinker / full context
  -> SchemaContextBuilder
  -> QueryPlanBuilder
  -> local heuristic or LLM
  -> TrustGate.evaluate
  -> LLMLog
  -> return GeneratedSqlResult
  -> user reviews SQL
  -> /query/execute
  -> PolicyEngine.enforce_query_policy
  -> execute_query
  -> QueryHistory
  -> result table/chart
```

### 15.3 SQL Editor + `@` 注解链路

```text
SQL text + @ annotations
  -> query-actions.parseAll
  -> QueryExecutionPlan
  -> validate duplicate/conflict
  -> compile pureSql / compiledSql
  -> apply context: timeout/export/chart
  -> /query/validate or /query/execute
  -> result rendering
```

重点：

```text
后端 query API 接收的应该是 pure SQL / compiled SQL。
@ 注解是前端 SQL Editor 层，不是后端 Agent Tool。
```

### 15.4 Agent 分析链路

```text
Agent input
  -> /query/agent-run/stream
  -> DataBoxAgentRuntime.run_iter
  -> AgentRun + Session
  -> build_schema_context
  -> build_query_plan
  -> generate_sql_candidate
  -> validate_sql
  -> execute_sql
  -> profile_result
  -> suggest_chart
  -> suggest_followups
  -> answer_synthesizer
  -> artifacts / trace / events
  -> AgentWorkspace render
```

### 15.5 高风险操作链路

```text
DDL / restore / test data / delete datasource
  -> PolicyEngine
  -> ConfirmationManager creates token
  -> frontend shows confirmation dialog
  -> user enters datasource name
  -> validate_and_consume
  -> execute operation
  -> audit / sync if needed
```

---

## 16. 几个必须明确的架构边界

### 16.1 QueryPlan vs AgentPlan

当前代码已经有 `QueryPlan`，但没有正式 `AgentPlan`。

```text
QueryPlan:
  - 面向一条 SQL 的结构化查询计划
  - tables / metrics / dimensions / filters / joins / order_by / limit

AgentPlan:
  - 面向一个 AgentRun 的任务级计划
  - 多个 step
  - 可能包含多个 QueryPlan
```

建议：

```text
不要用 AgentPlan 替换 QueryPlan。
AgentPlan 应该包含 QueryPlan。
```

### 16.2 TrustGate vs PolicyEngine

```text
TrustGate:
  - 更靠近 AI / Agent 生成 SQL
  - schema validation + guardrail + execution safety decision

PolicyEngine:
  - 更通用的操作策略
  - query / DDL / test data / restore
  - 根据 env / read_only / AST mutation 拦截
```

建议：

```text
保留两者，但统一输出 PolicyDecision 结构。
```

### 16.3 ConfirmationManager vs Agent Approval

当前 ConfirmationManager 是同步式、一次性 token、面向 API 高风险操作。

Agent Approval 应该是持久化的、run-aware 的：

```text
agent_approvals
run_id
step_id
policy_decision
status
approved/rejected
resume
```

建议：

```text
ConfirmationManager 不要直接替代 Agent Approval。
Agent Approval 可以复用 Confirmation 的校验思想，但要持久化到 agent run。
```

### 16.4 `@` Annotation vs Agent Tool

```text
@ Annotation:
  - SQL Editor
  - SQL text
  - 用户显式写入
  - 前端 query-actions
  - 编译 SQL / context

Agent Tool:
  - Agent Runtime
  - 内部步骤调用
  - ToolObservation / Artifact / Event
  - 后端 engine/agent/tools.py
```

建议：

```text
两个 registry 分开。
两个 trace 分开。
底层执行可以共用。
```

### 16.5 Semantic Layer vs Agent

```text
Semantic Layer:
  - 问数基础设施
  - Text-to-SQL 和 Agent 都用
  - 不依赖 Agent 状态

Agent:
  - 任务运行时
  - 依赖 Semantic Layer 作为工具之一
```

---

## 17. 建议的目标架构图

```text
┌────────────────────────────────────────────────────────────┐
│                    Desktop / Workbench UI                  │
│                                                            │
│  Project / Datasource  SQL Editor  ER  History  Agent Area │
│        │              │          │     │          │        │
└────────┼──────────────┼──────────┼─────┼──────────┼────────┘
         │              │          │     │          │
         ▼              ▼          ▼     ▼          ▼
┌────────────────────────────────────────────────────────────┐
│                    FastAPI /api/v1 Routers                 │
│ projects datasources query ai backup table_design          │
└────────────────────────────────────────────────────────────┘
         │              │                         │
         ▼              ▼                         ▼
┌─────────────────┐ ┌─────────────────────┐ ┌──────────────────┐
│ Project/Env/DS  │ │ SQL Query Runtime    │ │ Agent Runtime    │
│ Domain          │ │ validate/execute     │ │ run/stream       │
└─────────────────┘ └─────────────────────┘ └──────────────────┘
         │              │                         │
         ▼              ▼                         ▼
┌────────────────────────────────────────────────────────────┐
│                 Shared Domain Services                     │
│ Schema Metadata | Semantic Linker | QueryPlan | TrustGate   │
│ Guardrail | PolicyEngine | Confirmation | Executor          │
│ QueryHistory | LLMLog | GoldenSQL | Artifact/Event Store    │
└────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────┐
│                 Local Metastore + Target Databases          │
│ SQLite metastore | demo db | mysql | postgresql | sqlite     │
└────────────────────────────────────────────────────────────┘
```

---

## 18. 当前代码基础上的演进路线

### Phase 1：文档和命名先对齐

目标：让团队先理解真实边界。

任务：

```text
README / docs 中把“Workspace”与当前 Project 模型关系写清楚
把 @ 注解明确写成 SQL Editor Action Annotation
把 Agent Runtime 明确写成独立 Agent Area 运行时
把 Semantic Query 写成问数前置优化层，而不是 Agent 附属
```

### Phase 2：前端 API 拆分

目标：降低 `desktop/src/lib/api.ts` 复杂度。

任务：

```text
api/projects.ts
api/datasources.ts
api/schema.ts
api/query.ts
api/ai.ts
api/agent.ts
api/backup.ts
api/tableDesign.ts
```

验收：

```text
行为不变
类型分领域导出
Workbench 引用路径清晰
```

### Phase 3：Agent Runtime 内部重构

目标：不改变外部 API，拆清内部结构。

任务：

```text
ToolSpec / ToolRegistry
StepExecutor
EventEmitter
ArtifactEmitter
AgentState
```

保持当前固定 step 顺序不变。

### Phase 4：Agent Approval / Checkpoint / Resume

目标：把 Agent 从“可观测固定管线”升级成“可暂停可恢复运行时”。

任务：

```text
agent_approvals
agent_checkpoints
waiting_approval status
resume API
frontend ApprovalCard
```

### Phase 5：Semantic Layer 产品化

目标：把当前 alias / linker / query plan 从轻量 heuristic 升级成可配置语义层。

任务：

```text
semantic_aliases table
metric_definitions table
dimension_definitions table
workspace_table_scope table
schema_linking_eval
```

### Phase 6：Evaluation 扩展

目标：SQL 级评测和 Agent 级评测并存。

任务：

```text
保留 GoldenSQL
新增 AgentGoldenTask
新增 Agent regression
Agent trace completeness
artifact correctness
approval correctness
```

---

## 19. 推荐目录演进

### 19.1 后端建议

```text
engine/
  api/
    projects.py
    datasources.py
    schema.py              # 可从 datasources.py 拆出 schema tables/columns/ER
    query.py
    ai.py
    agent.py               # 可从 ai.py 拆出 agent endpoints
    backup.py
    table_design.py

  domain/
    projects/
    datasources/
    schema_metadata/
    semantic_query/
    sql_runtime/
    agent_runtime/
    table_design/
    backup_restore/
    evaluation/
    governance/

  semantic/
    alias.py
    schema_linker.py
    semantic_context.py
    query_plan.py

  agent/
    runtime.py
    planner.py
    executor.py
    registry.py
    tools.py
    state.py
    persistence.py
    artifacts.py
    events.py
    approvals.py
    checkpoints.py

  policy/
    engine.py
    confirmation.py
    redactor.py
```

### 19.2 前端建议

```text
desktop/src/
  lib/api/
    index.ts
    projects.ts
    datasources.ts
    schema.ts
    query.ts
    ai.ts
    agent.ts
    backup.ts
    tableDesign.ts

  lib/query-actions/
    registry.ts
    types.ts
    processors/

  features/
    agent/
    query-editor/
    datasources/
    schema-explorer/
    table-design/
    backup/
    evaluation/

  pages/
    WorkbenchPage.tsx
    DataSourcesPage.tsx
    EnvironmentsPage.tsx
    BackupsPage.tsx
```

---

## 20. 最终定位

DataBox 的架构不应该收敛成一个“大 Agent”。

正确定位是：

```text
DataBox 是本地优先的数据工作台。
Text-to-SQL 是可信问数能力。
Semantic Query 是问数前置优化能力。
SQL Editor 是用户直接操作 SQL 的区域。
@ 注解是 SQL Editor 的快捷操作 DSL。
Agent 是独立分析区域和任务运行时。
TrustGate / Guardrail / Policy / Confirmation 是共享治理底座。
Schema Metadata 是所有问数、执行、ER、Agent、表设计的基础。
Backup / Restore / Table Design 是独立高风险能力域。
Evaluation 是横跨 SQL 与 Agent 的质量保障系统。
```

最终架构应该做到：

```text
领域边界清晰
产品入口清晰
运行时边界清晰
治理底座统一
代码目录逐步对齐
现有功能不重写
Agent 只做自己该做的事
@ 注解只做 SQL Editor 该做的事
语义层成为所有问数能力的前置基础设施
