# Agent Tool Name Mapping & Analysis Flow Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `_tool_name_from_step` no-op that breaks state writes, and merge `result.profile` + `answer.synthesize` into a single `analyze_data` tool that lets the model generate natural-language answers directly.

**Architecture:** Extract a shared `STEP_NAME_MAP` so forward (`_step_name`) and reverse (`_tool_name_from_step`) mappings never drift. Replace two tools with one `analyze_data` that accepts `execution_result` as optional input with state fallback. Remove `answer.synthesize` entirely. Let the model produce answers as natural-language `AIMessage.content`; `finalize_node` wraps it into `AgentAnswer` with code-computed `evidence`.

**Tech Stack:** Python 3.12+, LangGraph, Pydantic v2

---

### Task 1: Extract shared STEP_NAME_MAP into tool_aliases.py

**Files:**
- Modify: `engine/agent/tools/tool_aliases.py`
- Modify: `engine/agent/nodes/tool_node.py:22-41`

- [ ] **Step 1: Add STEP_NAME_MAP constant to tool_aliases.py**

Add after the existing `ALIAS_TO_INTERNAL` block in `engine/agent/tools/tool_aliases.py`:

```python
# Step-name ↔ internal-name bidirectional map.
# _step_name() in tool_node.py and _tool_name_from_step() in observe_node.py
# MUST both derive from this single source of truth.
STEP_NAME_MAP: dict[str, str] = {
    "schema.list_tables": "list_tables",
    "schema.describe_table": "describe_table",
    "schema.refresh_catalog": "refresh_catalog",
    "db.observe": "observe_database",
    "db.search": "search_database",
    "db.inspect": "inspect_database",
    "db.preview": "preview_table",
    "db.query": "query_database",
    "db.remember": "remember_database_semantics",
    "memory.search": "memory_search",
    "memory.write": "memory_write",
    "memory.delete": "memory_delete",
    "memory.summarize_session": "summarize_session",
    "result.profile": "profile_result",
    "chart.suggest": "suggest_chart",
    "answer.synthesize": "synthesize_answer",
    # New tool — step name equals internal name (identity mapping, but must
    # be present so _step_name() and _tool_name_from_step() handle it).
    "analyze_data": "analyze_data",
}

# Reverse lookup: step name → internal name.
# IMPORTANT: computed once at import time. If STEP_NAME_MAP is mutated after
# import, call _rebuild_step_name_reverse() to update this dict.
STEP_NAME_TO_INTERNAL: dict[str, str] = {}

def _rebuild_step_name_reverse() -> None:
    """Rebuild STEP_NAME_TO_INTERNAL from STEP_NAME_MAP."""
    STEP_NAME_TO_INTERNAL.clear()
    STEP_NAME_TO_INTERNAL.update({v: k for k, v in STEP_NAME_MAP.items()})

_rebuild_step_name_reverse()
```

- [ ] **Step 2: Rewrite _step_name() in tool_node.py to use STEP_NAME_MAP**

Replace the existing `_step_name()` function body in `engine/agent/nodes/tool_node.py` (lines 22-41):

```python
from engine.agent.tools.tool_aliases import STEP_NAME_MAP

def _step_name(tool_name: str) -> str:
    return STEP_NAME_MAP.get(tool_name, tool_name)
```

- [ ] **Step 3: Verify import works**

Run: `python -c "from engine.agent.tools.tool_aliases import STEP_NAME_MAP, STEP_NAME_TO_INTERNAL; print(len(STEP_NAME_MAP))"`
Expected: prints `17` (or the count of entries)

- [ ] **Step 4: Commit**

```bash
git add engine/agent/tools/tool_aliases.py engine/agent/nodes/tool_node.py
git commit -m "refactor: extract shared STEP_NAME_MAP into tool_aliases, use in tool_node"
```

---

### Task 2: Fix _tool_name_from_step reverse mapping in observe_node.py

**Files:**
- Modify: `engine/agent/nodes/observe_node.py:29-30`

- [ ] **Step 1: Replace the no-op _tool_name_from_step**

Replace lines 29-30 in `engine/agent/nodes/observe_node.py`:

```python
# Before (no-op)
def _tool_name_from_step(step_name: str) -> str:
    return step_name

# After
from engine.agent.tools.tool_aliases import STEP_NAME_TO_INTERNAL

def _tool_name_from_step(step_name: str) -> str:
    return STEP_NAME_TO_INTERNAL.get(step_name, step_name)
```

- [ ] **Step 2: Verify the mapping works**

Run: `python -c "from engine.agent.nodes.observe_node import _tool_name_from_step; print(_tool_name_from_step('query_database'))"`
Expected: `db.query`

Run: `python -c "from engine.agent.nodes.observe_node import _tool_name_from_step; print(_tool_name_from_step('profile_result'))"`
Expected: `result.profile`

- [ ] **Step 3: Commit**

```bash
git add engine/agent/nodes/observe_node.py
git commit -m "fix: map step names back to internal tool names in observe_node"
```

---

### Task 3: Create analyze_data YAML tool spec

**Files:**
- Create: `engine/tools/builtin/analyze_data.yaml`

- [ ] **Step 1: Write the YAML spec**

Create `engine/tools/builtin/analyze_data.yaml`:

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
metadata:
  next_route: model
state_contract:
  merge_strategy: new
  emit_artifact: true
```

- [ ] **Step 2: Verify YAML is valid**

Run: `python -c "import yaml; yaml.safe_load(open('engine/tools/builtin/analyze_data.yaml')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add engine/tools/builtin/analyze_data.yaml
git commit -m "feat: add analyze_data YAML tool spec"
```

---

### Task 4: Create analyze_data handler in databox_tools.py

**Files:**
- Modify: `engine/tools/databox_tools.py`

- [ ] **Step 1: Add import for STEP_NAME_MAP at top**

Add after existing imports in `engine/tools/databox_tools.py`:

```python
from engine.agent.tools.tool_aliases import STEP_NAME_MAP
```

- [ ] **Step 2: Register and write the handler (no STEP_NAME_MAP change needed)**

In `engine/tools/databox_tools.py`, in `register_databox_tools()`, replace the existing `result_profile_handler` and `answer_synthesize_handler` registration lines (lines 69-71) with:

```python
    # -- Analysis tools ---------------------------------------------------
    handlers.force_register("analyze_data_handler", _analyze_data_handler)
    handlers.force_register("chart_suggest_handler", _chart_suggest_handler)
```

Then replace the `_result_profile_handler` and `_answer_synthesize_handler` functions (lines 141-270) with:

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
    import time
    start = time.monotonic()
    try:
        question = args.get("question") or (ctx.request.question if ctx.request else "") or ""
        columns = list(execution.get("columns") or [])
        rows = list(execution.get("rows") or [])
        from engine.agent_core.result_profiler import profile_result
        data_profile = profile_result(
            question=question,
            columns=columns,
            rows=rows,
            execution_success=True,
        )
        latency = int((time.monotonic() - start) * 1000)
        return ToolObservation(
            name="analyze_data",
            status="success",
            input=args,
            output=data_profile.model_dump(mode="json"),
            latency_ms=latency,
        )
    except Exception as exc:
        latency = int((time.monotonic() - start) * 1000)
        return ToolObservation(
            name="analyze_data",
            status="failed",
            input=args,
            error=str(exc),
            latency_ms=latency,
        )
```

- [ ] **Step 4: Add _step_name entry for analyze_data in tool_node.py**

In `STEP_NAME_MAP` in `engine/agent/tools/tool_aliases.py` (already done in step 2), verify the entry is present. The `tool_node.py` import already uses `STEP_NAME_MAP` so no additional change needed.

- [ ] **Step 5: Verify handler import works**

Run: `python -c "from engine.tools.databox_tools import _analyze_data_handler; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add engine/tools/databox_tools.py engine/agent/tools/tool_aliases.py
git commit -m "feat: add analyze_data handler replacing result.profile and answer.synthesize"
```

---

### Task 5: Add analyze_data state applier and update databinding.py

**Files:**
- Modify: `engine/agent_core/databinding.py`

- [ ] **Step 1: Replace _apply_result_profile and _apply_answer_synthesize with _apply_analyze_data**

In `engine/agent_core/databinding.py`, remove functions `_apply_result_profile` (lines 90-91) and `_apply_answer_synthesize` (lines 98-99). Add:

```python
def _apply_analyze_data(_state: dict[str, Any], output: dict[str, Any], _obs: ToolObservation) -> dict[str, Any]:
    return {"data_profile": output}
```

- [ ] **Step 2: Update TOOL_STATE_APPLIERS**

Replace the entries for `"result.profile"` and `"answer.synthesize"` in `TOOL_STATE_APPLIERS` (lines 139, 141) with:

```python
    "analyze_data": _apply_analyze_data,
```

And remove the `"answer.synthesize"` entry entirely. Keep `"result.profile"` entry for backward compat until Task 8 removes the old spec. Actually, since `result.profile` will be deleted, remove both entries and add only the new one.

The updated `TOOL_STATE_APPLIERS` (lines 126-142) should read:

```python
TOOL_STATE_APPLIERS: dict[str, _ToolApplyFn] = {
    "environment.get_profile": _apply_environment_get_profile,
    "semantic.resolve": _apply_semantic_resolve,
    "schema.list_tables": _apply_schema_list_tables,
    "schema.describe_table": _apply_schema_describe_table,
    "schema.refresh_catalog": _apply_schema_refresh_catalog,
    "memory.search": _apply_memory_search,
    "memory.write": _apply_memory_write,
    "db.observe": _apply_db_observe,
    "db.search": _apply_db_search,
    "db.inspect": _apply_db_inspect,
    "db.preview": _apply_db_preview,
    "db.query": _apply_db_query,
    "analyze_data": _apply_analyze_data,
    "chart.suggest": _apply_chart_suggest,
}
```

- [ ] **Step 3: Update _ARTIFACT_TOOLS**

Replace lines 144-150:

```python
_ARTIFACT_TOOLS: frozenset[str] = frozenset({
    "db.preview",
    "db.query",
    "analyze_data",
    "chart.suggest",
})
```

- [ ] **Step 4: Commit**

```bash
git add engine/agent_core/databinding.py
git commit -m "feat: add analyze_data state applier, remove answer.synthesize from databinding"
```

---

### Task 6: Delete answer.synthesize artifacts

**Files:**
- Delete: `engine/tools/builtin/answer_synthesize.yaml`
- Modify: `engine/agent/tools/tool_aliases.py`
- Modify: `engine/agent/tools/tool_manifest.py`

- [ ] **Step 1: Delete the YAML spec**

```bash
git rm engine/tools/builtin/answer_synthesize.yaml
```

- [ ] **Step 2: Remove answer_synthesize from tool_aliases.py**

In `engine/agent/tools/tool_aliases.py`:

1. Remove the alias line:
```python
    "answer_synthesize": "answer.synthesize",
```

2. Remove from `STEP_NAME_MAP`:
```python
    "answer.synthesize": "synthesize_answer",
```

3. After removing, rebuild the reverse mapping:

```python
_rebuild_step_name_reverse()
```

(Add this call after the removal — `_rebuild_step_name_reverse` was defined in Task 1.)

- [ ] **Step 3: Remove answer.synthesize affordance from tool_manifest.py**

In `engine/agent/tools/tool_manifest.py`, remove lines 93-100 (the `"answer.synthesize"` entry in `TOOL_AFFORDANCE`).

- [ ] **Step 4: Commit**

```bash
git add -u engine/tools/builtin/answer_synthesize.yaml engine/agent/tools/tool_aliases.py engine/agent/tools/tool_manifest.py
git commit -m "feat: remove answer.synthesize tool — model now generates answers directly"
```

---

### Task 7: Delete result.profile artifacts and add analyze_data affordance

**Files:**
- Delete: `engine/tools/builtin/result_profile.yaml`
- Modify: `engine/agent/tools/tool_aliases.py`
- Modify: `engine/agent/tools/tool_manifest.py`

- [ ] **Step 1: Delete the old result.profile YAML spec**

```bash
git rm engine/tools/builtin/result_profile.yaml
```

- [ ] **Step 2: Update STEP_NAME_MAP in tool_aliases.py**

In `engine/agent/tools/tool_aliases.py`:

1. Replace the `"result_profile"` alias:
```python
# Before
    "result_profile": "result.profile",
# After
    "analyze_data": "analyze_data",
```

2. In `STEP_NAME_MAP`, remove the old `"result.profile": "profile_result"` entry (the `"analyze_data": "analyze_data"` entry was already added in Task 1).

3. After changes, rebuild the reverse mapping:
```python
_rebuild_step_name_reverse()
```

- [ ] **Step 3: Update affordance in tool_manifest.py**

In `engine/agent/tools/tool_manifest.py`, replace the `"result.profile"` entry (lines 80-86) with:

```python
    "analyze_data": (
        "Compute a statistical profile of query execution results. Produces row count, "
        "column-level statistics (type, null ratio, min/max/avg, top values), detected "
        "patterns (time_series, category_breakdown, top_k, single_metric), notable "
        "facts, and anomalies. Call after db.query when results are too large or complex "
        "to analyze by inspection. Can be called with no arguments — auto-reads execution "
        "from state. Skip for simple lookups or single-value results."
    ),
```

- [ ] **Step 4: Commit**

```bash
git add -u engine/tools/builtin/result_profile.yaml engine/agent/tools/tool_aliases.py engine/agent/tools/tool_manifest.py
git commit -m "feat: replace result.profile with analyze_data affordance and alias"
```

---

### Task 8: Update state.py — rename result_profile to data_profile

**Files:**
- Modify: `engine/agent/graph/state.py`

- [ ] **Step 1: Rename the state key**

In `engine/agent/graph/state.py`, line 99, replace:

```python
# Before
    result_profile: dict[str, Any] | None
# After
    data_profile: dict[str, Any] | None
```

- [ ] **Step 2: Verify the TypedDict still loads**

Run: `python -c "from engine.agent.graph.state import DataBoxAgentState; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add engine/agent/graph/state.py
git commit -m "refactor: rename result_profile → data_profile in agent state"
```

---

### Task 9: Update context_builder.py and context_pack.py for data_profile

**Files:**
- Modify: `engine/agent/model/context_builder.py`
- Modify: `engine/agent/context_pack.py`

- [ ] **Step 1: Update context_builder.py**

In `engine/agent/model/context_builder.py`, lines 157-159, replace `result_profile` with `data_profile`:

```python
# Before
    profile = state.get("result_profile")
    if profile:
        parts.append(f"- **Result Profile**:\n```json\n{profile}\n```")

# After
    profile = state.get("data_profile")
    if profile:
        parts.append(f"- **Data Profile**:\n```json\n{profile}\n```")
```

- [ ] **Step 2: Update context_pack.py**

Search `engine/agent/context_pack.py` for `result_profile` and replace with `data_profile`:

```bash
# Run this to find occurrences:
grep -n "result_profile" engine/agent/context_pack.py
```

Replace each occurrence of `result_profile` with `data_profile` in that file. Also update any field name references (e.g., in ContextPack model if it has a `result_profile` field).

- [ ] **Step 3: Commit**

```bash
git add engine/agent/model/context_builder.py engine/agent/context_pack.py
git commit -m "refactor: update context builder and pack for data_profile rename"
```

---

### Task 10: Update observe_node.py emit_artifacts and other consumers

**Files:**
- Modify: `engine/agent/nodes/observe_node.py`
- Modify: `engine/agent_core/artifacts.py`

- [ ] **Step 1: Update emit_artifacts_from_observation in observe_node.py**

In `engine/agent/nodes/observe_node.py`, line 93, replace the `"result.profile"` artifact emission block:

```python
# Before (lines 93-111)
    if step_name == "result.profile" and state.get("result_profile") and observation.status == "success":
        from engine.agent_core.types import ResultProfile as RP
        profile_raw = state.get("result_profile")
        ...

# After
    if step_name == "analyze_data" and state.get("data_profile") and observation.status == "success":
        from engine.agent_core.types import ResultProfile as RP
        profile_raw = state.get("data_profile")
        if isinstance(profile_raw, dict):
            try:
                profile_obj = RP.model_validate(profile_raw)
            except Exception:
                profile_obj = None
        elif isinstance(profile_raw, RP):
            profile_obj = profile_raw
        else:
            profile_obj = None
        if profile_obj is not None:
            artifacts.append(build_profile_artifact(
                profile_obj,
                execution=state.get("execution"),
                safety=state.get("safety"),
                identity=identity,
            ))
```

Also remove the `"answer.synthesize"` artifact emission block (lines 118-131):

```python
# Remove this entire block:
    if step_name == "answer.synthesize" and state.get("answer") and observation.status == "success":
        ...
```

- [ ] **Step 2: Update artifacts.py**

Grep for `result_profile` in `engine/agent_core/artifacts.py` and replace with `data_profile`:

```bash
grep -n "result_profile" engine/agent_core/artifacts.py
```

Replace each occurrence. The `build_profile_artifact` function likely references `result_profile` in its signature or body — update accordingly.

- [ ] **Step 3: Commit**

```bash
git add engine/agent/nodes/observe_node.py engine/agent_core/artifacts.py
git commit -m "refactor: update observe_node emit_artifacts and artifacts for data_profile"
```

---

### Task 11: Relax fast_path.py progress guard

**Files:**
- Modify: `engine/agent/progress/fast_path.py`

- [ ] **Step 1: Relax the analysis guard in deterministic_progress_fastpath**

In `engine/agent/progress/fast_path.py`, lines 183-195, replace the hard guard:

```python
# Before (lines 183-195)
    # ---- Analysis guard: db.query succeeded but no analysis step yet --------
    execution = state.get("execution")
    if (isinstance(execution, dict) and execution.get("success")
            and not state.get("result_profile") and not state.get("answer")):
        decision = progress_decision_dict(
            status="continue",
            reason_summary="Query succeeded but result profiling not yet performed.",
            next_action_hint="Call result.profile to analyze the query result before answering.",
        )
        return {
            "progress_decision": decision,
            "trace_events": [progress_trace(decision, fastpath=True)],
        }

# After — allow model to decide, only intervene if model appears stuck
    # ---- Analysis hint: db.query succeeded but no analysis step yet --------
    # Since analyze_data is optional (simple queries skip it), we no longer
    # force a "continue" here. The model can choose to answer directly.
    # We only emit a gentle hint in the progress_decision (which becomes
    # guidance for the model via build_progress_guidance_message).
    execution = state.get("execution")
    if (isinstance(execution, dict) and execution.get("success")
            and not state.get("data_profile") and not state.get("answer")
            and not state.get("final_answer")):
        # Only intervene if model has been cycling (called db.query multiple times
        # without producing text or calling analyze_data)
        last_tool_results = state.get("last_tool_results") or []
        query_call_count = sum(
            1 for r in last_tool_results
            if isinstance(r, dict) and r.get("name") == "query_database"
        )
        if query_call_count >= 2 and step_count > 4:
            decision = progress_decision_dict(
                status="continue",
                reason_summary="Multiple db.query calls without analysis or answer — consider calling analyze_data or answering the user.",
                next_action_hint="You have query results. Consider calling analyze_data for complex data, or answer the user directly if the results are simple.",
            )
            return {
                "progress_decision": decision,
                "trace_events": [progress_trace(decision, fastpath=True)],
            }
```

- [ ] **Step 2: Update rule_fallback similarly**

In the same file, `rule_fallback()` function lines 348-353, update `result_profile` → `data_profile`:

```python
# Before
    elif (isinstance(execution, dict) and execution.get("success")
            and not state.get("result_profile") and not state.get("answer")):
        decision = ProgressDecision(
            status="continue",
            reason_summary="Query succeeded but result profiling not yet performed.",
            next_action_hint="Call result.profile to analyze the query result before answering.",
        )

# After
    elif (isinstance(execution, dict) and execution.get("success")
            and not state.get("data_profile") and not state.get("answer")):
        decision = ProgressDecision(
            status="continue",
            reason_summary="Query succeeded. You may call analyze_data for complex results, or answer directly.",
            next_action_hint="Consider calling analyze_data for complex data, or answer the user directly if the results are simple.",
        )
```

- [ ] **Step 3: Commit**

```bash
git add engine/agent/progress/fast_path.py
git commit -m "refactor: relax fast_path analysis guard — analyze_data is optional"
```

---

### Task 12: Simplify finalize_node.py

**Files:**
- Modify: `engine/agent/nodes/finalize_node.py`

- [ ] **Step 1: Update finalize_answer to use data_profile and remove answer.synthesize cleanup**

In `engine/agent/nodes/finalize_node.py`, update the `finalize_answer` function:

1. Replace `result_profile` → `data_profile` in evidence building (if referenced)
2. Remove the `[answer.synthesize]` prefix cleanup block (lines 71-76):

```python
# Remove this block entirely:
    # Clean up any raw tool node prefix from answer if present
    if isinstance(answer_payload.get("answer"), str):
        ans_str = answer_payload["answer"]
        if ans_str.startswith("[") and "]" in ans_str:
            parts = ans_str.split("]", 1)
            if len(parts) > 1:
                answer_payload["answer"] = parts[1].strip()
```

3. Update the `existing_answer` merge logic (lines 43-52). Since `answer.synthesize` no longer writes `state["answer"]`, simplify:

```python
    # Build answer payload for AgentRunResponse compatibility
    # Model's natural language answer becomes the primary answer text.
    # Structured fields are empty unless evidence is available from state.
    answer_payload: dict[str, Any] = {
        "answer": answer_text,
        "key_findings": [],
        "evidence": _build_evidence_from_state(state),
        "caveats": [],
        "recommendations": [],
        "follow_up_questions": [],
    }
```

4. Add `_build_evidence_from_state` helper function at module level:

```python
def _build_evidence_from_state(state: DataBoxAgentState) -> list[dict[str, Any]]:
    """Build evidence list from code-computed state — never from model output."""
    evidence: list[dict[str, Any]] = []
    execution = state.get("execution")
    if isinstance(execution, dict) and execution.get("success"):
        evidence.append({
            "artifact_id": "query_result",
            "label": "Rows returned",
            "value": execution.get("rowCount", 0),
        })
    data_profile = state.get("data_profile")
    if isinstance(data_profile, dict):
        evidence.append({
            "artifact_id": "data_profile",
            "label": "Data profile",
            "value": f"{data_profile.get('row_count', 0)} rows profiled",
        })
    sql = state.get("sql")
    if sql:
        evidence.append({
            "artifact_id": "sql_candidate",
            "label": "SQL",
            "value": "validated candidate",
        })
    safety = state.get("safety")
    if isinstance(safety, dict) and safety.get("can_execute"):
        evidence.append({
            "artifact_id": "safety_report",
            "label": "Safety",
            "value": "passed",
        })
    return evidence
```

- [ ] **Step 2: Commit**

```bash
git add engine/agent/nodes/finalize_node.py
git commit -m "refactor: simplify finalize_node — model text as answer, evidence from state"
```

---

### Task 13: Update remaining consumers of result_profile

**Files:**
- Modify: `engine/agent_core/analysis_composer.py`
- Modify: `engine/agent_core/recommendations.py`
- Modify: `engine/agent/repair/sql_repair.py`
- Modify: `engine/agent/progress/llm_judge.py`
- Modify: `engine/agent/app/response_builder.py`
- Modify: `engine/agent/app/service.py`

- [ ] **Step 1: Replace result_profile → data_profile in all remaining files**

Run the search to find all occurrences:

```bash
grep -rn "result_profile" engine/ --include="*.py" | grep -v __pycache__ | grep -v ".pyc" | grep -v test_
```

For each file that has `result_profile`:
- If it reads from state: change `state.get("result_profile")` to `state.get("data_profile")`
- If it writes to state: this should have been handled by Task 5 (databinding)
- If it checks for existence: change `"result_profile"` to `"data_profile"`

Specifically:

**engine/agent_core/analysis_composer.py**: Replace `result_profile` → `data_profile` in all occurrences.
**engine/agent_core/recommendations.py**: Replace `result_profile` → `data_profile`.
**engine/agent/repair/sql_repair.py**: Replace `result_profile` → `data_profile`.
**engine/agent/progress/llm_judge.py**: Replace `result_profile` → `data_profile`.
**engine/agent/app/response_builder.py**: Replace `result_profile` → `data_profile`.
**engine/agent/app/service.py**: Replace `result_profile` → `data_profile`.
**engine/agent_core/answer.py**: Replace `result_profile` → `data_profile`.
**engine/agent/nodes/tool_node.py**: Replace `result_profile` → `data_profile` in `_execute_tool` state merge (line 127).
**engine/agent/nodes/model_node.py**: Replace `result_profile` → `data_profile` (line 32 in `_within_post_query_analysis_grace`).

- [ ] **Step 2: Commit**

```bash
git add engine/agent_core/analysis_composer.py engine/agent_core/recommendations.py engine/agent/repair/sql_repair.py engine/agent/progress/llm_judge.py engine/agent/app/response_builder.py engine/agent/app/service.py engine/agent_core/answer.py engine/agent/nodes/tool_node.py engine/agent/nodes/model_node.py
git commit -m "refactor: update all consumers from result_profile → data_profile"
```

---

### Task 14: Update tests

**Files:**
- Modify: `engine/tests/test_analysis_flow.py`
- Modify: `engine/agent/tests/test_progress_runtime_v2.py`
- Modify: `engine/agent/tests/test_e2e_qwen.py`
- Modify: `engine/tests/test_tool_contract.py`

- [ ] **Step 1: Update test_analysis_flow.py**

Replace all `result.profile` → `analyze_data`, `answer.synthesize` → removed, `result_profile` → `data_profile`, `answer_synthesize` → removed.

Key changes:
- Line 1: Update docstring — remove `answer.synthesize`, add `analyze_data`
- Line 64: Change tool name list to `["analyze_data", "chart.suggest"]`
- Line 77: `assert "analyze_data" in tool_names` (was `result_profile`)
- Line 79: Remove `assert "answer_synthesize" in tool_names`
- Line 84-86: Change test name to `test_tool_to_group_analyze_data` and assert `tool_to_group("analyze_data") == "analysis"`
- Lines 92-94: Remove `test_tool_to_group_answer_synthesize` test
- Lines 102-106: Rename test to `test_analyze_data_applier`, use `tool_name="analyze_data"`, assert `result["data_profile"]`
- Lines 114-118: Remove `test_answer_synthesize_applier` test
- Lines 124-126: Update `_ARTIFACT_TOOLS` assertions — remove `answer.synthesize`, add `analyze_data`
- Lines 156-182: Remove `test_answer_synthesize_uses_request_question_when_arg_missing` (or rewrite for `analyze_data`)
- Lines 202, 219, 235, 276: Update `result_profile` → `data_profile` in test state dicts
- Line 283: Update comment — `data_profile` exists
- Lines 296-298: Update system prompt assertions — `analyze_data` instead of `result.profile`/`answer.synthesize`

- [ ] **Step 2: Update test_progress_runtime_v2.py**

Replace `result_profile` → `data_profile` in all test state dicts and assertions.

- [ ] **Step 3: Update test_e2e_qwen.py**

Replace `result_profile` → `data_profile` in all references.

- [ ] **Step 4: Update test_tool_contract.py**

Replace the `answer.synthesize` contract entry:

```python
# Before (lines 43-44)
    "answer.synthesize": ToolStateContract(
        tool_name="answer.synthesize",
# After
    "analyze_data": ToolStateContract(
        tool_name="analyze_data",
```

Update any `result.profile` contract entries similarly.

- [ ] **Step 5: Run the updated tests**

```bash
python -m pytest engine/tests/test_analysis_flow.py -v
python -m pytest engine/tests/test_tool_contract.py -v
python -m pytest engine/agent/tests/test_progress_runtime_v2.py -v
```

Expected: all tests pass (or fail with clear reasons if further updates needed).

- [ ] **Step 6: Commit**

```bash
git add engine/tests/test_analysis_flow.py engine/agent/tests/test_progress_runtime_v2.py engine/agent/tests/test_e2e_qwen.py engine/tests/test_tool_contract.py
git commit -m "test: update tests for analyze_data and data_profile rename"
```

---

### Task 15: Final integration verification

**Files:**
- None (verification only)

- [ ] **Step 1: Verify tool registry loads without errors**

```bash
python -c "from engine.tools.databox_tools import register_databox_tools; r = register_databox_tools(); print('Tools:', len(r.list_specs())); assert r.get('analyze_data') is not None; print('analyze_data registered OK')"
```

- [ ] **Step 2: Verify graph can be built**

```bash
python -c "from engine.agent.graph.react_graph import build_databox_react_graph; g = build_databox_react_graph(); print('Graph built OK')"
```

- [ ] **Step 3: Run full test suite**

```bash
python -m pytest engine/tests/ engine/agent/tests/ -v --tb=short 2>&1 | tail -50
```

- [ ] **Step 4: Fix any remaining failures and commit**

```bash
git add -u
git commit -m "fix: resolve remaining test failures after analyze_data migration"
```

---
