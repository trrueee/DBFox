# Agent State Contract & AI Schema Linking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two parallel tracks — Track 1 establishes declarative tool state contracts for consistent error cleanup; Track 2 replaces hardcoded synonyms with AI-enriched schema search docs + FTS5.

**Architecture:** Track 1 adds `ToolStateContract` as a declarative per-tool state contract, refactors `databinding.py` to drive state cleanup from contracts, and wires `merge_strategy` through SSE events to the frontend `agentTimeline.ts`. Track 2 extends `schema_tables`/`schema_columns` with AI metadata columns, creates `schema_search_docs` + FTS5 index, adds `engine/ai_index.py` for LLM batch enrichment during `schema.refresh_catalog`, and refactors `db.search` to use FTS-based scoring with a keyword fallback path.

**Tech Stack:** Python (dataclasses, SQLAlchemy, jieba, aliyun LLM SDK), TypeScript (React, Vitest), SQLite FTS5

---

## File Structure

```
New files:
  engine/agent_core/tool_contract.py         — ToolStateContract dataclass + registry
  engine/ai_index.py                         — LLM enrich + jieba tokenizer + search_text builder
  engine/tests/test_tool_contract.py         — Contract validation tests
  engine/tests/test_ai_index.py              — AI index unit tests

Modified files:
  engine/agent_core/databinding.py           — Contract-driven success/failure paths
  engine/agent/app/event_mapper.py           — Pass merge_strategy through trace
  engine/models.py                           — New columns on SchemaTable/SchemaColumn + SchemaSearchDoc model
  engine/tools/db_tools.py                   — FTS search path + fallback + delete bootstrap
  engine/schema_sync.py                      — AI enrich phase in refresh_catalog
  engine/config.py                           — (or wherever AI_* configs live)
  desktop/src/lib/api/types.ts               — AgentStep merge_strategy field
  desktop/src/features/workspace/agentTimeline.ts — merge_strategy-aware upsert
  desktop/src/features/workspace/__tests__/agentTimeline.test.ts — New test cases
  engine/tests/test_db_tools.py              — FTS search tests
```

---

## Phase 1: Track 1 — State Contract (Backend)

### Task 1: Create ToolStateContract and register all tools

**Files:**
- Create: `engine/agent_core/tool_contract.py`
- Modify: (none)

- [ ] **Step 1: Create the module with dataclass and full registry**

```python
# engine/agent_core/tool_contract.py
"""Declarative per-tool state contracts — success cleanup, failure telemetry, merge strategy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MergeStrategy = Literal["reuse", "new", "always_new"]


@dataclass(frozen=True)
class ToolStateContract:
    tool_name: str
    on_success_clear: tuple[str, ...]   # keys set to None on success
    on_success_reset: tuple[str, ...]   # keys reset via RESET_* constants
    merge_strategy: MergeStrategy
    emit_artifact: bool


# ── Reusable reset groups ──
RESET_ERROR = ("error",)
RESET_SELF_HEALING = ("last_error_telemetry", "last_failed_tool_call")
RESET_ALL_ERROR_STATE = RESET_ERROR + RESET_SELF_HEALING


TOOL_CONTRACTS: dict[str, ToolStateContract] = {
    # ── Database operations ──
    "db.query": ToolStateContract(
        tool_name="db.query",
        on_success_clear=RESET_ALL_ERROR_STATE,
        on_success_reset=(),
        merge_strategy="reuse",
        emit_artifact=True,
    ),
    "db.preview": ToolStateContract(
        tool_name="db.preview",
        on_success_clear=RESET_ALL_ERROR_STATE,
        on_success_reset=(),
        merge_strategy="reuse",
        emit_artifact=True,
    ),
    "db.inspect": ToolStateContract(
        tool_name="db.inspect",
        on_success_clear=RESET_ALL_ERROR_STATE,
        on_success_reset=(),
        merge_strategy="new",
        emit_artifact=False,
    ),
    "db.search": ToolStateContract(
        tool_name="db.search",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="reuse",
        emit_artifact=False,
    ),
    "db.observe": ToolStateContract(
        tool_name="db.observe",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="reuse",
        emit_artifact=False,
    ),
    "db.remember": ToolStateContract(
        tool_name="db.remember",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="new",
        emit_artifact=False,
    ),

    # ── Schema operations ──
    "schema.list_tables": ToolStateContract(
        tool_name="schema.list_tables",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="reuse",
        emit_artifact=False,
    ),
    "schema.describe_table": ToolStateContract(
        tool_name="schema.describe_table",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="reuse",
        emit_artifact=False,
    ),
    "schema.refresh_catalog": ToolStateContract(
        tool_name="schema.refresh_catalog",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="new",
        emit_artifact=False,
    ),

    # ── Semantic / memory ──
    "semantic.resolve": ToolStateContract(
        tool_name="semantic.resolve",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="reuse",
        emit_artifact=False,
    ),
    "memory.search": ToolStateContract(
        tool_name="memory.search",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="reuse",
        emit_artifact=False,
    ),
    "memory.write": ToolStateContract(
        tool_name="memory.write",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="new",
        emit_artifact=False,
    ),

    # ── Analysis / synthesis ──
    "environment.get_profile": ToolStateContract(
        tool_name="environment.get_profile",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="reuse",
        emit_artifact=False,
    ),
    "result.profile": ToolStateContract(
        tool_name="result.profile",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="new",
        emit_artifact=True,
    ),
    "chart.suggest": ToolStateContract(
        tool_name="chart.suggest",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="new",
        emit_artifact=True,
    ),
    "answer.synthesize": ToolStateContract(
        tool_name="answer.synthesize",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="always_new",
        emit_artifact=True,
    ),
}


def get_contract(tool_name: str) -> ToolStateContract:
    """Return the contract for a tool, or a safe default for unregistered tools."""
    if tool_name in TOOL_CONTRACTS:
        return TOOL_CONTRACTS[tool_name]
    if tool_name.startswith("workspace."):
        return ToolStateContract(
            tool_name=tool_name,
            on_success_clear=(),
            on_success_reset=(),
            merge_strategy="new",
            emit_artifact=True,
        )
    return ToolStateContract(
        tool_name=tool_name,
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="reuse",
        emit_artifact=False,
    )
```

- [ ] **Step 2: Verify the module imports cleanly**

Run: `python -c "from engine.agent_core.tool_contract import TOOL_CONTRACTS, get_contract; print(len(TOOL_CONTRACTS))"`
Expected: prints `16` or the current count.

- [ ] **Step 3: Commit**

```bash
git add engine/agent_core/tool_contract.py
git commit -m "feat: add ToolStateContract dataclass and registry for all tools"
```

---

### Task 2: Refactor databinding.py to use contracts

**Files:**
- Modify: `engine/agent_core/databinding.py:158-290`

- [ ] **Step 1: Import contract module in databinding.py**

In `engine/agent_core/databinding.py`, after the existing imports, add:

```python
from engine.agent_core.tool_contract import get_contract
```

- [ ] **Step 2: Replace `apply_tool_result_to_state` with contract-driven version**

Replace the existing `apply_tool_result_to_state` function (currently at lines 158-202) with:

```python
def apply_tool_result_to_state(
    *,
    state: dict[str, Any],
    tool_name: str,
    observation: ToolObservation,
) -> dict[str, Any]:
    contract = get_contract(tool_name)
    output = observation.output or {}

    update: dict[str, Any] = {
        "tool_results": [observation.model_dump(mode="json")],
        "trace_events": [
            {
                "type": "tool.completed",
                "payload": {
                    "tool_name": tool_name,
                    "observation_name": observation.name,
                    "status": observation.status,
                    "_merge_strategy": contract.merge_strategy,
                },
            }
        ],
    }

    # ── Failed path ──
    if observation.status == "failed":
        _apply_failed_telemetry(state, tool_name, observation, output, update)
        return update

    # ── Success path: contract-driven cleanup first ──
    for key in contract.on_success_clear:
        update[key] = None
    for key in contract.on_success_reset:
        update[key] = None

    # ── Then tool-specific state handler ──
    handler = TOOL_STATE_APPLIERS.get(tool_name)
    if handler is not None:
        tool_update = handler(state, output, observation)
    elif tool_name.startswith("workspace."):
        tool_update = _apply_workspace_prefix(state, output, observation)
    else:
        tool_update = {}

    extra_trace = tool_update.pop("_trace", None)
    if isinstance(extra_trace, list):
        update["trace_events"].extend(extra_trace)
    update.update(tool_update)

    # ── Artifact emission ──
    if contract.emit_artifact:
        update["artifacts"] = [_artifact_event(tool_name, output)]

    return update
```

- [ ] **Step 3: Remove hand-written cleanup from `_apply_db_query`**

In `_apply_db_query` (currently lines 75-87), remove the manual `"error": None` and `**RESET_SELF_HEALING`:

```python
def _apply_db_query(state: dict[str, Any], output: dict[str, Any], _obs: ToolObservation) -> dict[str, Any]:
    execution = dict(output)
    execution["success"] = output.get("status") == "success"
    execution["rowCount"] = output.get("rowCount", output.get("returned_rows", 0))
    execution["latencyMs"] = output.get("latencyMs", output.get("execution_time_ms", 0))
    update: dict[str, Any] = {"execution": execution}
    if output.get("safe_sql"):
        update["sql"] = output.get("safe_sql")
    return update
```

- [ ] **Step 4: Remove `RESET_SELF_HEALING` import/definition from databinding.py**

Delete lines 16-19:
```python
RESET_SELF_HEALING: dict[str, Any] = {
    "last_error_telemetry": None,
    "last_failed_tool_call": None,
}
```

- [ ] **Step 5: Run existing tests to verify no regression**

```bash
cd engine && python -m pytest tests/test_analysis_flow.py -x -q
```

Expected: PASS (or same failures as before)

- [ ] **Step 6: Commit**

```bash
git add engine/agent_core/databinding.py
git commit -m "refactor: drive state cleanup from ToolStateContract, remove hand-written error reset"
```

---

### Task 3: Pass merge_strategy through event_mapper to frontend

**Files:**
- Modify: `engine/agent/app/event_mapper.py:45-83`

- [ ] **Step 1: Add merge_strategy to trace_to_events step payloads**

In `engine/agent/app/event_mapper.py`, within `trace_to_events`, modify the `agent.tool.completed` handler (lines 71-82) to include `_merge_strategy`:

```python
elif trace_type == "agent.tool.completed":
    payload = trace.get("payload", trace)
    yield emit(
        "agent.step.completed",
        step={
            "name": mapped_name,
            "tool_name": tool_name,
            "status": payload.get("status") if isinstance(payload, dict) else trace.get("status"),
            "latency_ms": payload.get("latency_ms") if isinstance(payload, dict) else trace.get("latency_ms"),
            "input": payload.get("input") if isinstance(payload, dict) else trace.get("input"),
            "output": payload.get("output") if isinstance(payload, dict) else trace.get("output"),
            "error": payload.get("error") if isinstance(payload, dict) else trace.get("error"),
            "merge_strategy": (payload.get("_merge_strategy") if isinstance(payload, dict) else None) or "reuse",
        },
    )
```

> Note: `trace_to_events` reads `trace["payload"]` because `databinding.py` nests fields under `"payload"`. The `_merge_strategy` field was added to that payload in Task 2.

- [ ] **Step 2: Verify the trace event structure is consistent**

Run: `python -c "
from engine.agent_core.databinding import apply_tool_result_to_state
from engine.agent_core.types import ToolObservation
state = {}
obs = ToolObservation(name='query_database', status='success', input={'sql': 'SELECT 1'}, output={'rows': []}, error=None, latency_ms=10)
update = apply_tool_result_to_state(state=state, tool_name='db.query', observation=obs)
print('_merge_strategy in payload:', update['trace_events'][0]['payload'].get('_merge_strategy'))
print('on_success_clear applied: error' in update and update.get('error') is None)
"`

Expected: prints `_merge_strategy: reuse` and `on_success_clear applied: True`

- [ ] **Step 3: Commit**

```bash
git add engine/agent/app/event_mapper.py
git commit -m "feat: pass merge_strategy through trace events to frontend"
```

---

## Phase 1: Track 1 — State Contract (Frontend)

### Task 4: Extend AgentStep type with merge_strategy

**Files:**
- Modify: `desktop/src/lib/api/types.ts:283-295`

- [ ] **Step 1: Add merge_strategy to AgentStep interface**

In `desktop/src/lib/api/types.ts`, find `export interface AgentStep` (around line 283). Add the field:

```typescript
export interface AgentStep {
  name: string;
  status: AgentStepStatus;
  tool_name?: string;
  input?: Record<string, unknown> | null;
  output?: Record<string, unknown> | null;
  error?: string | null;
  latency_ms?: number | null;
  merge_strategy?: "reuse" | "new" | "always_new";  // ← ADD
  // ... any other existing fields
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd desktop && npx tsc --noEmit src/lib/api/types.ts 2>&1 | head -5
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add desktop/src/lib/api/types.ts
git commit -m "feat: add merge_strategy to AgentStep type"
```

---

### Task 5: Refactor agentTimeline.ts with merge_strategy-aware error clearing

**Files:**
- Modify: `desktop/src/features/workspace/agentTimeline.ts:118-147`

- [ ] **Step 1: Rewrite upsertToolStep to consume merge_strategy**

In `desktop/src/features/workspace/agentTimeline.ts`, replace the `upsertToolStep` function (lines 118-147) with:

```typescript
function upsertToolStep(
  current: AgentTimelineItem[],
  event: AgentRuntimeEvent,
): AgentTimelineItem[] {
  const step = event.step || {};
  const toolName = stringValue(step.tool_name) || stringValue(step.name) || "tool";
  const stepName = stringValue(step.name);
  const isCompleted = event.type === "agent.step.completed";
  const strategy = step.merge_strategy || "reuse";

  // Id strategy: "new" and "always_new" always create fresh cards
  let id: string;
  if (strategy === "always_new" || strategy === "new") {
    id = toolEventId(toolName, event.sequence);
  } else {
    // reuse: match the latest running card of same tool name
    id = isCompleted
      ? findLatestRunningToolId(current, toolName, stepName) || toolEventId(toolName, event.sequence)
      : toolEventId(toolName, event.sequence);
  }

  const previous = current.find((item) => item.id === id);
  const input = recordValue(step.input) ?? previous?.input ?? null;
  const output = recordValue(step.output) ?? previous?.output ?? null;

  // Core fix: on success + reuse, force clear error (old error from retry must not persist)
  const stepStatus = isCompleted ? statusValue(step.status, "success") : "running";
  const error =
    isCompleted && strategy === "reuse" && stepStatus === "success"
      ? null
      : stringValue(step.error) || previous?.error || null;

  const content = isCompleted
    ? toolStepSummary(toolName, output, error)
    : previous?.content;

  return upsertById(current, {
    id,
    kind: "tool",
    title: toolName,
    subtitle: stepName,
    status: stepStatus,
    toolName,
    content,
    input,
    output,
    error,
    latencyMs: numberValue(step.latency_ms) ?? previous?.latencyMs ?? null,
  });
}
```

- [ ] **Step 2: Run existing frontend tests**

```bash
cd desktop && npx vitest run src/features/workspace/__tests__/agentTimeline.test.ts
```

Expected: All existing tests pass, especially the "keeps repeated tool invocations separate" test.

- [ ] **Step 3: Commit**

```bash
git add desktop/src/features/workspace/agentTimeline.ts
git commit -m "fix: clear error on tool retry success via merge_strategy contract"
```

---

### Task 6: Add frontend tests for merge_strategy behaviors

**Files:**
- Modify: `desktop/src/features/workspace/__tests__/agentTimeline.test.ts`

- [ ] **Step 1: Add test for reuse strategy clearing error on retry success**

Add at the end of the `describe("agentTimeline", ...)` block:

```typescript
it("clears error when a reuse-strategy tool succeeds after failure (merge_strategy=reuse)", () => {
  let timeline = createInitialAgentTimeline("test retry");

  // First: failed attempt
  timeline = appendAgentRuntimeEvent(timeline, event({
    sequence: 2,
    type: "agent.step.completed",
    step: {
      name: "query_database",
      tool_name: "db.query",
      status: "failed",
      error: "TrustGate Error",
      merge_strategy: "reuse",
      latency_ms: 10,
    },
  }));
  expect(timeline[1].error).toBe("TrustGate Error");
  expect(timeline[1].status).toBe("failed");

  // Second: successful retry — same tool, reuse strategy
  timeline = appendAgentRuntimeEvent(timeline, event({
    sequence: 3,
    type: "agent.step.completed",
    step: {
      name: "query_database",
      tool_name: "db.query",
      status: "success",
      output: { rows: [{ cnt: 42 }] },
      merge_strategy: "reuse",
      latency_ms: 15,
    },
  }));

  const toolItems = timeline.filter((item) => item.kind === "tool");
  expect(toolItems).toHaveLength(1); // reused card
  expect(toolItems[0].status).toBe("success");
  expect(toolItems[0].error).toBeNull(); // ← KEY: old error cleared
  expect(toolItems[0].output).toEqual({ rows: [{ cnt: 42 }] });
});

it("does not clear error for new-strategy tools (each invocation separate)", () => {
  let timeline = createInitialAgentTimeline("test");

  timeline = appendAgentRuntimeEvent(timeline, event({
    sequence: 2,
    type: "agent.step.completed",
    step: {
      name: "remember_database_semantics",
      tool_name: "db.remember",
      status: "failed",
      error: "type and target are required",
      merge_strategy: "new",
      latency_ms: 5,
    },
  }));
  timeline = appendAgentRuntimeEvent(timeline, event({
    sequence: 3,
    type: "agent.step.completed",
    step: {
      name: "remember_database_semantics",
      tool_name: "db.remember",
      status: "success",
      output: { status: "remembered" },
      merge_strategy: "new",
      latency_ms: 8,
    },
  }));

  const toolItems = timeline.filter((item) => item.kind === "tool");
  expect(toolItems).toHaveLength(2); // separate cards, no merge
  expect(toolItems[0].status).toBe("failed");
  expect(toolItems[0].error).toBe("type and target are required");
  expect(toolItems[1].status).toBe("success");
  expect(toolItems[1].error).toBeNull();
});

it("always_new strategy never reuses cards", () => {
  let timeline = createInitialAgentTimeline("test");

  timeline = appendAgentRuntimeEvent(timeline, event({
    sequence: 2,
    type: "agent.step.completed",
    step: {
      name: "answer_synthesize",
      tool_name: "answer.synthesize",
      status: "success",
      output: { answer: "first" },
      merge_strategy: "always_new",
      latency_ms: 5,
    },
  }));
  timeline = appendAgentRuntimeEvent(timeline, event({
    sequence: 3,
    type: "agent.step.completed",
    step: {
      name: "answer_synthesize",
      tool_name: "answer.synthesize",
      status: "success",
      output: { answer: "second" },
      merge_strategy: "always_new",
      latency_ms: 5,
    },
  }));

  const toolItems = timeline.filter((item) => item.kind === "tool");
  expect(toolItems).toHaveLength(2);
  expect(toolItems[0].id).not.toBe(toolItems[1].id);
});
```

- [ ] **Step 2: Run the new tests**

```bash
cd desktop && npx vitest run src/features/workspace/__tests__/agentTimeline.test.ts
```

Expected: 3 new tests PASS.

- [ ] **Step 3: Commit**

```bash
git add desktop/src/features/workspace/__tests__/agentTimeline.test.ts
git commit -m "test: add merge_strategy behavior tests for timeline error clearing"
```

---

## Phase 2: Track 2 — AI Schema Linking (DB + Models)

### Task 7: Add AI metadata columns to SchemaTable and SchemaColumn

**Files:**
- Modify: `engine/models.py:181-239`

- [ ] **Step 1: Add new columns to SchemaTable**

In `engine/models.py`, inside `class SchemaTable`, add after `engine_name`:

```python
    # AI-enriched metadata (populated by schema.refresh_catalog ai_enrich=True)
    ai_description = Column(Text, nullable=True)
    semantic_tags = Column(Text, nullable=True)       # JSON array
    business_terms = Column(Text, nullable=True)      # JSON array
    aliases = Column(Text, nullable=True)             # JSON array
    table_role = Column(String, nullable=True)        # fact / dim / bridge / log / agg
    grain = Column(Text, nullable=True)
    subject_area = Column(String, nullable=True)      # user / order / content / traffic
    ai_confidence = Column(Float, nullable=True)
    ai_enriched_at = Column(DateTime, nullable=True)
    schema_hash = Column(String, nullable=True)       # structural hash for incremental refresh
```

- [ ] **Step 2: Add new columns to SchemaColumn**

In `engine/models.py`, inside `class SchemaColumn`, add after `ordinal_position`:

```python
    ai_description = Column(Text, nullable=True)
    semantic_tags = Column(Text, nullable=True)       # JSON array
    business_terms = Column(Text, nullable=True)      # JSON array
    aliases = Column(Text, nullable=True)             # JSON array
    column_role = Column(String, nullable=True)       # dimension / measure / time / id / status
    metric_type = Column(String, nullable=True)       # count / amount / rate / duration
    is_pii = Column(Boolean, nullable=False, default=False)
    ai_confidence = Column(Float, nullable=True)
    ai_enriched_at = Column(DateTime, nullable=True)
```

- [ ] **Step 3: Create the DB migration**

```bash
cd engine && python -c "
from engine.models import Base, engine
# SQLite auto-adds columns; for production, create an Alembic migration
# For now, SQLAlchemy create_all handles new columns on next startup
print('Columns defined in models — migration applied on next create_all')
"
```

- [ ] **Step 4: Commit**

```bash
git add engine/models.py
git commit -m "feat: add AI metadata columns to SchemaTable and SchemaColumn"
```

---

### Task 8: Create SchemaSearchDoc model and FTS5 table

**Files:**
- Modify: `engine/models.py` (add SchemaSearchDoc model)

- [ ] **Step 1: Add SchemaSearchDoc model**

In `engine/models.py`, before the last class, add:

```python
class SchemaSearchDoc(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "schema_search_docs"
    __table_args__ = (
        Index("ix_search_docs_ds", "datasource_id", "entity_type"),
        Index("ix_search_docs_table", "datasource_id", "table_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    datasource_id = Column(String, nullable=False)

    entity_type = Column(String, nullable=False)       # 'table' / 'column'
    entity_id = Column(String, nullable=False)          # SchemaTable.id / SchemaColumn.id

    table_name = Column(String, nullable=True)
    column_name = Column(String, nullable=True)

    name = Column(String, nullable=False)
    ai_description = Column(Text, nullable=True)
    semantic_tags = Column(Text, nullable=True)
    business_terms = Column(Text, nullable=True)
    aliases = Column(Text, nullable=True)

    table_role = Column(String, nullable=True)
    column_role = Column(String, nullable=True)
    metric_type = Column(String, nullable=True)
    grain = Column(Text, nullable=True)
    subject_area = Column(String, nullable=True)

    column_summary = Column(Text, nullable=True)
    relation_summary = Column(Text, nullable=True)

    search_text = Column(Text, nullable=False)          # FTS indexed — jieba-segmented
    ai_confidence = Column(Float, nullable=True)

    updated_at = Column(DateTime, nullable=False, default=utcnow)
```

- [ ] **Step 2: Add FTS5 creation helper**

In the same file or a migration helper, add:

```python
FTS5_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS schema_search_fts USING fts5(
    name,
    ai_description,
    semantic_tags,
    business_terms,
    aliases,
    column_summary,
    relation_summary,
    search_text,
    content='schema_search_docs',
    content_rowid='id'
);
"""
```

- [ ] **Step 3: Commit**

```bash
git add engine/models.py
git commit -m "feat: add SchemaSearchDoc model and FTS5 DDL"
```

---

## Phase 2: Track 2 — AI Index Module

### Task 9: Create engine/ai_index.py — jieba tokenizer and search_text builder

**Files:**
- Create: `engine/ai_index.py`

- [ ] **Step 1: Create the module with tokenizer + builder**

```python
# engine/ai_index.py
"""AI schema enrichment — LLM batch tagging, jieba tokenizer, search_text builder."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

logger = logging.getLogger("databox.ai_index")

# ── Tokenization ────────────────────────────────────────────────────────────────

# Lazy-load jieba to avoid import cost when ai_index is unused
_jieba_loaded = False


def _ensure_jieba():
    global _jieba_loaded
    if not _jieba_loaded:
        import jieba
        jieba.setLogLevel(logging.WARNING)
        _jieba_loaded = True


def tokenize_query(query: str) -> list[str]:
    """Tokenize a user query into Chinese + English tokens."""
    _ensure_jieba()
    import jieba

    tokens: list[str] = []
    # English / numeric tokens
    eng_tokens = re.findall(r"[A-Za-z0-9_]+", query)
    tokens.extend(t for t in eng_tokens if len(t) >= 2)

    # Chinese via jieba
    chinese_part = re.sub(r"[A-Za-z0-9_]+", " ", query)
    tokens.extend(t.strip() for t in jieba.lcut(chinese_part) if t.strip())

    return list(dict.fromkeys(tokens))  # dedup, preserve order


def segment_for_fts(text: str) -> str:
    """Segment Chinese text with jieba for FTS5 insertion (spaces between words)."""
    _ensure_jieba()
    import jieba
    if not text:
        return ""
    # Split on existing whitespace, segment each chunk
    parts = text.split()
    result: list[str] = []
    for part in parts:
        if re.search(r"[一-鿿]", part):
            result.extend(jieba.lcut(part))
        else:
            result.append(part)
    return " ".join(result)


# ── Search text builders ─────────────────────────────────────────────────────────

def build_table_search_text(
    table_name: str,
    ai_description: str | None,
    semantic_tags: list[str] | None,
    business_terms: list[str] | None,
    aliases: list[str] | None,
    table_role: str | None,
    grain: str | None,
    column_names: list[str],
    column_ai_descriptions: dict[str, str | None],
    relation_text: str | None,
) -> str:
    """Construct the FTS5 search_text for one table."""
    parts: list[str] = []

    parts.append(f"表名: {table_name}")
    if ai_description:
        parts.append(f"业务描述: {ai_description}")
    if semantic_tags:
        parts.append(f"语义标签: {' '.join(semantic_tags)}")
    if business_terms:
        parts.append(f"业务术语: {' '.join(business_terms)}")
    if aliases:
        parts.append(f"别名: {' '.join(aliases)}")
    if table_role:
        parts.append(f"表角色: {table_role}")
    if grain:
        parts.append(f"表粒度: {grain}")

    # Columns
    col_parts: list[str] = []
    for cname in column_names:
        cdesc = column_ai_descriptions.get(cname)
        col_parts.append(f"{cname}{' ' + cdesc if cdesc else ''}")
    parts.append(f"字段: {' '.join(col_parts)}")

    if relation_text:
        parts.append(f"关系: {relation_text}")

    raw = " ".join(parts)
    return segment_for_fts(raw)


def build_column_search_text(
    column_name: str,
    table_name: str,
    ai_description: str | None,
    semantic_tags: list[str] | None,
    business_terms: list[str] | None,
    column_role: str | None,
    metric_type: str | None,
) -> str:
    """Construct the FTS5 search_text for one column."""
    parts: list[str] = []

    parts.append(f"字段名: {column_name}")
    parts.append(f"所属表: {table_name}")
    if ai_description:
        parts.append(f"字段描述: {ai_description}")
    if semantic_tags:
        parts.append(f"语义标签: {' '.join(semantic_tags)}")
    if business_terms:
        parts.append(f"业务术语: {' '.join(business_terms)}")
    if column_role:
        parts.append(f"字段角色: {column_role}")
    if metric_type:
        parts.append(f"指标类型: {metric_type}")

    raw = " ".join(parts)
    return segment_for_fts(raw)


# ── Schema hash (for incremental refresh) ────────────────────────────────────────

def compute_schema_hash(table) -> str:
    """Compute a stable structural hash for a SchemaTable.
    Changes when columns, types, or comments change.
    """
    import hashlib

    digest = hashlib.sha256()
    digest.update(str(table.table_name or "").encode())
    for col in sorted(getattr(table, "columns", []) or [], key=lambda c: str(c.column_name)):
        digest.update(str(col.column_name or "").encode())
        digest.update(str(col.column_type or col.data_type or "").encode())
        digest.update(str(col.column_comment or "").encode())
    return digest.hexdigest()
```

- [ ] **Step 2: Verify imports**

Run: `python -c "from engine.ai_index import tokenize_query, segment_for_fts, compute_schema_hash; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add engine/ai_index.py
git commit -m "feat: add ai_index module with jieba tokenizer and search_text builders"
```

---

### Task 10: Add LLM enrichment function to ai_index.py

**Files:**
- Modify: `engine/ai_index.py` (append)

- [ ] **Step 1: Add the LLM caller and result validator**

Append to `engine/ai_index.py`:

```python
# ── LLM enrichment ───────────────────────────────────────────────────────────────

def enrich_tables_batch(
    tables_context: list[dict[str, Any]],
    *,
    provider: str = "aliyun",
    model: str = "qwen-plus",
    max_retries: int = 3,
) -> dict[str, Any]:
    """Call LLM to generate AI metadata for a batch of tables.

    Args:
        tables_context: list of dicts with keys:
            name, comment, columns: [{name, type, comment, is_pk, is_fk, fk_ref}],
            sample_rows (3-5 redacted rows), related_tables

    Returns:
        {"tables": [{name, ai_description, semantic_tags, business_terms, aliases,
                      table_role, grain, subject_area, ai_confidence,
                      columns: [{name, ai_description, semantic_tags, business_terms,
                                  aliases, column_role, metric_type, ai_confidence}]}]}
    """
    if not tables_context:
        return {"tables": []}

    prompt = _build_enrich_prompt(tables_context)
    last_error = None

    for attempt in range(max_retries):
        try:
            result = _call_llm(prompt, provider=provider, model=model)
            parsed = json.loads(result) if isinstance(result, str) else result
            _validate_enrich_result(parsed, [t["name"] for t in tables_context])
            return parsed
        except Exception as exc:
            last_error = exc
            logger.warning("LLM enrich attempt %d/%d failed: %s", attempt + 1, max_retries, exc)
            time.sleep(0.5 * (attempt + 1))

    raise RuntimeError(f"LLM enrichment failed after {max_retries} attempts: {last_error}")


def _build_enrich_prompt(tables: list[dict[str, Any]]) -> str:
    """Build the structured prompt for schema enrichment."""
    import json as _json
    context = _json.dumps(tables, ensure_ascii=False, indent=2, default=str)
    return f"""You are a database schema analyst. For each table below, generate business-meaningful metadata in Chinese.

Output JSON only — no commentary. For each table:
- ai_description: 1-2 sentences describing the business meaning of this table
- semantic_tags: 3-6 Chinese tags capturing domain, behavior, and usage
- business_terms: 3-8 searchable business terms users might query for (Chinese + English abbreviations)
- aliases: common abbreviations and alternative names (English)
- table_role: one of [fact, dim, bridge, log, agg]
- grain: what one row represents (e.g. "按用户、日期聚合")
- subject_area: one of [user, order, product, payment, content, traffic, system, other]
- ai_confidence: 0-1 confidence score

For each column:
- ai_description: 1 sentence about the business meaning
- semantic_tags: 1-3 tags
- business_terms: 1-3 searchable terms
- aliases: abbreviations (e.g. feat_id for feature_id)
- column_role: one of [dimension, measure, time, id, status]
- metric_type: one of [count, amount, rate, duration] if column_role=measure, else null
- ai_confidence: 0-1

Table context:
{context}

Return JSON:
{{"tables": [{{"name": "...", "ai_description": "...", ...}}]}}"""


def _call_llm(prompt: str, *, provider: str, model: str) -> str:
    """Call the configured LLM provider. Extend this for additional providers."""
    if provider == "aliyun":
        return _call_aliyun_llm(prompt, model=model)
    raise ValueError(f"Unknown LLM provider: {provider}")


def _call_aliyun_llm(prompt: str, *, model: str) -> str:
    """Call Aliyun (Qwen) via OpenAI-compatible API."""
    import os
    from openai import OpenAI

    client = OpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY", ""),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=4096,
    )
    content = response.choices[0].message.content
    # Strip markdown code fences if present
    if content and content.startswith("```"):
        lines = content.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        content = "\n".join(lines)
    return content or "{}"


def _validate_enrich_result(result: dict[str, Any], expected_table_names: list[str]) -> None:
    """Validate LLM output structure. Raises ValueError on mismatch."""
    tables = result.get("tables")
    if not isinstance(tables, list) or len(tables) == 0:
        raise ValueError("AI result missing 'tables' array")
    returned_names = {t.get("name") for t in tables if isinstance(t, dict)}
    missing = set(expected_table_names) - returned_names
    if missing:
        raise ValueError(f"AI result missing tables: {missing}")
```

- [ ] **Step 2: Verify module imports**

Run: `python -c "from engine.ai_index import enrich_tables_batch; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add engine/ai_index.py
git commit -m "feat: add LLM batch enrichment function to ai_index"
```

---

## Phase 2: Track 2 — Catalog Refresh Integration

### Task 11: Add AI enrich phase to schema.refresh_catalog

**Files:**
- Modify: `engine/schema_sync.py` (or wherever `refresh_catalog` / `sync_schema` lives)

- [ ] **Step 1: Locate refresh_catalog**

Read the current `sync_schema` / `refresh_catalog` implementation:

```bash
grep -rn "def sync_schema\|def refresh_catalog" engine/
```

- [ ] **Step 2: Add AI enrich function**

Add to the same file (or a new `engine/ai_enrich.py` if you prefer separation):

```python
# engine/ai_enrich.py (or appended to schema_sync.py)
"""AI schema enrichment — called from schema.refresh_catalog with ai_enrich=True."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session as OrmSession

from engine.ai_index import (
    build_column_search_text,
    build_table_search_text,
    compute_schema_hash,
    enrich_tables_batch,
)
from engine.models import SchemaColumn, SchemaSearchDoc, SchemaTable

logger = logging.getLogger("databox.ai_enrich")

AI_LLM_TABLE_BATCH = 50
AI_LLM_BATCH_INTERVAL_MS = 200


def ai_enrich_catalog(
    db: OrmSession,
    datasource_id: str,
    *,
    table_batch: int = AI_LLM_TABLE_BATCH,
) -> dict[str, Any]:
    """Run AI enrichment on all changed tables for a datasource.

    Returns {"ai_enriched": bool, "enriched_count": int, "reason": str}
    """
    tables = (
        db.query(SchemaTable)
        .filter(SchemaTable.data_source_id == datasource_id)
        .order_by(SchemaTable.table_schema, SchemaTable.table_name)
        .all()
    )

    # 1. Incremental detection via schema_hash
    changed: list[SchemaTable] = []
    for t in tables:
        current_hash = compute_schema_hash(t)
        if current_hash != t.schema_hash:
            changed.append(t)

    if not changed:
        return {"ai_enriched": False, "enriched_count": 0, "reason": "no structural changes"}

    # 2. Batch LLM enrichment
    enriched_count = 0
    for i in range(0, len(changed), table_batch):
        batch = changed[i : i + table_batch]
        context = _build_table_context(db, batch)

        try:
            ai_result = enrich_tables_batch(context)
        except Exception as exc:
            logger.exception("AI enrich batch %d failed: %s", i // table_batch, exc)
            continue

        _write_ai_metadata(db, batch, ai_result)
        _rebuild_search_docs(db, datasource_id, batch, ai_result)
        _update_schema_hashes(batch, ai_result)

        enriched_count += len(batch)
        if i + table_batch < len(changed):
            time.sleep(AI_LLM_BATCH_INTERVAL_MS / 1000)

    # 3. Cleanup orphan search docs (tables dropped from source)
    _clean_orphan_search_docs(db, datasource_id)

    db.commit()
    return {"ai_enriched": True, "enriched_count": enriched_count, "reason": ""}


def _build_table_context(db: OrmSession, tables: list[SchemaTable]) -> list[dict[str, Any]]:
    """Build LLM input context for a batch of tables."""
    result: list[dict[str, Any]] = []
    for table in tables:
        columns = sorted(
            list(table.columns or []),
            key=lambda c: (c.ordinal_position or 0, str(c.column_name)),
        )
        result.append({
            "name": str(table.table_name),
            "comment": str(table.table_comment or ""),
            "columns": [
                {
                    "name": str(c.column_name),
                    "type": str(c.column_type or c.data_type or ""),
                    "comment": str(c.column_comment or ""),
                    "is_pk": bool(c.is_primary_key),
                    "is_fk": bool(c.is_foreign_key),
                }
                for c in columns
            ],
            "related_tables": sorted(_connected_table_names(db, table)),
        })
    return result


def _write_ai_metadata(db: OrmSession, tables: list[SchemaTable], ai_result: dict[str, Any]) -> None:
    """Write AI-generated metadata back to SchemaTable and SchemaColumn."""
    now = datetime.now(timezone.utc)
    ai_tables = {t["name"]: t for t in ai_result.get("tables", []) if isinstance(t, dict)}

    for table in tables:
        ai = ai_tables.get(str(table.table_name))
        if not ai:
            continue

        table.ai_description = str(ai.get("ai_description") or "") or None
        table.semantic_tags = json.dumps(ai.get("semantic_tags") or [], ensure_ascii=False)
        table.business_terms = json.dumps(ai.get("business_terms") or [], ensure_ascii=False)
        table.aliases = json.dumps(ai.get("aliases") or [], ensure_ascii=False)
        table.table_role = str(ai.get("table_role") or "") or None
        table.grain = str(ai.get("grain") or "") or None
        table.subject_area = str(ai.get("subject_area") or "") or None
        table.ai_confidence = float(ai.get("ai_confidence", 0))
        table.ai_enriched_at = now

        ai_cols = {c["name"]: c for c in ai.get("columns", []) if isinstance(c, dict)}
        for col in table.columns or []:
            ac = ai_cols.get(str(col.column_name))
            if not ac:
                continue
            col.ai_description = str(ac.get("ai_description") or "") or None
            col.semantic_tags = json.dumps(ac.get("semantic_tags") or [], ensure_ascii=False)
            col.business_terms = json.dumps(ac.get("business_terms") or [], ensure_ascii=False)
            col.aliases = json.dumps(ac.get("aliases") or [], ensure_ascii=False)
            col.column_role = str(ac.get("column_role") or "") or None
            col.metric_type = str(ac.get("metric_type") or "") if ac.get("metric_type") else None
            col.is_pii = False
            col.ai_confidence = float(ac.get("ai_confidence", 0))
            col.ai_enriched_at = now


def _rebuild_search_docs(
    db: OrmSession,
    datasource_id: str,
    tables: list[SchemaTable],
    ai_result: dict[str, Any],
) -> None:
    """Rebuild schema_search_docs rows for a batch of tables."""
    from engine.ai_index import build_column_search_text, build_table_search_text

    now = datetime.now(timezone.utc)
    ai_tables = {t["name"]: t for t in ai_result.get("tables", []) if isinstance(t, dict)}

    # Delete existing rows for these tables
    table_names = [str(t.table_name) for t in tables]
    if table_names:
        db.query(SchemaSearchDoc).filter(
            SchemaSearchDoc.datasource_id == datasource_id,
            SchemaSearchDoc.table_name.in_(table_names),
        ).delete(synchronize_session=False)

    for table in tables:
        ai = ai_tables.get(str(table.table_name))
        tags = ai.get("semantic_tags") if ai else []
        terms = ai.get("business_terms") if ai else []
        aliases = ai.get("aliases") if ai else []
        role = ai.get("table_role") if ai else None
        grain = ai.get("grain") if ai else None
        desc = ai.get("ai_description") if ai else None
        confidence = float(ai.get("ai_confidence", 0)) if ai else None
        cols = sorted(list(table.columns or []), key=lambda c: (c.ordinal_position or 0, str(c.column_name)))

        col_names = [str(c.column_name) for c in cols]
        col_descs = {str(c.column_name): c.ai_description for c in cols if c.ai_description}

        relation_text = ", ".join(sorted(_connected_table_names(db, table))) or None

        search_text = build_table_search_text(
            table_name=str(table.table_name),
            ai_description=desc,
            semantic_tags=tags if isinstance(tags, list) else None,
            business_terms=terms if isinstance(terms, list) else None,
            aliases=aliases if isinstance(aliases, list) else None,
            table_role=role,
            grain=grain,
            column_names=col_names,
            column_ai_descriptions=col_descs,
            relation_text=relation_text,
        )

        db.add(SchemaSearchDoc(
            datasource_id=datasource_id,
            entity_type="table",
            entity_id=str(table.id),
            table_name=str(table.table_name),
            column_name=None,
            name=str(table.table_name),
            ai_description=desc,
            semantic_tags=json.dumps(tags, ensure_ascii=False) if tags else None,
            business_terms=json.dumps(terms, ensure_ascii=False) if terms else None,
            aliases=json.dumps(aliases, ensure_ascii=False) if aliases else None,
            table_role=role,
            grain=grain,
            subject_area=ai.get("subject_area") if ai else None,
            column_summary=", ".join(col_names),
            relation_summary=relation_text,
            search_text=search_text,
            ai_confidence=confidence,
            updated_at=now,
        ))

        # Column-level docs
        ai_cols = {c["name"]: c for c in (ai.get("columns") or []) if isinstance(c, dict)} if ai else {}
        for col in cols:
            ac = ai_cols.get(str(col.column_name))
            if not ac:
                continue
            ctags = ac.get("semantic_tags")
            cterms = ac.get("business_terms")
            caliases = ac.get("aliases")
            crole = ac.get("column_role")
            cmtype = ac.get("metric_type")
            cdesc = ac.get("ai_description")
            cconf = float(ac.get("ai_confidence", 0))

            col_search_text = build_column_search_text(
                column_name=str(col.column_name),
                table_name=str(table.table_name),
                ai_description=cdesc,
                semantic_tags=ctags if isinstance(ctags, list) else None,
                business_terms=cterms if isinstance(cterms, list) else None,
                column_role=crole,
                metric_type=cmtype,
            )

            db.add(SchemaSearchDoc(
                datasource_id=datasource_id,
                entity_type="column",
                entity_id=str(col.id),
                table_name=str(table.table_name),
                column_name=str(col.column_name),
                name=str(col.column_name),
                ai_description=cdesc,
                semantic_tags=json.dumps(ctags, ensure_ascii=False) if ctags else None,
                business_terms=json.dumps(cterms, ensure_ascii=False) if cterms else None,
                aliases=json.dumps(caliases, ensure_ascii=False) if caliases else None,
                column_role=crole,
                metric_type=cmtype,
                column_summary=None,
                relation_summary=None,
                search_text=col_search_text,
                ai_confidence=cconf,
                updated_at=now,
            ))

    db.flush()


def _update_schema_hashes(tables: list[SchemaTable], ai_result: dict[str, Any]) -> None:
    """Update schema_hash after successful enrichment."""
    for table in tables:
        table.schema_hash = compute_schema_hash(table)


def _clean_orphan_search_docs(db: OrmSession, datasource_id: str) -> None:
    """Remove search docs for tables that no longer exist in catalog."""
    db.execute(
        db.query(SchemaSearchDoc).filter(
            SchemaSearchDoc.datasource_id == datasource_id,
            SchemaSearchDoc.entity_type == "table",
            ~SchemaSearchDoc.table_name.in_(
                db.query(SchemaTable.table_name).filter(
                    SchemaTable.data_source_id == datasource_id,
                )
            ),
        ).delete(synchronize_session=False)
    )
    db.execute(
        db.query(SchemaSearchDoc).filter(
            SchemaSearchDoc.datasource_id == datasource_id,
            SchemaSearchDoc.entity_type == "column",
            ~SchemaSearchDoc.table_name.in_(
                db.query(SchemaTable.table_name).filter(
                    SchemaTable.data_source_id == datasource_id,
                )
            ),
        ).delete(synchronize_session=False)
    )


def _connected_table_names(db: OrmSession, table: SchemaTable) -> set[str]:
    """Get FK-connected table names."""
    connected: set[str] = set()
    for col in table.columns or []:
        if col.is_foreign_key and col.foreign_table_id:
            target = db.query(SchemaTable).filter(SchemaTable.id == col.foreign_table_id).first()
            if target:
                connected.add(str(target.table_name))
    return connected
```

- [ ] **Step 2: Wire ai_enrich into the existing refresh_catalog**

In the file that contains the `refresh_catalog` or `sync_schema` function, add the AI enrich call at the end:

```python
# At end of the existing sync_schema / refresh_catalog function:
if ai_enrich:
    from engine.ai_enrich import ai_enrich_catalog
    enrich_result = ai_enrich_catalog(db, datasource_id)
    logger.info("AI enrich: %s", enrich_result)
```

- [ ] **Step 3: Create FTS5 table on startup**

In the function that handles app startup / DB initialization, add:

```python
from engine.models import FTS5_DDL
from sqlalchemy import text

# After all tables are created:
try:
    db.execute(text("SELECT 1 FROM schema_search_fts LIMIT 0"))
except Exception:
    db.execute(text(FTS5_DDL))
    db.commit()
```

- [ ] **Step 4: Commit**

```bash
git add engine/ai_enrich.py engine/models.py
git commit -m "feat: add AI enrich phase to refresh_catalog with search_docs + FTS5"
```

---

## Phase 2: Track 2 — db.search Refactor

### Task 12: Refactor db.search to use FTS with keyword fallback

**Files:**
- Modify: `engine/tools/db_tools.py:123-167`

- [ ] **Step 1: Add FTS search function**

After the existing imports in `engine/tools/db_tools.py`, add:

```python
from engine.ai_index import tokenize_query
from engine.models import SchemaSearchDoc
```

- [ ] **Step 2: Rewrite db_search with FTS path + fallback**

Replace the `db_search` function body (lines 136-166) with:

```python
def db_search(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Search tables and columns via FTS5 when AI-enriched; fallback to keyword otherwise."""
    start = time.perf_counter()
    query = str(args.get("query") or ctx.request.question or "").strip()
    limit = _clamp(int(args.get("limit", DEFAULT_SEARCH_LIMIT) or DEFAULT_SEARCH_LIMIT), 1, 50)

    # Check if AI enrichment has run (schema_search_docs exists)
    has_docs = (
        ctx.db.query(SchemaSearchDoc)
        .filter(SchemaSearchDoc.datasource_id == ctx.request.datasource_id)
        .first()
        is not None
    )

    if has_docs:
        results = _fts_search(ctx.db, ctx.request.datasource_id, query, limit)
    else:
        results = _fallback_keyword_search(ctx, query, limit)

    output = {
        "query": query,
        "results": results,
        "total_matches": len(results),
    }
    return _success("db.search", args, output, start)
```

- [ ] **Step 3: Add _fts_search implementation**

Add before `db_search`:

```python
def _fts_search(db: Session, datasource_id: str, query: str, limit: int) -> list[dict[str, Any]]:
    """FTS5-based search using AI-enriched schema_search_docs."""
    from sqlalchemy import text as sa_text

    tokens = tokenize_query(query)
    if not tokens:
        return []

    # Build FTS5 query: exact phrases + OR tokens
    exact_parts = [f'"{t}"' for t in tokens if len(t) >= 2]
    token_parts = [t for t in tokens if len(t) >= 2]
    fts_query = " OR ".join(exact_parts + token_parts)

    # FTS5 recall
    sql = sa_text("""
        SELECT d.*, fts.rank
        FROM schema_search_fts fts
        JOIN schema_search_docs d ON d.id = fts.rowid
        WHERE fts MATCH :q AND d.datasource_id = :ds_id
        ORDER BY fts.rank
        LIMIT :lim
    """)
    rows = db.execute(sql, {"q": fts_query, "ds_id": datasource_id, "lim": limit * 3}).fetchall()

    # Score and group
    results: list[dict[str, Any]] = []
    seen_tables: set[str] = set()
    for row in rows:
        item = _row_to_search_result(row, tokens, query)
        if item is None:
            continue
        if item["type"] == "table":
            if item["table_name"] in seen_tables:
                continue
            seen_tables.add(item["table_name"])
        results.append(item)

    results.sort(key=lambda r: (-float(r["score"]), r["type"], r["name"]))
    return results[:limit]


def _row_to_search_result(row, tokens: list[str], query: str) -> dict[str, Any] | None:
    """Convert a schema_search_docs row to a search result dict with scoring."""
    entity_type = str(getattr(row, "entity_type", "table") or "table")
    score = _compute_total_score(row, tokens, query)
    if score <= 0:
        return None

    import json as _json

    item: dict[str, Any] = {
        "type": entity_type,
        "name": str(getattr(row, "name", "")),
        "table_name": str(getattr(row, "table_name", "")),
        "score": round(score, 3),
        "reasons": _compute_reasons(row, tokens),
    }

    if entity_type == "table":
        item["ai_description"] = str(getattr(row, "ai_description", "") or "")
        item["table_role"] = str(getattr(row, "table_role", "") or "")

        try:
            item["semantic_tags"] = _json.loads(getattr(row, "semantic_tags", "[]") or "[]")
        except (json.JSONDecodeError, TypeError):
            item["semantic_tags"] = []

    if entity_type == "column":
        item["column_name"] = str(getattr(row, "column_name", ""))
        item["column_role"] = str(getattr(row, "column_role", "") or "")
        item["metric_type"] = str(getattr(row, "metric_type", "") or "")

    return item


def _compute_total_score(row, tokens: list[str], query: str) -> float:
    """Compute unified total_score from exact alias, business term, field match, description, structure, usage."""
    aliases_raw = str(getattr(row, "aliases", "") or "")
    terms_raw = str(getattr(row, "business_terms", "") or "")
    tags_raw = str(getattr(row, "semantic_tags", "") or "")
    desc_raw = str(getattr(row, "ai_description", "") or "")
    name_raw = str(getattr(row, "name", "") or "")

    query_lower = query.lower()
    haystack = f"{aliases_raw} {terms_raw} {tags_raw} {desc_raw} {name_raw}".lower()

    # exact_alias_match (0 or 1)
    exact_alias = 0.0
    for token in tokens:
        if token.lower() in aliases_raw.lower():
            exact_alias = 1.0
            break
    if not exact_alias:
        for token in tokens:
            if token.lower() == name_raw.lower() or name_raw.lower().endswith(f".{token.lower()}"):
                exact_alias = 1.0
                break

    # business_term_match (coverage ratio)
    all_terms = terms_raw.lower().split()
    if all_terms:
        hits = sum(1 for t in all_terms if any(tok.lower() in t for tok in tokens))
        term_score = hits / len(all_terms) if all_terms else 0
    else:
        term_score = 0.0

    # field_name_match (token coverage in search_text)
    search_text = str(getattr(row, "search_text", "") or "").lower()
    if tokens:
        hits = sum(1 for tok in tokens if tok.lower() in search_text)
        field_score = hits / len(tokens)
    else:
        field_score = 0.0

    # ai_description_match (normalized token hits in description)
    desc_lower = desc_raw.lower()
    if tokens and desc_lower:
        hits = sum(1 for tok in tokens if tok.lower() in desc_lower)
        desc_score = hits / len(tokens)
    else:
        desc_score = 0.0

    # structure_boost
    column_role = str(getattr(row, "column_role", "") or "")
    metric_type = str(getattr(row, "metric_type", "") or "")
    struct_score = 0.0
    if column_role == "time":
        struct_score += 0.3
    if column_role == "measure" or metric_type:
        struct_score += 0.3
    if column_role == "dimension":
        struct_score += 0.2

    # usage_boost — placeholder (future: history hits)
    usage_score = 0.0

    total = (
        exact_alias * 0.25
        + term_score * 0.25
        + field_score * 0.20
        + desc_score * 0.15
        + min(struct_score, 1.0) * 0.10
        + usage_score * 0.05
    )
    return total * 100


def _compute_reasons(row, tokens: list[str]) -> list[str]:
    """Generate human-readable reasons for the match."""
    reasons: list[str] = []
    name = str(getattr(row, "name", "") or "")
    aliases = str(getattr(row, "aliases", "") or "")
    terms = str(getattr(row, "business_terms", "") or "")
    table_name = str(getattr(row, "table_name", "") or "")

    for token in tokens:
        tl = token.lower()
        if tl == name.lower() or name.lower().endswith(f".{tl}"):
            reasons.append(f"精确名称命中: {token}")
        elif tl in aliases.lower():
            reasons.append(f"别名命中: {token}")
        elif tl in terms.lower():
            reasons.append(f"业务词命中: {token}")

    col_role = str(getattr(row, "column_role", "") or "")
    m_type = str(getattr(row, "metric_type", "") or "")
    if col_role == "time":
        reasons.append("时间字段加权")
    if m_type:
        reasons.append("指标字段加权")
    if table_name and any(tok.lower() in table_name.lower() for tok in tokens):
        reasons.append("表名命中")

    return reasons[:6]
```

- [ ] **Step 4: Add _fallback_keyword_search (existing logic stripped of bootstrap)**

```python
def _fallback_keyword_search(ctx: ToolContext, query: str, limit: int) -> list[dict[str, Any]]:
    """Fallback keyword search: table/column name + comment match, no AI tags, no bootstrap synonyms."""
    tables = _catalog_tables(ctx.db, ctx.request.datasource_id)

    results: list[dict[str, Any]] = []
    query_lower = query.lower()
    for table in tables:
        tname = str(table.table_name).lower()
        tcomment = str(table.table_comment or "").lower()
        if query_lower in tname or query_lower in tcomment:
            results.append({
                "type": "table",
                "name": str(table.table_name),
                "table_name": str(table.table_name),
                "score": 0.5 if query_lower in tname else 0.3,
                "reasons": ["名称匹配" if query_lower in tname else "注释匹配"],
                "columns": [str(c.column_name) for c in _ordered_columns(table)][:8],
            })
        for col in _ordered_columns(table):
            cname = str(col.column_name).lower()
            ccomment = str(col.column_comment or "").lower()
            if query_lower in cname or query_lower in ccomment:
                results.append({
                    "type": "column",
                    "name": f"{table.table_name}.{col.column_name}",
                    "table_name": str(table.table_name),
                    "column_name": str(col.column_name),
                    "score": 0.4 if query_lower in cname else 0.2,
                    "reasons": ["字段名匹配" if query_lower in cname else "字段注释匹配"],
                })

    results.sort(key=lambda r: (-float(r["score"]), r["type"], r["name"]))
    return results[:limit]
```

- [ ] **Step 5: Run existing db_tools tests**

```bash
cd engine && python -m pytest tests/test_db_tools.py -x -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add engine/tools/db_tools.py
git commit -m "feat: refactor db.search with FTS5 path and keyword fallback"
```

---

## Phase 2: Track 2 — Bootstrap Cleanup

### Task 13: Delete _BOOTSTRAP_SYNONYMS and all bootstrap code

**Files:**
- Modify: `engine/tools/db_tools.py`

- [ ] **Step 1: Delete _BOOTSTRAP_SYNONYMS constant**

Delete lines 40-63 in `db_tools.py` (the entire `_BOOTSTRAP_SYNONYMS` dict).

- [ ] **Step 2: Delete _bootstrap_synonyms function**

Delete lines 1610-1621 (the entire `_bootstrap_synonyms` function).

- [ ] **Step 3: Remove bootstrap fallback from _expanded_terms**

In `_expanded_terms` (currently around line 512), remove lines 519-523 (the entire `for phrase, defaults in _BOOTSTRAP_SYNONYMS.items():` block).

Result after removal:

```python
def _expanded_terms(query: str, synonyms: dict[str, list[str]]) -> list[str]:
    terms: list[str] = []
    normalized_query = query.lower()
    for token in TOKEN_RE.findall(normalized_query):
        terms.append(token)
        for syn in synonyms.get(token, []):
            terms.append(syn)
    # dedup preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for t in terms:
        if t and t not in seen:
            seen.add(t)
            deduped.append(t)
    return deduped
```

- [ ] **Step 4: Simplify _load_synonyms — no bootstrap check**

Replace `_load_synonyms` (currently lines 1571-1607) with:

```python
def _load_synonyms(db: Session, datasource_id: str) -> dict[str, list[str]]:
    """Return synonym map from SemanticAlias (no bootstrap fallback)."""
    rows = (
        db.query(SemanticAlias)
        .filter(
            SemanticAlias.data_source_id == datasource_id,
            SemanticAlias.target_type.in_(("synonym", "table", "column")),
        )
        .all()
    )
    result: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        alias = str(r.alias).strip().lower()
        target = str(r.target).strip().lower()
        if r.target_type == "synonym":
            result[alias].append(target)
        elif r.target_type in ("table", "column"):
            result[target].append(alias)
    return dict(result)
```

- [ ] **Step 5: Delete bootstrap migration SQL**

If your migration script runs `DELETE FROM semantic_aliases WHERE description = 'Bootstrapped default'`, keep that line. The code-side bootstrap is now fully removed.

- [ ] **Step 6: Run tests**

```bash
cd engine && python -m pytest tests/test_db_tools.py -x -q
```

Expected: PASS (no test should reference `_BOOTSTRAP_SYNONYMS`).

- [ ] **Step 7: Commit**

```bash
git add engine/tools/db_tools.py
git commit -m "refactor: remove _BOOTSTRAP_SYNONYMS hardcoded aliases"
```

---

## Phase 3: Test Coverage

### Task 14: Add backend tests for tool_contract

**Files:**
- Create: `engine/tests/test_tool_contract.py`

- [ ] **Step 1: Write the test file**

```python
# engine/tests/test_tool_contract.py
"""Verify every registered tool has a valid state contract."""

from __future__ import annotations

import pytest
from engine.agent_core.tool_contract import TOOL_CONTRACTS, get_contract, ToolStateContract
from engine.agent_core.databinding import apply_tool_result_to_state, TOOL_STATE_APPLIERS
from engine.agent_core.types import ToolObservation


# ── Every tool handler must have a matching contract ──

def test_all_handlers_have_contracts():
    """Every tool with a state applier must be in TOOL_CONTRACTS."""
    unregistered = []
    for tool_name in TOOL_STATE_APPLIERS:
        if tool_name not in TOOL_CONTRACTS and not tool_name.startswith("workspace."):
            unregistered.append(tool_name)
    assert unregistered == [], f"Tools without contracts: {unregistered}"


# ── Contracts for db.* tools with side effects must clear error state on success ──

REQUIRE_ERROR_CLEAR = {"db.query", "db.preview", "db.inspect"}


def test_db_tools_clear_error_on_success():
    for name in REQUIRE_ERROR_CLEAR:
        contract = TOOL_CONTRACTS.get(name)
        assert contract is not None, f"No contract for {name}"
        assert "error" in contract.on_success_clear, (
            f"{name} must clear 'error' on success"
        )


# ── Success path clears error, failure path does not ──

def test_success_clears_error_via_contract():
    state: dict = {"error": "old error", "last_error_telemetry": {"old": True}}
    obs = ToolObservation(
        name="query_database", status="success",
        input={"sql": "SELECT 1"}, output={"rows": [], "status": "success"},
        error=None, latency_ms=10,
    )
    update = apply_tool_result_to_state(state=state, tool_name="db.query", observation=obs)
    assert update.get("error") is None
    assert update.get("last_error_telemetry") is None


def test_failure_preserves_error():
    state: dict = {"pending_tool_call": {"tool_name": "db.query", "args": {}}}
    obs = ToolObservation(
        name="query_database", status="failed",
        input={"sql": "SELECT bad"}, output={"status": "blocked"},
        error="TrustGate Error", latency_ms=10,
    )
    update = apply_tool_result_to_state(state=state, tool_name="db.query", observation=obs)
    # failed path: error is written by _apply_failed_telemetry
    assert update.get("last_error_telemetry") is not None


# ── merge_strategy is always injected ──

def test_merge_strategy_in_trace_events():
    obs = ToolObservation(
        name="search", status="success", input={}, output={}, error=None, latency_ms=5,
    )
    update = apply_tool_result_to_state(state={}, tool_name="db.search", observation=obs)
    payload = update["trace_events"][0]["payload"]
    assert payload["_merge_strategy"] == "reuse"


# ── Unregistered tools get safe default ──

def test_unregistered_tool_gets_default_contract():
    contract = get_contract("some.unknown.tool")
    assert isinstance(contract, ToolStateContract)
    assert contract.merge_strategy == "reuse"
    assert contract.emit_artifact is False
    assert contract.on_success_clear == ()
```

- [ ] **Step 2: Run tests**

```bash
cd engine && python -m pytest tests/test_tool_contract.py -v
```

Expected: 6 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add engine/tests/test_tool_contract.py
git commit -m "test: add contract validation and state cleanup tests"
```

---

### Task 15: Add tests for ai_index tokenizer and search_text

**Files:**
- Create: `engine/tests/test_ai_index.py`

- [ ] **Step 1: Write the test file**

```python
# engine/tests/test_ai_index.py
"""Unit tests for ai_index tokenizer and search_text builders."""

from __future__ import annotations

from engine.ai_index import (
    build_column_search_text,
    build_table_search_text,
    compute_schema_hash,
    segment_for_fts,
    tokenize_query,
)


def test_tokenize_query_chinese_english_mixed():
    tokens = tokenize_query("小红书功能使用频率 daily")
    assert "小红书" in tokens or "小红" in tokens
    assert "功能" in tokens
    assert "daily" in tokens


def test_tokenize_query_english_only():
    tokens = tokenize_query("xhs feature usage count")
    assert "xhs" in tokens
    assert "feature" in tokens
    assert "usage" in tokens
    assert "count" in tokens


def test_segment_for_fts_chinese():
    result = segment_for_fts("小红书功能使用频率日统计表")
    # Should have spaces between segmented Chinese words
    assert " " in result
    assert "小红书" in result or "小红" in result


def test_segment_for_fts_preserves_english():
    result = segment_for_fts("xhs_feature_usage_daily")
    assert result == "xhs_feature_usage_daily"


def test_build_table_search_text_includes_all_fields():
    text = build_table_search_text(
        table_name="xhs_feature_usage_daily",
        ai_description="小红书功能使用频率日统计表",
        semantic_tags=["小红书", "功能使用", "频率统计"],
        business_terms=["小红书", "使用频率", "功能模块"],
        aliases=["xhs", "redbook", "feature_usage"],
        table_role="agg",
        grain="按用户、功能、日期聚合",
        column_names=["user_id", "feature_id", "usage_count", "dt"],
        column_ai_descriptions={"usage_count": "功能使用次数", "dt": "统计日期"},
        relation_text="user_id 关联用户表",
    )
    assert "xhs_feature_usage_daily" in text
    assert "功能使用" in text or "功能" in text
    assert "usage_count" in text


def test_build_column_search_text():
    text = build_column_search_text(
        column_name="usage_count",
        table_name="xhs_feature_usage_daily",
        ai_description="功能使用次数",
        semantic_tags=["使用次数", "频率"],
        business_terms=["功能使用频率", "使用次数"],
        column_role="measure",
        metric_type="count",
    )
    assert "usage_count" in text
    assert "xhs_feature_usage_daily" in text
    assert "measure" in text or "指标" in text


def test_compute_schema_hash_detects_change():
    """schema_hash must change when a column is added/removed."""
    class FakeCol:
        def __init__(self, name, ctype, comment=""):
            self.column_name = name
            self.column_type = ctype
            self.data_type = ctype
            self.column_comment = comment

    class FakeTable:
        def __init__(self, name, cols):
            self.table_name = name
            self.columns = cols

    t1 = FakeTable("users", [FakeCol("id", "INT"), FakeCol("name", "VARCHAR")])
    t2 = FakeTable("users", [FakeCol("id", "INT"), FakeCol("name", "VARCHAR"), FakeCol("email", "VARCHAR")])

    h1 = compute_schema_hash(t1)
    h2 = compute_schema_hash(t2)
    assert h1 != h2
```

- [ ] **Step 2: Run tests**

```bash
cd engine && python -m pytest tests/test_ai_index.py -v
```

Expected: 7 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add engine/tests/test_ai_index.py
git commit -m "test: add ai_index tokenizer and search_text tests"
```

---

## Summary

| Phase | Tasks | Description |
|-------|-------|-------------|
| 1 (T1 Backend) | 1–3 | ToolStateContract, databinding refactor, event_mapper pass-through |
| 1 (T1 Frontend) | 4–6 | types.ts extension, agentTimeline.ts refactor, timeline tests |
| 2 (T2 DB) | 7–8 | SchemaTable/Column AI columns, SchemaSearchDoc + FTS5 |
| 2 (T2 AI) | 9–10 | ai_index.py tokenizer + search_text + LLM enrich |
| 2 (T2 Catalog) | 11 | ai_enrich_catalog wired into refresh_catalog |
| 2 (T2 Search) | 12 | db.search FTS path + fallback |
| 2 (T2 Clean) | 13 | Bootstrap deletion |
| 3 (Tests) | 14–15 | tool_contract tests + ai_index tests |

Tracks 1 and 2 are independent — Phase 1 and Phase 2 can execute in parallel. Phase 3 runs after both tracks are complete.
