# SQL-backed Data View Productization Design

Date: 2026-06-23  
Status: Design approved for planning

## Goal

Make DBFox's database browsing and Agent result artifacts share one SQL-backed data view architecture, so large query results are never treated as long-lived frontend/backend application state and are never fully handed to the AI.

## Architecture

DBFox should keep two product entry points: the database browser tab for real database exploration, and the artifact result tab for Agent-produced query evidence. Both entries should render through a shared SQL-backed query capability, where view state is `page`, `pageSize`, `filters`, `sort`, `search`, and export intent, while the actual rows are fetched from the database by derived read-only SQL. The shared abstraction is not a visual table component; it is a query/view contract called `SqlBackedDataView`.

## Tech Stack

FastAPI, SQLAlchemy, Pydantic, sqlglot, React, TypeScript, Zustand, existing table/artifact workspace components, Vitest/Testing Library, pytest.

---

## Architecture Principle

DBFox must not move "large data results" around as application state.

Large result sets are represented by SQL-backed views:

- Store SQL, source identity, columns, small previews, execution metadata, and safety metadata.
- Fetch visible pages on demand by deriving SQL from a validated base query.
- Apply filter, search, sort, count, and export through backend SQL, not frontend-only row arrays.
- Allow the Agent to inspect samples and aggregate outputs, then write more SQL when it needs more evidence.
- Do not put complete result sets into artifact payloads, conversation state, frontend store, or LLM context.

Small payload tables may remain as compatibility fallback for legacy artifacts or genuinely tiny results, but the preferred path for any database-backed result is `sql_backed`.

## Current State Audit

### Database Browsing Chain

Current chain:

```text
DataSourceTree -> openTableTab -> TableWorkspace -> TablePreviewPane/TableSchemaPane/TableErPane
```

This is the real database browsing entry and should stay that way.

Current issues:

- `TablePreviewPane` hand-writes pagination and table rendering.
- It builds direct preview SQL with `LIMIT pageSize + 1 OFFSET ...`, which is good for not loading the full table.
- It clears `data` when page/page size changes if the cache misses, causing skeleton/layout jumps.
- Filter, sort, and export toolbar actions are toast placeholders.
- Footer/buttons include inline sizing and the table does not have a stable product-grade viewport.

### Agent Artifact Result Chain

Current chain:

```text
ArtifactDock -> TableArtifactView -> useArtifactTableData
```

This is the Agent evidence/result entry and should stay separate from database browsing.

Current strengths:

- `result_view` already supports `storageMode: "sql_backed"`.
- Frontend already calls `/agent/results/page` for SQL-backed workspace results.
- The model already keeps `sourceSqlSemanticId`, `sourceSql`, `safeSql`, `datasourceId`, `columns`, and preview rows.

Current issues:

- SQL-backed artifact filtering/search/export are incomplete.
- Sorting is only partly wired.
- Export currently behaves like current frontend rows, not all rows matching the current SQL-backed view state.
- UI still feels like a temporary result card instead of a durable data view.
- Payload rows are still used as fallback and need clear boundaries.

### Backend SQL-backed Capability

Current endpoint:

```text
POST /agent/results/page
```

Current strengths:

- `ResultPageRequest` and `ResultPageResponse` already exist.
- The endpoint verifies datasource scope.
- It loads the persisted source artifact by id or semantic id.
- It rejects missing or mismatched `safeSql`.
- It validates that the source SQL is a single read-only `SELECT`.
- It validates sort columns against the source artifact columns.
- It wraps the persisted safe SQL as a derived query and applies pagination.

Current gaps:

- `filters` and `search` exist in the request type but are not applied to derived SQL.
- `build_derived_sql` supports pagination and sorting only.
- There is no unified SQL-backed export API.
- Count behavior needs to be explicit: none, estimate, or exact.

## Keep

- Keep the Agent `sql` plus `result_view` artifact model.
- Keep `/agent/results/page` and its persisted safe SQL verification approach.
- Keep the database tree and table tab as the real database browsing entry.
- Keep artifact result tabs as the Agent result/evidence entry.
- Keep the Agent design where AI generates, validates, repairs, and executes SQL progressively.
- Keep the rule that AI should analyze via SQL, not by receiving complete raw data dumps.

## Integrate

The integration point is a query abstraction, not a UI component.

```text
SqlBackedDataView
  state:
    page
    pageSize
    filters
    sort
    search
  data:
    columns
    rows
    rowCount
    hasNextPage
    executedSql
    warnings
    notices
    latencyMs
  behavior:
    lastStableData
    loadingMode
    refresh()
    exportAll()
```

There are two source adapters:

```text
DatabaseTableSource
  datasourceId
  tableName
  schema metadata
  baseSql = SELECT <visible columns> FROM <table>

ArtifactResultSource
  datasourceId
  sourceSqlArtifactId
  persisted safeSql
  columns
  baseSql = persisted safeSql from result_view/sql artifact
```

The same SQL-backed query engine should support both, but the two product surfaces keep different language and affordances.

## Backend Design

### Source Contracts

Introduce a backend-level source model that can represent both database tables and artifacts.

For database table browsing:

- Source is scoped by `datasourceId` and table name.
- Columns come from schema metadata.
- The server builds a base SQL using quoted identifiers.
- The base SQL is never trusted from the client.

For Agent artifact results:

- Source is scoped by `datasourceId` and source artifact id/semantic id.
- Columns come from the persisted artifact payload.
- Base SQL is the persisted `safeSql`.
- Client-provided `safeSql` must match persisted safe SQL while compatibility requires it; the long-term source of truth remains the persisted artifact.

### Derived SQL

Extend `build_derived_sql` into a safe derived-query builder.

Rules:

- Parse the base SQL with sqlglot.
- Accept only a single `SELECT`.
- Wrap as:

```sql
SELECT *
FROM (<base_sql>) AS dbfox_result
```

- Apply filters/search/sort outside the subquery.
- Apply `LIMIT pageSize + 1` and `OFFSET`.
- Validate the final derived SQL as a single read-only `SELECT`.
- Execute with an internal safety decision that records the derived SQL lineage.

### Filter Rules

Filters must be structured, not raw SQL fragments.

Supported operators:

```text
equals
not_equals
contains
starts_with
ends_with
gt
gte
lt
lte
is_null
is_not_null
in
not_in
```

Safety rules:

- Filter column must exist in the source column whitelist.
- Operator must be from the whitelist.
- Values are rendered through sqlglot literals or bound parameters where supported by the existing execution layer.
- Empty filters are ignored.
- Invalid filters return a structured 400 error; they do not silently fall back to frontend filtering.

### Search Rules

Search is a global convenience filter.

Rules:

- Search applies only to a bounded list of searchable columns.
- Prefer string-like columns from schema metadata when available.
- For artifact sources without types, search may apply to visible columns with explicit casting.
- Search is escaped and rendered as safe `LIKE`/dialect equivalent.
- Search must run in SQL so paging and total counts match the visible result.

### Sorting Rules

Sorting stays SQL-backed.

Rules:

- Sort column must exist in the source column whitelist.
- Direction is only `asc` or `desc`.
- Multi-column sort is supported by the request model, but UI can start with one active column.
- Sorting should reset page to 1.

### Count Rules

Count mode is explicit:

```text
none      no total count, only hasNextPage
estimate  use available metadata when cheap; otherwise omit rowCount
exact     run SELECT COUNT(*) FROM (<filtered source>) AS dbfox_count
```

The default for interactive browsing should be `estimate` or `none`, not exact, to avoid expensive counts on large tables.

### Export

Export must mean "all rows matching the current view state", not "current page".

Add a SQL-backed CSV export path:

```text
POST /sql-backed/export
```

or a scoped Agent endpoint if the first implementation keeps artifact-specific routing:

```text
POST /agent/results/export
```

Behavior:

- Reuse the same source verification and derived SQL builder.
- Apply the current filters/search/sort.
- Do not apply page/pageSize.
- Stream CSV from the backend.
- Enforce export safety limits, cancellation, timeout, and query history.
- The frontend receives a file stream, not a giant JSON row array.

## Frontend Design

### Shared Hook

Create a shared hook:

```text
useSqlBackedDataView(source, options)
```

State:

- `page`
- `pageSize`
- `filters`
- `sort`
- `search`
- `loadingMode`
- `lastStableData`
- `error`

Derived data:

- `data`
- `rows`
- `columns`
- `rowCount`
- `hasNextPage`
- `executedSql`
- `warnings`
- `notices`
- `latencyMs`

Behavior:

- Keep `lastStableData` during pagination, sorting, searching, and refresh.
- Use a thin loading bar or footer status for background fetches.
- Use skeleton only when there is no stable data.
- Abort stale requests or ignore stale responses with a request sequence.
- Reset page to 1 when filters/search/sort/page size changes.
- Expose `exportAll()` for SQL-backed export.

### Database Table View

`TablePreviewPane` should become the database-specific shell around `SqlBackedDataView`.

It should not become the artifact table component.

Product behavior:

- Toolbar: refresh, filter, sort, column visibility, export, open SQL.
- Table body: stable height, sticky header, stable column sizing, empty/error overlays that do not change layout.
- Footer: current page, page size, visible range, latency, count mode, has-next status.
- Page changes preserve current rows until the next page arrives.
- Filters/sort/search are real SQL-backed state.
- Export exports all matching rows through backend SQL.

Database table tabs remain:

```text
Preview | Schema | ER
```

The ER tab should use the existing schema metadata and eventually the existing ReactFlow-based ER diagram component.

### Agent Result View

`TableArtifactView` should keep the artifact product semantics but delegate SQL-backed data behavior to the shared hook.

Inline mode:

- Show a compact preview.
- Show SQL-backed badge/source status.
- Do not expose the full tool surface.
- Offer open-as-tab for full exploration.

Workspace tab mode:

- Toolbar: filter, sort, search, export all, copy current page, open SQL.
- Show source SQL, execution time, truncation/count status, and SQL-backed status.
- Page/sort/filter/search all call backend SQL.
- Export all uses the SQL-backed export endpoint.

Payload fallback:

- Legacy or tiny payload artifacts may keep local rows.
- Local filtering/sorting is allowed only for payload artifacts.
- UI should label this as a payload result, not SQL-backed.
- New Agent-generated database results should prefer `result_view.storageMode = "sql_backed"`.

## Agent Artifact Strategy

Agent outputs should prioritize references and evidence, not raw data payloads.

Preferred artifacts:

```text
sql
  safeSql
  originalSql
  purpose
  table dependencies
  validation status
  execution status

result_view
  storageMode = "sql_backed"
  datasourceId
  sourceSqlSemanticId
  sourceSql
  safeSql
  columns
  previewRows
  previewRowCount
  rowCount when cheap
  latencyMs
  warnings/notices
```

Rules:

- Do not persist complete large result sets to `payload.rows`.
- Keep only small previews for immediate answer grounding.
- If the Agent needs a different slice, it should write another SQL query.
- Final answers should cite result artifacts and summarize findings, not embed massive raw tables.

## Product Design Requirements

### Database Browsing

Database browsing should feel like a durable database tool:

- Stable table viewport.
- Sticky headers.
- Real toolbar actions.
- Clear SQL provenance via "Open SQL".
- No layout shift during paging.
- Empty states that explain whether the table is empty, filters matched nothing, or the query failed.
- Schema and ER remain nearby as database-specific views.

### Artifact Results

Artifact results should feel like query evidence:

- Clear result title and source SQL.
- SQL-backed badge when the result can be re-queried.
- Query timing, truncation, count mode, and warnings visible but quiet.
- Inline preview stays lightweight.
- Full tab unlocks database-like exploration tools.

## Explicit Non-goals

- Do not merge database browsing into the artifact table UI.
- Do not treat Agent result artifacts as full data caches.
- Do not implement filter/sort only against the current frontend page.
- Do not clear the main content area during pagination or refresh.
- Do not pass complete large result sets to the LLM.
- Do not replace the existing SQL validation and persisted safe SQL verification model.

## Error Handling

Backend errors should be structured:

```text
SOURCE_NOT_FOUND
SOURCE_SQL_MISSING
SOURCE_SQL_MISMATCH
SOURCE_COLUMNS_MISSING
FILTER_COLUMN_NOT_ALLOWED
FILTER_OPERATOR_NOT_ALLOWED
SORT_COLUMN_NOT_ALLOWED
DERIVED_SQL_BUILD_FAILED
DERIVED_SQL_VALIDATION_FAILED
EXPORT_LIMIT_EXCEEDED
```

Frontend behavior:

- Keep `lastStableData` visible on background failures.
- Show inline error banner or footer error for refresh/page failures.
- Show empty state only for successful zero-row results.
- Do not hide warnings/notices produced by the backend.

## Testing Strategy

Backend pytest:

- Derived SQL applies filters, search, sort, limit, and offset.
- Invalid filter columns are rejected.
- Invalid operators are rejected.
- Sort columns outside the source columns are rejected.
- Artifact pagination still rejects safe SQL mismatches.
- Database table sources build quoted SQL from metadata, not client raw SQL.
- Export reuses the same filtered/sorted source and does not apply page limit.

Frontend Vitest:

- `useSqlBackedDataView` keeps last stable rows during page changes.
- Sorting/search/filter resets page to 1.
- Stale responses do not overwrite newer data.
- Database table preview no longer clears into skeleton during pagination.
- Artifact result view uses backend pagination for `sql_backed` results.
- Payload artifacts still use local fallback.
- Export all calls the SQL-backed export path with current filters/search/sort.

Visual checks:

- Database preview page does not jump during pagination.
- Artifact result tab has stable split-pane sizing.
- Toolbars and footers do not resize when loading.
- Empty/error/loading states preserve the table viewport.

## Implementation Slices

1. Define shared SQL-backed request/response/source types and tests.
2. Extend backend derived SQL builder with filters/search/sort/count tests.
3. Add SQL-backed export endpoint with streaming CSV tests.
4. Add `useSqlBackedDataView` with last-stable-data and request sequencing.
5. Refactor `TablePreviewPane` onto `DatabaseTableSource`.
6. Refactor SQL-backed `TableArtifactView/useArtifactTableData` onto `ArtifactResultSource`.
7. Productize table toolbar/footer/empty/error states for both surfaces.
8. Tighten Agent artifact generation so new database results prefer SQL-backed `result_view`.
9. Add focused regressions and run full frontend/backend verification.

## Open Implementation Decisions

- Whether the shared backend endpoint is introduced as `/sql-backed/page` immediately, or `/agent/results/page` is extended first and generalized afterward.
- Whether export first ships as artifact-only or shared SQL-backed export.
- Whether database table source uses all columns by default or visible-column selection from the first slice.

Recommended choices:

- Keep `/agent/results/page` compatible, but introduce shared internal service functions so database table preview and artifacts do not duplicate derived SQL logic.
- Build export through the shared internal service even if the route starts artifact-specific.
- Start database table browsing with all columns, then add visible-column selection as a UI enhancement.

