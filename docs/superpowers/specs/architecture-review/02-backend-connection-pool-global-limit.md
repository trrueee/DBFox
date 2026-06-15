# Backend Global Connection Pool Limit Spec

Date: 2026-06-15
Priority: P2
Area: Backend SQL execution
Primary files: `engine/sql/executor.py`

## Problem

`engine/sql/executor.py` keeps `_MYSQL_POOLS` and `_POSTGRES_POOLS` as module-level dictionaries keyed by datasource and connection parameters. Each datasource can create its own SQLAlchemy `QueuePool`. With many saved data sources, total open connections can exceed database `max_connections` or local resource limits.

## Goals

- Bound total database connections across all datasource pools.
- Keep existing per-datasource pooling behavior for common use.
- Make pool eviction predictable and observable.
- Avoid breaking SQLite execution.

## Non-Goals

- Do not build a distributed pool manager.
- Do not auto-detect remote database `max_connections`.
- Do not change SQL safety behavior.

## Proposed Design

Introduce a `PoolRegistry` in `engine/sql/executor.py` or a new `engine/sql/pool_registry.py`.

Registry responsibilities:

- Track MySQL and PostgreSQL pools in one place.
- Enforce configurable global limits:
  - `DATABOX_SQL_MAX_POOLS`, default `16`.
  - `DATABOX_SQL_MAX_CONNECTIONS`, default `64`.
- Maintain last-used timestamps per pool.
- Evict least-recently-used idle pools when adding a new pool would exceed limits.
- Dispose evicted SQLAlchemy engines cleanly.
- Expose a lightweight diagnostic snapshot for tests and logs.

Pool key remains based on datasource id plus connection parameters so credential changes create a new pool.

## Acceptance Criteria

- Creating pools beyond `DATABOX_SQL_MAX_POOLS` evicts least-recently-used idle pools.
- Total configured pool capacity never exceeds `DATABOX_SQL_MAX_CONNECTIONS`.
- Evicted pools call `.dispose()`.
- Active query execution is not interrupted by eviction of unrelated pools.
- Existing MySQL/PostgreSQL execution tests pass.

## Test Plan

- Unit test registry LRU eviction with fake pool objects.
- Unit test connection-capacity accounting.
- Integration-style test that repeated datasource ids reuse the same pool.
- Regression test that SQLite execution bypasses the registry.

## Rollout

Use conservative defaults and log evictions at info level. If users hit limits, they can tune environment variables without changing code.
