# Core Flow Hardening P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden DBFox's P0 datasource sync, trusted SQL execution, and agent event flows so the existing product paths become testable, traceable, and resistant to silent contract drift.

**Architecture:** Keep the existing Tauri + React + FastAPI sidecar architecture. Add the smallest explicit contracts on top of current services: one authoritative schema-sync service, structured SQL execution contract metadata on `QueryHistory`, and versioned snake_case agent runtime events with replay fixtures. Avoid broad rewrites; each task adds failing tests first, then minimal implementation, then focused verification.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Alembic, Pydantic, sqlglot, pytest, React 19, TypeScript, Vitest, existing DBFox API clients and Zustand stores.

---

## Scope Check

This plan covers only the P0 hardening slice from `docs/superpowers/specs/2026-07-04-core-flow-hardening-design.md`:

- P0-Preflight: LLM base URL compatibility and DuckDB dependency declaration.
- Flow 1: Datasource connection and schema sync.
- Flow 2: Trusted SQL execution contract.
- Flow 3: Agent event versioning and replay.

This plan does not implement P0.5 artifact-backed result-view hardening, P1 persistent workspace views, or full desktop smoke diagnostics. Those should get separate plans after P0 is green.

## File Structure

### P0 Preflight

- `engine/llm/factory.py`
  - Resolve LLM base URL from explicit arg, `OPENAI_API_BASE`, then `OPENAI_BASE_URL`.
- `engine/ai_index.py`
  - Use the same base URL precedence for AI schema enrichment.
- `.env.example`
  - Document the canonical variable and compatibility alias.
- `requirements.txt`
  - Declare `duckdb` because runtime introspection already imports it.
- `build_sidecar.py`
  - Add `duckdb` to PyInstaller hidden imports.
- `engine/tests/test_llm_config.py`
  - Verify env precedence and alias compatibility.
- `engine/tests/test_schema_introspector.py`
  - Keep existing DuckDB introspection coverage meaningful once dependency is declared.

### Datasource Sync Hardening

- `engine/environment/schema_introspector.py`
  - Stop converting MySQL/PostgreSQL/DuckDB connection failures into empty successful inventories.
- `engine/schema_sync.py`
  - Make `sync_schema()` the authoritative sync service for explicit and auto sync calls.
  - Return structured status fields while preserving existing response keys.
- `engine/api/datasources/schema.py`
  - Call `sync_schema()` instead of `_sync_catalog()` for `/datasources/{id}/sync` and auto-sync.
- `engine/tests/test_schema_sync.py`
  - Add failed-introspection preservation tests for empty-inventory risk.
- `engine/tests/test_datasource_schema_api.py`
  - Add API contract tests for shared sync status semantics.

### Trusted SQL Execution Contract

- `engine/models.py`
  - Add `QueryHistory.execution_contract_json`.
- `engine/migrations/versions/e8f9a0b1c2d3_add_query_execution_contract.py`
  - Add/drop the column using Alembic batch mode.
- `engine/sql/executor.py`
  - Build and persist an execution contract for success and blocked paths.
  - Return the same contract in API responses.
- `engine/sql/result_view/service.py`
  - Pass source type/scope metadata for result-view derived SQL execution.
- `engine/tools/db/sql_execution.py`
  - Pass source type for agent SQL tool execution.
- `engine/tools/db/preview.py`
  - Pass source type for agent preview SQL execution.
- `engine/tests/test_executor.py`
  - Assert persisted and returned execution contract fields.
- `engine/tests/test_sql_execution_architecture.py`
  - Guard against direct dialect executor bypass outside the SQL execution module.

### Agent Event Contract And Replay

- `engine/agent_core/types.py`
  - Add `event_contract_version: int = 1` to `AgentRuntimeEvent`.
- `engine/agent/app/runtime_config.py`
  - Add the same field to the app runtime event type if this legacy model still serializes events.
- `engine/agent_core/persistence/events.py`
  - Ensure persisted `event_json` includes `event_contract_version`.
- `desktop/src/lib/api/types/agent.ts`
  - Add `event_contract_version: number`.
- `docs/contracts/agent_runtime_events_v1.json`
  - Shared v1 replay fixture with approval/resume path.
- `engine/tests/test_agent_runtime_event_contract.py`
  - Validate fixture shape against backend Pydantic model.
- `desktop/src/lib/api/__tests__/agentRuntimeEventContract.test.ts`
  - Replay the shared fixture through `reduceAgentRuntimeEvent()`.

## Task 1: P0 Preflight Compatibility

**Files:**
- Modify: `engine/llm/factory.py`
- Modify: `engine/ai_index.py`
- Modify: `.env.example`
- Modify: `requirements.txt`
- Modify: `build_sidecar.py`
- Test: `engine/tests/test_llm_config.py`
- Test: `engine/tests/test_schema_introspector.py`

- [ ] **Step 1: Write failing LLM base URL tests**

Create `engine/tests/test_llm_config.py`:

```python
from __future__ import annotations

from typing import Any

import engine.llm.factory as factory


def test_get_chat_model_uses_openai_api_base_before_base_url(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_create_openai_client(**kwargs: Any) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(factory, "create_openai_client", fake_create_openai_client)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_API_BASE", "https://api-base.example/v1")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://base-url.example/v1")

    factory.get_chat_model()

    assert captured["api_base"] == "https://api-base.example/v1"


def test_get_chat_model_accepts_openai_base_url_alias(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_create_openai_client(**kwargs: Any) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(factory, "create_openai_client", fake_create_openai_client)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://base-url.example/v1")

    factory.get_chat_model()

    assert captured["api_base"] == "https://base-url.example/v1"
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
pytest engine/tests/test_llm_config.py -q
```

Expected: the alias test fails because `engine/llm/factory.py` does not read `OPENAI_BASE_URL`.

- [ ] **Step 3: Implement shared base URL fallback in LLM factory**

In `engine/llm/factory.py`, add:

```python
def resolve_openai_api_base(explicit: str | None = None) -> str:
    raw_base = (
        explicit
        or os.environ.get("OPENAI_API_BASE")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    )
    return raw_base.strip()
```

Then replace:

```python
raw_base = api_base or os.environ.get("OPENAI_API_BASE") or "https://api.openai.com/v1"
base = raw_base.strip()
```

with:

```python
base = resolve_openai_api_base(api_base)
```

- [ ] **Step 4: Use the same fallback in AI enrichment/search**

In `engine/ai_index.py`, replace any direct fallback chain that reads only `OPENAI_API_BASE` with:

```python
from engine.llm.factory import resolve_openai_api_base

api_base = resolve_openai_api_base(api_base)
```

Keep existing explicit `api_base` precedence.

- [ ] **Step 5: Declare DuckDB support**

In `requirements.txt`, add:

```text
duckdb>=1.1.0
```

In `build_sidecar.py`, add to `HIDDEN_IMPORTS`:

```python
"duckdb",
```

In `.env.example`, document both names with a canonical note:

```text
# OPENAI_API_BASE is the canonical OpenAI-compatible endpoint variable.
# OPENAI_BASE_URL is accepted as a compatibility alias.
# OPENAI_API_BASE=https://api.openai.com/v1
# OPENAI_BASE_URL=https://api.openai.com/v1
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
pytest engine/tests/test_llm_config.py engine/tests/test_schema_introspector.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add .env.example requirements.txt build_sidecar.py engine/llm/factory.py engine/ai_index.py engine/tests/test_llm_config.py
git commit -m "fix: normalize llm base url and duckdb support"
```

## Task 2: Authoritative Datasource Sync Service

**Files:**
- Modify: `engine/environment/schema_introspector.py`
- Modify: `engine/schema_sync.py`
- Modify: `engine/api/datasources/schema.py`
- Test: `engine/tests/test_schema_sync.py`
- Test: `engine/tests/test_datasource_schema_api.py`

- [ ] **Step 1: Add failing sync preservation tests for connection failures**

Append to `engine/tests/test_schema_sync.py`:

```python
from engine.environment.models import SchemaInventory


def test_mysql_connection_failure_does_not_clear_existing_catalog(db_session, test_datasource, monkeypatch) -> None:
    sync_schema(db_session, test_datasource.id)
    initial_tables = db_session.query(SchemaTable).filter(SchemaTable.data_source_id == test_datasource.id).count()

    test_datasource.db_type = "mysql"
    test_datasource.host = "127.0.0.1"
    test_datasource.port = 3306
    test_datasource.database_name = "dbfox_test"
    db_session.commit()

    def fake_empty_inventory(_db, datasource_id: str) -> SchemaInventory:
        return SchemaInventory(datasource_id=datasource_id, dialect="mysql", database_name="dbfox_test")

    monkeypatch.setattr("engine.environment.schema_catalog_sync.introspect_datasource", fake_empty_inventory)

    with pytest.raises(ValueError, match="Schema sync failed"):
        sync_schema(db_session, test_datasource.id)

    assert db_session.query(SchemaTable).filter(SchemaTable.data_source_id == test_datasource.id).count() == initial_tables
    db_session.refresh(test_datasource)
    assert test_datasource.last_sync_status == "failed"
    assert "empty inventory" in (test_datasource.last_sync_error or "").lower()
```

Add a genuine empty schema test:

```python
def test_successful_empty_inventory_marks_success_when_allowed(db_session, test_datasource, monkeypatch) -> None:
    test_datasource.db_type = "sqlite"
    db_session.commit()

    def fake_empty_inventory(_db, datasource_id: str) -> SchemaInventory:
        inventory = SchemaInventory(datasource_id=datasource_id, dialect="sqlite", database_name="empty.db")
        inventory.introspection_status = "success"
        return inventory

    monkeypatch.setattr("engine.environment.schema_catalog_sync.introspect_datasource", fake_empty_inventory)

    result = sync_schema(db_session, test_datasource.id)

    assert result["ok"] is True
    db_session.refresh(test_datasource)
    assert test_datasource.last_sync_status == "success"
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
pytest engine/tests/test_schema_sync.py -q
```

Expected: the failed empty-inventory test fails because empty inventory currently syncs as a successful removal set.

- [ ] **Step 3: Add explicit inventory status fields**

In `engine/environment/models.py`, add fields to `SchemaInventory`:

```python
introspection_status: Literal["success", "failed"] = "success"
introspection_error: str | None = None
```

Use existing typing imports in that file; add `Literal` if missing.

- [ ] **Step 4: Raise on connection failures instead of returning empty inventories**

In `engine/environment/schema_introspector.py`, replace MySQL/PostgreSQL/DuckDB connection-failure returns with exceptions:

```python
except Exception as exc:
    logger.warning("MySQL connect failed for %s: %s", resolved.datasource_id, exc)
    raise DataSourceConnectionError(f"MySQL connection failed: {public_message(exc)}") from exc
```

Use the same pattern for PostgreSQL and DuckDB. Import:

```python
from engine.app.errors import public_message
from engine.errors import DataSourceConnectionError
```

Keep SQLite missing-file behavior aligned with `sync_schema()` path validation; if direct catalog sync can reach SQLite without wrapper validation, raise `DataSourceConnectionError` for a missing file there too.

- [ ] **Step 5: Guard `sync_schema()` against failed empty inventories**

In `engine/schema_sync.py`, after `result = ensure_catalog(...)`, validate:

```python
if getattr(result, "introspection_status", "success") == "failed":
    raise DataSourceConnectionError(getattr(result, "introspection_error", None) or "Schema introspection failed")
```

If `SyncResult` does not yet carry those fields, update `engine/environment/models.py`:

```python
introspection_status: str = "success"
introspection_error: str | None = None
```

and copy them from inventory in `SchemaCatalogSync.sync_inventory()`.

- [ ] **Step 6: Route API sync through `sync_schema()`**

In `engine/api/datasources/schema.py`, replace `_sync_catalog(...)` in `api_sync_schema()` with:

```python
from engine.schema_sync import sync_schema

response = sync_schema(
    db,
    id,
    ai_enrich=payload.ai_enrich,
    ai_api_key=payload.api_key,
    ai_api_base=payload.api_base,
    ai_model_name=payload.model_name,
)
return response
```

In `api_list_tables()`, replace auto-sync `_sync_catalog(db, datasource_id)` with:

```python
sync_schema(db, datasource_id, ai_enrich=False)
```

- [ ] **Step 7: Add API test for shared status semantics**

Create `engine/tests/test_datasource_schema_api.py`:

```python
from __future__ import annotations

import pytest

from engine.api.datasources.schema import api_sync_schema, SchemaSyncRequest
from engine.models import SchemaTable
from engine.schema_sync import sync_schema


def test_api_sync_updates_datasource_status(db_session, test_datasource) -> None:
    response = api_sync_schema(test_datasource.id, SchemaSyncRequest(ai_enrich=False), db_session)

    assert response["ok"] is True
    db_session.refresh(test_datasource)
    assert test_datasource.last_sync_status == "success"


def test_api_sync_failure_preserves_catalog_and_status(db_session, test_datasource, monkeypatch) -> None:
    sync_schema(db_session, test_datasource.id)
    initial_tables = db_session.query(SchemaTable).filter(SchemaTable.data_source_id == test_datasource.id).count()

    def fail_sync(*_args, **_kwargs):
        raise ValueError("Schema sync failed: connection refused")

    monkeypatch.setattr("engine.api.datasources.schema.sync_schema", fail_sync)

    with pytest.raises(Exception):
        api_sync_schema(test_datasource.id, SchemaSyncRequest(ai_enrich=False), db_session)

    assert db_session.query(SchemaTable).filter(SchemaTable.data_source_id == test_datasource.id).count() == initial_tables
```

- [ ] **Step 8: Run focused tests**

Run:

```bash
pytest engine/tests/test_schema_sync.py engine/tests/test_datasource_schema_api.py engine/tests/test_schema_introspector.py -q
```

Expected: pass.

- [ ] **Step 9: Commit**

```bash
git add engine/environment/models.py engine/environment/schema_introspector.py engine/schema_sync.py engine/api/datasources/schema.py engine/tests/test_schema_sync.py engine/tests/test_datasource_schema_api.py
git commit -m "fix: preserve schema catalog on sync failure"
```

## Task 3: Trace ID For P0 Flows

**Files:**
- Create: `engine/observability/trace_context.py`
- Modify: `engine/schema_sync.py`
- Modify: `engine/sql/executor.py`
- Modify: `engine/agent_core/types.py`
- Test: `engine/tests/test_trace_contract.py`

- [ ] **Step 1: Write failing trace contract tests**

Create `engine/tests/test_trace_contract.py`:

```python
from __future__ import annotations

from engine.observability.trace_context import make_trace_id, normalize_trace_id


def test_make_trace_id_has_stable_prefix() -> None:
    trace_id = make_trace_id("sync")

    assert trace_id.startswith("sync-")
    assert len(trace_id) > len("sync-")


def test_normalize_trace_id_reuses_valid_value() -> None:
    assert normalize_trace_id("sql", "sql-existing") == "sql-existing"


def test_normalize_trace_id_replaces_blank_value() -> None:
    assert normalize_trace_id("agent", " ") .startswith("agent-")
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```bash
pytest engine/tests/test_trace_contract.py -q
```

Expected: import failure because `engine.observability.trace_context` does not exist.

- [ ] **Step 3: Implement trace helper**

Create `engine/observability/trace_context.py`:

```python
from __future__ import annotations

import re
import uuid

_TRACE_RE = re.compile(r"^[a-z][a-z0-9_-]{1,31}-[A-Za-z0-9_.:-]{4,128}$")


def make_trace_id(prefix: str) -> str:
    safe_prefix = re.sub(r"[^a-z0-9_-]+", "-", prefix.lower()).strip("-") or "trace"
    return f"{safe_prefix}-{uuid.uuid4().hex}"


def normalize_trace_id(prefix: str, trace_id: str | None = None) -> str:
    candidate = str(trace_id or "").strip()
    if candidate and _TRACE_RE.match(candidate):
        return candidate
    return make_trace_id(prefix)
```

- [ ] **Step 4: Add trace ids to P0 return models**

In `engine/schema_sync.py`, create at start of `sync_schema()`:

```python
from engine.observability.trace_context import normalize_trace_id

trace_id = normalize_trace_id("sync")
```

Add `traceId` to success and failure response/error context where currently returning dicts.

In `engine/sql/executor.py`, create at the start of `execute_query()`:

```python
trace_id = normalize_trace_id("sql", execution_id)
```

Add `"traceId": trace_id` to returned success and blocked response dictionaries.

In `engine/agent_core/types.py`, add optional trace id to `AgentRuntimeEvent`:

```python
trace_id: str | None = None
```

Do not require frontend display in this task; only make backend payloads capable of carrying it.

- [ ] **Step 5: Run trace and smoke tests**

Run:

```bash
pytest engine/tests/test_trace_contract.py engine/tests/test_executor.py engine/tests/test_schema_sync.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add engine/observability/trace_context.py engine/schema_sync.py engine/sql/executor.py engine/agent_core/types.py engine/tests/test_trace_contract.py
git commit -m "feat: add trace ids to core flows"
```

## Task 4: SQL Execution Contract Metadata

**Files:**
- Modify: `engine/models.py`
- Create: `engine/migrations/versions/e8f9a0b1c2d3_add_query_execution_contract.py`
- Modify: `engine/sql/executor.py`
- Modify: `engine/sql/result_view/service.py`
- Modify: `engine/tools/db/sql_execution.py`
- Modify: `engine/tools/db/preview.py`
- Test: `engine/tests/test_executor.py`

- [ ] **Step 1: Write failing executor contract tests**

Add to `engine/tests/test_executor.py`:

```python
import json


def test_execute_query_persists_execution_contract(db_session_module, test_datasource_module) -> None:
    sync_schema(db_session_module, test_datasource_module.id)

    res = execute_query(
        db_session_module,
        test_datasource_module.id,
        "SELECT id, username FROM users LIMIT 3",
        question="show users",
    )

    assert res["executionContract"]["source_type"] == "user_sql"
    assert res["executionContract"]["decision_state"] == "allowed"
    assert res["executionContract"]["execution_id"] == res["executionId"]
    assert res["executionContract"]["history_id"] == res["historyId"]

    history = db_session_module.query(QueryHistory).filter(QueryHistory.id == res["historyId"]).first()
    assert history is not None
    contract = json.loads(history.execution_contract_json)
    assert contract["source_type"] == "user_sql"
    assert contract["decision_state"] == "allowed"
    assert contract["history_id"] == res["historyId"]


def test_blocked_query_returns_execution_contract(db_session_module, test_datasource_module) -> None:
    sync_schema(db_session_module, test_datasource_module.id)

    with pytest.raises(GuardrailValidationError) as exc_info:
        execute_query(db_session_module, test_datasource_module.id, "DELETE FROM users")

    assert exc_info.value.public_payload["executionContract"]["decision_state"] == "blocked"
    assert exc_info.value.public_payload["executionContract"]["source_type"] == "user_sql"
```

If `GuardrailValidationError` does not expose `public_payload`, adjust the implementation to add a compatible field or assert the persisted failed `QueryHistory` row instead.

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
pytest engine/tests/test_executor.py -q
```

Expected: failures because `execution_contract_json` and `executionContract` do not exist.

- [ ] **Step 3: Add model and migration**

In `engine/models.py`, add to `QueryHistory`:

```python
execution_contract_json = Column(Text, nullable=True)
```

Create `engine/migrations/versions/e8f9a0b1c2d3_add_query_execution_contract.py`. `python -m alembic heads` currently reports `2b4c6d8e0f12`, so use that as the down revision unless a newer migration has landed by the time this task is executed. If a newer migration has landed, stop and rebase the revision id before editing code.

```python
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, Sequence[str], None] = "2b4c6d8e0f12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("query_history", schema=None) as batch_op:
        batch_op.add_column(sa.Column("execution_contract_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("query_history", schema=None) as batch_op:
        batch_op.drop_column("execution_contract_json")
```

- [ ] **Step 4: Implement contract builder**

In `engine/sql/executor.py`, add:

```python
def _execution_contract(
    *,
    source_type: str,
    decision_state: str,
    policy: str,
    decision_id: str | None,
    execution_id: str,
    history_id: str | None = None,
    artifact_id: str | None = None,
    timings: dict[str, int] | None = None,
    row_count: int = 0,
    column_count: int = 0,
    truncated: bool = False,
    redacted_error: str | None = None,
    trace_id: str | None = None,
) -> dict[str, object | None]:
    return {
        "source_type": source_type,
        "decision_state": decision_state,
        "policy": policy,
        "decision_id": decision_id,
        "history_id": history_id,
        "artifact_id": artifact_id,
        "execution_id": execution_id,
        "timings": timings or {},
        "row_count": row_count,
        "column_count": column_count,
        "truncated": truncated,
        "redacted_error": redacted_error,
        "trace_id": trace_id,
    }
```

Add an `execution_source_type: str = "user_sql"` parameter to `execute_query()` and pass it through to `_run_approved_query()`.

When persisting `QueryHistory`, set:

```python
history.execution_contract_json = json.dumps(contract, ensure_ascii=False)
```

After `_write_query_history()` returns `history_id`, update `contract["history_id"] = history_id` and return:

```python
"executionContract": contract,
```

- [ ] **Step 5: Add source type at existing callers**

In `engine/sql/result_view/service.py`, pass:

```python
execution_source_type=f"result_view.{scope}"
```

where `scope` is already passed to `_result_view_decision()`.

In `engine/tools/db/sql_execution.py`, pass:

```python
execution_source_type="agent_sql"
```

In `engine/tools/db/preview.py`, pass:

```python
execution_source_type="agent_preview"
```

Keep default `"user_sql"` for SQL console/API calls.

- [ ] **Step 6: Run migration and focused tests**

Run:

```bash
alembic upgrade head
pytest engine/tests/test_executor.py engine/tests/test_sql_safety_service.py engine/tests/test_result_view_service.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add engine/models.py engine/migrations/versions engine/sql/executor.py engine/sql/result_view/service.py engine/tools/db/sql_execution.py engine/tools/db/preview.py engine/tests/test_executor.py
git commit -m "feat: persist sql execution contracts"
```

## Task 5: SQL Execution Architecture Guard

**Files:**
- Create: `engine/tests/test_sql_execution_architecture.py`

- [ ] **Step 1: Add architecture guard test**

Create `engine/tests/test_sql_execution_architecture.py`:

```python
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_DIALECT_EXECUTOR_IMPORTERS = {
    Path("sql/executor.py"),
    Path("sql/executor_guardrail_bypass_helper.py"),
}


def test_dialect_executors_are_not_imported_outside_sql_executor() -> None:
    offenders: list[str] = []
    for path in ROOT.rglob("*.py"):
        if "tests" in path.parts:
            continue
        rel = path.relative_to(ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("engine.sql.dialect."):
                imported = {alias.name for alias in node.names}
                if any(name.startswith("_execute_on_") for name in imported) and rel not in ALLOWED_DIALECT_EXECUTOR_IMPORTERS:
                    offenders.append(str(rel))
    assert offenders == []


def test_execute_query_call_sites_use_named_safety_or_source_metadata() -> None:
    offenders: list[str] = []
    for path in ROOT.rglob("*.py"):
        if "tests" in path.parts:
            continue
        rel = path.relative_to(ROOT)
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "execute_query":
                keyword_names = {kw.arg for kw in node.keywords if kw.arg}
                if "execution_source_type" not in keyword_names and rel != Path("sql/executor.py"):
                    offenders.append(f"{rel}:{node.lineno}")
    assert offenders == []
```

- [ ] **Step 2: Run and resolve call sites**

Run:

```bash
pytest engine/tests/test_sql_execution_architecture.py -q
```

Expected: if any `execute_query()` call lacks `execution_source_type`, add the appropriate keyword argument. Keep test-only helpers out of production allowlists.

- [ ] **Step 3: Run related tests**

Run:

```bash
pytest engine/tests/test_sql_execution_architecture.py engine/tests/test_executor.py engine/tests/test_result_view_service.py -q
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add engine/tests/test_sql_execution_architecture.py engine
git commit -m "test: guard trusted sql execution path"
```

## Task 6: Version Agent Runtime Events

**Files:**
- Modify: `engine/agent_core/types.py`
- Modify: `engine/agent/app/runtime_config.py`
- Modify: `engine/agent_core/persistence/events.py`
- Modify: `desktop/src/lib/api/types/agent.ts`
- Test: `engine/tests/test_persistence_sink.py`
- Test: `desktop/src/lib/api/__tests__/agentDraft.test.ts`

- [ ] **Step 1: Add failing backend event version test**

In `engine/tests/test_persistence_sink.py`, add:

```python
def test_runtime_event_payload_includes_contract_version(db_session):
    event = AgentRuntimeEvent(
        event_id="event-version-1",
        run_id="run-version-1",
        sequence=1,
        created_at_ms=1,
        type="agent.run.started",
    )

    payload = event.model_dump(mode="json")

    assert payload["event_contract_version"] == 1
```

- [ ] **Step 2: Add failing frontend type/reducer test**

In `desktop/src/lib/api/__tests__/agentDraft.test.ts`, add:

```typescript
it("accepts v1 snake_case runtime events", () => {
  const event: AgentRuntimeEvent = {
    event_contract_version: 1,
    event_id: "event-v1",
    run_id: "run-v1",
    sequence: 1,
    created_at_ms: 1,
    type: "agent.run.started",
  };

  const next = reduceAgentRuntimeEvent(createAgentRunDraft("question"), event);

  expect(next.events[0].event_contract_version).toBe(1);
});
```

- [ ] **Step 3: Run tests and confirm failure**

Run:

```bash
pytest engine/tests/test_persistence_sink.py -q
cd desktop && npm run test -- --run src/lib/api/__tests__/agentDraft.test.ts
```

Expected: fail because event contract version is missing in Python and TypeScript types.

- [ ] **Step 4: Add `event_contract_version` to backend models**

In `engine/agent_core/types.py`, add to `AgentRuntimeEvent`:

```python
event_contract_version: int = 1
```

In `engine/agent/app/runtime_config.py`, add the same field to its `AgentRuntimeEvent` class:

```python
event_contract_version: int = 1
```

No event type names or field casing change in this task.

- [ ] **Step 5: Add frontend type field**

In `desktop/src/lib/api/types/agent.ts`, add:

```typescript
event_contract_version: number;
```

to `AgentRuntimeEvent`.

If many test factories need updates, add a default in local helper functions rather than weakening the type.

- [ ] **Step 6: Run focused tests**

Run:

```bash
pytest engine/tests/test_persistence_sink.py engine/tests/test_agent_api.py -q
cd desktop && npm run test -- --run src/lib/api/__tests__/agentDraft.test.ts src/features/workspace/__tests__/agentTimeline.test.ts src/stores/__tests__/conversationStore.test.ts
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add engine/agent_core/types.py engine/agent/app/runtime_config.py engine/agent_core/persistence/events.py desktop/src/lib/api/types/agent.ts engine/tests/test_persistence_sink.py desktop/src/lib/api/__tests__/agentDraft.test.ts
git commit -m "feat: version agent runtime events"
```

## Task 7: Shared Agent Replay Fixture

**Files:**
- Create: `docs/contracts/agent_runtime_events_v1.json`
- Create: `engine/tests/test_agent_runtime_event_contract.py`
- Create: `desktop/src/lib/api/__tests__/agentRuntimeEventContract.test.ts`

- [ ] **Step 1: Add shared v1 fixture**

Create `docs/contracts/agent_runtime_events_v1.json`:

```json
[
  {
    "event_contract_version": 1,
    "event_id": "evt-001",
    "run_id": "run-contract",
    "sequence": 1,
    "created_at_ms": 1,
    "type": "agent.run.started",
    "step": {"name": "start", "status": "running"}
  },
  {
    "event_contract_version": 1,
    "event_id": "evt-002",
    "run_id": "run-contract",
    "sequence": 2,
    "created_at_ms": 2,
    "type": "agent.tool.started",
    "step": {"name": "execute_readonly", "tool_name": "db.sql.execute", "status": "running"}
  },
  {
    "event_contract_version": 1,
    "event_id": "evt-003",
    "run_id": "run-contract",
    "sequence": 3,
    "created_at_ms": 3,
    "type": "agent.approval.required",
    "approval": {"id": "approval-1", "status": "pending", "reason": "readonly query approval"}
  },
  {
    "event_contract_version": 1,
    "event_id": "evt-004",
    "run_id": "run-contract",
    "sequence": 4,
    "created_at_ms": 4,
    "type": "agent.run.resumed",
    "approval": {"id": "approval-1", "status": "approved"}
  },
  {
    "event_contract_version": 1,
    "event_id": "evt-005",
    "run_id": "run-contract",
    "sequence": 5,
    "created_at_ms": 5,
    "type": "agent.answer.completed",
    "answer": {"text": "There are 3 matching rows."}
  },
  {
    "event_contract_version": 1,
    "event_id": "evt-006",
    "run_id": "run-contract",
    "sequence": 6,
    "created_at_ms": 6,
    "type": "agent.run.completed",
    "response": {"id": "run-contract", "status": "completed", "final_answer": "There are 3 matching rows."}
  }
]
```

- [ ] **Step 2: Add backend fixture validation**

Create `engine/tests/test_agent_runtime_event_contract.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from engine.agent_core.types import AgentRuntimeEvent


FIXTURE = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "agent_runtime_events_v1.json"


def test_agent_runtime_event_v1_fixture_matches_backend_contract() -> None:
    events = json.loads(FIXTURE.read_text(encoding="utf-8"))
    parsed = [AgentRuntimeEvent.model_validate(event) for event in events]

    assert [event.sequence for event in parsed] == sorted(event.sequence for event in parsed)
    assert {event.event_contract_version for event in parsed} == {1}
    assert parsed[-1].type == "agent.run.completed"
```

- [ ] **Step 3: Add frontend replay test**

Create `desktop/src/lib/api/__tests__/agentRuntimeEventContract.test.ts`:

```typescript
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { createAgentRunDraft, reduceAgentRuntimeEvent } from "../agent";
import type { AgentRuntimeEvent } from "../types";

function loadFixture(): AgentRuntimeEvent[] {
  const here = fileURLToPath(new URL(".", import.meta.url));
  const path = resolve(here, "../../../../../docs/contracts/agent_runtime_events_v1.json");
  return JSON.parse(readFileSync(path, "utf8")) as AgentRuntimeEvent[];
}

it("replays the shared v1 agent runtime event fixture", () => {
  const events = loadFixture();
  const final = events.reduce(
    (draft, event) => reduceAgentRuntimeEvent(draft, event),
    createAgentRunDraft("How many matching rows?")
  );

  expect(final.status).toBe("completed");
  expect(final.events).toHaveLength(events.length);
  expect(final.events.every((event) => event.event_contract_version === 1)).toBe(true);
  expect(final.answer?.text ?? final.response?.final_answer).toContain("3 matching rows");
});
```

- [ ] **Step 4: Run fixture tests**

Run:

```bash
pytest engine/tests/test_agent_runtime_event_contract.py -q
cd desktop && npm run test -- --run src/lib/api/__tests__/agentRuntimeEventContract.test.ts
```

Expected: pass. If the frontend path resolution differs under Vitest, adjust only the path expression and keep the shared JSON fixture location.

- [ ] **Step 5: Commit**

```bash
git add docs/contracts/agent_runtime_events_v1.json engine/tests/test_agent_runtime_event_contract.py desktop/src/lib/api/__tests__/agentRuntimeEventContract.test.ts
git commit -m "test: add agent runtime event replay contract"
```

## Task 8: Final P0 Verification

**Files:**
- No source edits unless verification exposes failures.

- [ ] **Step 1: Run P0 backend suite**

Run:

```bash
pytest engine/tests/test_llm_config.py engine/tests/test_schema_introspector.py engine/tests/test_schema_sync.py engine/tests/test_datasource_schema_api.py engine/tests/test_trace_contract.py engine/tests/test_executor.py engine/tests/test_sql_execution_architecture.py engine/tests/test_result_view_service.py engine/tests/test_agent_api.py engine/tests/test_agent_runtime_event_contract.py engine/tests/test_persistence_sink.py -q
```

Expected: pass.

- [ ] **Step 2: Run P0 frontend suite**

Run:

```bash
cd desktop && npm run test -- --run src/lib/api/__tests__/agentDraft.test.ts src/lib/api/__tests__/agentRuntimeEventContract.test.ts src/features/workspace/__tests__/agentTimeline.test.ts src/stores/__tests__/conversationStore.test.ts
```

Expected: pass.

- [ ] **Step 3: Run type/build gates**

Run:

```bash
mypy engine
cd desktop && npm run lint
cd desktop && npm run build
```

Expected: all commands pass. If `mypy engine` exposes pre-existing ignored-module noise, record the exact failure and run the narrower impacted module check before committing.

- [ ] **Step 4: Review invariants manually**

Confirm each invariant from the spec has a corresponding test:

- failed introspection cannot delete catalog;
- empty inventory requires successful introspection;
- SQL executor cannot be bypassed from other modules;
- SQL result has `execution_id` plus `history_id` or `artifact_id`;
- agent runtime events replay in `(run_id, sequence)` order under v1;
- approval/resume appears in the shared replay fixture;
- diagnostics fields include trace id on P0 outputs.

- [ ] **Step 5: Commit verification fixes only if needed**

If verification produces source changes, run the failed command again, then commit only the fixed files:

```bash
git status --short
git add .env.example requirements.txt build_sidecar.py engine/llm/factory.py engine/ai_index.py engine/environment/models.py engine/environment/schema_introspector.py engine/schema_sync.py engine/api/datasources/schema.py engine/observability/trace_context.py engine/models.py engine/migrations/versions/e8f9a0b1c2d3_add_query_execution_contract.py engine/sql/executor.py engine/sql/result_view/service.py engine/tools/db/sql_execution.py engine/tools/db/preview.py engine/agent_core/types.py engine/agent/app/runtime_config.py engine/agent_core/persistence/events.py desktop/src/lib/api/types/agent.ts docs/contracts/agent_runtime_events_v1.json engine/tests/test_llm_config.py engine/tests/test_schema_sync.py engine/tests/test_datasource_schema_api.py engine/tests/test_trace_contract.py engine/tests/test_executor.py engine/tests/test_sql_execution_architecture.py engine/tests/test_agent_runtime_event_contract.py engine/tests/test_persistence_sink.py desktop/src/lib/api/__tests__/agentDraft.test.ts desktop/src/lib/api/__tests__/agentRuntimeEventContract.test.ts
git commit -m "fix: complete core flow hardening verification"
```

If verification produces no changes, do not create an empty commit.

## Execution Notes

- Do not start P0.5/P1 work until this P0 plan is green.
- Keep `event_contract_version` snake_case for v1.
- Prefer adding one migration for all QueryHistory contract fields in Task 4; do not combine it with unrelated schema changes.
- Keep result-view fingerprint hardening in a separate P0.5 plan unless a P0 test failure proves it is required now.
- Use CodeGraph before editing any nontrivial agent, SQL executor, or schema sync symbol.
