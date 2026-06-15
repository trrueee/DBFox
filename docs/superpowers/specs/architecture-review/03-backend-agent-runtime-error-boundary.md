# Backend Agent Runtime Error Boundary Spec

Date: 2026-06-15
Priority: P3
Area: Backend Agent runtime
Primary files: `engine/agent/runtime.py`, `engine/api/agent.py`, `engine/errors.py`

## Problem

`DataBoxAgentRuntime.run()` delegates directly to `DataBoxAgentService`. If lower layers raise unexpected exceptions, the API layer may receive internal exceptions without a consistent `DataBoxError` envelope.

## Goals

- Convert unexpected runtime failures into stable DataBox error types.
- Preserve original `DataBoxError` subclasses unchanged.
- Keep enough logging context for debugging.
- Prevent leaking stack traces or internal object details to API responses.

## Non-Goals

- Do not change agent graph execution semantics.
- Do not change SSE event formats except for stable error events where needed.
- Do not mask cancellation or user-rejected approval flows as generic failures.

## Proposed Design

Add a facade-level error boundary in `DataBoxAgentRuntime`.

Behavior:

- If the service raises `DataBoxError`, re-raise it.
- If the service raises `asyncio.CancelledError`, re-raise it so cancellation remains cancellation.
- For all other exceptions:
  - Log with `logger.exception`.
  - Raise `DataBoxError` or a new `AgentRuntimeError` with code `AGENT_RUNTIME_ERROR`.
  - Message should be user-safe: "Agent 运行失败，请稍后重试或查看日志。"

For streaming endpoints, convert the wrapped error into the existing terminal error event format if such a pattern already exists in `engine/api/agent.py`.

## Acceptance Criteria

- Unexpected runtime exceptions become a stable error code.
- Existing explicit `DataBoxError` behavior is preserved.
- Cancellation still cancels.
- API response and stream error paths do not expose raw tracebacks.

## Test Plan

- Unit test runtime re-raises `DataBoxError`.
- Unit test runtime wraps generic `RuntimeError`.
- Unit test runtime preserves cancellation.
- API test confirms error response contains `AGENT_RUNTIME_ERROR` and safe message.

## Rollout

Backend-only change. Logs should include traceback for maintainers while API output remains safe.
