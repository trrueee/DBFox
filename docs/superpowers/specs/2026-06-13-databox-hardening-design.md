# DataBox Hardening Design

## Context

The current DataBox architecture is strong, but four gaps reduce product readiness and day-to-day maintainability:

1. `SchemaIntrospector` advertises PostgreSQL support through the product surface while returning an empty inventory for PostgreSQL and DuckDB.
2. `LongTermMemoryStore` has a production-shaped API but stores records only in process memory.
3. Frontend lint currently fails with React hook, Fast Refresh, and `any` issues.
4. `desktop/src/App.tsx` owns too many responsibilities: tab state, datasource state, conversation persistence, agent streaming, layout controls, and command wiring.

This design keeps the existing product model intact and makes targeted changes around those gaps.

## Goals

- Implement practical PostgreSQL and DuckDB schema introspection that returns tables, columns, foreign keys, sample rows, and row-count estimates where supported.
- Add a durable SQLite-backed long-term memory store behind the current memory API.
- Reduce frontend lint failures caused by `App.tsx` typing and extraction issues without changing the visible UI.
- Split the highest-risk `App.tsx` responsibilities into focused hooks/modules while keeping current behavior.
- Preserve existing public APIs and data models unless a local extension is necessary for implementation.

## Non-Goals

- No redesign of the Agent graph.
- No full frontend state-management migration to Redux, Zustand, or another global store.
- No migration of every frontend component to a new architecture.
- No cloud sync for memory records.
- No broad database feature expansion beyond introspection.

## Approach

### 1. Database Introspection

`engine/environment/schema_introspector.py` remains the orchestration point. SQLite and MySQL behavior stay compatible. PostgreSQL and DuckDB gain real implementations:

- PostgreSQL uses `psycopg2` and catalog queries against `information_schema` plus `pg_catalog` for comments and approximate row counts.
- DuckDB uses the Python `duckdb` package when installed. If the package is missing, introspection returns an empty inventory and logs a warning instead of crashing application startup.
- Identifier quoting is centralized in small helpers so sample and count queries avoid string interpolation hazards as much as possible.
- Tests cover PostgreSQL and DuckDB logic through fake connections/cursors, avoiding a hard dependency on real database servers.

### 2. Durable Long-Term Memory

The memory store API remains `put`, `upsert`, `delete`, `get`, `search`, `list_by_namespace`, `all`, and `count`.

Implementation adds a `SQLiteLongTermMemoryStore` in `engine/memory/long_term_store.py` or a small sibling module if the file becomes too large. It serializes `MemoryRecord` fields into a local SQLite table under the DataBox private runtime path. The module-level `get_long_term_store()` returns SQLite by default and can still return an in-memory store when `DATABOX_MEMORY_STORE=memory` is set for tests or local debugging.

Search semantics must match the current in-memory store:

- deleted records are hidden,
- expired records are skipped,
- namespace prefix filtering is preserved,
- type, status, confidence, user, project, datasource, keyword, and limit filters behave the same.

### 3. Frontend Lint and Typing

The first pass fixes lint failures that are both high-signal and low-risk:

- Replace `any[]` datasource/table state with imported API types.
- Remove `as any` tab type casts by relying on `WorkspaceTabType`.
- Move non-component exports out of UI component files where Fast Refresh complains, or relax only clearly generated/duplicated shadcn-style locations if moving would create noisy churn.
- Fix obvious React hook dependency and purity issues in files touched by the App extraction.

Because the current ESLint config includes stricter React compiler lint rules, the implementation should prefer code changes for app-owned code and minimal config exceptions only for library-style UI primitives.

### 4. App.tsx Responsibility Split

The extraction is intentionally narrow:

- `useWorkspaceTabs` owns tab array, active tab, tab patching, tab opening/closing helpers, and selected table context.
- `useDatasourceState` owns datasource loading, active datasource, table loading, schema refresh, and column prefetching.
- `useAgentRunner` owns `runAgentForTab`, approval handling, SSE event handling, agent abort controllers, and conversation persistence callbacks.

`App.tsx` remains the composition root. It wires hooks together and renders the existing layout. The visible UI should not change.

## Error Handling

- PostgreSQL/DuckDB connection or query failures return partial or empty inventories and log warnings, matching existing MySQL behavior.
- SQLite memory initialization creates the table lazily. Corrupt records are skipped with a warning instead of failing all memory reads.
- Agent streaming error messages stay unchanged for users.
- Lint fixes must not weaken TypeScript strictness.

## Testing

Backend:

- Add PostgreSQL/DuckDB introspection unit tests with fake cursor/connection objects.
- Add SQLite memory persistence tests that write through one store instance and read through another.
- Keep the existing policy gate test green by making `execute=False` produce the expected blocking reason before validation checks.
- Run targeted backend tests, then the non-e2e backend suite.

Frontend:

- Add or adjust hook tests where extraction creates meaningful pure logic.
- Run `npm test -- --run`.
- Run `npm run build`.
- Run `npm run lint`; remaining failures are acceptable only if documented and outside touched scope, but the target is to reduce the current lint output materially.

## Acceptance Criteria

- PostgreSQL and DuckDB introspection no longer return stub-only empty inventories when provided a valid fake or real connection path.
- Long-term memory survives process-level store recreation.
- The existing backend policy failure is fixed.
- Frontend tests and production build pass.
- `App.tsx` is smaller and delegates datasource, tab, and agent responsibilities to focused modules.
- The final report includes exact verification commands and any remaining lint/test gaps.
