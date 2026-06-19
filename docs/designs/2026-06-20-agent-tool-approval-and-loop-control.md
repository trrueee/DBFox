# Agent Tool Approval and Loop Control — Design Spec

> 2026-06-20 | split SQL validation from execution, route manual approval correctly, and stop recursive tool loops

## 1. Context

DBFox Agent 当前 tool 调用链路里有两个明显问题：

```text
1. manual confirmation 没有真正弹到前端审批，而是变成 db.query failed。
2. ReAct loop 对 allowed tools 的失败 / 空结果 / 重复调用缺少熔断，容易跑到 max_steps。
```

当前 `db.query` 一个 tool 同时承担：

```text
1. SQL validation
2. TrustGate safety decision
3. manual confirmation decision
4. SQL execution
```

这导致 manual confirmation 没有插入点。

当 TrustGate 发现：

```text
requires_confirmation = true
blocked_reasons = ["requires_confirmation"]
can_execute = false
```

`execute_query()` 会把它当作阻断错误抛出，tool runtime 得到 failed observation。Agent 看到 failed tool 后可能继续修复、重试或重新 query，最后递归到 max_steps。

正确设计应把 SQL validate 和 SQL execute 拆开：

```text
sql.validate          # 只验证，不读真实数据
sql.execute_readonly  # 只执行已验证 SQL
```

manual approval 应发生在 `sql.execute_readonly` 进入真正执行之前，由 `PolicyGate` 统一转换成 `approval_required`，再进入 LangGraph approval interrupt。

## 2. Goals

目标：

1. `db.query` 不再作为 Agent 主执行 tool。
2. 新增 `sql.validate` tool。
3. 新增 `sql.execute_readonly` tool。
4. manual confirmation 必须从 TrustGate safety decision 转成 Agent approval interrupt。
5. 用户批准后，继续执行同一个已验证 SQL，不重新触发 confirmation。
6. Agent 不得重复调用同一个失败 / 空结果 / 无新信息 tool 直到 max_steps。
7. 前端看到的 tool 状态、approval 状态、checkpoint 状态必须一致。

非目标：

1. 不改变 TrustGate 的底层 SQL 安全规则。
2. 不降低生产环境确认要求。
3. 不让 LLM 自己决定是否需要人工确认。
4. 不让 execute tool 重新生成或修改 SQL。

## 3. Current Failure Mode

### 3.1 Current `db.query` Path

当前路径：

```text
model
  -> db.query(sql)
  -> execute_query(... safety_policy="agent_readonly")
  -> TrustGate.execution_decision()
  -> requires_confirmation=True
  -> blocked_reasons += ["requires_confirmation"]
  -> can_execute=False
  -> execute_query throws GuardrailValidationError
  -> ToolObservation(status="failed")
  -> progress continues ReAct loop
```

问题：

```text
requires_confirmation 被当作失败，而不是 pending approval。
```

### 3.2 Why PolicyGate Does Not Catch It

PolicyGate 里已经有 `requires_validated_sql` 逻辑，但 active `db.query` tool 当前没有设置：

```text
requires_validated_sql=True
```

因此 `_rule_validated_sql()` 不会拦截 `db.query`。

这意味着：

```text
manual approval 发生在 execute_query 内部，已经太晚了。
```

### 3.3 Warning Also Requires Confirmation

当前 TrustGate 规则不是只有 prod 才确认。

对于 Agent 自动执行：

```text
policy = agent_readonly
requires_confirmation = env == "prod" or risk_level == "warning"
```

所以以下情况都可能触发 manual confirmation：

```text
1. prod datasource
2. non-prod datasource but SQL risk_level=warning
```

这条规则可以保留，但必须正确进入 approval flow。

## 4. Target Tool Design

### 4.1 Replace Agent-Facing `db.query`

Agent 主工具链应从：

```text
db.observe -> db.search -> db.inspect -> db.preview -> db.query -> answer.synthesize
```

改为：

```text
db.observe -> db.search -> db.inspect -> db.preview -> sql.validate -> sql.execute_readonly -> answer.synthesize
```

`db.query` 可以短期保留给 legacy / compatibility，但不应该暴露给 Agent model。

### 4.2 `sql.validate`

职责：

```text
只做 SQL 安全验证，不执行真实查询。
```

输入：

```json
{
  "sql": "SELECT id, name FROM users",
  "question": "用户原始问题"
}
```

输出：

```json
{
  "can_execute": true,
  "requires_confirmation": false,
  "safe_sql": "SELECT id, name FROM users LIMIT 100",
  "original_sql": "SELECT id, name FROM users",
  "risk_level": "safe",
  "blocked_reasons": [],
  "messages": []
}
```

如果需要确认：

```json
{
  "can_execute": false,
  "requires_confirmation": true,
  "safe_sql": "SELECT id, name FROM users LIMIT 100",
  "original_sql": "SELECT id, name FROM users",
  "risk_level": "warning",
  "blocked_reasons": ["requires_confirmation"],
  "messages": ["Production datasource agent execution requires manual confirmation."]
}
```

注意：`sql.validate` 不应该因为 `requires_confirmation` 返回 failed。它应该返回 success observation，并把 safety decision 写入 state。

Tool spec：

```python
class SqlValidateTool(BaseTool[SqlValidateInput, LooseOutput]):
    name = "sql.validate"
    group = "sql"
    policy = ToolPolicy(side_effect="none", risk_level="safe")
    state = ToolStateSpec(produces=("safety", "sql"), merge_strategy="new")
```

### 4.3 `sql.execute_readonly`

职责：

```text
只执行已经通过 sql.validate 生成的 safe_sql。
```

输入：

```json
{
  "sql": "SELECT id, name FROM users LIMIT 100",
  "question": "用户原始问题"
}
```

Tool spec：

```python
class SqlExecuteReadonlyTool(BaseTool[SqlExecuteReadonlyInput, LooseOutput]):
    name = "sql.execute_readonly"
    group = "sql"
    policy = ToolPolicy(
        side_effect="read",
        risk_level="warning",
        requires_validated_sql=True,
    )
    state = ToolStateSpec(
        consumes=("safety", "sql"),
        produces=("execution",),
        clear_on_success=("error", "last_error_telemetry", "last_failed_tool_call"),
        merge_strategy="new",
    )
```

`sql.execute_readonly` 不允许执行任意 SQL。它必须满足：

```text
1. state.safety 存在。
2. input.sql 与 state.safety.safe_sql 或 state.safety.original_sql 一致。
3. safety.can_execute 为 true，或者只因为 requires_confirmation 需要审批。
4. 如果 requires_confirmation=true，PolicyGate 必须先返回 approval_required。
```

## 5. Approval Flow

### 5.1 Normal Safe Path

```text
model calls sql.validate
  -> safety.can_execute=true
  -> safety.requires_confirmation=false

model calls sql.execute_readonly
  -> PolicyGate checks state.safety
  -> allowed
  -> tool executes safe_sql
  -> execution stored in state
```

### 5.2 Manual Confirmation Path

```text
model calls sql.validate
  -> safety.can_execute=false
  -> safety.requires_confirmation=true
  -> safety.blocked_reasons=["requires_confirmation"]

model calls sql.execute_readonly
  -> PolicyGate sees requires_confirmation
  -> returns approval_required
  -> policy_node creates pending_approval
  -> graph routes to approval node
  -> frontend displays approval UI
```

User approves:

```text
approval_node
  -> clears safety.requires_confirmation
  -> removes requires_confirmation from blocked_reasons
  -> sets safety.can_execute=true
  -> reconstructs allowed_tool_calls=[sql.execute_readonly]
  -> graph routes to tools
  -> sql.execute_readonly executes safe_sql using supplied safety_decision
```

User rejects:

```text
approval_node
  -> approval_result.status=rejected
  -> allowed_tool_calls=[]
  -> run finalizes as rejected / failed
```

### 5.3 Important Rule

`sql.execute_readonly` must call `execute_query()` with the existing safety decision:

```python
execute_query(
    db,
    datasource_id,
    safe_sql,
    question=question,
    safety_decision=state["safety"],
    safety_policy="agent_readonly",
    redact=True,
)
```

Do not call `execute_query()` without `safety_decision`, or TrustGate will re-evaluate and may require confirmation again.

## 6. PolicyGate Changes

### 6.1 Allow Confirmation-Only Safety State

Current `_rule_validated_sql()` expects:

```text
can_execute=true
safe_sql exists
```

But after validation, confirmation-required state is valid even though:

```text
can_execute=false
blocked_reasons=["requires_confirmation"]
```

PolicyGate should treat this as approval-required, not blocked.

Required behavior:

```text
if blocked_reasons only contains "requires_confirmation":
    return approval_required
```

Only hard blockers should block:

```text
guardrail_reject
schema_error
syntax_error
select_star
safe_sql_missing
datasource_scope
```

### 6.2 Do Not Store Allowed Calls While Waiting Approval

When policy returns `approval_required`, `policy_node` should not also set `allowed_tool_calls`.

Bad:

```python
return {
    "status": "waiting_approval",
    "pending_approval": pending,
    "allowed_tool_calls": [safe_tool_call],
}
```

Good:

```python
return {
    "status": "waiting_approval",
    "pending_approval": pending,
    "allowed_tool_calls": [],
}
```

Only `approval_node` should create the executable tool call after approval.

This avoids stale tool calls leaking through checkpoints, frontend state, or resume flows.

## 7. Tool Loop Control

### 7.1 Problem

Current progress logic effectively says:

```text
if last_tool_results exists:
    continue ReAct loop
```

This is too weak. It treats these as the same:

```text
1. successful tool with useful new evidence
2. successful tool with empty result
3. failed tool
4. same tool with same args and same result repeated
```

The result is recursive tool loops until max_steps.

### 7.2 Add Tool Call History

State should track recent normalized tool calls:

```python
tool_call_history: list[dict]
```

Each entry:

```json
{
  "tool_name": "db.search",
  "args_hash": "...",
  "status": "success",
  "result_signature": "empty_results",
  "step_count": 4
}
```

`args_hash` should be computed from canonical JSON:

```python
json.dumps(args, sort_keys=True, ensure_ascii=False)
```

`result_signature` examples:

```text
db.search: results_count=0 / top_names hash
db.inspect: status failed + error class
db.query: safe_sql hash + returned_rows + error class
schema.describe_table: table not found / column count
```

### 7.3 Repetition Rules

Hard stop / finalize when:

```text
1. same tool + same args + same failure repeated 2 times
2. db.search same query returns empty results 2 times
3. schema.describe_table same table not found 2 times
4. db.query same SQL returns same execution error 2 times
5. sql.validate same SQL has same hard blockers 2 times
```

Soft replan once when:

```text
1. db.search returns empty once
2. db.inspect returns missing object once
3. sql.validate returns schema warning once
```

After soft replan budget is exhausted, finalize or ask user.

### 7.4 Progress Fast Path Change

Replace:

```python
if state.get("last_tool_results"):
    return continue
```

With:

```text
if last tool failed and repeat limit hit:
    failed / clarify / finalize
elif last tool failed and repairable:
    repair
elif last tool success but no new evidence:
    replan once
elif last tool success with useful evidence:
    continue
else:
    LLM progress judge
```

### 7.5 Define Useful Evidence

Tool result is useful if it produces new state that can move toward answering.

Examples:

```text
db.search: results length > 0
db.inspect: table columns returned
db.preview: rows returned or schema sample returned
db.query: execution success and rows/columns returned
sql.validate: safe_sql returned and no hard blockers
result.profile: profile produced
answer.synthesize: answer produced
```

Tool result is not useful if:

```text
db.search: 0 results
schema.describe_table: table not found
db.inspect: object missing
sql.validate: same hard blocker
db.query: same execution error
```

## 8. State Merge Fix

The app service `_merge_state()` currently appends all list fields. This is wrong for routing lists.

These should be replace semantics:

```text
allowed_tool_calls
blocked_tool_calls
pending_tool_calls
last_tool_results
allowed_tool_groups
```

These should remain append semantics:

```text
messages
trace_events
runtime_events
artifacts
plan_events
suggestions
repair_trace
```

If a node returns:

```python
{"allowed_tool_calls": []}
```

service accumulated state must clear previous allowed calls.

This is especially important around approval resume, because stale `allowed_tool_calls` can make frontend / checkpoint state disagree with graph state.

## 9. Frontend Expectations

Frontend approval UI should show approval only when backend state has:

```text
status = waiting_approval
pending_approval != null
```

Approval payload should include:

```json
{
  "tool_name": "sql.execute_readonly",
  "risk_level": "warning",
  "reason": "Production datasource agent execution requires manual confirmation.",
  "requested_action": {
    "tool_name": "sql.execute_readonly",
    "args": {
      "sql": "SELECT ... LIMIT 100"
    }
  },
  "safety": {
    "safe_sql": "SELECT ... LIMIT 100",
    "risk_level": "warning",
    "blocked_reasons": ["requires_confirmation"]
  }
}
```

Frontend should not call SQL execution directly after user approval. It should call the existing approval resume endpoint, and the graph should continue from the checkpoint.

## 10. Migration Plan

### Phase 1 — Add New Tools

```text
1. Add sql.validate.
2. Add sql.execute_readonly.
3. Register group "sql" in TOOL_GROUP_MAP.
4. Expose sql tools to model.
5. Remove db.query from model-facing tool list.
```

### Phase 2 — Wire Approval

```text
1. Make sql.validate write safety + sql state.
2. Make sql.execute_readonly require validated SQL.
3. Adjust PolicyGate to treat requires_confirmation-only as approval_required.
4. Ensure policy_node does not store allowed_tool_calls while waiting approval.
5. Ensure approval_node is the only node that creates allowed_tool_calls after approval.
```

### Phase 3 — Loop Control

```text
1. Add tool_call_history state.
2. Add result_signature helpers.
3. Add repeated allowed tool detection.
4. Replace unconditional last_tool_results -> continue behavior.
5. Add tests for repeated empty db.search, repeated table-not-found, repeated same SQL error.
```

### Phase 4 — State Merge Fix

```text
1. Replace routing list keys in service accumulated state.
2. Keep append semantics only for event/history lists.
3. Add approval checkpoint/resume regression tests.
```

### Phase 5 — Remove Legacy Path

```text
1. Keep db.query available internally or legacy-only.
2. Do not expose db.query to Agent model.
3. Remove old tests that assume db.query handles validation + execution + confirmation in one step.
```

## 11. Required Tests

### Approval Tests

```text
1. sql.validate on prod datasource returns requires_confirmation but does not fail.
2. sql.execute_readonly after confirmation-required validation returns approval_required from PolicyGate.
3. approval_node approved clears requires_confirmation and executes safe_sql.
4. approval_node rejected finalizes without executing SQL.
5. approved execute reuses supplied safety_decision and does not re-trigger confirmation.
```

### Policy Tests

```text
1. sql.execute_readonly without state.safety is blocked.
2. sql.execute_readonly with mismatched SQL is blocked.
3. sql.execute_readonly with hard blockers is blocked.
4. sql.execute_readonly with only requires_confirmation returns approval_required.
5. sql.validate is always no-side-effect and does not require approval.
```

### Loop Tests

```text
1. same db.search empty result twice triggers stop / clarify.
2. same schema.describe_table not found twice triggers stop / clarify.
3. same db.query / sql.execute_readonly error twice triggers stop.
4. one empty search can replan once.
5. useful db.search result continues normally.
```

### Merge Tests

```text
1. allowed_tool_calls=[] clears accumulated allowed calls.
2. last_tool_results=[] clears previous last results.
3. trace_events still append.
4. approval checkpoint does not store stale allowed_tool_calls.
```

## 12. Summary

The fix is not to patch `db.query` in place. The right boundary is:

```text
sql.validate = decide what is safe
PolicyGate = decide whether approved execution is allowed
approval_node = wait for human if needed
sql.execute_readonly = execute only already-safe SQL
```

And the ReAct loop must stop treating every tool observation as progress. Empty, failed, or repeated allowed tool calls need explicit loop control before they consume the whole max_steps budget.
