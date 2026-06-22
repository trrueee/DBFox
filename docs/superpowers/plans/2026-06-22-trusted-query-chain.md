# Trusted Query Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the trusted query chain so conversation context tables enter Agent runs, SQL/safety/result artifacts group correctly, and result pagination is tied to persisted safe SQL artifacts.

**Architecture:** Keep the existing Conversation API, DBFoxAgentRuntime, artifact persistence, and ConversationWorkspace UI. Add small contract helpers at the boundaries: context-table parsing in the conversation API, source-artifact verification in result pagination, result/safety mapping in the frontend bridge, and dual id/semantic-id grouping in the evidence panel.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, sqlglot, pytest, React, TypeScript, Zustand, Vitest, Testing Library.

---

## File Structure

Modify `engine/api/conversations.py`.
This file owns conversation HTTP routes. Add a private `_context_table_names_from_session()` helper and pass `AgentWorkspaceContext` into `AgentRunRequest`.

Modify `engine/tests/test_conversations.py`.
This file already tests conversation endpoints. Add streaming tests that monkeypatch `engine.api.conversations.DBFoxAgentRuntime` and inspect the request object passed to `run_iter()`.

Modify `engine/api/agent.py`.
This file owns `/agent/results/page`. Add private helpers for persisted source artifact lookup, safe SQL extraction, SQL normalization, and pagination source verification. Use those helpers before `build_derived_sql()`.

Modify `engine/sql/safety_gate.py`.
This file owns derived SQL helpers. Add a stricter base SQL validation helper for SQL-backed result pagination so base SQL must be a single `SELECT`.

Modify `engine/tests/test_agent_api.py`.
This file already tests API behavior and can use `db_session`. Add pagination safety tests that call `api_agent_result_page()` directly.

Modify `desktop/src/lib/api/types.ts`.
Add `"result_view"` to the backend `AgentArtifact["type"]` union.

Modify `desktop/src/types/agentArtifact.ts`.
Allow `ChartArtifact.chartType` to include existing backend chart types only if needed for compilation, and ensure mapped `ResultViewArtifact` carries `sourceSqlSemanticId` and `safeSql`.

Modify `desktop/src/features/workspace/agentBridge.ts`.
Map `result_view` and `safety`. Remove `safety` from hidden types. Keep query plan and agent plan hidden.

Modify `desktop/src/features/workspace/__tests__/agentBridge.test.ts`.
Extend existing bridge tests for `result_view` and `safety`.

Modify `desktop/src/features/conversation/workspace/ArtifactEvidencePanel.tsx`.
Extract grouping helpers, support `id` and `semantic_id`, render safety trust cards, and keep orphan artifacts visible.

Modify `desktop/src/features/conversation/workspace/__tests__/ArtifactEvidencePanel.test.tsx`.
Add tests for semantic-id grouping, physical-id compatibility, trust card rendering, and visible orphan artifacts.

## Task 1: Pass Conversation Context Tables Into Agent Runs

**Files:**
- Modify: `engine/api/conversations.py:13-142`
- Test: `engine/tests/test_conversations.py`

**Interfaces:**
- Consumes: `AgentSession.context_tables_json`, `AgentWorkspaceContext(datasource_id: str, selected_table_names: list[str])`
- Produces: `AgentRunRequest.workspace_context.selected_table_names`

- [ ] **Step 1: Write the failing context propagation test**

Add these imports near the top of `engine/tests/test_conversations.py`:

```python
import asyncio
import json

import engine.api.conversations as conversations_module
from engine.agent_core.types import AgentRunRequest, AgentRuntimeEvent
```

Add this helper near the existing fixtures:

```python
async def _streaming_response_text(response) -> str:
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk))
    return "".join(chunks)
```

Add this test:

```python
def test_stream_conversation_message_passes_context_tables_to_agent(monkeypatch, client, db_session):
    captured: dict[str, AgentRunRequest] = {}

    class FakeRuntime:
        def __init__(self, _db) -> None:
            pass

        def run_iter(self, req: AgentRunRequest):
            captured["req"] = req
            yield AgentRuntimeEvent(
                event_id="evt-context",
                run_id="run-context",
                sequence=1,
                created_at_ms=1,
                type="agent.run.started",
            )

    monkeypatch.setattr(conversations_module, "DBFoxAgentRuntime", FakeRuntime)
    session = AgentSession(
        id="conv-context",
        datasource_id="ds-1",
        title="Context test",
        context_tables_json=json.dumps(["orders", "orders", " customers ", "", 123], ensure_ascii=False),
    )
    db_session.add(session)
    db_session.commit()

    response = client.post(
        "/api/v1/conversations/conv-context/messages/stream",
        json={"content": "Count orders", "api_key": "test-key", "model_name": "test-model"},
        headers=_hdrs(),
    )
    body = asyncio.run(_streaming_response_text(response))

    assert response.status_code == 200
    assert "agent.run.started" in body
    req = captured["req"]
    assert req.workspace_context is not None
    assert req.workspace_context.datasource_id == "ds-1"
    assert req.workspace_context.selected_table_names == ["orders", "customers"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
pytest engine/tests/test_conversations.py::test_stream_conversation_message_passes_context_tables_to_agent -v
```

Expected: FAIL because `req.workspace_context` is `None`.

- [ ] **Step 3: Write the minimal implementation**

Change the import in `engine/api/conversations.py`:

```python
from engine.agent_core.types import AgentRunRequest, AgentWorkspaceContext
```

Add this helper above `stream_conversation_message()`:

```python
def _context_table_names_from_session(session: AgentSession) -> list[str]:
    try:
        raw = json.loads(session.context_tables_json or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(raw, list):
        return []

    names: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names
```

Update the `AgentRunRequest` construction:

```python
    context_table_names = _context_table_names_from_session(session)
    workspace_context = AgentWorkspaceContext(
        datasource_id=session.datasource_id,
        selected_table_names=context_table_names,
    )

    req = AgentRunRequest(
        datasource_id=session.datasource_id,
        question=payload.content,
        session_id=conversation_id,
        conversation_id=conversation_id,
        user_message_id=f"msg-user-{uuid4()}",
        assistant_message_id=f"msg-assistant-{uuid4()}",
        api_key=payload.api_key,
        api_base=payload.api_base,
        model_name=payload.model_name,
        workspace_context=workspace_context,
        execute=payload.execute,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
pytest engine/tests/test_conversations.py::test_stream_conversation_message_passes_context_tables_to_agent -v
```

Expected: PASS.

- [ ] **Step 5: Add malformed JSON regression test**

Add:

```python
def test_stream_conversation_message_ignores_malformed_context_tables(monkeypatch, client, db_session):
    captured: dict[str, AgentRunRequest] = {}

    class FakeRuntime:
        def __init__(self, _db) -> None:
            pass

        def run_iter(self, req: AgentRunRequest):
            captured["req"] = req
            yield AgentRuntimeEvent(
                event_id="evt-context-bad-json",
                run_id="run-context-bad-json",
                sequence=1,
                created_at_ms=1,
                type="agent.run.started",
            )

    monkeypatch.setattr(conversations_module, "DBFoxAgentRuntime", FakeRuntime)
    session = AgentSession(
        id="conv-bad-context",
        datasource_id="ds-1",
        title="Bad context",
        context_tables_json="{not-json",
    )
    db_session.add(session)
    db_session.commit()

    response = client.post(
        "/api/v1/conversations/conv-bad-context/messages/stream",
        json={"content": "Count orders", "api_key": "test-key", "model_name": "test-model"},
        headers=_hdrs(),
    )
    body = asyncio.run(_streaming_response_text(response))

    assert response.status_code == 200
    assert "agent.run.started" in body
    assert captured["req"].workspace_context is not None
    assert captured["req"].workspace_context.selected_table_names == []
```

- [ ] **Step 6: Run conversation tests**

Run:

```powershell
pytest engine/tests/test_conversations.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

Run:

```powershell
git add engine/api/conversations.py engine/tests/test_conversations.py
git commit -m "feat: pass conversation context tables to agent"
```

## Task 2: Bind Result Pagination To Persisted Safe SQL Artifacts

**Files:**
- Modify: `engine/sql/safety_gate.py:21-68`
- Modify: `engine/api/agent.py:398-513`
- Test: `engine/tests/test_agent_api.py`

**Interfaces:**
- Consumes: `ResultPageRequest.sourceSqlArtifactId`, `ResultPageRequest.safeSql`, `AgentArtifactRecord.payload_json`
- Produces: verified persisted safe SQL for `build_derived_sql()`

- [ ] **Step 1: Write failing mismatch test**

Add imports to `engine/tests/test_agent_api.py`:

```python
from datetime import UTC, datetime

from engine.api.agent import ResultPageRequest
from engine.models import AgentArtifactRecord, AgentRun, AgentSession, DataSource
```

Add this fixture helper:

```python
def _add_pagination_source(db_session, *, safe_sql: str = "SELECT id, amount FROM orders") -> None:
    now = datetime.now(UTC)
    datasource = DataSource(
        id="ds-page",
        name="Page DS",
        db_type="mysql",
        host="localhost",
        port=3306,
        database_name="dbfox",
        username="root",
        password_ciphertext="cipher",
        password_nonce="nonce",
    )
    session = AgentSession(
        id="conv-page",
        datasource_id="ds-page",
        title="Page",
        context_tables_json="[]",
        created_at=now,
        updated_at=now,
    )
    run = AgentRun(
        id="run-page",
        session_id="conv-page",
        datasource_id="ds-page",
        question="Orders",
        status="completed",
        created_at=now,
        updated_at=now,
    )
    artifact = AgentArtifactRecord(
        id="artifact-result-page",
        run_id="run-page",
        session_id="conv-page",
        semantic_id="result_view_1",
        type="result_view",
        title="Orders result",
        payload_json=json.dumps(
            {
                "safeSql": safe_sql,
                "columns": ["id", "amount"],
                "storageMode": "sql_backed",
            }
        ),
        presentation_json=json.dumps({"mode": "both", "priority": 1, "collapsed": False}),
        depends_on_json=json.dumps(["sql_candidate"]),
        status="completed",
        sequence=1,
        created_at=now,
    )
    db_session.add_all([datasource, session, run, artifact])
    db_session.commit()
```

Add:

```python
def test_result_page_rejects_safe_sql_that_differs_from_source_artifact(db_session):
    _add_pagination_source(db_session)

    with pytest.raises(HTTPException) as exc_info:
        agent_module.api_agent_result_page(
            ResultPageRequest(
                datasourceId="ds-page",
                sourceSqlArtifactId="artifact-result-page",
                safeSql="SELECT id FROM users",
                page=1,
                pageSize=20,
            ),
            db_session,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "SOURCE_SQL_MISMATCH"
```

- [ ] **Step 2: Run mismatch test to verify it fails**

Run:

```powershell
pytest engine/tests/test_agent_api.py::test_result_page_rejects_safe_sql_that_differs_from_source_artifact -v
```

Expected: FAIL because current endpoint trusts request `safeSql`.

- [ ] **Step 3: Add strict base SQL validation helper**

In `engine/sql/safety_gate.py`, add:

```python
def validate_pagination_base_sql(base_sql: str, dialect: str = "mysql") -> list[str]:
    """Validate the persisted source SQL before deriving a paginated query."""
    try:
        exprs = sqlglot.parse(base_sql, read=dialect)
    except Exception as exc:
        return [f"Source SQL validation parse error: {exc}"]
    if len(exprs) != 1:
        return ["Source SQL must be a single statement."]
    if not isinstance(exprs[0], exp.Select):
        return ["Source SQL must be a SELECT statement."]
    return []
```

- [ ] **Step 4: Add source artifact verification helpers**

In `engine/api/agent.py`, add imports inside or near the result pagination section:

```python
from engine.models import AgentArtifactRecord, AgentRun
```

Add helpers above `api_agent_result_page()`:

```python
def _normalize_sql_for_source_match(sql: str) -> str:
    return " ".join(sql.strip().split())


def _artifact_payload(record: AgentArtifactRecord) -> dict[str, object]:
    try:
        payload = json.loads(record.payload_json or "{}")
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_sql_from_artifact(record: AgentArtifactRecord) -> str:
    payload = _artifact_payload(record)
    for key in ("safeSql", "safe_sql", "sourceSql", "source_sql", "sql"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _load_source_artifact(
    db: Session,
    *,
    datasource_id: str,
    source_artifact_id: str,
) -> AgentArtifactRecord | None:
    base_query = (
        db.query(AgentArtifactRecord)
        .join(AgentRun, AgentRun.id == AgentArtifactRecord.run_id)
        .filter(AgentRun.datasource_id == datasource_id)
    )
    by_id = base_query.filter(AgentArtifactRecord.id == source_artifact_id).first()
    if by_id is not None:
        return by_id
    return (
        base_query
        .filter(AgentArtifactRecord.semantic_id == source_artifact_id)
        .order_by(AgentArtifactRecord.created_at.desc())
        .first()
    )


def _verified_pagination_source_sql(db: Session, req: ResultPageRequest, dialect: str) -> str:
    source = _load_source_artifact(
        db,
        datasource_id=req.datasourceId,
        source_artifact_id=req.sourceSqlArtifactId,
    )
    if source is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "SOURCE_ARTIFACT_NOT_FOUND", "message": "Source result artifact was not found."},
        )
    if source.type not in {"result_view", "table", "sql"}:
        raise HTTPException(
            status_code=400,
            detail={"code": "SOURCE_ARTIFACT_UNSUPPORTED", "message": "Source artifact cannot back pagination."},
        )

    persisted_safe_sql = _safe_sql_from_artifact(source)
    if not persisted_safe_sql:
        raise HTTPException(
            status_code=400,
            detail={"code": "SOURCE_SQL_MISSING", "message": "Source artifact does not contain safe SQL."},
        )
    if _normalize_sql_for_source_match(persisted_safe_sql) != _normalize_sql_for_source_match(req.safeSql):
        raise HTTPException(
            status_code=400,
            detail={"code": "SOURCE_SQL_MISMATCH", "message": "Requested SQL does not match the source artifact."},
        )

    from engine.sql.safety_gate import validate_pagination_base_sql

    warnings = validate_pagination_base_sql(persisted_safe_sql, dialect=dialect)
    if warnings:
        raise HTTPException(
            status_code=400,
            detail={"code": "SOURCE_SQL_VALIDATION_FAILED", "message": warnings[0]},
        )
    return persisted_safe_sql
```

- [ ] **Step 5: Use verified source SQL in pagination endpoint**

Inside `api_agent_result_page()`, replace:

```python
        derived_sql = build_derived_sql(
            base_sql=req.safeSql,
```

with:

```python
        source_sql = _verified_pagination_source_sql(db, req, dialect)
        derived_sql = build_derived_sql(
            base_sql=source_sql,
```

Replace the exact count parse input:

```python
            base_expr = sqlglot.parse_one(source_sql, read=dialect)
```

- [ ] **Step 6: Run mismatch test to verify it passes**

Run:

```powershell
pytest engine/tests/test_agent_api.py::test_result_page_rejects_safe_sql_that_differs_from_source_artifact -v
```

Expected: PASS.

- [ ] **Step 7: Add accepted pagination test**

Add:

```python
def test_result_page_uses_persisted_safe_sql_for_derived_query(monkeypatch, db_session):
    _add_pagination_source(db_session)
    executed_sql: dict[str, str] = {}

    def fake_execute_query(_db, datasource_id, sql, safety_decision):
        executed_sql["datasource_id"] = datasource_id
        executed_sql["sql"] = sql
        assert safety_decision.can_execute is True
        return {
            "columns": ["id", "amount"],
            "rows": [{"id": 1, "amount": 20}],
            "latencyMs": 3,
            "warnings": [],
            "notices": [],
        }

    monkeypatch.setattr("engine.sql.executor.execute_query", fake_execute_query)

    response = agent_module.api_agent_result_page(
        ResultPageRequest(
            datasourceId="ds-page",
            sourceSqlArtifactId="artifact-result-page",
            safeSql="SELECT id, amount FROM orders",
            page=1,
            pageSize=20,
            sort=[agent_module.ResultSort(column="id", direction="desc")],
        ),
        db_session,
    )

    assert response.columns == ["id", "amount"]
    assert response.rows == [{"id": 1, "amount": 20}]
    assert response.hasNextPage is False
    assert "orders" in executed_sql["sql"]
    assert "LIMIT" in executed_sql["sql"].upper()
```

- [ ] **Step 8: Add non-select source SQL test**

Add:

```python
def test_result_page_rejects_persisted_non_select_source_sql(db_session):
    _add_pagination_source(db_session, safe_sql="DELETE FROM orders")

    with pytest.raises(HTTPException) as exc_info:
        agent_module.api_agent_result_page(
            ResultPageRequest(
                datasourceId="ds-page",
                sourceSqlArtifactId="artifact-result-page",
                safeSql="DELETE FROM orders",
                page=1,
                pageSize=20,
            ),
            db_session,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "SOURCE_SQL_VALIDATION_FAILED"
```

- [ ] **Step 9: Run result pagination tests**

Run:

```powershell
pytest engine/tests/test_agent_api.py::test_result_page_rejects_safe_sql_that_differs_from_source_artifact engine/tests/test_agent_api.py::test_result_page_uses_persisted_safe_sql_for_derived_query engine/tests/test_agent_api.py::test_result_page_rejects_persisted_non_select_source_sql -v
```

Expected: PASS.

- [ ] **Step 10: Commit Task 2**

Run:

```powershell
git add engine/api/agent.py engine/sql/safety_gate.py engine/tests/test_agent_api.py
git commit -m "fix: bind result pagination to source artifacts"
```

## Task 3: Map Result View And Safety Artifacts For Frontend Consumers

**Files:**
- Modify: `desktop/src/lib/api/types.ts:336-350`
- Modify: `desktop/src/features/workspace/agentBridge.ts:20-127`
- Test: `desktop/src/features/workspace/__tests__/agentBridge.test.ts`

**Interfaces:**
- Consumes: backend `AgentArtifact` with `type: "result_view" | "safety"`
- Produces: `ResultViewArtifact` and `MarkdownArtifact` view models

- [ ] **Step 1: Write failing bridge tests**

Add this test to `desktop/src/features/workspace/__tests__/agentBridge.test.ts`:

```typescript
it("maps result_view artifacts for sql-backed result tabs", () => {
  const artifacts: AgentArtifact[] = [
    {
      id: "result-view-1",
      semantic_id: "result_view_1",
      type: "result_view",
      title: "Result view",
      status: "completed",
      presentation: { mode: "both", priority: 1, collapsed: false },
      payload: {
        storageMode: "sql_backed",
        datasourceId: "ds-1",
        sourceSqlSemanticId: "sql_candidate",
        sourceSql: "SELECT id, amount FROM orders",
        safeSql: "SELECT id, amount FROM orders",
        columns: ["id", "amount"],
        previewRows: [{ id: 1, amount: 20 }],
        previewRowCount: 1,
        rowCount: 128,
        returnedRows: 1,
        latencyMs: 42,
      },
      depends_on: ["sql_candidate"],
      refs: [],
    },
  ];

  const [resultView] = toViewArtifacts(artifacts);

  expect(resultView?.type).toBe("result_view");
  if (resultView?.type !== "result_view") throw new Error("Expected result_view artifact");
  expect(resultView.storageMode).toBe("sql_backed");
  expect(resultView.datasourceId).toBe("ds-1");
  expect(resultView.sourceSqlSemanticId).toBe("sql_candidate");
  expect(resultView.safeSql).toBe("SELECT id, amount FROM orders");
  expect(resultView.columns).toEqual(["id", "amount"]);
  expect(resultView.previewRows).toEqual([["1", "20"]]);
  expect(resultView.rowCount).toBe(128);
  expect(resultView.depends_on).toEqual(["sql_candidate"]);
});

it("maps safety artifacts into visible markdown trust summaries", () => {
  const artifacts: AgentArtifact[] = [
    {
      id: "safety-1",
      semantic_id: "safety_report",
      type: "safety",
      title: "Safety",
      status: "completed",
      presentation: { mode: "both", priority: 1, collapsed: true },
      payload: {
        passed: true,
        can_execute: true,
        requires_confirmation: false,
        guardrail_result: "passed",
        schema_warnings_count: 0,
      },
      depends_on: ["sql_candidate"],
      refs: [],
    },
  ];

  const [safety] = toViewArtifacts(artifacts);

  expect(safety?.type).toBe("markdown");
  if (safety?.type !== "markdown") throw new Error("Expected markdown artifact");
  expect(safety.title).toBe("安全检查");
  expect(safety.content).toContain("可执行");
  expect(safety.depends_on).toEqual(["sql_candidate"]);
});
```

- [ ] **Step 2: Run bridge tests to verify they fail**

Run:

```powershell
cd desktop; npm run test -- --run src/features/workspace/__tests__/agentBridge.test.ts
```

Expected: FAIL because backend type union does not include `result_view`, `result_view` is not mapped, and `safety` is hidden.

- [ ] **Step 3: Update backend artifact TypeScript union**

In `desktop/src/lib/api/types.ts`, change:

```typescript
  type: "agent_plan" | "query_plan" | "sql" | "sql_suggestion" | "safety" | "table" | "chart" | "error" | "insight" | "recommendation";
```

to:

```typescript
  type: "agent_plan" | "query_plan" | "sql" | "sql_suggestion" | "safety" | "table" | "result_view" | "chart" | "error" | "insight" | "recommendation";
```

- [ ] **Step 4: Map result_view and safety in agentBridge**

Update `TYPE_ORDER` and hidden types:

```typescript
const TYPE_ORDER: Record<string, number> = {
  sql: 0,
  sql_suggestion: 1,
  safety: 2,
  result_view: 3,
  table: 4,
  chart: 5,
  insight: 6,
  recommendation: 7,
  error: 8,
};

const HIDDEN_TYPES = new Set(["agent_plan", "query_plan"]);
```

Add `ResultViewArtifact` to the import from `../../types/agentArtifact`.

Add `case "result_view": return mapResultViewArtifact(artifact);` and `case "safety": return mapSafetyArtifact(artifact);`.

Add this function after `mapTableArtifact()`:

```typescript
function mapResultViewArtifact(artifact: ApiAgentArtifact): ResultViewArtifact | null {
  const payload = artifact.payload || {};
  const columns = Array.isArray(payload.columns) ? payload.columns.map(String) : [];
  const rawRows = Array.isArray(payload.previewRows)
    ? payload.previewRows
    : Array.isArray(payload.preview_rows)
      ? payload.preview_rows
      : Array.isArray(payload.rows)
        ? payload.rows
        : [];
  if (columns.length === 0) return null;
  const rows = rowsFromPayload(columns, rawRows);
  const storageMode = firstString(payload, ["storageMode", "storage_mode"]) === "sql_backed" ? "sql_backed" : "payload";
  return {
    id: artifact.id,
    type: "result_view",
    title: artifact.title || "查询结果",
    description: `${numberValue(payload, ["rowCount", "row_count"]) ?? rows.length} 行 · ${columns.length} 列`,
    storageMode,
    datasourceId: firstString(payload, ["datasourceId", "datasource_id"]),
    sourceSqlSemanticId: firstString(payload, ["sourceSqlSemanticId", "source_sql_semantic_id"]),
    sourceSql: firstString(payload, ["sourceSql", "source_sql"]),
    safeSql: firstString(payload, ["safeSql", "safe_sql"]),
    columns,
    previewRows: rows,
    previewRowCount: numberValue(payload, ["previewRowCount", "preview_row_count"]) ?? rows.length,
    rows: storageMode === "payload" ? rows : undefined,
    rowCount: numberValue(payload, ["rowCount", "row_count"]),
    returnedRows: numberValue(payload, ["returnedRows", "returned_rows"]) ?? rows.length,
    latencyMs: numberValue(payload, ["latencyMs", "latency_ms"]),
    truncated: Boolean(payload.truncated),
    warnings: stringArray(payload.warnings),
    notices: stringArray(payload.notices),
    depends_on: artifact.depends_on,
    payload: artifact.payload,
  };
}
```

Add a row conversion helper and reuse it in `mapTableArtifact()`:

```typescript
function rowsFromPayload(columns: string[], rawRows: unknown[]): string[][] {
  return rawRows.flatMap((row) => {
    if (Array.isArray(row)) {
      return [columns.map((_, columnIndex) => formatCell(row[columnIndex]))];
    }
    if (row && typeof row === "object") {
      const record = row as Record<string, unknown>;
      return [columns.map((column) => formatCell(record[column]))];
    }
    return [];
  });
}
```

Add safety mapper:

```typescript
function mapSafetyArtifact(artifact: ApiAgentArtifact): MarkdownArtifact {
  const payload = artifact.payload || {};
  const canExecute = Boolean(payload.can_execute ?? payload.canExecute);
  const requiresConfirmation = Boolean(payload.requires_confirmation ?? payload.requiresConfirmation);
  const passed = Boolean(payload.passed ?? canExecute);
  const guardrail = firstString(payload, ["guardrail_result", "guardrailResult"]) || "unknown";
  const schemaWarnings = numberValue(payload, ["schema_warnings_count", "schemaWarningsCount"]) ?? 0;
  const lines = [
    passed ? "状态：通过" : "状态：需注意",
    canExecute ? "执行：可执行" : "执行：不可执行",
    requiresConfirmation ? "确认：需要用户确认" : "确认：无需用户确认",
    `Guardrail：${guardrail}`,
    `Schema warnings：${schemaWarnings}`,
  ];
  return {
    id: artifact.id,
    type: "markdown",
    title: "安全检查",
    content: lines.join("\n"),
    depends_on: artifact.depends_on,
    payload: artifact.payload,
  };
}
```

- [ ] **Step 5: Run bridge tests**

Run:

```powershell
cd desktop; npm run test -- --run src/features/workspace/__tests__/agentBridge.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

Run:

```powershell
git add desktop/src/lib/api/types.ts desktop/src/features/workspace/agentBridge.ts desktop/src/features/workspace/__tests__/agentBridge.test.ts
git commit -m "feat: map trusted query artifacts"
```

## Task 4: Group Evidence By Semantic Id And Render Safety Trust Cards

**Files:**
- Modify: `desktop/src/features/conversation/workspace/ArtifactEvidencePanel.tsx:1-237`
- Test: `desktop/src/features/conversation/workspace/__tests__/ArtifactEvidencePanel.test.tsx`

**Interfaces:**
- Consumes: `ConversationArtifact.id`, `ConversationArtifact.semantic_id`, `ConversationArtifact.depends_on`
- Produces: grouped SQL/safety/result/chart evidence display

- [ ] **Step 1: Write failing semantic grouping test**

Add:

```typescript
it("groups SQL, safety, result_view, and chart by semantic ids", () => {
  const artifacts: ConversationArtifact[] = [
    {
      id: "artifact-sql",
      semantic_id: "sql_candidate",
      conversation_id: "conv",
      run_id: "run",
      message_id: "assistant",
      type: "sql",
      title: "SQL",
      status: "completed",
      sequence: 1,
      payload: { sql: "SELECT id, amount FROM orders" },
      depends_on: [],
    },
    {
      id: "artifact-safety",
      semantic_id: "safety_report",
      conversation_id: "conv",
      run_id: "run",
      message_id: "assistant",
      type: "safety",
      title: "Safety",
      status: "completed",
      sequence: 2,
      payload: {
        passed: true,
        can_execute: true,
        requires_confirmation: false,
        guardrail_result: "passed",
        schema_warnings_count: 0,
      },
      depends_on: ["sql_candidate"],
    },
    {
      id: "artifact-result",
      semantic_id: "result_view_1",
      conversation_id: "conv",
      run_id: "run",
      message_id: "assistant",
      type: "result_view",
      title: "Result view",
      status: "completed",
      sequence: 3,
      payload: {
        columns: ["id", "amount"],
        previewRows: [{ id: 1, amount: 20 }],
        rowCount: 1,
        storageMode: "sql_backed",
        safeSql: "SELECT id, amount FROM orders",
      },
      depends_on: ["sql_candidate"],
    },
    {
      id: "artifact-chart",
      semantic_id: "chart_1",
      conversation_id: "conv",
      run_id: "run",
      message_id: "assistant",
      type: "chart",
      title: "Amount chart",
      status: "completed",
      sequence: 4,
      payload: { type: "bar", series: [{ label: "1", value: 20 }] },
      depends_on: ["result_view_1"],
    },
  ];

  const { container } = render(<ArtifactEvidencePanel artifacts={artifacts} onOpenSqlConsole={vi.fn()} />);

  const group = container.querySelector(".conv-sql-group");
  expect(group).toBeTruthy();
  expect(group?.textContent).toContain("SQL");
  expect(group?.textContent).toContain("安全检查");
  expect(group?.textContent).toContain("Result view");
  expect(group?.textContent).toContain("Amount chart");
});
```

- [ ] **Step 2: Write failing orphan visibility test**

Add:

```typescript
it("keeps ungrouped safety artifacts visible", () => {
  const artifacts: ConversationArtifact[] = [
    {
      id: "orphan-safety",
      semantic_id: "safety_orphan",
      conversation_id: "conv",
      run_id: "run",
      message_id: "assistant",
      type: "safety",
      title: "Safety",
      status: "completed",
      sequence: 1,
      payload: {
        passed: false,
        can_execute: false,
        requires_confirmation: true,
        guardrail_result: "blocked",
        schema_warnings_count: 2,
      },
      depends_on: ["missing_sql"],
    },
  ];

  render(<ArtifactEvidencePanel artifacts={artifacts} onOpenSqlConsole={vi.fn()} />);

  expect(screen.getByText("安全检查")).toBeTruthy();
  expect(screen.getByText("不可执行")).toBeTruthy();
  expect(screen.getByText("需要确认")).toBeTruthy();
});
```

- [ ] **Step 3: Run evidence tests to verify they fail**

Run:

```powershell
cd desktop; npm run test -- --run src/features/conversation/workspace/__tests__/ArtifactEvidencePanel.test.tsx
```

Expected: FAIL because semantic-id grouping and safety rendering are missing.

- [ ] **Step 4: Implement id and semantic-id matching helpers**

In `ArtifactEvidencePanel.tsx`, add:

```typescript
function artifactKeys(artifact: ConversationArtifact): string[] {
  return [artifact.id, artifact.semantic_id].filter((item): item is string => Boolean(item));
}

function dependsOnAny(artifact: ConversationArtifact, keys: Set<string>): boolean {
  return dependsOn(artifact).some((id) => keys.has(id));
}
```

Replace `groupedArtifacts()` with:

```typescript
function groupedArtifacts(artifacts: ConversationArtifact[]) {
  const sql = artifacts
    .filter(isSqlArtifact)
    .sort((a, b) => (a.sequence || 0) - (b.sequence || 0));
  return sql.map((sqlArtifact) => {
    const sqlKeys = new Set(artifactKeys(sqlArtifact));
    const safety = artifacts.filter(
      (item) => item.type === "safety" && dependsOnAny(item, sqlKeys),
    );
    const tables = artifacts.filter(
      (item) => (item.type === "table" || item.type === "result_view") && dependsOnAny(item, sqlKeys),
    );
    const resultKeys = new Set(tables.flatMap(artifactKeys));
    const charts = artifacts.filter(
      (item) =>
        item.type === "chart" &&
        (dependsOnAny(item, sqlKeys) || dependsOnAny(item, resultKeys)),
    );
    return { sql: sqlArtifact, safety, tables, charts };
  });
}
```

Update grouped id collection:

```typescript
const groupedIds = new Set(
  groups.flatMap((group) => [
    group.sql.id,
    ...group.safety.map((item) => item.id),
    ...group.tables.map((item) => item.id),
    ...group.charts.map((item) => item.id),
  ]),
);
```

- [ ] **Step 5: Implement SafetyArtifact component**

Add helper readers:

```typescript
function payloadBoolean(payload: Record<string, unknown>, keys: string[]): boolean {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "boolean") return value;
  }
  return false;
}
```

Add component:

```tsx
function SafetyArtifact({ artifact }: { artifact: ConversationArtifact }) {
  const canExecute = payloadBoolean(artifact.payload, ["can_execute", "canExecute"]);
  const requiresConfirmation = payloadBoolean(artifact.payload, ["requires_confirmation", "requiresConfirmation"]);
  const passed = payloadBoolean(artifact.payload, ["passed"]) || canExecute;
  const guardrail = payloadString(artifact.payload, ["guardrail_result", "guardrailResult"]) || "unknown";
  const schemaWarnings = payloadNumber(artifact.payload, ["schema_warnings_count", "schemaWarningsCount"]) ?? 0;
  return (
    <div className={`conv-safety-artifact ${passed ? "is-safe" : "is-warning"}`}>
      <div className="conv-artifact-heading">
        <strong>安全检查</strong>
        <span>{canExecute ? "可执行" : "不可执行"}</span>
        <span>{requiresConfirmation ? "需要确认" : "无需确认"}</span>
      </div>
      <div className="conv-table-meta">
        <span>Guardrail: {guardrail}</span>
        <span>Schema warnings: {schemaWarnings}</span>
      </div>
    </div>
  );
}
```

Render safety inside each SQL group before tables:

```tsx
{group.safety.map((safety) => <SafetyArtifact key={safety.id} artifact={safety} />)}
```

Render orphan safety:

```tsx
if (artifact.type === "safety") return <SafetyArtifact key={artifact.id} artifact={artifact} />;
```

- [ ] **Step 6: Run evidence tests**

Run:

```powershell
cd desktop; npm run test -- --run src/features/conversation/workspace/__tests__/ArtifactEvidencePanel.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

Run:

```powershell
git add desktop/src/features/conversation/workspace/ArtifactEvidencePanel.tsx desktop/src/features/conversation/workspace/__tests__/ArtifactEvidencePanel.test.tsx
git commit -m "feat: group trusted query evidence"
```

## Task 5: Final Verification And Integration Sweep

**Files:**
- Verify all files changed by Tasks 1-4

**Interfaces:**
- Confirms the complete trusted query chain works across backend and frontend boundaries.

- [ ] **Step 1: Run backend targeted tests**

Run:

```powershell
pytest engine/tests/test_conversations.py engine/tests/test_agent_api.py -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend targeted tests**

Run:

```powershell
cd desktop; npm run test -- --run src/features/workspace/__tests__/agentBridge.test.ts src/features/conversation/workspace/__tests__/ArtifactEvidencePanel.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run frontend lint**

Run:

```powershell
cd desktop; npm run lint
```

Expected: PASS.

- [ ] **Step 4: Inspect git diff for unrelated changes**

Run:

```powershell
git diff --stat
git status --short
```

Expected: only files from this plan are modified, plus the existing untracked `docs/reviews/architecture/gpt-pro-review.md` if it remains untracked.

- [ ] **Step 5: Commit final verification adjustments if any were needed**

If Task 5 required code or test adjustments, run:

```powershell
git add engine/api/conversations.py engine/api/agent.py engine/sql/safety_gate.py engine/tests/test_conversations.py engine/tests/test_agent_api.py desktop/src/lib/api/types.ts desktop/src/features/workspace/agentBridge.ts desktop/src/features/workspace/__tests__/agentBridge.test.ts desktop/src/features/conversation/workspace/ArtifactEvidencePanel.tsx desktop/src/features/conversation/workspace/__tests__/ArtifactEvidencePanel.test.tsx
git commit -m "test: verify trusted query chain"
```

If no adjustments were needed, do not create an empty commit.

## Plan Self-Review

Spec coverage:
- Conversation context table propagation is covered by Task 1.
- Persisted source artifact verification and paginated SQL safety are covered by Task 2.
- `result_view` and `safety` frontend mapping are covered by Task 3.
- `id` and `semantic_id` evidence grouping plus visible safety cards are covered by Task 4.
- End-to-end verification commands are covered by Task 5.

Placeholder scan:
- No incomplete placeholder markers are present.
- Every task has concrete files, test snippets, implementation snippets, commands, and expected outcomes.

Type consistency:
- `sourceSqlArtifactId`, `safeSql`, `semantic_id`, `depends_on`, `selected_table_names`, `ResultViewArtifact`, and `ConversationArtifact` are used with the same names as the design spec and existing code.
