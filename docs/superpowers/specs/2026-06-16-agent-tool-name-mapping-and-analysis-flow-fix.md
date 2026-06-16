# Agent Tool Name Mapping & Analysis Flow Fix

## Date

2026-06-16

## Status

Design — approved, pending implementation

## Problem Summary

**Root Cause:** `_tool_name_from_step()` in `observe_node.py` is a no-op (`return step_name`), so step names like `query_database` are never mapped back to internal tool names like `db.query`. This causes `TOOL_STATE_APPLIERS` in `databinding.py` to miss every tool that uses the `base_tool` execution path, and `state["execution"]` is never written.

**Consequence chain:**
1. `db.query` executes successfully
2. `ToolObservation.name` = `query_database` (step name, set by `_step_name()`)
3. `_tool_name_from_step("query_database")` returns `query_database` (no-op)
4. `TOOL_STATE_APPLIERS.get("query_database")` → miss (key is `db.query`)
5. `state["execution"]` never set
6. `result.profile` fails: "No successful execution result available to profile"
7. `answer.synthesize` produces degraded output without execution data
8. `progress guard` cannot detect "query done, need analysis" state
9. Model re-cycles, trying to work around broken tools

**Secondary issue:** The current design splits "look at data → understand → answer" across three tools (`db.query` → `result.profile` → `answer.synthesize`), requiring 3+ ReAct rounds. `answer.synthesize` uses template-based string assembly instead of letting the model generate natural language answers, producing stiff, mechanical responses.

## Design

### Part 1: Fix Tool Name Reverse Mapping

**File:** `engine/agent/nodes/observe_node.py`

Change `_tool_name_from_step()` from a no-op to a real reverse lookup, reusing the same mapping table that `_step_name()` in `tool_node.py` already defines.

```python
# Current (no-op)
def _tool_name_from_step(step_name: str) -> str:
    return step_name

# Fixed — reverse of _step_name() in tool_node.py
_STEP_TO_INTERNAL: dict[str, str] = {
    "list_tables": "schema.list_tables",
    "describe_table": "schema.describe_table",
    "refresh_catalog": "schema.refresh_catalog",
    "observe_database": "db.observe",
    "search_database": "db.search",
    "inspect_database": "db.inspect",
    "preview_table": "db.preview",
    "query_database": "db.query",
    "remember_database_semantics": "db.remember",
    "memory_search": "memory.search",
    "memory_write": "memory.write",
    "memory_delete": "memory.delete",
    "summarize_session": "memory.summarize_session",
    "profile_result": "result.profile",
    "suggest_chart": "chart.suggest",
    "synthesize_answer": "answer.synthesize",
}

def _tool_name_from_step(step_name: str) -> str:
    return _STEP_TO_INTERNAL.get(step_name, step_name)
```

**Rationale:** The forward mapping (`_step_name`) and reverse mapping (`_tool_name_from_step`) should be derived from a single source of truth.

**Implementation TODO:** In this implementation, extract the mapping table from `_step_name()` in `tool_node.py` into a shared constant (e.g., `STEP_NAME_MAP` in `engine/agent/tools/tool_aliases.py` or a new shared module). Both `_step_name()` and `_tool_name_from_step()` MUST reference the same dict so that adding a new tool requires only one change. This prevents future drift where a developer adds a step name in `tool_node.py` but forgets the reverse mapping in `observe_node.py`.

### Part 2: Merge result.profile + answer.synthesize → analyze_data

#### 2a. Remove answer.synthesize

Delete or deprecate:
- `engine/tools/builtin/answer_synthesize.yaml`
- `_answer_synthesize_handler` in `engine/tools/databox_tools.py`
- `_apply_answer_synthesize` in `engine/agent_core/databinding.py`
- `"answer.synthesize"` entry in `TOOL_STATE_APPLIERS`
- `"answer_synthesize"` alias in `engine/agent/tools/tool_aliases.py`
- `"answer.synthesize"` affordance in `engine/agent/tools/tool_manifest.py`
- Cleanup related code in `emit_artifacts_from_observation` (observe_node.py)

#### 2b. Replace result.profile with analyze_data

**New YAML spec:** `engine/tools/builtin/analyze_data.yaml`

```yaml
name: analyze_data
group: analysis
kind: code
description: >
  Compute a statistical profile of query execution results. Returns row count,
  column-level statistics (type, null ratio, min/max/avg, top values), detected
  patterns (time_series, category_breakdown, top_k, single_metric), notable
  facts, and anomalies. Use this when query results are too large or complex
  to analyze by inspection. Skip for simple lookups or single-value results.
  Can be called with no arguments — it will auto-detect execution results from
  the current session state.
handler: analyze_data_handler
input_schema:
  type: object
  description: Profile execution results. All parameters are optional.
  properties:
    execution_result:
      type: object
      description: >
        Optional. The execution output from db.query (rows, columns, status).
        If omitted, the tool auto-reads the latest execution result from state.
    question:
      type: string
      description: Original user question for context.
  required: []
binding:
  consumes_state_keys: [execution]
  produces_state_keys: [data_profile]
policy:
  side_effect: none
  risk_level: safe
state_contract:
  merge_strategy: new
  emit_artifact: true
```

**Key design decisions:**
- `execution_result` is optional in args — if not provided, handler falls back to `ctx.state_view.get("execution")`. Since Part 1 fixes state writes, state IS reliable. This means the model can call `analyze_data()` with no arguments and it just works.
- Output is `DataProfile` (pure statistics, no answer text)
- `consumes_state_keys: [execution]` — reflects the implicit fallback path

#### 2c. New handler

```python
def _analyze_data_handler(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Compute statistical profile from execution results.

    Dual-path data access:
    1. Explicit: model passes execution_result in args (clean, self-contained)
    2. Implicit: falls back to ctx.state_view.get("execution") (zero-arg convenience)
    """
    execution = args.get("execution_result") or ctx.state_view.get("execution")
    if not execution or not execution.get("success"):
        return ToolObservation(
            name="analyze_data",
            status="failed",
            input=args,
            error="No successful execution result available. Run db.query first.",
            latency_ms=0,
        )
    # ... pure Python computation: profile_result() ...
    return ToolObservation(
        name="analyze_data",
        status="success",
        input=args,
        output=data_profile.model_dump(mode="json"),
        latency_ms=latency,
    )
```

#### 2d. State applier

```python
def _apply_analyze_data(_state, output, _obs):
    return {"data_profile": output}
```

### Part 3: Simplified Execution Flow

**Before (3+ ReAct rounds):**
```
model → db.query → observe → progress → model → result.profile → observe → progress → model → answer.synthesize → observe → progress → finalize
```

**After (1-2 ReAct rounds):**
```
Scenario A (simple query):
  model → db.query → observe → model sees result in ToolMessage → directly outputs AIMessage answer → progress → finalize

Scenario B (complex analysis):
  model → db.query → observe → model sees large result → analyze_data(execution_result=...) → observe → model writes analysis → progress → finalize
```

### Part 4: Finalize Behavior & AgentAnswer Compatibility

**The problem:** Previously, `answer.synthesize` produced structured `AgentAnswer` fields (`key_findings`, `caveats`, `recommendations`, `follow_up_questions`) via template code. Now the model outputs free-text `AIMessage.content`. If the frontend strongly depends on these structured fields, we need a strategy to bridge the gap.

**Primary strategy (preferred):** `finalize_node` puts the model's natural language text into `AgentAnswer.answer`. Other structured fields default to empty unless evidence is available from state:

```
AgentAnswer(
    answer = <model's AIMessage.content>,   # natural language, model-authored
    key_findings = [],                       # empty unless model output parseable
    evidence = <auto-built from execution + data_profile>,  # code-computed
    caveats = [],                            # empty unless model output parseable
    recommendations = [],                    # empty unless model output parseable
    follow_up_questions = [],                # empty unless model output parseable
)
```

**Fallback strategy (if frontend demands structured fields):** The model is instructed (via system prompt) to end its final response with optional light markup sections that `finalize_node` can regex-extract:

```
[Final Answer text here...]

### Key Findings
- Finding 1
- Finding 2

### Caveats
- Caveat 1

### Recommendations
- Rec 1
```

`finalize_node` attempts to parse these sections; any unparseable content stays in `answer` as-is.

**Decision:** Start with the primary strategy. Only add regex parsing if frontend feedback demands structured fields.

**State evidence (always populated):**
- `evidence` is built from `state["execution"]` (row count, SQL) and `state["data_profile"]` (statistics) — code-computed, always correct.
- Remove `[answer.synthesize]` prefix cleanup (no longer needed).

## Scope

### In scope
1. Fix `_tool_name_from_step` reverse mapping
2. Merge `result.profile` + `answer.synthesize` → `analyze_data`
3. `analyze_data` accepts data via args, not state
4. Model generates answers directly (natural language)
5. Cleanup: remove answer.synthesize artifacts
6. Update `finalize_node` to match simplified flow
7. Update `tool_aliases.py`, `tool_manifest.py`, `observe_node.py` (`emit_artifacts_from_observation`)

### Out of scope
- LangSmith trace event improvements (separate issue)
- Model prompt changes for tool-calling content (already addressed)
- ReAct loop optimization beyond tool count reduction

## Files to Modify

| File | Change |
|------|--------|
| `engine/agent/nodes/observe_node.py` | `_tool_name_from_step` reverse mapping; update `emit_artifacts_from_observation` |
| `engine/tools/databox_tools.py` | Replace `_result_profile_handler` + `_answer_synthesize_handler` with `_analyze_data_handler` |
| `engine/tools/builtin/analyze_data.yaml` | New YAML spec |
| `engine/tools/builtin/result_profile.yaml` | Delete or repurpose |
| `engine/tools/builtin/answer_synthesize.yaml` | Delete |
| `engine/agent_core/databinding.py` | Replace `_apply_result_profile` + `_apply_answer_synthesize` with `_apply_analyze_data`; update `TOOL_STATE_APPLIERS` |
| `engine/agent/tools/tool_aliases.py` | Add `analyze_data` alias, remove `answer_synthesize` |
| `engine/agent/tools/tool_manifest.py` | Replace affordances |
| `engine/agent/nodes/finalize_node.py` | Simplify answer extraction |
| `engine/agent/progress/fast_path.py` | **Relax** the hard guard that forces "must profile after query". Since `analyze_data` is now optional (simple queries skip it), the guard must NOT block finalize when `execution` exists but `data_profile` doesn't. Change from "query succeeded + no profile → continue with hint" to "query succeeded + no profile → allow model to decide (proceed to finalize if model outputs text without tool_calls)". Only intervene when the model appears stuck (e.g., calls db.query repeatedly without ever producing text or calling analyze_data). |

## Risks

- **Breaking change:** `answer.synthesize` and `result.profile` are removed from the tool set. Any saved prompts, eval cases, or LangSmith traces referencing them will break.
- **AgentAnswer compatibility:** Frontend expects `AgentAnswer` structure; `finalize_node` must still produce it from model output + state evidence. Primary strategy: model's natural language goes into `answer` field; `evidence` auto-built from state; remaining structured fields default to empty. Fallback: light markdown parsing if frontend demands structured `key_findings`/`caveats`/`recommendations`. See Part 4 for details.
- **State key changes:** `result_profile` state key replaced by `data_profile`; any downstream consumers (eval, persistence) need updating.
- **Model hallucination in structured fields:** The model may produce incorrect claims in free-text answers. Mitigation: `evidence` field is always code-computed from execution/profile (never model-generated). Model-authored text lives in `answer` only.
- **fast_path guard relaxation:** Removing the hard "must profile after query" guard means the model could finalize without profiling even for complex queries. Mitigation: the model's own judgment should drive this — if results are too large to inspect visually, it will call `analyze_data`. The guard should only intervene if the model loops without producing text.
