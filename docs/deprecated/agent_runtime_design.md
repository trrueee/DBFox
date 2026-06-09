# DataBox Agent Runtime 优化方向与详细设计

> 版本：v0.1  
> 日期：2026-06-02  
> 目标：在不推翻现有 Text-to-SQL 管线的前提下，将 DataBox 从“强垂直 SQL 执行管线”升级为“可控、可观测、可恢复的垂直 Agent Runtime”。

---

## 1. 背景与结论

DataBox 当前已经具备非常清晰的本地优先 Text-to-SQL 架构：

```text
NL Question
  -> Workspace Scope
  -> Semantic Layer / Schema Linking
  -> Query Plan
  -> Text-to-SQL Generator
  -> Trust Gate
  -> SQL Action Engine
  -> Local Execution
  -> Visualization / Export
  -> Evaluation Harness
```

这套架构在“可信问数、SQL 生成、安全校验、执行编排、结果展示”场景中已经接近一个垂直 runtime。现有能力主要集中在：

- `QueryPlanBuilder`：结构化查询计划生成与校验。
- `TrustGate`：SQL 安全、schema 校验、执行确认策略。
- `ActionRegistry` / `ActionProcessor`：基于 `@` DSL 的插件式 SQL 行为编排。
- `LLMLog`：模型调用日志和基础审计。
- 本地 heuristic fallback：无模型配置时仍可演示和离线运行。

但如果目标是达到 LangGraph / CrewAI / OpenAI Agents SDK 等开源 Agent Runtime 的效果，DataBox 还需要补齐一层更通用的 Agent Runtime 抽象：

```text
AgentRun
  -> AgentPlan
  -> Step Executor
  -> Tool Registry
  -> State Store
  -> Event Log
  -> Checkpoint / Resume
  -> Approval Gate
  -> Trace / Replay
```

核心判断：

> DataBox 不应该重写成通用 Agent 框架，而应该在现有 SQL Runtime 之上增加一层受控 Agent Runtime。这样既保留 DataBox 的领域优势，又能获得开源 runtime 的长流程、状态、可观测和工具编排能力。

---

## 2. 当前能力评估

### 2.1 已经具备的强项

#### 2.1.1 垂直领域能力强

DataBox 对数据库问数场景有明确边界：

- Workspace 限定业务域。
- Schema Linking 缓解字段幻觉。
- Query Plan 拆解 intent、metrics、dimensions、filters、joins。
- SQL Guardrail 拦截危险查询。
- Action Engine 控制 limit、timeout、export、chart 等执行行为。

这比通用 Agent 框架更适合数据产品，因为它不是让模型自由行动，而是让模型在强约束下完成任务。

#### 2.1.2 Query Plan 是重要资产

现有 `QueryPlan` 已经包含：

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

这相当于 DataBox 的“领域计划语言”。后续不应该废弃，而应该升级为 `AgentPlanStep` 的一种。

#### 2.1.3 Trust Gate 已经接近生产治理层

现有 `TrustGate` 已经支持：

- schema warnings
- guardrail result
- risk level
- production datasource confirmation
- canExecute
- blocked reasons
- execution decision

这比很多开源 demo 更接近真实产品。后续应该把它提升为所有 tool execution 的通用策略层，而不是只服务 SQL。

#### 2.1.4 SQL Action Engine 已有插件 runtime 形态

现有 `ActionProcessor` 的生命周期包括：

```text
compile
beforeExecute
aroundExecute
afterExecute
```

这已经是一个窄域插件系统。下一步可以抽象出更通用的 `ToolRegistry`，让 SQL action 成为 tool 的一种。

---

### 2.2 主要缺口

| 能力 | 当前状态 | 需要增强 |
|---|---|---|
| AgentRun | 暂无统一 run 对象 | 新增任务级运行实体 |
| Step Event Log | 只有 LLMLog，粒度不足 | 记录每个 tool call / llm call / approval / error |
| Tool Registry | 目前偏 SQL action | 升级为通用 tool registry |
| Agent Loop | 当前更像单次管线 | 新增受控多步循环 |
| State Store | 任务状态不完整 | run state、step state、artifact state 持久化 |
| Checkpoint / Resume | 暂无 | 长任务失败后恢复 |
| Human-in-the-loop | SQL 确认已有 | 抽象成通用 approval gate |
| Replay / Trace | 只有基础日志 | 支持完整 run replay 和调试 |
| Multi-step Analysis | 需要增强 | 支持趋势、归因、拆解、多 SQL 合成 |
| Evaluation | README 有方向 | 增加 Agent run 级 eval |

---

## 3. 优化方向总览

### 方向一：从 SQL 管线升级为 Agent Run 管线

当前执行模型：

```text
question -> generate_sql -> trust_gate -> execute -> render
```

目标执行模型：

```text
question
  -> create AgentRun
  -> build AgentPlan
  -> execute steps
  -> call tools
  -> update state
  -> checkpoint
  -> approval if needed
  -> synthesize final answer
```

### 方向二：把 SQL 能力工具化

现有能力应该全部工具化：

```text
schema.link
query_plan.build
sql.generate
sql.validate_schema
sql.trust_gate
sql.execute
sql.revise
chart.render
result.export
insight.summarize
```

这样 Agent 不直接操作底层函数，而是通过统一 tool contract 操作 DataBox 能力。

### 方向三：加入受控 Agent Loop，而不是完全自由 ReAct

DataBox 的安全边界很重要，不建议让模型自由选择任意操作。推荐使用“受控 loop”：

```text
Planner 决定高层计划
Runtime 校验计划合法性
Executor 执行白名单 tool
Policy/TrustGate 拦截风险
State Store 保存每一步
LLM 只在限定节点参与决策
```

### 方向四：把 TrustGate 提升为通用 Policy Engine

当前 TrustGate 主要管 SQL。后续应扩展成：

```text
PolicyEngine
  -> SQLPolicy
  -> DataExportPolicy
  -> ChartPolicy
  -> ExternalActionPolicy
  -> WorkspaceScopePolicy
  -> ProductionConfirmationPolicy
```

### 方向五：补齐可观测性与可恢复性

达到开源 runtime 效果的关键不只是“能执行”，而是：

- 每一步为什么执行？
- 执行了什么输入？
- 调用了什么工具？
- 访问了哪些数据源？
- 是否经过确认？
- 出错后能否恢复？
- 能否复现同一次 run？

---

## 4. 目标架构

### 4.1 分层架构

```text
DataBox Agent Runtime

[1] Agent API Layer
    - POST /agent/runs
    - GET /agent/runs/{run_id}
    - POST /agent/runs/{run_id}/resume
    - POST /agent/runs/{run_id}/approve
    - GET /agent/runs/{run_id}/events

[2] Agent Runtime Core
    - AgentRunManager
    - AgentPlanner
    - StepExecutor
    - StateStore
    - EventLogger
    - CheckpointManager

[3] Tool Layer
    - ToolRegistry
    - ToolSpec
    - ToolExecutor
    - ToolPolicyAdapter

[4] Domain Runtime Layer
    - SQL Runtime
    - QueryPlanBuilder
    - TrustGate
    - ActionRegistry
    - Result Renderer

[5] Governance Layer
    - PolicyEngine
    - ApprovalGate
    - AuditLog
    - PermissionScope

[6] Evaluation Layer
    - AgentRunEval
    - Golden Task Suite
    - Regression Harness
```

### 4.2 与现有模块关系

```text
engine/
  ai.py                      # 保留：Text-to-SQL 生成入口，后续拆出 tools
  trust_gate.py              # 保留：升级为 PolicyEngine 的 SQL policy backend
  semantic/query_plan.py     # 保留：作为 QueryPlan tool 和 AgentPlan 子结构
  guardrail.py               # 保留：作为 SQLPolicy 的底层 checker

新增：
  agent/
    models.py
    runtime.py
    planner.py
    executor.py
    state.py
    events.py
    tools.py
    policies.py
    checkpoints.py
    evals.py
```

---

## 5. 核心对象设计

### 5.1 AgentRun

`AgentRun` 是一次用户任务的顶层实体。

```python
class AgentRun(BaseModel):
    id: str
    user_id: str | None
    workspace_id: str | None
    datasource_id: str | None
    goal: str
    status: Literal[
        "queued",
        "running",
        "waiting_approval",
        "completed",
        "failed",
        "cancelled",
    ]
    mode: Literal["analysis", "readonly", "interactive"]
    state: dict[str, Any]
    final_output: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
```

### 5.2 AgentPlan

`AgentPlan` 是 AgentRun 的高层计划。

```python
class AgentPlan(BaseModel):
    goal: str
    steps: list[AgentPlanStep]
    assumptions: list[str] = []
    required_approvals: list[str] = []
```

### 5.3 AgentPlanStep

```python
class AgentPlanStep(BaseModel):
    id: str
    kind: Literal[
        "build_query_plan",
        "generate_sql",
        "validate_sql",
        "execute_sql",
        "render_chart",
        "export_result",
        "summarize_insight",
        "ask_user",
        "approval",
    ]
    description: str
    tool_name: str | None
    input: dict[str, Any]
    depends_on: list[str] = []
    risk_level: Literal["safe", "warning", "danger"] = "safe"
```

### 5.4 AgentStepEvent

每一步都应该落 event log，支持 trace、debug、replay。

```python
class AgentStepEvent(BaseModel):
    id: str
    run_id: str
    step_id: str | None
    event_type: Literal[
        "run_created",
        "plan_created",
        "llm_call_started",
        "llm_call_finished",
        "tool_call_started",
        "tool_call_finished",
        "approval_required",
        "approval_resolved",
        "checkpoint_saved",
        "run_completed",
        "run_failed",
    ]
    payload: dict[str, Any]
    created_at: datetime
```

### 5.5 ToolSpec

```python
class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None
    risk_level: Literal["safe", "warning", "danger"] = "safe"
    requires_approval: bool = False
    timeout_seconds: int = 30
```

### 5.6 ToolResult

```python
class ToolResult(BaseModel):
    tool_name: str
    ok: bool
    output: dict[str, Any] | None = None
    error: str | None = None
    artifacts: list[dict[str, Any]] = []
    policy_decision: dict[str, Any] | None = None
```

---

## 6. Tool Registry 设计

### 6.1 接口

```python
class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.spec.name] = tool

    def get(self, name: str) -> Tool:
        return self._tools[name]

    def list_specs(self) -> list[ToolSpec]:
        return [tool.spec for tool in self._tools.values()]
```

### 6.2 Tool 抽象

```python
class Tool(Protocol):
    spec: ToolSpec

    async def execute(self, input: dict[str, Any], ctx: AgentContext) -> ToolResult:
        ...
```

### 6.3 首批内置工具

| Tool | 说明 | 风险 |
|---|---|---|
| `schema.link` | 根据问题召回相关表和字段 | safe |
| `query_plan.build` | 生成结构化 QueryPlan | safe |
| `sql.generate` | 生成 SQL | safe |
| `sql.trust_gate` | 执行 SQL 安全检查 | safe |
| `sql.execute_readonly` | 只读执行 SQL | warning |
| `sql.revise` | 根据错误修复 SQL | safe |
| `chart.render` | 根据结果生成图表 spec | safe |
| `result.export` | 导出 CSV/JSON | warning |
| `insight.summarize` | 根据结果生成解释 | safe |

---

## 7. Agent Runtime 执行流程

### 7.1 基础流程

```text
1. 用户提交问题
2. 创建 AgentRun
3. Planner 生成 AgentPlan
4. Runtime 保存 plan_created event
5. StepExecutor 按依赖顺序执行 step
6. 每个 step 调用 ToolRegistry
7. ToolExecutor 调用 PolicyEngine
8. 如果需要确认：run.status = waiting_approval
9. 用户确认后 resume
10. 所有 step 完成后 synthesize final answer
11. run.status = completed
```

### 7.2 伪代码

```python
async def run_agent(goal: str, ctx: AgentContext) -> AgentRun:
    run = await runs.create(goal=goal, ctx=ctx)
    await events.append(run.id, "run_created", {"goal": goal})

    plan = await planner.build(goal, ctx)
    await state.save_plan(run.id, plan)
    await events.append(run.id, "plan_created", plan.model_dump())

    for step in plan.steps:
        decision = await policy.precheck(step, ctx)
        if decision.requires_approval:
            await approvals.create(run.id, step.id, decision)
            await runs.mark_waiting_approval(run.id)
            return run

        await executor.execute_step(run.id, step, ctx)
        await checkpoints.save(run.id)

    final_output = await synthesizer.summarize(run.id)
    await runs.complete(run.id, final_output)
    return run
```

---

## 8. 受控 Agent Loop 设计

DataBox 不建议一开始实现完全自由的 ReAct loop，而建议实现受控 loop。

### 8.1 Loop 状态

```python
class AgentLoopState(BaseModel):
    goal: str
    observations: list[dict[str, Any]]
    completed_steps: list[str]
    pending_steps: list[str]
    artifacts: list[dict[str, Any]]
    risk_flags: list[str]
    final_answer: str | None
```

### 8.2 Loop 终止条件

满足任一条件即停止：

- plan steps 全部完成。
- 达到最大 step 数。
- 达到最大 token/cost/latency 限制。
- 出现 danger risk。
- 需要人工确认。
- planner 判断已有足够信息回答。

### 8.3 默认限制

```text
max_steps = 8
max_sql_queries = 5
max_runtime_seconds = 90
max_export_rows = 10000
max_result_preview_rows = 100
```

---

## 9. Policy Engine 设计

### 9.1 统一策略结果

```python
class PolicyDecision(BaseModel):
    passed: bool
    can_execute: bool
    requires_approval: bool
    risk_level: Literal["safe", "warning", "danger"]
    blocked_reasons: list[str]
    messages: list[str]
    safe_input: dict[str, Any] | None = None
```

### 9.2 SQL Policy

复用现有 `TrustGate.execution_decision`。

检查：

- datasource 是否存在。
- workspace scope 是否允许。
- schema validation 是否通过。
- guardrail 是否 reject。
- prod 数据源是否需要确认。
- agent_readonly 模式是否禁止 `SELECT *`。
- limit 是否存在。

### 9.3 Export Policy

检查：

- 是否包含敏感字段。
- 导出行数是否超过阈值。
- 是否生产环境。
- 是否需要用户确认。

### 9.4 Chart Policy

检查：

- 结果集是否过大。
- x/y 字段是否存在。
- 字段类型是否适合图表。

---

## 10. Checkpoint / Resume 设计

### 10.1 Checkpoint 内容

```python
class AgentCheckpoint(BaseModel):
    run_id: str
    checkpoint_index: int
    status: str
    state: dict[str, Any]
    completed_steps: list[str]
    pending_steps: list[str]
    artifacts: list[dict[str, Any]]
    created_at: datetime
```

### 10.2 恢复策略

- 已完成 step 不重复执行。
- 幂等 tool 可以重试。
- 非幂等 tool 必须要求确认或跳过。
- SQL readonly tool 默认可重试。
- export tool 需要检查 artifact 是否已存在。

---

## 11. API 设计

### 11.1 创建 Agent Run

```http
POST /api/agent/runs
```

请求：

```json
{
  "goal": "分析本周订单下降原因",
  "workspaceId": "workspace_xxx",
  "datasourceId": "ds_xxx",
  "mode": "analysis"
}
```

响应：

```json
{
  "runId": "run_xxx",
  "status": "running"
}
```

### 11.2 获取 Run 状态

```http
GET /api/agent/runs/{run_id}
```

响应：

```json
{
  "runId": "run_xxx",
  "status": "waiting_approval",
  "goal": "分析本周订单下降原因",
  "currentStep": "sql.execute_readonly",
  "requiredApproval": {
    "reason": "Production datasource requires manual confirmation",
    "riskLevel": "warning"
  }
}
```

### 11.3 获取事件流

```http
GET /api/agent/runs/{run_id}/events
```

### 11.4 审批

```http
POST /api/agent/runs/{run_id}/approve
```

请求：

```json
{
  "approvalId": "approval_xxx",
  "decision": "approved"
}
```

### 11.5 恢复执行

```http
POST /api/agent/runs/{run_id}/resume
```

---

## 12. 数据表设计建议

### 12.1 agent_runs

```sql
CREATE TABLE agent_runs (
  id VARCHAR(64) PRIMARY KEY,
  user_id VARCHAR(64),
  workspace_id VARCHAR(64),
  datasource_id VARCHAR(64),
  goal TEXT NOT NULL,
  mode VARCHAR(32) NOT NULL,
  status VARCHAR(32) NOT NULL,
  state_json JSON,
  final_output_json JSON,
  error_message TEXT,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);
```

### 12.2 agent_events

```sql
CREATE TABLE agent_events (
  id VARCHAR(64) PRIMARY KEY,
  run_id VARCHAR(64) NOT NULL,
  step_id VARCHAR(64),
  event_type VARCHAR(64) NOT NULL,
  payload_json JSON,
  created_at TIMESTAMP NOT NULL,
  INDEX idx_agent_events_run_id (run_id),
  FOREIGN KEY (run_id) REFERENCES agent_runs(id)
);
```

### 12.3 agent_checkpoints

```sql
CREATE TABLE agent_checkpoints (
  id VARCHAR(64) PRIMARY KEY,
  run_id VARCHAR(64) NOT NULL,
  checkpoint_index INT NOT NULL,
  state_json JSON NOT NULL,
  created_at TIMESTAMP NOT NULL,
  INDEX idx_agent_checkpoints_run_id (run_id),
  FOREIGN KEY (run_id) REFERENCES agent_runs(id)
);
```

### 12.4 agent_approvals

```sql
CREATE TABLE agent_approvals (
  id VARCHAR(64) PRIMARY KEY,
  run_id VARCHAR(64) NOT NULL,
  step_id VARCHAR(64),
  status VARCHAR(32) NOT NULL,
  risk_level VARCHAR(32) NOT NULL,
  reason TEXT,
  decision VARCHAR(32),
  decided_at TIMESTAMP NULL,
  created_at TIMESTAMP NOT NULL,
  FOREIGN KEY (run_id) REFERENCES agent_runs(id)
);
```

---

## 13. 前端交互设计

### 13.1 Agent Run Timeline

新增一个执行时间线组件：

```text
[✓] 创建任务
[✓] 生成分析计划
[✓] 召回相关表：orders, order_items, products
[✓] 生成 SQL：订单趋势
[✓] Trust Gate 通过
[✓] 执行 SQL
[✓] 生成图表
[ ] 汇总结论
```

### 13.2 Approval Card

当 runtime 进入 `waiting_approval`：

```text
需要确认
原因：生产数据源需要人工确认
将执行：SELECT ...
风险等级：warning
按钮：确认执行 / 拒绝 / 查看详情
```

### 13.3 Trace Drawer

每个 step 可展开：

- 输入
- 输出
- tool name
- latency
- token usage
- policy decision
- SQL diff
- result preview

---

## 14. 与现有 SQL Action Engine 的关系

现有 SQL Action Engine 不废弃，定位调整为：

```text
Agent Runtime
  -> ToolRegistry
    -> sql.execute_readonly tool
      -> SQL Action Engine
        -> @limit
        -> @timeout
        -> @explain
        -> @export
        -> @chart
```

也就是说，SQL Action Engine 继续负责 SQL 内部的声明式控制；Agent Runtime 负责跨工具、跨步骤、跨状态的任务级控制。

---

## 15. 实施路线图

### Phase 1：最小 Agent Runtime 骨架

目标：先跑通一次完整 run。

任务：

- 新增 `engine/agent/models.py`
- 新增 `AgentRun` / `AgentStepEvent`
- 新增 `ToolRegistry`
- 把 `generate_sql` 包成 `sql.generate` tool
- 把 `TrustGate` 包成 `sql.trust_gate` tool
- 新增 `/api/agent/runs`
- 前端展示 run timeline

验收：

- 用户提问后生成 run。
- 至少记录 5 类 event。
- SQL 生成、校验、执行可以通过 tool 完成。

### Phase 2：受控多步分析

目标：支持一个问题拆成多条 SQL。

任务：

- 新增 `AgentPlanner`
- 支持 `AgentPlan.steps`
- 支持 step dependency
- 支持 max_steps / timeout
- 增加 insight summary tool

验收：

- “为什么订单下降”能自动执行趋势、渠道、商品三个查询。
- 最终输出结构化分析结论。

### Phase 3：Approval / Checkpoint / Resume

目标：接近生产 runtime。

任务：

- 新增 `agent_approvals`
- 新增 checkpoint 保存
- 支持 waiting_approval
- 支持 resume
- 支持失败重试

验收：

- prod datasource 自动进入确认态。
- 用户批准后继续执行。
- 服务重启后可从 checkpoint 恢复。

### Phase 4：Evaluation Harness 升级

目标：用测试集衡量 Agent 效果。

任务：

- 新增 Agent golden tasks
- 指标：completion rate、step success rate、SQL accuracy、approval correctness、latency、cost
- 增加回归测试

验收：

- 每次改 runtime 可以跑 agent eval。
- 能看到版本间能力变化。

---

## 16. 测试设计

### 16.1 单元测试

- ToolRegistry 注册 / 查询 / 重复注册。
- AgentRun 状态流转。
- PolicyDecision 生成。
- EventLogger 事件写入。
- Checkpoint 序列化 / 反序列化。

### 16.2 集成测试

- NL -> AgentRun -> SQL -> TrustGate -> Execute -> Final Output。
- schema warning 导致阻断。
- prod datasource 需要 approval。
- approval 后 resume。
- SQL tool timeout。

### 16.3 回归测试

基于 Golden Task：

```json
{
  "goal": "统计最近 7 天订单数量趋势",
  "expected_tools": ["query_plan.build", "sql.generate", "sql.trust_gate", "sql.execute_readonly"],
  "expected_tables": ["orders"],
  "expected_final_contains": ["趋势", "订单"]
}
```

---

## 17. 成功指标

### 17.1 Runtime 指标

- Run completion rate >= 95%
- Tool success rate >= 98%
- Failed run replayable rate >= 95%
- Approval correctness >= 99%
- P95 run latency 可观测

### 17.2 Text-to-SQL 指标

- Valid SQL Rate
- Execution Accuracy
- Schema Linking Recall
- Hallucination Rate
- Revise Success Rate

### 17.3 产品体验指标

- 用户是否理解 Agent 正在做什么。
- 用户是否能在风险操作前确认。
- 用户是否能复查每一步。
- 用户是否能复用分析结果。

---

## 18. 风险与取舍

### 18.1 不建议一开始做完全通用 Agent

原因：

- 会削弱 DataBox 的强安全边界。
- 会增加不可控 tool call。
- 会让 SQL 产品复杂度过高。

推荐：

```text
先做 DataBox-specific controlled agent runtime。
后续再抽象通用能力。
```

### 18.2 不建议替换现有 QueryPlan

QueryPlan 是领域优势，应作为 AgentPlan 的子结构保留。

### 18.3 不建议引入多 Agent 作为第一阶段

多 Agent 会增加调试和状态复杂度。第一阶段应该先做好单 Agent 多步执行。

---

## 19. 最终目标形态

最终 DataBox Agent Runtime 应该具备：

```text
可信：所有数据访问都经过 scope + policy + trust gate
可控：模型不能自由越权执行工具
可观测：每一步都有 event trace
可恢复：长任务有 checkpoint/resume
可评测：每个版本都能跑 golden tasks
可扩展：SQL、chart、export、insight 都是 tools
领域强：QueryPlan / SchemaLinking / TrustGate 保持核心优势
```

最终定位：

> DataBox Agent Runtime 不是通用开源 Agent 框架的复制品，而是面向本地优先可信数据探索场景的垂直 Agent Runtime。它应该在 Databox 问数和数据分析场景中达到甚至超过通用开源 runtime 的实际效果。
# 2026-06-04 Agent Kernel Implementation Contract

This section records the current Agent Kernel behavior after the approval-aware follow-up and artifact-streaming work.

## Division of responsibility

The frontend provides context only. It does not classify whether the user wants to explain, approve, reject, or modify SQL.

The backend controller decides intent from current state, workspace context, artifacts, pending approval, SQL, safety, and recent tool results.

PolicyGate enforces tool safety. TrustGate validates SQL before execution. Approval API endpoints are the only path for clear approve or reject decisions.

## PlanState and tool execution sync

Controller `update_plan` decisions produce PlanState patches. The reducer supports creating, updating, clearing, running, completing, failing, and skipping steps.

Tool execution also updates PlanState automatically:

- before a matched tool final status, the plan step is marked running
- successful tools mark the matched step completed
- failed tools mark the matched step failed
- skipped tools mark the matched step skipped

The `agent_plan` artifact is streamed as soon as a plan is available, before the planned tool runs. Its stable semantic id is `agent_plan_draft`; its UI title is `Agent plan`.

## Artifact identity and dependencies

Artifacts should expose stable `semantic_id` values so streamed drafts and final artifacts can be merged without duplicate cards. The frontend reducer keys artifacts by `semantic_id` when present, otherwise by `id`.

Artifact dependencies are bound from semantic ids to real artifact ids before the final response contract is validated. Answer evidence uses real artifact ids as well.

Recommendation artifacts may depend on `result_profile`, but if no profile artifact exists they fall back to an existing artifact in this order:

```text
result_profile
result_table
sql_candidate
safety_report
```

This avoids dangling dependencies in responses that have recommendations but no profile artifact.

## Pending approval revision state machine

When `pending_approval` exists:

- questions about SQL, risk, safety, or why approval is needed can be answered from current state
- user-requested SQL modifications go through `sql.revise`
- revised SQL is never executed directly
- revised SQL must be validated again before execution
- clear approve or reject intent goes through the approval API flow

`sql.revise` accepts `instruction`, `user_instruction`, `reason`, and `error`. It resolves SQL from explicit args first, then current state, then pending approval requested action SQL.

If `sql.revise` returns no `fixed_sql`, the previous pending approval remains valid. The old approval is not expired, and stale safety or execution state is not cleared.

If `sql.revise` returns `fixed_sql`, stale safety, execution, profile, chart, and suggestions are cleared. Any previous pending approval is expired as superseded. The revised SQL must pass `sql.validate` before any execution can be considered.

If validation of the revised SQL still requires confirmation, PolicyGate creates a new pending approval. The final waiting response points to the new pending approval; the expired approval is only historical state.

## Recommendation artifact frontend

`RecommendationArtifactView` renders recommendation artifacts as actionable next steps and follow-up questions. Follow-up buttons call `onAsk(question, workspace_context)` and preserve the workspace context supplied by `AgentWorkspace`.

During `waiting_approval`, `AgentWorkspace` still shows `AgentComposer` with the approval-specific placeholder:

```text
Ask about this pending approval, SQL, or risk
```

The workspace context includes pending approval id, status, reason, selected SQL, active SQL, and selected artifact id. The backend controller decides whether the follow-up is explanatory or requires `sql.revise`.

---
