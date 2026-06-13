# DataBox Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the named product-readiness gaps around database introspection, durable long-term memory, frontend lint, and `App.tsx` responsibility boundaries.

**Architecture:** Keep existing public APIs stable. Extend backend services behind their current interfaces, and extract frontend stateful behavior into feature hooks while leaving `App.tsx` as the composition root.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Pydantic, SQLite, psycopg2, optional duckdb, React 19, TypeScript, Vite, Vitest, ESLint.

---

## File Structure

- Modify `engine/environment/schema_introspector.py`: add PostgreSQL and DuckDB implementations plus identifier quoting helpers.
- Modify `engine/policy/gate.py`: make `execute=False` block SQL execution before SQL validation.
- Modify `engine/memory/long_term_store.py`: add SQLite-backed durable store and keep in-memory implementation for tests.
- Add `engine/tests/test_memory_long_term_store.py`: persistence and search contract tests.
- Expand `engine/tests/test_schema_introspector.py`: fake PostgreSQL/DuckDB connection tests.
- Modify `desktop/src/App.tsx`: compose extracted hooks and remove local `any` casts.
- Add `desktop/src/features/workspace/useWorkspaceTabs.ts`: tab and table-selection state.
- Add `desktop/src/features/datasource/useDatasourceState.ts`: datasource/table/column loading state.
- Add `desktop/src/features/agentTask/useAgentRunner.ts`: agent streaming, approval, and persistence orchestration.
- Modify `desktop/src/features/engine/engineApi.ts`: reuse exported API types where needed.
- Modify `desktop/eslint.config.js`: only add scoped Fast Refresh ignores for UI primitive modules if moving exports creates noisy churn.

---

### Task 1: Backend Policy Gate Regression

**Files:**
- Modify: `engine/policy/gate.py`
- Test: `engine/agent/tests/test_policy_gate.py`

- [ ] **Step 1: Verify existing regression test fails**

Run:

```powershell
python -m pytest engine\agent\tests\test_policy_gate.py::TestSqlExecutionPolicy::test_execute_disabled_in_state -q
```

Expected: FAIL because the reason says SQL validation is required instead of live execution being disallowed.

- [ ] **Step 2: Move execute-mode block before SQL validation**

In `PolicyGate.check`, when `policy.requires_validated_sql` is true, compute effective mode and return a blocked decision before reading `state["safety"]`:

```python
if policy.requires_validated_sql:
    effective_mode = execution_mode
    if execution_mode == "user_requested_read" and not state.get("execute", True):
        effective_mode = "suggest_only"
    if effective_mode in ("none", "suggest_only"):
        return PolicyDecision(
            status="blocked",
            reason=f"SQL execution is not allowed in {effective_mode} mode.",
            risk_level="danger",
        )
```

- [ ] **Step 3: Verify policy test passes**

Run:

```powershell
python -m pytest engine\agent\tests\test_policy_gate.py::TestSqlExecutionPolicy::test_execute_disabled_in_state -q
```

Expected: PASS.

---

### Task 2: PostgreSQL and DuckDB Introspection Tests

**Files:**
- Modify: `engine/tests/test_schema_introspector.py`

- [ ] **Step 1: Add fake cursor/connection helpers**

Add small fake classes that capture SQL and return deterministic rows for table, column, foreign-key, sample, and count queries. Keep helpers local to the test file.

- [ ] **Step 2: Add PostgreSQL test**

Add a test that monkeypatches `_connect_postgres` to return the fake connection and asserts:

```python
inventory.dialect == "postgres"
inventory.table_count == 1
inventory.column_count == 2
inventory.tables[0].table_schema == "public"
inventory.tables[0].table_name == "orders"
inventory.tables[0].columns[0].is_primary_key is True
inventory.tables[0].foreign_keys[0].referenced_table == "customers"
```

- [ ] **Step 3: Add DuckDB test**

Add a test that monkeypatches `_connect_duckdb` to return the fake connection and asserts a non-empty inventory with sample rows.

- [ ] **Step 4: Run tests to verify they fail before implementation**

Run:

```powershell
python -m pytest engine\tests\test_schema_introspector.py -q
```

Expected: FAIL because `_connect_postgres`, `_connect_duckdb`, or concrete inspection paths are missing.

---

### Task 3: PostgreSQL and DuckDB Introspection Implementation

**Files:**
- Modify: `engine/environment/schema_introspector.py`
- Test: `engine/tests/test_schema_introspector.py`

- [ ] **Step 1: Add connection helpers**

Implement `_connect_postgres(db, resolved)` with `psycopg2.connect` and decrypted password. Implement `_connect_duckdb(resolved)` with optional `import duckdb`.

- [ ] **Step 2: Add identifier quoting helpers**

Add:

```python
def _quote_sql_identifier(identifier: str, quote: str = '"') -> str:
    return quote + identifier.replace(quote, quote + quote) + quote

def _qualified_name(schema: str, table: str, quote: str = '"') -> str:
    if schema:
        return f"{_quote_sql_identifier(schema, quote)}.{_quote_sql_identifier(table, quote)}"
    return _quote_sql_identifier(table, quote)
```

- [ ] **Step 3: Implement `_inspect_postgres`**

Query user schemas from `information_schema.tables`, columns from `information_schema.columns`, keys from `information_schema.table_constraints` and `key_column_usage`, and approximate row counts from `pg_class.reltuples`. Use `LIMIT 3` samples.

- [ ] **Step 4: Implement `_inspect_duckdb`**

Use `information_schema.tables`, `information_schema.columns`, and `information_schema.key_column_usage` when available. Use exact `COUNT(*)` and `LIMIT 3` samples.

- [ ] **Step 5: Verify schema introspection tests pass**

Run:

```powershell
python -m pytest engine\tests\test_schema_introspector.py -q
```

Expected: PASS.

---

### Task 4: Durable Memory Store Tests

**Files:**
- Add: `engine/tests/test_memory_long_term_store.py`

- [ ] **Step 1: Add persistence test**

Create a `SQLiteLongTermMemoryStore` at a temp file, upsert a record, create a second store at the same path, and assert the second store can read the record.

- [ ] **Step 2: Add search contract test**

Write active, deleted, expired, low-confidence, and different-namespace records. Assert `search()` preserves existing filters.

- [ ] **Step 3: Run tests to verify they fail before implementation**

Run:

```powershell
python -m pytest engine\tests\test_memory_long_term_store.py -q
```

Expected: FAIL because `SQLiteLongTermMemoryStore` does not exist.

---

### Task 5: Durable Memory Store Implementation

**Files:**
- Modify: `engine/memory/long_term_store.py`
- Test: `engine/tests/test_memory_long_term_store.py`

- [ ] **Step 1: Add SQLite schema**

Create a table `long_term_memories` with columns for id, namespace JSON, type, content JSON, text, source, confidence, status, timestamps, scope ids, and tags JSON.

- [ ] **Step 2: Implement serialization helpers**

Use `record.model_dump(mode="json")` and `MemoryRecord.model_validate(payload)` so Pydantic remains the source of truth.

- [ ] **Step 3: Implement `SQLiteLongTermMemoryStore`**

Mirror the in-memory store methods exactly. Search can load candidate records and apply the same in-Python filtering logic used by the existing store.

- [ ] **Step 4: Add store selection**

`get_long_term_store()` returns in-memory when `DATABOX_MEMORY_STORE=memory`; otherwise it uses `private_runtime_file("memory", "long_term_memory.sqlite")`.

- [ ] **Step 5: Verify memory tests pass**

Run:

```powershell
python -m pytest engine\tests\test_memory_long_term_store.py -q
```

Expected: PASS.

---

### Task 6: Frontend Hook Extraction

**Files:**
- Add: `desktop/src/features/workspace/useWorkspaceTabs.ts`
- Add: `desktop/src/features/datasource/useDatasourceState.ts`
- Add: `desktop/src/features/agentTask/useAgentRunner.ts`
- Modify: `desktop/src/App.tsx`

- [ ] **Step 1: Extract datasource state**

Move datasource loading, table loading, schema refresh, active datasource calculation, and column prefetch into `useDatasourceState`. Use `EngineDataSource`, `EngineSchemaTable`, and `EngineColumn` types from `engineApi.ts`.

- [ ] **Step 2: Extract tab helpers**

Move `tabs`, `activeTabId`, `selectedTables`, `contextTables`, `tableSubTabs`, `patchTab`, `appendTabMessages`, `updateTabMessage`, and table/tab opening helpers into `useWorkspaceTabs`.

- [ ] **Step 3: Extract agent runner**

Move streaming and approval logic into `useAgentRunner`. Pass callbacks for toast, conversation persistence, active datasource id, context tables, and tab patching.

- [ ] **Step 4: Keep App as composition root**

`App.tsx` imports hooks, wires command palette and render branches, and keeps layout-only state locally.

- [ ] **Step 5: Verify TypeScript build**

Run:

```powershell
npm run build
```

Expected: PASS.

---

### Task 7: Frontend Lint Reduction

**Files:**
- Modify: `desktop/src/App.tsx`
- Modify: hook files from Task 6
- Modify: `desktop/eslint.config.js` only if needed

- [ ] **Step 1: Remove app-owned `any`**

Replace `any[]` and `as any` in `App.tsx` with concrete local or imported types.

- [ ] **Step 2: Resolve high-signal hook issues in touched files**

Use `useCallback` for callbacks passed into effects or hooks. Move impure `Date.now()` initialization into lazy refs or event-only helper functions where lint requires it.

- [ ] **Step 3: Scope Fast Refresh handling**

If UI primitive modules still fail only because they export class helpers or setup functions, add a scoped ESLint override for those primitive files rather than rewriting every UI primitive.

- [ ] **Step 4: Run frontend lint**

Run:

```powershell
npm run lint
```

Expected: materially fewer errors than the original 53 errors. If any remain, record exact files and reasons.

---

### Task 8: Full Verification

**Files:**
- No new code unless verification reveals a failure in touched scope.

- [ ] **Step 1: Run targeted backend tests**

Run:

```powershell
python -m pytest engine\agent\tests\test_policy_gate.py::TestSqlExecutionPolicy::test_execute_disabled_in_state engine\tests\test_schema_introspector.py engine\tests\test_memory_long_term_store.py -q
```

- [ ] **Step 2: Run backend non-e2e suite**

Run:

```powershell
python -m pytest -q -m "not e2e and not integration and not slow"
```

- [ ] **Step 3: Run frontend tests**

Run:

```powershell
npm test -- --run
```

- [ ] **Step 4: Run frontend build**

Run:

```powershell
npm run build
```

- [ ] **Step 5: Run frontend lint**

Run:

```powershell
npm run lint
```

- [ ] **Step 6: Review diff**

Run:

```powershell
git diff --stat
git diff --check
```

Expected: no whitespace errors, touched files match the design scope, and final report lists any command failures honestly.
