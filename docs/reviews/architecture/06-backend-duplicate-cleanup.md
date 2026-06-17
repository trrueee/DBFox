# Backend Duplicate Cleanup Spec

Date: 2026-06-15
Priority: P1/P2
Area: Backend maintainability

## Corrected Judgment

These are real but low-risk refactors. They should not be described as critical security failures. They are worth doing because each duplicated shape is small, clear, and likely to drift.

## Code Evidence

- `engine/datasource.py:564-592` defines `datasource_connection_dict`.
- `engine/sql/executor.py:684` uses `datasource_connection_dict(ds)` for PostgreSQL execution.
- `engine/sql/executor.py:692-713` manually rebuilds the MySQL datasource dict.
- `engine/sql/executor.py:878-899` manually rebuilds the MySQL datasource dict again for EXPLAIN.
- `engine/api/datasources.py:146-148` wraps `engine.api.projects._resolve_project_id`.
- `engine/api/backup.py:59-66` repeats the same wrapper pattern.
- `engine/api/agent.py:298-336` and `engine/api/agent.py:358-396` duplicate SSE error payload construction.

## Problem

Small duplicated conversion and error-shaping code makes future changes easy to miss. For example, adding a new SSL/SSH field requires updating helper and manual dicts. Changing SSE error shape requires editing two streaming routes.

## Goals

- Centralize datasource-to-connection dict conversion.
- Centralize project ID resolution import/wrapper.
- Centralize Agent SSE failure event construction.
- Keep behavior identical.

## Non-Goals

- Do not rewrite datasource connection handling wholesale.
- Do not change streaming protocol event names.
- Do not merge unrelated API modules.

## Proposed Design

Datasource connection dict:

- Use `datasource_connection_dict(ds)` in all executor paths that need raw connection metadata.
- Prefer a typed helper return alias if practical:

```python
DatasourceConnectionConfig = dict[str, Any]
```

Project ID resolution:

- Move reusable project resolution into a non-route module, for example `engine/projects/service.py`.
- API route modules import from that service, not from each other.

SSE error payload:

- Add one helper in `engine/api/agent.py` or a nearby streaming utility:

```python
def sse_failed_event(
    *,
    event_id: str,
    run_id: str,
    message: str,
    code: str,
) -> str:
    ...
```

- Use it for run stream and resume stream error handling.

## Acceptance Criteria

- No manual MySQL datasource dicts remain in `engine/sql/executor.py`.
- Route modules no longer locally wrap `engine.api.projects._resolve_project_id`.
- Agent run and resume streaming routes use one helper for failed SSE events.
- Existing response shapes remain byte-compatible except for field ordering.

## Test Plan

- Unit test `datasource_connection_dict` includes all SSH and SSL fields used by MySQL/PostgreSQL helpers.
- Existing datasource health/sync tests pass.
- Agent streaming error tests, if present, continue to pass; otherwise add a small unit test for the failed SSE helper.
- Run backend tests that cover datasource and Agent API routes.

## Verification (2026-06-17)

**Status: ✅ RESOLVED**

Three of four items were already done; the fourth fixed now:

| Item | Status | Detail |
|------|--------|--------|
| Datasource connection dict | ✅ Fixed | `backup.py` local `_datasource_connection_dict` removed; now imports canonical `datasource_connection_dict` from `engine.datasource` |
| Project ID resolution | ✅ Already | Both `datasources.py` and `backup.py` use `from engine.projects.service import resolve_project_id` |
| SSE failure event | ✅ Already | `sse_failed_event()` at `agent.py:127` used uniformly for run and resume streams |
| Manual MySQL dicts | ✅ Already | No manual dict construction remains in `executor.py`; all paths use `datasource_connection_dict(ds)` |

491 tests pass.
