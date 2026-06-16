# DataBox Analysis Agent Flow Design

Date: 2026-06-16
Status: approved for implementation planning

## Context

DataBox is positioned as an autonomous data analysis agent, but the current runtime behaves more like a database query assistant. For database questions, the agent usually explores schema, writes SQL through `db.query`, then returns a direct answer from the raw result. Existing skill specs such as `safe_data_lookup` and `result_analysis` describe a richer flow with result profiling, chart suggestion, and answer synthesis, but that path is not wired into the active default flow.

Observed implementation gaps:

- `engine/agent/model/system_prompt.py` tells the model: "Once db.query returns data, synthesize a direct answer" and explicitly says not to call more tools unless the result is wrong or incomplete.
- `engine/agent/app/service.py` initializes `FULL_SAFE_TOOL_GROUPS` with only `environment`, `schema`, `db`, `semantic`, and `memory`.
- `engine/tools/databox_tools.py` only lets `escalate.tool_group` request `environment`, `schema`, `db`, `semantic`, `memory`, and `execution`.
- Built-in tool specs under `engine/tools/builtin` do not currently expose `result.profile`, `chart.suggest`, or `answer.synthesize`.
- `engine/agent_core/databinding.py` binds `db.query` into `execution`, but does not bind `result.profile`, `chart.suggest`, or `answer.synthesize` into `result_profile`, `chart_suggestion`, and `answer`.

## Decision

Use the "smart triggered analysis" behavior.

The agent should not treat a successful database query as the finish line. Every successful `db.query` should receive at least a short interpretation step before final response. Deeper result analysis should be required when the user asks for statistics, trends, comparisons, rankings, anomalies, changes, causes, business performance, or recommendations.

This balances product positioning and ergonomics:

- It makes DataBox feel like an analysis agent by default.
- It avoids turning simple detail lookups into long reports.
- It keeps chart generation useful rather than noisy.
- It gives the runtime deterministic hooks that tests can verify.

## Behavioral Contract

After a successful `db.query`:

1. The agent must reflect on whether the result answers the user's analytical intent.
2. The agent must not immediately finalize with only raw rows or a raw number.
3. The agent must produce an answer that includes interpretation grounded in the query result.
4. If the result is empty, truncated, unexpectedly small, or unexpectedly large, the answer must mention the limitation or likely reason.
5. If the question is analytical, the agent must profile the result before final answer.

Analytical questions include:

- Trend questions: growth, decline, changes over time, recent movement.
- Comparison questions: segment A versus B, before versus after, top and bottom groups.
- Ranking questions: top N, worst N, largest contributors.
- Anomaly questions: outliers, spikes, drops, unusual values.
- Explanation questions: why, reason, root cause, what caused.
- Recommendation questions: what should we do, next step, action suggestion.
- Aggregation questions where raw totals alone are insufficient.

Simple detail lookups include:

- "List the latest 10 orders."
- "Show the rows for customer X."
- "What is the email for user Y?"
- "How many records match this exact filter?"

For simple detail lookups, `result.profile` may be skipped, but the final answer still needs a concise interpretation such as result count, visible constraints, and a short caveat when appropriate.

## Proposed Runtime Shape

### Tool Surface

Expose these analysis groups to the active runtime:

- `result` for `result.profile`
- `chart` for `chart.suggest`
- `answer` for `answer.synthesize`

The default safe groups should include `result` and `answer`. `chart` can be available by escalation or default-safe if its implementation is read-only and deterministic. The recommended initial implementation includes all three in the safe set because chart suggestion is derived from existing result data and has no database side effect.

### Tool Registration

Add built-in tool specs and handlers for:

- `result.profile`: consumes `execution`, produces a `ResultProfile`-shaped output.
- `chart.suggest`: consumes `execution` and optionally `result_profile`, produces a chart suggestion when useful.
- `answer.synthesize`: consumes question, SQL, safety, execution, result profile, chart suggestion, and suggestions, then produces the structured `AgentAnswer`.

Where possible, reuse existing core functions:

- `engine.agent_core.answer.synthesize_agent_answer`
- existing `ResultProfile` data model
- existing artifact builders in `engine.agent_core.artifacts`
- any existing recommendation helpers

### State Binding

Extend `engine/agent_core/databinding.py` so successful analysis tool calls update state:

- `result.profile` -> `result_profile`
- `chart.suggest` -> `chart_suggestion`
- `answer.synthesize` -> `answer` and `final_answer`

This lets `finalize_answer` preserve structured findings, evidence, caveats, recommendations, and follow-up questions instead of relying only on the last natural-language model message.

### Prompt Guidance

Replace the current "STOP and answer" query-result guidance with:

- Successful `db.query` means the data acquisition phase is done, not the task.
- For analytical questions, call `result.profile`, optionally `chart.suggest`, then `answer.synthesize`.
- For simple detail lookups, provide a concise interpreted answer, not just raw rows.
- Do not call additional database tools unless the result is wrong, incomplete, empty due to likely over-filtering, or the user asks for follow-up investigation.

The prompt should still discourage unnecessary tool calls for chat and non-data questions.

### Deterministic Guard

Prompt-only changes are not enough. Add a small runtime guard after tool observation or in routing/progress logic:

- If the latest successful tool is `db.query` and the task is analytical, the graph should continue rather than finalize until `result_profile` exists.
- If `answer.synthesize` has run successfully, the graph may finalize.
- If the query is a simple detail lookup, finalization can proceed only when the final answer includes interpretation rather than an empty or raw tool summary.

The guard should be conservative and focused. It should not generate new SQL by itself.

## Data Flow

Analytical query:

1. User asks a data question.
2. Agent uses `db.observe`, `db.search`, `db.inspect`, and `db.preview` as needed.
3. Agent executes `db.query`.
4. Observation binds result into `execution` and emits table artifact.
5. Agent calls `result.profile`.
6. Observation binds `result_profile` and emits profile artifact.
7. Agent calls `chart.suggest` when the result shape benefits from visualization.
8. Observation binds `chart_suggestion` and emits chart artifact.
9. Agent calls `answer.synthesize`.
10. Observation binds structured answer.
11. Finalization returns the synthesized analysis answer.

Simple detail query:

1. User asks for specific rows or a specific value.
2. Agent executes a safe database lookup.
3. Agent finalizes with a concise interpreted answer, including count and caveats.
4. Agent may skip chart and deep profiling.

## Error Handling

- If `result.profile` fails, answer with the query result plus a caveat that profiling failed.
- If `chart.suggest` fails, do not fail the run; continue to `answer.synthesize` without a chart.
- If `answer.synthesize` fails, fall back to a structured answer assembled from `execution` and `result_profile`.
- Empty results should trigger a short diagnostic explanation and, when likely over-filtered, a suggested follow-up query rather than silent completion.
- Truncated results should explicitly say that findings are based on returned rows and mention the limit.

## Tests

Add or update tests that prove:

- Default safe groups include `result`, `chart`, and `answer`.
- `escalate.tool_group` accepts `result`, `chart`, and `answer`.
- Built-in registry loads `result.profile`, `chart.suggest`, and `answer.synthesize`.
- Databinding stores outputs from those tools in `result_profile`, `chart_suggestion`, and `answer`.
- The system prompt no longer instructs the model to stop immediately after `db.query`.
- An analytical data question cannot complete immediately after `db.query` without a profile or synthesized answer.
- A simple detail lookup may skip chart/profile but still returns an interpreted answer.

## Implementation Plan

### Phase 1: Tool Specs and Handlers (foundation)

No new Python modules required. All three tools wrap existing pure functions.

**New files:**

| File | Purpose |
|------|---------|
| `engine/tools/builtin/result_profile.yaml` | Builtin YAML spec for `result.profile` |
| `engine/tools/builtin/chart_suggest.yaml` | Builtin YAML spec for `chart.suggest` |
| `engine/tools/builtin/answer_synthesize.yaml` | Builtin YAML spec for `answer.synthesize` |

**Modified files:**

| File | Change |
|------|--------|
| `engine/tools/databox_tools.py` | Register handlers `result_profile_handler`, `chart_suggest_handler`, `answer_synthesize_handler` via `handlers.force_register`. Add `"result"`, `"chart"`, `"answer"` to `valid_groups` in `_escalate_tool_group`. |
| `engine/agent_core/tool_registry.py` | Add `"result."`, `"chart."`, `"answer."` prefixes to `TOOL_GROUP_MAP`. |

**Handler implementations** (all in `engine/tools/databox_tools.py` as thin wrappers):

```python
def _result_profile_handler(ctx, args):
    # Reuse engine.agent_core.result_profiler.profile_result
    # Consumes ctx.state_view["execution"]

def _chart_suggest_handler(ctx, args):
    # Reuse engine.agent_core.chart_builder.suggest_plotly_chart
    # Consumes ctx.state_view["execution"]

def _answer_synthesize_handler(ctx, args):
    # Reuse engine.agent_core.answer.synthesize_agent_answer
    # Consumes question, sql, safety, execution, result_profile from state
```

Each handler returns `ToolObservation` with the structured output.

### Phase 2: State Binding

**Modified files:**

| File | Change |
|------|--------|
| `engine/agent_core/databinding.py` | Add three appliers to `TOOL_STATE_APPLIERS`: `result.profile` -> `_apply_result_profile`, `chart.suggest` -> `_apply_chart_suggest`, `answer.synthesize` -> `_apply_answer_synthesize`. Add `"result.profile"`, `"chart.suggest"`, `"answer.synthesize"` to `_ARTIFACT_TOOLS`. |

**Applier implementations:**

```python
def _apply_result_profile(state, output, obs):
    return {"result_profile": output}

def _apply_chart_suggest(state, output, obs):
    return {"chart_suggestion": output}

def _apply_answer_synthesize(state, output, obs):
    return {"answer": output, "final_answer": output}
```

### Phase 3: Safe Tool Groups

**Modified files:**

| File | Change |
|------|--------|
| `engine/agent/app/service.py` | Add `"result"`, `"chart"`, `"answer"` to `FULL_SAFE_TOOL_GROUPS` (line 48-50). |

Result: `FULL_SAFE_TOOL_GROUPS = ["environment", "schema", "db", "semantic", "memory", "result", "chart", "answer"]`

### Phase 4: Artifact Emission

**Modified files:**

| File | Change |
|------|--------|
| `engine/agent/nodes/observe_node.py` | Extend `emit_artifacts_from_observation` to emit `build_profile_artifact` when `step_name == "result.profile"` and `state["result_profile"]` exists. Emit `build_chart_artifact` when `step_name == "chart.suggest"` and chart type is not `"table"`. Emit `build_recommendations_artifact` when `step_name == "answer.synthesize"` and answer has recommendations. |

### Phase 5: Deterministic Guard

**Modified files:**

| File | Change |
|------|--------|
| `engine/agent/progress/fast_path.py` | In `deterministic_progress_fastpath`, after the existing `answer`/`final_answer` check (line 173-183), add a guard: if the last successful tool was `db.query` and `result_profile` is not set and the question looks analytical, return `continue` instead of allowing finalization. This is a heuristic check based on presence of `execution` without `result_profile`. |

The guard logic:

```python
execution = state.get("execution")
if (execution and execution.get("success")
    and not state.get("result_profile")
    and not state.get("answer")):
    # db.query succeeded but no analysis step ran yet — continue
    return {
        "progress_decision": progress_decision_dict(
            status="continue",
            reason_summary="Query succeeded but result profiling not yet performed.",
            next_action_hint="Call result.profile to analyze the query result before answering.",
        ),
        "trace_events": [...],
    }
```

This is conservative: it only fires when execution succeeded, no profile exists, and no answer is set yet. It does not generate SQL or make analytical judgments.

### Phase 6: System Prompt Update

**Modified files:**

| File | Change |
|------|--------|
| `engine/agent/model/system_prompt.py` | Replace the "When you have query results — STOP and answer" section (line 70-72) with the new analysis-aware guidance. |

New prompt section:

```
## After query results

A successful db.query completes the data acquisition phase. The next step depends on the question:

**Analytical questions** (trends, comparisons, rankings, anomalies, explanations, recommendations):
1. Call result.profile to understand the result shape and notable facts.
2. Call chart.suggest if the result would benefit from visualization.
3. Call answer.synthesize to produce a structured analysis with findings, evidence, caveats, and follow-up questions.

**Simple detail lookups** (specific rows, exact values, counts with clear filters):
Provide a concise interpreted answer directly. Include result count, visible constraints, and caveats when appropriate. You may skip result.profile and chart.suggest.

Do NOT call additional database tools unless the result is wrong, incomplete, empty due to likely over-filtering, or the user asks for follow-up investigation.
```

### Phase 7: Tests

**New test files:**

| File | Coverage |
|------|----------|
| `engine/tests/test_analysis_flow.py` | Integration tests for the full analysis flow |

**Modified test files:**

| File | Coverage |
|------|----------|
| `engine/agent/tests/test_react_graph.py` | Verify progress fast-path guards the analysis flow |

**Test cases:**

1. `test_safe_groups_include_analysis_tools` — `FULL_SAFE_TOOL_GROUPS` contains `"result"`, `"chart"`, `"answer"`.
2. `test_escalate_accepts_analysis_groups` — `_escalate_tool_group` accepts `"result"`, `"chart"`, `"answer"` as valid groups.
3. `test_builtin_registry_loads_analysis_tools` — `ToolRegistry` loads `result.profile`, `chart.suggest`, `answer.synthesize` from builtin YAML specs.
4. `test_databinding_stores_result_profile` — `apply_tool_result_to_state` with `result.profile` sets `result_profile`.
5. `test_databinding_stores_chart_suggestion` — `apply_tool_result_to_state` with `chart.suggest` sets `chart_suggestion`.
6. `test_databinding_stores_answer` — `apply_tool_result_to_state` with `answer.synthesize` sets `answer` and `final_answer`.
7. `test_tool_group_map_includes_analysis_groups` — `tool_to_group("result.profile")` returns `"result"`, etc.
8. `test_progress_guard_continues_after_db_query_without_profile` — When execution succeeds but `result_profile` is absent and no answer exists, progress fast-path returns `continue`.
9. `test_progress_guard_allows_finalize_with_answer` — When `answer` exists, progress fast-path returns `complete` regardless of profile state.

## Out of Scope

- Building a full causal analysis engine.
- Automatically issuing extra SQL for root-cause investigation after every anomaly.
- Changing database safety or approval policy.
- Redesigning the frontend artifact UI.
- Adding new chart rendering components beyond existing chart artifact support.

## Self Review

- No placeholders remain.
- The design chooses one behavior mode: smart triggered analysis.
- Runtime, prompt, tool registration, state binding, and tests are all covered.
- The scope is limited to making the existing analysis flow reachable and enforceable.
