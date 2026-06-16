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
