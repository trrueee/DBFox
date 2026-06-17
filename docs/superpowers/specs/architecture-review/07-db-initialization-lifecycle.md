# Database Initialization Lifecycle Spec

Date: 2026-06-15
Priority: P1/P2
Area: Backend lifecycle

## Corrected Judgment

This is a real lifecycle smell, not an immediate security issue. `engine/db.py` opens SQLite and writes PRAGMAs during module import. That makes imports perform filesystem and database work before the app lifecycle has started.

## Code Evidence

- `engine/db.py:55-65` imports `sqlite3`, creates the SQLite file path, opens a connection, executes PRAGMA statements, and closes the connection at import time.
- `engine/db.py:67-78` creates the SQLAlchemy engine immediately after that.
- `engine/db.py:174-279` already has `init_db()`, the intended startup lifecycle function.

## Problem

Import-time database work can make tests harder to isolate, can fail before logging/lifespan setup is ready, and can surprise CLI scripts that only need metadata or configuration. It also spreads database lifecycle responsibilities across import and startup.

## Goals

- Move SQLite PRAGMA initialization into explicit startup lifecycle.
- Keep WAL, busy timeout, and synchronous settings.
- Preserve current behavior for FastAPI startup.
- Make tests able to set `DBFOX_DATABASE_URL` before initialization.

## Non-Goals

- Do not change the metastore database technology.
- Do not rewrite Alembic migration flow.
- Do not remove SQLAlchemy global engine in this spec unless needed for explicit initialization.

## Proposed Design

Add an explicit helper:

```python
def configure_sqlite_pragmas(database_url: str = DATABASE_URL) -> None:
    ...
```

Call it from `init_db()` before Alembic inspection/migration. Keep it no-op for non-SQLite URLs.

If the existing `engine` must still be module-level, ensure PRAGMA configuration is idempotent and called during startup, not import. Tests can call the helper explicitly when they bypass app startup.

## Acceptance Criteria

- Importing `engine.db` no longer opens a raw SQLite connection or creates the DB file.
- `init_db()` configures SQLite PRAGMAs before migrations.
- App startup still creates and migrates the metastore.
- Test DB URL overrides remain honored.

## Test Plan

- Unit test importing `engine.db` with a temporary `DBFOX_DATABASE_URL` does not create the file until `init_db()` or the helper runs.
- Unit test `configure_sqlite_pragmas` applies WAL/busy timeout for SQLite.
- Existing migration/startup tests pass.
