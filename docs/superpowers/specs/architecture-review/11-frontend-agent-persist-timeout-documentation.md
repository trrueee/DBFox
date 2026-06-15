# Frontend Agent Persistence Timing Spec

Date: 2026-06-15
Priority: P5
Area: Frontend Agent runtime
Primary files: `desktop/src/features/agentTask/useAgentRunner.ts`

## Problem

`useAgentRunner.ts` uses `setTimeout(..., 0)` to defer conversation persistence. This can be a valid React pattern, but without an explanation it looks arbitrary and invites accidental removal or misuse.

## Goals

- Make the scheduling reason explicit.
- Keep persistence behavior stable.
- Evaluate whether a named helper makes the intent clearer.

## Non-Goals

- Do not redesign Agent streaming.
- Do not change conversation persistence storage.
- Do not introduce `useDeferredValue` unless it exactly matches the need.

## Proposed Design

Replace inline `setTimeout(..., 0)` with a named helper:

```ts
function scheduleAfterStateFlush(callback: () => void) {
  window.setTimeout(callback, 0);
}
```

Add a short comment at the helper:

```ts
// Defers persistence until React has applied the tab state update that produced the conversation snapshot.
```

If the current callback can instead use a direct next-state value without deferral, prefer that refactor and remove the timeout. The implementation task should inspect the state update sequence before choosing.

## Acceptance Criteria

- The reason for deferral is clear at the call site or helper definition.
- Existing Agent streaming and persistence tests pass.
- No new timing delay larger than the current next-tick behavior.

## Test Plan

- Existing `useAgentRunner` or Agent timeline tests.
- Add a focused test if the helper can be tested without brittle timer internals.
- Manual smoke test: ask a question, receive stream, reload conversation history.

## Rollout

Small frontend-only cleanup. Can be batched with Agent code quality work.
