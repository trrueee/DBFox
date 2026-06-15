# Backend SQL Executor Profiling Refactor Spec

Date: 2026-06-15
Priority: P5
Area: Backend SQL execution
Primary files: `engine/sql/executor.py`

## Problem

Profiled and unprofiled SQL execution functions duplicate most of their logic. For example, MySQL and PostgreSQL variants differ mainly in whether timing/profile metadata is returned. Duplication increases the chance that safety, timeout, or result-shaping changes land in one path but not the other.

## Goals

- Unify profiled and unprofiled execution paths per dialect.
- Keep public function behavior backward compatible.
- Reduce duplicated query execution, row conversion, and error handling code.
- Make timing/profile collection opt-in.

## Non-Goals

- Do not change SQL guardrail behavior.
- Do not change result table shape.
- Do not rewrite database dialect support.

## Proposed Design

Introduce a shared internal execution helper:

```python
def _execute_on_mysql_core(..., profile: bool = False) -> SqlExecutionInternalResult:
    ...
```

Use a small dataclass for internal return:

```python
@dataclass
class SqlExecutionInternalResult:
    rows: list[dict[str, Any]]
    columns: list[str]
    row_count: int
    elapsed_ms: int | None = None
    profile: dict[str, Any] | None = None
```

Public unprofiled functions unwrap only the existing result fields. Public profiled functions include timing/profile fields exactly as before.

Repeat the same pattern for PostgreSQL. If MySQL and PostgreSQL can share more code safely, extract only the dialect-independent parts such as row conversion and timing context.

## Acceptance Criteria

- Existing unprofiled SQL execution tests pass unchanged.
- Existing profiled execution behavior and keys remain unchanged.
- Duplicated database cursor/connection code is reduced.
- New helper tests cover both profile false and profile true behavior.

## Test Plan

- Add tests around helper behavior using fake cursor/connection objects if available.
- Run existing executor tests.
- Add regression test proving profiled and unprofiled paths return the same rows for the same query.

## Rollout

Do this as a refactor-only branch. No UI or API behavior changes should ship with it.
