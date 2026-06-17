# Guardrail Bypass and Policy Boundary Spec

Date: 2026-06-15
Priority: P1
Area: SQL execution safety

## Corrected Judgment

The previous spec overstated part of the issue. Current code already has a strong `guardrail_bypass_allowed()` predicate requiring both `DBFOX_TESTING=1` and `DBFOX_ALLOW_GUARDRAIL_BYPASS=1`, and it denies frozen builds. The remaining real issue is API shape: a general-purpose executor still exposes `bypass_guardrail` as a normal parameter.

## Code Evidence

- `engine/sql/executor.py:79-96` centralizes bypass gating and denies frozen builds.
- `engine/sql/executor.py:419-510` implements bypass decision logic.
- `engine/sql/executor.py:598-607` exposes `bypass_guardrail` on the general `execute_query` function.
- `engine/schemas/query.py:8-13` does not expose bypass in the public HTTP request schema.
- `engine/api/query.py:71-78` calls `PolicyEngine.enforce_query_policy` before `execute_query`.

## Problem

The HTTP API does not expose bypass, which is good. But a reusable production module exposes `execute_query(..., bypass_guardrail=True)`. Future internal callers can misuse it by accident. Environment gates are necessary, but the safer boundary is to remove bypass from the ordinary execution path and keep it behind test-only or fixture-only helpers.

## Goals

- Keep test-only bypass for controlled automated tests.
- Prevent production application code from calling bypass through the standard executor.
- Clarify the order and responsibilities of `PolicyEngine`, Guardrail, and TrustGate.
- Keep existing SQL safety behavior for user and Agent execution.

## Non-Goals

- Do not remove Guardrail or TrustGate.
- Do not remove test fixtures that need unsafe SQL setup.
- Do not turn layered safety checks into one monolithic checker.

## Proposed Design

Split the execution boundary:

- Public/internal normal path:
  - `execute_query(db, datasource_id, sql_str, ..., safety_decision=None, safety_policy="readonly")`
  - no `bypass_guardrail` parameter.

- Test fixture path:
  - `execute_query_for_test_fixture(...)` or `unsafe_execute_for_seed_data(...)`
  - lives in a clearly named test support module or a private executor function.
  - checks `guardrail_bypass_allowed()`.
  - refuses frozen builds and non-dev/test datasource environments.
  - logs usage at warning level.

Clarify policy order in code comments or docs:

1. `PolicyEngine` handles datasource-level and product policy before request reaches execution.
2. TrustGate owns AST guardrail, schema validation, dry-run, and approval requirements.
3. Executor only executes an approved `safe_sql`.

## Acceptance Criteria

- Normal app code cannot pass `bypass_guardrail` to `execute_query`.
- All tests that need bypass call an explicitly unsafe test helper.
- Bypass remains denied without both test env vars.
- Bypass remains denied in frozen builds.
- Bypass remains denied for prod datasource environments.
- Policy order is documented near the executor or TrustGate boundary.

## Test Plan

- Update existing bypass tests to call the explicit test helper.
- Add a unit test proving normal `execute_query` has no bypass parameter.
- Add tests for bypass denied by default, denied in frozen mode, and denied on prod datasource env.
- Run existing SQL guardrail, TrustGate, and executor tests.
