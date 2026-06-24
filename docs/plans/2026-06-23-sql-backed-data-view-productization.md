# SQL-backed Data View Productization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor DBFox database browsing and Agent result artifacts onto one SQL-backed data view architecture, with stable productized table UX, real SQL-backed filter/sort/search/export, and no large result sets treated as application state.

**Architecture:** Keep database browsing and Agent artifact results as separate product surfaces, but share backend derived SQL services and a frontend `useSqlBackedDataView` hook. Rows are fetched page-by-page from validated SQL sources; large exports stream from backend CSV; UI keeps `lastStableData` during refresh/page changes to avoid jitter.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, sqlglot, React, TypeScript, Zustand, Vitest/Testing Library, pytest, existing DBFox engine API clients.

---

## Requirements Source

This plan implements:

- `docs/designs/2026-06-23-sql-backed-data-view-productization.md`
- User-approved architecture principle: DBFox must not move large data results as application state; database browsing and Agent artifacts should both be SQL-backed views.

## File Structure

### Backend SQL-backed Service

- `engine/sql/sql_backed_view.py`
  - New shared derived SQL builder for page/search/filter/sort/count/export.
  - Owns column/operator validation and SQL construction.
- `engine/api/agent.py`
  - Keeps `/agent/results/page` compatibility while delegating derived SQL work to shared service.
  - Adds artifact result export endpoint if shared route is not introduced in the first slice.
- `engine/api/sql_backed.py`
  - Optional shared route module for database table and artifact SQL-backed paging/export.
  - Use only if route registration can be done cleanly without disrupting existing Agent APIs.
- `engine/main.py`
  - Include the shared route if `engine/api/sql_backed.py` is created.
- `engine/tests/test_sql_backed_view.py`
  - Pure tests for derived SQL builder, filter/search/sort validation, count SQL, and export SQL.
- `engine/tests/test_agent_api.py`
  - Regression tests for artifact pagination, filter/search application, safe SQL mismatch, and export.

### Frontend SQL-backed Data View

- `desktop/src/features/workspace/sqlBacked/sqlBackedTypes.ts`
  - Shared frontend source, request, response, filter, sort, loading-mode types.
- `desktop/src/features/workspace/sqlBacked/useSqlBackedDataView.ts`
  - Shared hook with `lastStableData`, request sequencing, paging, filter/search/sort state, and export.
- `desktop/src/features/workspace/sqlBacked/__tests__/useSqlBackedDataView.test.tsx`
  - Hook tests for stable data, stale responses, page reset, and export request shape.
- `desktop/src/lib/api/types.ts`
  - Extend or align `ResultPageRequest`, `ResultFilter`, `ResultSort`, export request/response types.
- `desktop/src/lib/api/agent.ts`
  - Add export request helper for artifact result export.
- `desktop/src/features/engine/engineApi.ts`
  - Add database table SQL-backed page/export helpers if the shared backend route is introduced.

### Database Browsing Surface

- `desktop/src/features/workspace/table/TablePreviewPane.tsx`
  - Refactor to `DatabaseTableSource` and `useSqlBackedDataView`.
  - Preserve database-specific toolbar, schema metadata, image cells, and open-SQL action.
- `desktop/src/features/workspace/table/TablePreviewToolbar.tsx`
  - New focused toolbar for refresh, search, filters, sort, column display, export, open SQL.
- `desktop/src/features/workspace/table/TablePreviewFooter.tsx`
  - New stable footer for page, page size, range, latency, count mode, and loading/error state.
- `desktop/src/features/workspace/table/__tests__/TablePreviewPane.test.tsx`
  - Covers no data clearing during pagination, request shape, toolbar behavior, and export.

### Artifact Result Surface

- `desktop/src/features/workspace/artifacts/table/useArtifactTableData.ts`
  - Delegate SQL-backed result behavior to `useSqlBackedDataView`.
  - Keep payload fallback for legacy/tiny artifacts.
- `desktop/src/features/workspace/artifacts/TableArtifactView.tsx`
  - Productize workspace mode controls and status; keep inline mode lightweight.
- `desktop/src/features/workspace/artifacts/table/ArtifactTableToolbar.tsx`
  - Replace placeholder filter/sort/export actions with real SQL-backed state.
- `desktop/src/features/workspace/artifacts/table/ArtifactTableFooter.tsx`
  - Align footer behavior with SQL-backed hook metadata.
- `desktop/src/features/workspace/artifacts/__tests__/TableArtifactView.test.tsx`
  - Covers SQL-backed pagination/filter/export and payload fallback.

### Agent Artifact Generation

- `engine/agent_core/artifacts.py`
  - `build_result_view_artifact()` currently emits `storageMode: "payload"` and full `rows`; update it to prefer SQL-backed result views with preview-only rows.
- `engine/agent/tests/test_agent_artifacts.py`
  - Add regression for no large `payload.rows` on SQL-backed result views.

## Implementation Tasks

### Task 1: Backend Derived SQL Builder

**Files:**
- Create: `engine/sql/sql_backed_view.py`
- Test: `engine/tests/test_sql_backed_view.py`

- [ ] **Step 1: Write failing tests for filter/search/sort/page SQL**

Add tests shaped like:

```python
from engine.sql.sql_backed_view import (
    SqlBackedFilter,
    SqlBackedSort,
    build_sql_backed_page_sql,
)


def test_builds_filtered_sorted_paginated_sql():
    result = build_sql_backed_page_sql(
        base_sql="SELECT id, name, total FROM orders",
        dialect="mysql",
        columns=["id", "name", "total"],
        filters=[SqlBackedFilter(column="total", operator="gte", value=100)],
        search="acme",
        searchable_columns=["name"],
        sorts=[SqlBackedSort(column="total", direction="desc")],
        limit=26,
        offset=25,
    )

    assert "FROM (SELECT id, name, total FROM orders) AS dbfox_result" in result.sql
    assert "`total` >= 100" in result.sql
    assert "`name` LIKE '%acme%'" in result.sql
    assert "ORDER BY `total` DESC" in result.sql
    assert "LIMIT 26" in result.sql
    assert "OFFSET 25" in result.sql
```

Add rejection tests:

```python
import pytest
from engine.sql.sql_backed_view import SqlBackedFilter, SqlBackedViewError, build_sql_backed_page_sql


def test_rejects_filter_column_outside_source_columns():
    with pytest.raises(SqlBackedViewError, match="FILTER_COLUMN_NOT_ALLOWED"):
        build_sql_backed_page_sql(
            base_sql="SELECT id, name FROM users",
            dialect="mysql",
            columns=["id", "name"],
            filters=[SqlBackedFilter(column="password", operator="contains", value="x")],
            limit=20,
            offset=0,
        )


def test_rejects_unknown_filter_operator():
    with pytest.raises(SqlBackedViewError, match="FILTER_OPERATOR_NOT_ALLOWED"):
        build_sql_backed_page_sql(
            base_sql="SELECT id, name FROM users",
            dialect="mysql",
            columns=["id", "name"],
            filters=[SqlBackedFilter(column="name", operator="raw_sql", value="1=1")],
            limit=20,
            offset=0,
        )
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
pytest engine/tests/test_sql_backed_view.py -q
```

Expected: import failure because `engine.sql.sql_backed_view` does not exist.

- [ ] **Step 3: Implement minimal SQL-backed builder**

Create `engine/sql/sql_backed_view.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import sqlglot
from sqlglot import exp
from pydantic import BaseModel


FilterOperator = Literal[
    "equals", "not_equals", "contains", "starts_with", "ends_with",
    "gt", "gte", "lt", "lte", "is_null", "is_not_null", "in", "not_in",
]


class SqlBackedViewError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class SqlBackedFilter(BaseModel):
    column: str
    operator: str
    value: Any = None


class SqlBackedSort(BaseModel):
    column: str
    direction: Literal["asc", "desc"]


@dataclass(frozen=True)
class SqlBackedQuery:
    sql: str


ALLOWED_FILTER_OPERATORS = {
    "equals", "not_equals", "contains", "starts_with", "ends_with",
    "gt", "gte", "lt", "lte", "is_null", "is_not_null", "in", "not_in",
}


def build_sql_backed_page_sql(
    *,
    base_sql: str,
    dialect: str,
    columns: list[str],
    filters: list[SqlBackedFilter] | None = None,
    search: str | None = None,
    searchable_columns: list[str] | None = None,
    sorts: list[SqlBackedSort] | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> SqlBackedQuery:
    allowed = {_normalize_column(c) for c in columns}
    base_expr = sqlglot.parse_one(base_sql, read=dialect)
    if not isinstance(base_expr, exp.Select):
        raise SqlBackedViewError("SOURCE_SQL_VALIDATION_FAILED", "Source SQL must be a SELECT statement.")

    query = sqlglot.select("*").from_(base_expr.subquery("dbfox_result"))

    for item in filters or []:
        _ensure_column_allowed(item.column, allowed, "FILTER_COLUMN_NOT_ALLOWED")
        _ensure_operator_allowed(item.operator)
        query = query.where(_filter_expression(item))

    normalized_search = (search or "").strip()
    if normalized_search:
        search_columns = searchable_columns or columns
        expressions = []
        for column in search_columns:
            _ensure_column_allowed(column, allowed, "FILTER_COLUMN_NOT_ALLOWED")
            expressions.append(exp.Like(this=_identifier(column), expression=exp.Literal.string(f"%{normalized_search}%")))
        if expressions:
            combined = expressions[0]
            for expression in expressions[1:]:
                combined = exp.or_(combined, expression)
            query = query.where(combined)

    for item in sorts or []:
        _ensure_column_allowed(item.column, allowed, "SORT_COLUMN_NOT_ALLOWED")
        query = query.order_by(exp.Ordered(this=_identifier(item.column), desc=item.direction == "desc"))

    if limit is not None:
        query = query.limit(limit)
    if offset is not None:
        query = query.offset(offset)

    return SqlBackedQuery(sql=query.sql(dialect=dialect))


def _normalize_column(column: str) -> str:
    return column.strip().strip("`\"[]").lower()


def _ensure_column_allowed(column: str, allowed: set[str], code: str) -> None:
    if _normalize_column(column) not in allowed:
        raise SqlBackedViewError(code, f"Column '{column}' is not present in the source result.")


def _ensure_operator_allowed(operator: str) -> None:
    if operator not in ALLOWED_FILTER_OPERATORS:
        raise SqlBackedViewError("FILTER_OPERATOR_NOT_ALLOWED", f"Operator '{operator}' is not allowed.")


def _identifier(column: str) -> exp.Identifier:
    return exp.Identifier(this=column.strip(), quoted=True)


def _literal(value: Any) -> exp.Expression:
    if value is None:
        return exp.Null()
    if isinstance(value, bool):
        return exp.Boolean(this=value)
    if isinstance(value, (int, float)):
        return exp.Literal.number(value)
    return exp.Literal.string(str(value))


def _filter_expression(item: SqlBackedFilter) -> exp.Expression:
    left = _identifier(item.column)
    op = item.operator
    if op == "equals":
        return exp.EQ(this=left, expression=_literal(item.value))
    if op == "not_equals":
        return exp.NEQ(this=left, expression=_literal(item.value))
    if op == "gt":
        return exp.GT(this=left, expression=_literal(item.value))
    if op == "gte":
        return exp.GTE(this=left, expression=_literal(item.value))
    if op == "lt":
        return exp.LT(this=left, expression=_literal(item.value))
    if op == "lte":
        return exp.LTE(this=left, expression=_literal(item.value))
    if op == "is_null":
        return exp.Is(this=left, expression=exp.Null())
    if op == "is_not_null":
        return exp.Not(this=exp.Is(this=left, expression=exp.Null()))
    if op == "contains":
        return exp.Like(this=left, expression=exp.Literal.string(f"%{item.value}%"))
    if op == "starts_with":
        return exp.Like(this=left, expression=exp.Literal.string(f"{item.value}%"))
    if op == "ends_with":
        return exp.Like(this=left, expression=exp.Literal.string(f"%{item.value}"))
    if op in {"in", "not_in"}:
        values = item.value if isinstance(item.value, list) else [item.value]
        expression = exp.In(this=left, expressions=[_literal(value) for value in values])
        return exp.Not(this=expression) if op == "not_in" else expression
    raise SqlBackedViewError("FILTER_OPERATOR_NOT_ALLOWED", f"Operator '{op}' is not allowed.")
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest engine/tests/test_sql_backed_view.py -q
```

Expected: pass or fail only on exact SQL formatting. Adjust tests to assert sqlglot-equivalent syntax when formatting differs.

- [ ] **Step 5: Commit**

```bash
git add engine/sql/sql_backed_view.py engine/tests/test_sql_backed_view.py
git commit -m "feat: add sql backed derived query builder"
```

### Task 2: Apply Filters/Search In Agent Result Pagination

**Files:**
- Modify: `engine/api/agent.py`
- Modify: `engine/tests/test_agent_api.py`

- [ ] **Step 1: Write failing API tests**

Add tests using the existing `/agent/results/page` test fixtures:

```python
def test_result_page_applies_search_and_filter(client, db_session, sql_backed_result_artifact):
    response = client.post("/agent/results/page", json={
        "datasourceId": sql_backed_result_artifact.datasource_id,
        "sourceSqlArtifactId": sql_backed_result_artifact.semantic_id,
        "safeSql": sql_backed_result_artifact.safe_sql,
        "page": 1,
        "pageSize": 20,
        "filters": [{"column": "status", "operator": "equals", "value": "paid"}],
        "search": "enterprise",
        "countMode": "none",
    })

    assert response.status_code == 200
    body = response.json()
    assert "WHERE" in body["executedSql"].upper()
    assert "status" in body["executedSql"]
    assert "enterprise" in body["executedSql"]
```

Add rejection coverage:

```python
def test_result_page_rejects_filter_column_outside_source(client, db_session, sql_backed_result_artifact):
    response = client.post("/agent/results/page", json={
        "datasourceId": sql_backed_result_artifact.datasource_id,
        "sourceSqlArtifactId": sql_backed_result_artifact.semantic_id,
        "safeSql": sql_backed_result_artifact.safe_sql,
        "page": 1,
        "pageSize": 20,
        "filters": [{"column": "password", "operator": "contains", "value": "x"}],
    })

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "FILTER_COLUMN_NOT_ALLOWED"
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
pytest engine/tests/test_agent_api.py -q
```

Expected: new tests fail because filters/search are ignored or error codes are not mapped.

- [ ] **Step 3: Delegate `/agent/results/page` to builder**

In `api_agent_result_page`, map request models into `SqlBackedFilter` and `SqlBackedSort`, then call:

```python
from engine.sql.sql_backed_view import (
    SqlBackedFilter,
    SqlBackedSort,
    SqlBackedViewError,
    build_sql_backed_page_sql,
)

try:
    derived = build_sql_backed_page_sql(
        base_sql=source_sql,
        dialect=dialect,
        columns=sorted(_result_columns_from_artifact(source_artifact)),
        filters=[SqlBackedFilter.model_validate(item.model_dump()) for item in (req.filters or [])],
        search=req.search,
        searchable_columns=sorted(_result_columns_from_artifact(source_artifact)),
        sorts=[SqlBackedSort.model_validate(item.model_dump()) for item in (req.sort or [])],
        limit=limit + 1,
        offset=offset,
    )
    derived_sql = derived.sql
except SqlBackedViewError as exc:
    raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message})
```

Keep the existing safe SQL source verification and `validate_derived_sql` call.

- [ ] **Step 4: Run focused backend tests**

Run:

```bash
pytest engine/tests/test_sql_backed_view.py engine/tests/test_agent_api.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add engine/api/agent.py engine/tests/test_agent_api.py
git commit -m "feat: apply sql backed filters to agent results"
```

### Task 3: Add SQL-backed CSV Export

**Files:**
- Modify: `engine/api/agent.py` or Create: `engine/api/sql_backed.py`
- Modify: `engine/main.py` if a new router is created
- Test: `engine/tests/test_agent_api.py` or `engine/tests/test_sql_backed_api.py`

- [ ] **Step 1: Write failing export tests**

Add:

```python
def test_result_export_streams_all_matching_rows(client, db_session, sql_backed_result_artifact):
    response = client.post("/agent/results/export", json={
        "datasourceId": sql_backed_result_artifact.datasource_id,
        "sourceSqlArtifactId": sql_backed_result_artifact.semantic_id,
        "safeSql": sql_backed_result_artifact.safe_sql,
        "sort": [{"column": "created_at", "direction": "desc"}],
        "filters": [{"column": "status", "operator": "equals", "value": "paid"}],
        "search": "enterprise",
    })

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "created_at" in response.text.splitlines()[0]
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```bash
pytest engine/tests/test_agent_api.py -q
```

Expected: 404 because `/agent/results/export` is missing.

- [ ] **Step 3: Implement export request and route**

Add a request model:

```python
class ResultExportRequest(BaseModel):
    datasourceId: str
    sourceSqlArtifactId: str
    safeSql: str
    sort: list[ResultSort] | None = None
    filters: list[ResultFilter] | None = None
    search: str | None = None
```

Implement route:

```python
@router.post("/agent/results/export")
def api_agent_result_export(req: ResultExportRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    # Verify source artifact and safe SQL exactly as page endpoint does.
    # Build derived SQL with filters/search/sort and no page limit.
    # Execute readonly, then stream rows as CSV.
```

Use Python `csv.DictWriter` over an iterator. If the first slice uses `execute_query`, keep the executor limits and document that true cursor streaming is the next backend optimization.

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest engine/tests/test_agent_api.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add engine/api/agent.py engine/tests/test_agent_api.py
git commit -m "feat: export sql backed agent results"
```

### Task 4: Frontend API Types And Clients

**Files:**
- Modify: `desktop/src/lib/api/types.ts`
- Modify: `desktop/src/lib/api/agent.ts`
- Test: `desktop/src/lib/api/__tests__/agent.test.ts` if present, otherwise add focused hook tests in Task 5.

- [ ] **Step 1: Add frontend types**

Add:

```typescript
export interface ResultFilter {
  column: string;
  operator:
    | "equals"
    | "not_equals"
    | "contains"
    | "starts_with"
    | "ends_with"
    | "gt"
    | "gte"
    | "lt"
    | "lte"
    | "is_null"
    | "is_not_null"
    | "in"
    | "not_in";
  value?: unknown;
}

export interface ResultExportRequest {
  datasourceId: string;
  sourceSqlArtifactId: string;
  safeSql: string;
  sort?: ResultSort[];
  filters?: ResultFilter[];
  search?: string;
}
```

- [ ] **Step 2: Add agent API helper**

In `agentApi` add:

```typescript
exportResultCsv: (req: ResultExportRequest) =>
  requestBlob("/agent/results/export", {
    method: "POST",
    body: JSON.stringify(req),
  }),
```

If `requestBlob` does not exist, create a local helper in `agent.ts` mirroring the existing authenticated `request` behavior but returning `Blob`.

- [ ] **Step 3: Run TypeScript check through tests**

Run:

```bash
cd desktop && npm run test -- --run src/features/workspace/artifacts/__tests__/TableArtifactView.test.tsx
```

Expected: existing tests pass or only fail where signatures need follow-up in later tasks.

- [ ] **Step 4: Commit**

```bash
git add desktop/src/lib/api/types.ts desktop/src/lib/api/agent.ts
git commit -m "feat: add sql backed result export client"
```

### Task 5: Shared `useSqlBackedDataView` Hook

**Files:**
- Create: `desktop/src/features/workspace/sqlBacked/sqlBackedTypes.ts`
- Create: `desktop/src/features/workspace/sqlBacked/useSqlBackedDataView.ts`
- Create: `desktop/src/features/workspace/sqlBacked/__tests__/useSqlBackedDataView.test.tsx`

- [ ] **Step 1: Write failing hook tests**

Test stable data:

```tsx
it("keeps last stable data while loading the next page", async () => {
  const fetchPage = vi
    .fn()
    .mockResolvedValueOnce({ columns: ["id"], rows: [{ id: "1" }], page: 1, pageSize: 20, hasNextPage: true, latencyMs: 5 })
    .mockReturnValueOnce(new Promise(() => {}));

  const { result } = renderHook(() => useSqlBackedDataView({ source, fetchPage, exportAll }));
  await waitFor(() => expect(result.current.rows).toEqual([["1"]]));

  act(() => result.current.setPage(2));

  expect(result.current.rows).toEqual([["1"]]);
  expect(result.current.loadingMode).toBe("page");
});
```

Test stale response protection:

```tsx
it("does not let an older response overwrite a newer response", async () => {
  const resolvers: Array<(value: PageResponse) => void> = [];
  const fetchPage = vi.fn(() => new Promise<PageResponse>((resolve) => resolvers.push(resolve)));
  const { result } = renderHook(() => useSqlBackedDataView({ source, fetchPage, exportAll }));

  act(() => result.current.setPage(2));
  act(() => result.current.setPage(3));

  act(() => resolvers[1]({ columns: ["id"], rows: [{ id: "3" }], page: 3, pageSize: 20, hasNextPage: false, latencyMs: 5 }));
  await waitFor(() => expect(result.current.page).toBe(3));

  act(() => resolvers[0]({ columns: ["id"], rows: [{ id: "2" }], page: 2, pageSize: 20, hasNextPage: false, latencyMs: 5 }));
  expect(result.current.rows).toEqual([["3"]]);
});
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
cd desktop && npm run test -- --run src/features/workspace/sqlBacked/__tests__/useSqlBackedDataView.test.tsx
```

Expected: import failure.

- [ ] **Step 3: Implement hook**

Core type shape:

```typescript
export type SqlBackedLoadingMode = "idle" | "initial" | "refresh" | "page" | "filter" | "export";

export interface SqlBackedDataViewSource {
  kind: "database-table" | "artifact-result";
  datasourceId: string;
  columns: string[];
}
```

Hook behavior:

```typescript
const requestSeqRef = useRef(0);
const [lastStableData, setLastStableData] = useState<PageResponse | null>(null);

const load = useCallback(async (mode: SqlBackedLoadingMode) => {
  const seq = ++requestSeqRef.current;
  setLoadingMode(lastStableData ? mode : "initial");
  try {
    const response = await fetchPage(buildRequest());
    if (seq !== requestSeqRef.current) return;
    setLastStableData(response);
    setError(null);
  } catch (err) {
    if (seq !== requestSeqRef.current) return;
    setError(err instanceof Error ? err.message : String(err));
  } finally {
    if (seq === requestSeqRef.current) setLoadingMode("idle");
  }
}, [fetchPage, lastStableData, buildRequest]);
```

- [ ] **Step 4: Run hook tests**

Run:

```bash
cd desktop && npm run test -- --run src/features/workspace/sqlBacked/__tests__/useSqlBackedDataView.test.tsx
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add desktop/src/features/workspace/sqlBacked
git commit -m "feat: add sql backed data view hook"
```

### Task 6: Refactor Database Table Preview

**Files:**
- Modify: `desktop/src/features/workspace/table/TablePreviewPane.tsx`
- Create: `desktop/src/features/workspace/table/TablePreviewToolbar.tsx`
- Create: `desktop/src/features/workspace/table/TablePreviewFooter.tsx`
- Test: `desktop/src/features/workspace/table/__tests__/TablePreviewPane.test.tsx`

- [ ] **Step 1: Write failing tests for stable pagination**

Add:

```tsx
it("keeps current rows visible while loading a new page", async () => {
  mockExecuteSql
    .mockResolvedValueOnce(pageResult(["id"], [{ id: "1" }], true))
    .mockReturnValueOnce(new Promise(() => {}));

  render(<TablePreviewPane tableId="users" onOpenSqlConsole={vi.fn()} onToast={vi.fn()} />);
  expect(await screen.findByText("1")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: /下一页|>/ }));

  expect(screen.getByText("1")).toBeInTheDocument();
  expect(screen.queryByTestId("table-preview-skeleton")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```bash
cd desktop && npm run test -- --run src/features/workspace/table/__tests__/TablePreviewPane.test.tsx
```

Expected: fail because current preview clears data on uncached page.

- [ ] **Step 3: Refactor preview to hook-driven state**

Use a `DatabaseTableSource` object:

```typescript
const source = useMemo<SqlBackedDataViewSource>(() => ({
  kind: "database-table",
  datasourceId: resolved.datasource.id,
  tableName: tableId,
  columns,
}), [resolved.datasource.id, tableId, columns]);
```

Initial slice may keep the existing `executeSql` table SQL while adopting `lastStableData`. If the shared backend route is ready, replace direct SQL with that route in this task.

- [ ] **Step 4: Replace placeholder toolbar actions with real local state**

Minimum product behavior:

- Search input updates `search` and resets page.
- Sort uses selected column/direction and resets page.
- Export calls `exportAll`.
- Filter button opens a simple column/operator/value popover or a compact inline filter row.

- [ ] **Step 5: Run focused tests**

Run:

```bash
cd desktop && npm run test -- --run src/features/workspace/table/__tests__/TablePreviewPane.test.tsx
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add desktop/src/features/workspace/table
git commit -m "feat: stabilize database table preview"
```

### Task 7: Refactor Artifact Result Data View

**Files:**
- Modify: `desktop/src/features/workspace/artifacts/table/useArtifactTableData.ts`
- Modify: `desktop/src/features/workspace/artifacts/TableArtifactView.tsx`
- Modify: `desktop/src/features/workspace/artifacts/table/ArtifactTableToolbar.tsx`
- Test: `desktop/src/features/workspace/artifacts/__tests__/TableArtifactView.test.tsx`

- [ ] **Step 1: Write failing tests for SQL-backed filtering/export**

Add:

```tsx
it("sends search and sort to backend for sql backed result views", async () => {
  render(<TableArtifactView artifact={sqlBackedArtifact} mode="workspace" onToast={vi.fn()} />);

  await userEvent.type(screen.getByPlaceholderText(/搜索结果/), "enterprise");
  await userEvent.click(screen.getByRole("columnheader", { name: /total/ }));

  await waitFor(() => {
    expect(agentApi.fetchResultPage).toHaveBeenLastCalledWith(expect.objectContaining({
      search: "enterprise",
      sort: [{ column: "total", direction: "desc" }],
    }));
  });
});
```

Add export test:

```tsx
it("exports all matching rows for sql backed result views", async () => {
  render(<TableArtifactView artifact={sqlBackedArtifact} mode="workspace" onToast={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: /导出/ }));
  expect(agentApi.exportResultCsv).toHaveBeenCalledWith(expect.objectContaining({
    sourceSqlArtifactId: sqlBackedArtifact.sourceSqlSemanticId,
    safeSql: sqlBackedArtifact.safeSql,
  }));
});
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
cd desktop && npm run test -- --run src/features/workspace/artifacts/__tests__/TableArtifactView.test.tsx
```

Expected: fail because export/filter are placeholder/current-page behavior.

- [ ] **Step 3: Delegate SQL-backed branch to shared hook**

In `useArtifactTableData`, when:

```typescript
artifact.type === "result_view" && artifact.storageMode === "sql_backed" && mode === "workspace"
```

construct an `ArtifactResultSource` and use `useSqlBackedDataView`. Keep the existing local array behavior for payload artifacts.

- [ ] **Step 4: Productize workspace mode metadata**

Show:

- `SQL-backed`
- `latencyMs`
- `warnings/notices`
- `executedSql` available through "打开 SQL"
- current page and page size

- [ ] **Step 5: Run focused tests**

Run:

```bash
cd desktop && npm run test -- --run src/features/workspace/artifacts/__tests__/TableArtifactView.test.tsx src/features/workspace/sqlBacked/__tests__/useSqlBackedDataView.test.tsx
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add desktop/src/features/workspace/artifacts desktop/src/features/workspace/sqlBacked
git commit -m "feat: use sql backed view for artifacts"
```

### Task 8: Tighten Agent Result Artifact Payloads

**Files:**
- Modify: `engine/agent_core/artifacts.py`
- Test: `engine/agent/tests/test_agent_artifacts.py`

- [ ] **Step 1: Review artifact builder context**

Run:

```bash
codegraph node engine/agent_core/artifacts.py --symbol build_result_view_artifact --include-code
```

Expected: confirm `build_result_view_artifact()` currently sets `storageMode: "payload"` and includes full `rows`.

- [ ] **Step 2: Write failing test**

Test that SQL-backed result views do not persist large `rows`:

```python
def test_sql_backed_result_view_keeps_preview_not_full_rows(...):
    artifact = build_result_view_artifact(
        datasource_id="ds1",
        safe_sql="SELECT id FROM users LIMIT 1000",
        columns=["id"],
        rows=[{"id": str(i)} for i in range(100)],
    )

    assert artifact["storageMode"] == "sql_backed"
    assert len(artifact["previewRows"]) <= 10
    assert "rows" not in artifact or len(artifact["rows"]) <= 10
```

- [ ] **Step 3: Implement preview-only payload rule**

Apply:

```python
preview_rows = rows[:10]
payload = {
    "type": "result_view",
    "storageMode": "sql_backed",
    "datasourceId": datasource_id,
    "sourceSqlSemanticId": source_sql_semantic_id,
    "sourceSql": source_sql,
    "safeSql": safe_sql,
    "columns": columns,
    "previewRows": preview_rows,
    "previewRowCount": len(preview_rows),
    "returnedRows": returned_rows,
    "rowCount": row_count,
    "latencyMs": latency_ms,
}
```

Only keep `rows` for payload-mode legacy/tiny artifacts.

- [ ] **Step 4: Run focused engine tests**

Run:

```bash
pytest engine/tests/test_agent_api.py engine/tests/test_architecture.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add engine/agent_core/artifacts.py engine/agent/tests/test_agent_artifacts.py
git commit -m "fix: keep sql backed artifacts preview only"
```

### Task 9: Productized Table And Artifact UX Polish

**Files:**
- Modify: `desktop/src/styles/tokens.css`
- Modify: relevant CSS files for table/artifact workspace
- Modify: `desktop/src/features/workspace/table/TablePreviewPane.tsx`
- Modify: `desktop/src/features/workspace/artifacts/TableArtifactView.tsx`
- Test: `desktop/src/__tests__/agentVisualTokens.test.ts`

- [ ] **Step 1: Add visual regression/token expectations**

Add assertions for stable surface tokens and no inline table pagination sizing where feasible.

- [ ] **Step 2: Implement stable viewport CSS**

Ensure:

```css
.sql-backed-table-shell {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  min-height: 0;
}

.sql-backed-table-viewport {
  min-height: 320px;
  overflow: auto;
}

.sql-backed-table thead th {
  position: sticky;
  top: 0;
  z-index: 1;
}
```

- [ ] **Step 3: Remove placeholder toast actions**

Filter/sort/export controls must either execute real state changes or be absent from that mode.

- [ ] **Step 4: Run frontend focused tests**

Run:

```bash
cd desktop && npm run test -- --run src/__tests__/agentVisualTokens.test.ts src/features/workspace/table/__tests__/TablePreviewPane.test.tsx src/features/workspace/artifacts/__tests__/TableArtifactView.test.tsx
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add desktop/src/styles desktop/src/features/workspace/table desktop/src/features/workspace/artifacts desktop/src/__tests__
git commit -m "style: productize sql backed data views"
```

### Task 10: Final Verification

**Files:**
- No source edits unless verification reveals failures.

- [ ] **Step 1: Run backend tests**

Run:

```bash
pytest engine/tests/test_sql_backed_view.py engine/tests/test_agent_api.py engine/tests/test_architecture.py -q
```

Expected: pass.

- [ ] **Step 2: Run frontend focused tests**

Run:

```bash
cd desktop && npm run test -- --run src/features/workspace/sqlBacked/__tests__/useSqlBackedDataView.test.tsx src/features/workspace/table/__tests__/TablePreviewPane.test.tsx src/features/workspace/artifacts/__tests__/TableArtifactView.test.tsx src/__tests__/agentVisualTokens.test.ts
```

Expected: pass.

- [ ] **Step 3: Run full frontend tests single worker if worker pool flakes**

Run:

```bash
cd desktop && npm run test -- --run --maxWorkers=1
```

Expected: pass.

- [ ] **Step 4: Run lint and build**

Run:

```bash
cd desktop && npm run lint
cd desktop && npm run build
```

Expected: lint exits 0 with existing warnings only; build passes with existing Vite warnings only.

- [ ] **Step 5: Manual product checks**

Open the app and verify:

- Database table pagination does not clear rows or jump.
- Database preview filter/search/sort/export are real actions.
- Artifact result tab keeps right split-pane behavior.
- SQL-backed artifact export exports matching result, not current page.
- Inline artifact preview stays lightweight.

- [ ] **Step 6: Commit any verification fixes**

If verification produces no code changes, skip this commit. If verification reveals failures, fix only the files responsible for those failures, run the failed command again, then stage the exact changed files shown by `git status --short` and commit:

```bash
git status --short
git add engine/sql/sql_backed_view.py engine/api/agent.py engine/agent_core/artifacts.py engine/agent/tests/test_agent_artifacts.py engine/tests/test_sql_backed_view.py engine/tests/test_agent_api.py desktop/src/features/workspace/sqlBacked desktop/src/features/workspace/table desktop/src/features/workspace/artifacts desktop/src/lib/api/types.ts desktop/src/lib/api/agent.ts desktop/src/styles desktop/src/__tests__
git commit -m "fix: verify sql backed data views"
```

## Checkpoints

Commit after Tasks 1, 2, 3, 5, 6, 7, 8, 9, and final verification fixes. Run at least the focused tests listed in each task before committing.

## Execution Notes

- Preserve untracked `docs/reviews/architecture/17-gpt-pro-review.md`.
- Use CodeGraph before locating or editing Agent artifact builder code.
- Keep database browsing and artifact result UI separate; share query capability, not product shell.
- Do not add frontend-only fake filtering/sorting for SQL-backed results.
- Do not introduce a full-grid rewrite before the SQL-backed state model is working.
