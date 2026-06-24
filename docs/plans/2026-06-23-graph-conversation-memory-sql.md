# Graph Conversation Memory And SQL-Backed Artifact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move DBFox Agent memory toward LangGraph session threads, batch-compressed conversation memory, SQL-backed artifact refs, and datasource-scoped reusable SQL.

**Architecture:** Use `thread_id = session_id` for LangGraph checkpointed conversation runtime memory. Split graph state into durable conversation fields and turn-local runtime fields reset by `start_turn`, then update durable memory in `finalize_turn`. Keep artifacts SQL-backed: memory stores refs and `safe_sql`, large data is re-read through derived SQL.

**Tech Stack:** Python, FastAPI, SQLAlchemy/Alembic, LangGraph, langchain-core messages, pytest, React/TypeScript for later UI integration.

---

## Files

- Create: `engine/agent_core/memory.py`
  - Pure helpers for SQL fingerprints, memory ref upsert, turn window selection, and compact memory payloads.
- Create: `engine/agent/nodes/turn_node.py`
  - `start_turn` and `finalize_turn` graph nodes plus small pure helpers.
- Modify: `engine/agent/graph/state.py`
  - Add durable conversation memory fields and constants for turn-local reset fields.
- Modify: `engine/agent/graph/react_graph.py`
  - Insert `start_turn` before `model` and `finalize_turn` after `finalize`.
- Modify: `engine/agent/app/service.py`
  - Use `session_id` as LangGraph `thread_id`, keep `run_id` as execution identity.
- Modify: `engine/models.py`
  - Add `AgentSessionMemory` and `ReusableSQL` models. Keep `GoldenSQL` as legacy compatibility.
- Create: `engine/migrations/versions/f7a8b9c0d1e2_add_agent_memory_and_reusable_sql.py`
  - Add new tables and migrate existing `golden_sqls` rows into `reusable_sqls`.
- Modify: `engine/agent_core/persistence/__init__.py`
  - Export memory persistence helpers if needed.
- Create: `engine/agent_core/persistence/memory.py`
  - Load/save `AgentSessionMemory`; upsert `ReusableSQL`.
- Create: `engine/agent/tests/test_turn_node_memory.py`
  - TDD tests for reset/update/compression/remove-message behavior.
- Create: `engine/tests/test_agent_memory_models.py`
  - TDD tests for SQL fingerprint/upsert and persistence model behavior.
- Modify: `engine/tests/test_conversations.py`
  - Verify conversation stream sends requests through a session-thread memory path.

## Task 1: Pure Memory Helpers

**Files:**
- Create: `engine/agent_core/memory.py`
- Test: `engine/tests/test_agent_memory_models.py`

- [ ] **Step 1: Write failing tests for SQL fingerprint and ref upsert**

Add tests:

```python
from engine.agent_core.memory import normalize_sql_for_fingerprint, sql_fingerprint, upsert_memory_ref


def test_sql_fingerprint_ignores_whitespace_and_case():
    left = "SELECT  id, name  FROM users WHERE deleted_at IS NULL"
    right = " select id, name from users where deleted_at is null "

    assert normalize_sql_for_fingerprint(left) == normalize_sql_for_fingerprint(right)
    assert sql_fingerprint(left) == sql_fingerprint(right)


def test_upsert_memory_ref_updates_existing_ref_by_datasource_and_fingerprint():
    refs = [
        {
            "id": "mem_old",
            "kind": "result_view_ref",
            "datasource_id": "ds_1",
            "sql_fingerprint": "fp_1",
            "usage_count": 1,
            "last_used_at": "2026-06-20T00:00:00Z",
        }
    ]

    updated = upsert_memory_ref(
        refs,
        {
            "id": "mem_new",
            "kind": "result_view_ref",
            "datasource_id": "ds_1",
            "sql_fingerprint": "fp_1",
            "safe_sql": "SELECT 1",
            "columns": ["count"],
            "last_used_at": "2026-06-23T00:00:00Z",
        },
        max_refs=10,
    )

    assert len(updated) == 1
    assert updated[0]["id"] == "mem_old"
    assert updated[0]["safe_sql"] == "SELECT 1"
    assert updated[0]["usage_count"] == 2
    assert updated[0]["last_used_at"] == "2026-06-23T00:00:00Z"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
pytest engine/tests/test_agent_memory_models.py -q
```

Expected: import fails because `engine.agent_core.memory` does not exist.

- [ ] **Step 3: Implement minimal helpers**

Create `engine/agent_core/memory.py` with:

```python
from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any


def normalize_sql_for_fingerprint(sql: str) -> str:
    return " ".join(sql.strip().lower().split())


def sql_fingerprint(sql: str) -> str:
    normalized = normalize_sql_for_fingerprint(sql)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"sql_{digest[:24]}"


def upsert_memory_ref(
    refs: list[dict[str, Any]],
    candidate: dict[str, Any],
    *,
    max_refs: int,
) -> list[dict[str, Any]]:
    result = [deepcopy(ref) for ref in refs if isinstance(ref, dict)]
    datasource_id = candidate.get("datasource_id")
    fingerprint = candidate.get("sql_fingerprint")
    match_index = next(
        (
            index
            for index, ref in enumerate(result)
            if ref.get("datasource_id") == datasource_id
            and ref.get("sql_fingerprint") == fingerprint
            and ref.get("kind") == candidate.get("kind")
        ),
        None,
    )

    if match_index is not None:
        current = result[match_index]
        merged = {**current, **candidate, "id": current.get("id") or candidate.get("id")}
        merged["usage_count"] = int(current.get("usage_count") or 0) + 1
        result[match_index] = merged
    else:
        inserted = deepcopy(candidate)
        inserted["usage_count"] = int(inserted.get("usage_count") or 0) or 1
        result.append(inserted)

    result.sort(key=lambda ref: (bool(ref.get("pinned")), str(ref.get("last_used_at") or "")), reverse=True)
    return result[:max_refs]
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
pytest engine/tests/test_agent_memory_models.py -q
```

Expected: tests pass.

## Task 2: Turn Reset And Batch Compression Node Helpers

**Files:**
- Create: `engine/agent/nodes/turn_node.py`
- Modify: `engine/agent/graph/state.py`
- Test: `engine/agent/tests/test_turn_node_memory.py`

- [ ] **Step 1: Write failing tests for turn-local reset**

Add:

```python
from engine.agent.nodes.turn_node import build_turn_reset_update


def test_build_turn_reset_update_clears_turn_runtime_without_touching_durable_memory():
    update = build_turn_reset_update(
        run_id="run_2",
        session_id="session_1",
        datasource_id="ds_1",
        question="continue the analysis",
        execute=True,
        max_steps=50,
    )

    assert update["run_id"] == "run_2"
    assert update["thread_id"] == "session_1"
    assert update["session_id"] == "session_1"
    assert update["messages"] == [{"role": "user", "content": "continue the analysis"}]
    assert update["pending_tool_calls"] == []
    assert update["allowed_tool_calls"] == []
    assert update["blocked_tool_calls"] == []
    assert update["last_tool_results"] == []
    assert update["sql"] is None
    assert update["safety"] is None
    assert update["execution"] is None
    assert update["repair_mode"] is False
    assert update["revision_count"] == 0
    assert update["trace_events"] == [{"__clear__": True}]
    assert "conversation_summary" not in update
```

- [ ] **Step 2: Write failing tests for batch compression planning**

Add:

```python
from engine.agent.nodes.turn_node import plan_message_compaction


class Message:
    def __init__(self, id: str, type: str = "human"):
        self.id = id
        self.type = type


def test_plan_message_compaction_waits_until_batch_threshold():
    messages = [Message(f"m{i}") for i in range(1, 7)]

    plan = plan_message_compaction(messages, keep_recent=4, batch_size=3)

    assert plan.to_summarize == []
    assert plan.remove_messages == []


def test_plan_message_compaction_compacts_oldest_batch_only():
    messages = [Message(f"m{i}") for i in range(1, 9)]

    plan = plan_message_compaction(messages, keep_recent=4, batch_size=3)

    assert [message.id for message in plan.to_summarize] == ["m1", "m2", "m3"]
    assert [message.id for message in plan.remove_messages] == ["m1", "m2", "m3"]
```

- [ ] **Step 3: Run tests to verify RED**

Run:

```bash
pytest engine/agent/tests/test_turn_node_memory.py -q
```

Expected: import fails because `turn_node.py` does not exist.

- [ ] **Step 4: Implement minimal helpers and state fields**

Add durable fields to `DBFoxAgentState`:

```python
conversation_summary: str | None
summary_cursor_message_id: str | None
recent_turns: Annotated[list[dict[str, Any]], _add_list]
artifact_ref_index: Annotated[list[dict[str, Any]], _add_list]
sql_ref_index: Annotated[list[dict[str, Any]], _add_list]
active_task: dict[str, Any] | None
reusable_sql_candidates: list[dict[str, Any]]
```

Create `engine/agent/nodes/turn_node.py` with `build_turn_reset_update`, `plan_message_compaction`, and dataclass `CompactionPlan`.

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```bash
pytest engine/agent/tests/test_turn_node_memory.py -q
```

Expected: tests pass.

## Task 3: Session Thread ID In LangGraph Runtime

**Files:**
- Modify: `engine/agent/app/service.py`
- Modify: `engine/agent/graph/react_graph.py`
- Test: `engine/agent/tests/test_turn_node_memory.py`

- [ ] **Step 1: Write failing test for graph using session thread**

Add a test that monkeypatches graph execution enough to assert `ctx.graph_config(session_id)` is called with the session id and state `thread_id` equals session id.

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
pytest engine/agent/tests/test_turn_node_memory.py::test_agent_service_uses_session_id_as_graph_thread -q
```

Expected: assertion shows current code uses `run_id`.

- [ ] **Step 3: Update runtime**

Change:

```python
config = ctx.graph_config(run_id)
```

to:

```python
config = ctx.graph_config(session_id)
```

Keep `run_id` in state and persistence unchanged.

- [ ] **Step 4: Insert turn graph nodes**

Change graph flow:

```text
START -> start_turn -> model
finalize -> finalize_turn -> END
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
pytest engine/agent/tests/test_react_graph.py engine/agent/tests/test_turn_node_memory.py -q
```

Expected: pass.

## Task 4: Agent Session Memory And Reusable SQL Persistence

**Files:**
- Modify: `engine/models.py`
- Create: `engine/agent_core/persistence/memory.py`
- Create: `engine/migrations/versions/f7a8b9c0d1e2_add_agent_memory_and_reusable_sql.py`
- Test: `engine/tests/test_agent_memory_models.py`

- [ ] **Step 1: Write failing tests for models and upsert**

Add tests that create a datasource/session, save an `AgentSessionMemory`, and upsert a reusable SQL row twice by `(datasource_id, sql_fingerprint)`.

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
pytest engine/tests/test_agent_memory_models.py -q
```

Expected: model/table/helper imports fail.

- [ ] **Step 3: Add models**

Add `AgentSessionMemory` and `ReusableSQL` SQLAlchemy models. Use `reusable_sqls` as the table name; keep `GoldenSQL` unchanged as legacy.

- [ ] **Step 4: Add migration**

Create the migration with:

```python
op.create_table("agent_session_memories", ...)
op.create_table("reusable_sqls", ...)
op.create_index("ix_reusable_sqls_datasource", "reusable_sqls", ["data_source_id"])
op.create_unique_constraint("uq_reusable_sqls_ds_fingerprint", "reusable_sqls", ["data_source_id", "sql_fingerprint"])
```

Copy existing `golden_sqls` into `reusable_sqls` in upgrade when the legacy table exists.

- [ ] **Step 5: Add persistence helpers**

Implement:

```python
load_session_memory(db, session_id)
save_session_memory(db, session_id, payload)
upsert_reusable_sql(db, datasource_id, question, safe_sql, ...)
```

- [ ] **Step 6: Run model tests**

Run:

```bash
pytest engine/tests/test_agent_memory_models.py -q
```

Expected: pass.

## Task 5: SQL-Backed Artifact Ref Extraction And Dedup

**Files:**
- Modify: `engine/agent/nodes/turn_node.py`
- Modify: `engine/agent_core/memory.py`
- Test: `engine/agent/tests/test_turn_node_memory.py`

- [ ] **Step 1: Write failing tests for result refs**

Test that `finalize_turn` extracts completed `result_view` artifacts with `storageMode="sql_backed"` into `artifact_ref_index` and `sql_ref_index`, and skips failed/error/empty intermediate artifacts.

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
pytest engine/agent/tests/test_turn_node_memory.py -q
```

Expected: missing extraction behavior.

- [ ] **Step 3: Implement extraction**

Implement pure helper:

```python
extract_sql_backed_refs(state) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]
```

Use `safe_sql`, `datasource_id`, `columns`, `artifact_id`, `source_sql_artifact_id`, `purpose`, `row_count`, and `sql_fingerprint`.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
pytest engine/agent/tests/test_turn_node_memory.py -q
```

Expected: pass.

## Task 6: Follow-Up Analysis Through SQL-Backed Refs

**Files:**
- Create: `engine/tools/db/result_ref.py`
- Modify: `engine/tools/dbfox_tools.py`
- Test: `engine/tests/test_tool_runtime_v2.py` or a new focused test file.

- [ ] **Step 1: Write failing tests for resolving a result ref**

Test that a result ref with `safe_sql` can be profiled without loading full data: returned observation includes columns, row count, preview rows, and executable derived SQL.

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
pytest engine/tests/test_tool_runtime_v2.py -q
```

Expected: missing tool.

- [ ] **Step 3: Implement model-visible tools**

Add:

```text
result.resolve_ref
result.profile
result.query_derived
chart.from_result_ref
```

Keep returned observations compact. Do not return large result sets to the model.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
pytest engine/tests/test_tool_runtime_v2.py -q
```

Expected: pass.

## Task 7: Conversation API Memory Path

**Files:**
- Modify: `engine/api/conversations.py`
- Modify: `engine/tests/test_conversations.py`

- [ ] **Step 1: Write failing tests**

Verify streaming a second message in the same conversation sends an `AgentRunRequest` whose `session_id`, `conversation_id`, and graph thread path all point at the conversation id. Verify workspace recent run fallback is current-session scoped.

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
pytest engine/tests/test_conversations.py -q
```

Expected: fails on missing memory/session-thread behavior.

- [ ] **Step 3: Implement API wiring**

Keep payload stable. Set `workspace_context.recent_agent_run_id` only from the same session when useful. Do not fall back to another conversation in the same datasource.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
pytest engine/tests/test_conversations.py -q
```

Expected: pass.

## Verification

- [ ] Run focused backend tests:

```bash
pytest engine/tests/test_agent_memory_models.py engine/agent/tests/test_turn_node_memory.py engine/tests/test_conversations.py -q
```

- [ ] Run broader agent tests:

```bash
pytest engine/agent/tests/test_react_graph.py engine/agent/tests/test_finalize_node.py engine/agent/tests/test_progress_runtime_v2.py engine/tests/test_agent_api.py engine/tests/test_architecture.py -q
```

- [ ] Run migration sanity check:

```bash
alembic upgrade head
```

- [ ] Run frontend tests if artifact UI types are touched:

```bash
cd desktop && npm run test -- --run
```

## Self-Review Notes

- This plan preserves the user's core direction: use LangGraph session threads for runtime memory, not a separate ad-hoc memory runner.
- It avoids storing large result data in memory or artifacts; SQL-backed refs are the source of truth.
- It replaces the old broad "Golden SQL" meaning with datasource-scoped reusable SQL while keeping legacy compatibility.
- It keeps human-in-loop approval tied to run records and checkpoints while conversation durable memory remains session scoped.
