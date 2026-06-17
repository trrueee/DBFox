# Maintainability Debt Triage Spec

Date: 2026-06-15
Priority: P2/P3
Area: Code organization

## Corrected Judgment

Several large-file and boundary concerns are real, but the previous reports over-prioritized them. They should be treated as staged maintainability debt and handled only when adjacent feature work makes the boundary painful.

## Code Evidence

- `engine/models.py` is large, but current code already includes `__repr__` on important models such as `Project`, `DataSource`, `SchemaTable`, `SchemaColumn`, `QueryHistory`, `AgentSession`, `AgentRun`, and `AgentApproval`.
- `engine/sql/executor.py` is large and mixes guardrail resolution, execution, serialization, history logging, EXPLAIN, and schema validation.
- `engine/datasource.py` is large and mixes tunnel management, SSL mapping, connection params, and connection tests.
- `engine/agent/tools/registry_bridge.py` shows that some `agent` versus `agent_core` split is intentional adapter work, not automatically wrong.

## Problem

Large files slow understanding and make changes riskier, but splitting them without a feature reason can create churn. The correct plan is staged extraction around stable seams and compatibility wrappers.

## Goals

- Preserve stable public entry points.
- Extract modules only where there is clear ownership.
- Avoid treating every large file as urgent.
- Document intended boundaries for tools and agent layers.

## Non-Goals

- Do not split `models.py` immediately just because it is long.
- Do not merge all tool directories.
- Do not rewrite the Agent architecture in this batch.

## Proposed Design

Executor staged extraction:

- Keep `execute_query()` as the compatibility entry point.
- Extract low-risk helpers first:
  - connection config mapping;
  - row serialization;
  - EXPLAIN execution;
  - per-dialect execution functions after tests exist.

Datasource staged extraction:

- Keep `test_connection()` behavior stable.
- Extract per-dialect test helpers:
  - `_test_sqlite_connection`
  - `_test_mysql_connection`
  - `_test_postgres_connection`
- Share SSH/SSL config normalization with execution paths.

Models staged extraction:

- Do not split until migration/import boundaries are mapped.
- If split later, use domain modules plus compatibility re-exports from `engine/models.py`.

Agent/tool boundary:

- Document intended dependency direction:
  - `agent_core` defines contracts, types, and registries.
  - `agent` adapts those contracts to LangGraph/LangChain runtime.
  - `agent_core` should not depend on `agent` runtime implementation.

## Acceptance Criteria

- Any extraction keeps old imports working or updates all call sites in one change.
- Tests cover extracted behavior before moving dialect-specific executor code.
- `models.py` split is deferred until import/migration risks are reviewed.
- Tool directory cleanup focuses on registration and policy boundaries, not folder count alone.

## Test Plan

- Add characterization tests before moving executor or datasource functions.
- Run backend tests after each extraction step.
- Use import smoke tests for `engine.models` if models are ever split.
