# Frontend API Cache and Retry Layer Spec

Date: 2026-06-15
Priority: P4
Area: Frontend API client
Primary files: `desktop/src/lib/api/client.ts`, `desktop/src/features/datasource/useDatasourceState.ts`

## Problem

The frontend API client is a thin `fetch` wrapper. It has no retry, deduplication, or cache policy. Low-frequency data such as datasource lists and Schema metadata can refetch repeatedly, and transient local-engine startup races require feature-specific retry code.

## Goals

- Add reusable retry behavior for safe idempotent requests.
- Add small local cache/deduplication for low-frequency metadata.
- Preserve the current `request<T>` API for existing callers.
- Keep mutations explicit and cache-invalidating.

## Non-Goals

- Do not add React Query/SWR immediately.
- Do not cache SQL execution or Agent streaming requests.
- Do not retry unsafe mutations by default.

## Proposed Design

Extend API client with optional request policy:

```ts
type RequestPolicy = {
  retry?: "none" | "local-engine-startup";
  cacheKey?: string;
  cacheTtlMs?: number;
};
```

Keep existing `request<T>(path, options)` behavior unchanged. Add `requestWithPolicy<T>(path, options, policy)` or optional third argument only after checking call-site compatibility.

Retry policy:

- Retry only GET requests by default.
- Retry transient network errors and local engine startup fetch failures.
- Use short bounded delays, matching current datasource retry behavior.

Cache policy:

- In-memory cache with TTL.
- Deduplicate in-flight requests by cache key.
- Provide explicit `invalidateApiCache(prefix)` for mutations like datasource create/update/delete/sync.

## Acceptance Criteria

- Existing API callers keep working.
- `useDatasourceState` can remove its custom retry loop or delegate to shared retry.
- GET datasource/schema calls can opt into TTL cache.
- Mutations invalidate related datasource/schema cache keys.

## Test Plan

- Unit test transient retry succeeds after initial network errors.
- Unit test non-idempotent POST is not retried by default.
- Unit test cache returns same in-flight promise for duplicate GET.
- Unit test invalidation clears matching keys.

## Rollout

Introduce policy-based client first, then migrate one feature at a time. Avoid caching any user-generated SQL result in the first iteration.
