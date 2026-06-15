# Security Guardrail Bypass Hardening Spec

Date: 2026-06-15
Priority: P3
Area: SQL execution safety
Primary files: `engine/sql/executor.py`, startup/config validation

## Problem

The SQL executor includes a `bypass_guardrail` test backdoor guarded by `DATABOX_TESTING=1` and environment checks. This is useful for tests but must be impossible to enable accidentally in production or packaged desktop builds.

## Goals

- Preserve explicit test bypass for automated tests.
- Add startup validation that fails closed in production.
- Make bypass usage auditable in logs.
- Prevent bypass in frozen builds regardless of environment variables.

## Non-Goals

- Do not remove existing guardrail or TrustGate tests.
- Do not add a user-facing bypass setting.
- Do not allow bypass for production datasource environments.

## Proposed Design

Add a central config predicate:

```python
def guardrail_bypass_allowed() -> bool:
    return (
        os.environ.get("DATABOX_TESTING") == "1"
        and not is_frozen_build()
        and os.environ.get("DATABOX_ALLOW_GUARDRAIL_BYPASS") == "1"
    )
```

Require both `DATABOX_TESTING=1` and `DATABOX_ALLOW_GUARDRAIL_BYPASS=1`.

At startup:

- If frozen build and either bypass env var is set, log critical and ignore the bypass.
- If non-test runtime sees bypass env var, warn and ignore.

In executor:

- Use only the central predicate.
- Log every accepted bypass at warning level with datasource id and environment.

## Acceptance Criteria

- Tests can still enable bypass explicitly.
- Frozen/production runtime cannot enable bypass even with env vars.
- Bypass checks are centralized.
- Logs clearly mark bypass usage.

## Test Plan

- Unit test bypass denied by default.
- Unit test bypass allowed only with both test env vars.
- Unit test frozen mode denies bypass despite env vars.
- Existing guardrail bypass tests updated to use the explicit env pair.

## Rollout

Coordinate with CI test environment by setting the new explicit bypass env var only for tests that need it.
