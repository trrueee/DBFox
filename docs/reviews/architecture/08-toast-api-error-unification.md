# Toast and API Error Unification Spec

Date: 2026-06-15
Priority: P2
Area: Frontend UX and error handling

## Corrected Judgment

The API client is not just a thin fetch wrapper anymore; it already injects tokens, normalizes some errors, retries selected requests, deduplicates in-flight GETs, and supports TTL cache. The real remaining issue is inconsistent adoption and presentation: the app has two toast systems and API errors are still plain `Error` objects with ad hoc fields.

## Code Evidence

- `desktop/src/lib/api/client.ts:51-149` implements token injection, structured detail parsing, retry, cache, and in-flight deduplication.
- `desktop/src/lib/api/client.ts:89-94` creates a plain `Error` with optional `code` and `checks`.
- `desktop/src/App.tsx:41-47` implements inline `toastMsg` state.
- `desktop/src/App.tsx:576` renders an inline `.hifi-toast`.
- `desktop/src/components/Toast.tsx:20-177` provides `ToastProvider` and `useToast`.
- `desktop/src/pages/DataSourcesPage.tsx:90` uses `useToast`.
- `desktop/src/pages/AgentEvalPage.tsx:14-17` still receives an `onToast` callback.

## Verification (2026-06-17)

**Status: 📐 NARROWED → P3**

- App.tsx inline `toastMsg` state and `.hifi-toast` rendering already removed — unified to `useToast()`
- No `toastMsg` or `.hifi-toast` references remain in the codebase
- `Toast.tsx` is the single toast system with GSAP animation, portal, `role="status"`/`aria-live`
- **Residual**: `DataTable.tsx:50` has a local `useState<string | null>` CSS toast for clipboard copy feedback — a deliberate lightweight choice, not a duplicated system
- `AgentEvalPage` `onToast` callback is a page-level prop, not a separate toast implementation

**Residual action**: Replace DataTable clipboard toast with `useToast()` for consistency (P3).

## Problem

Users can see differently styled feedback depending on which feature emits it. Accessibility and lifecycle behavior must be fixed twice. API error handling also depends on callers casting `Error`, so code/checks/status handling is not standardized.

## Goals

- Use one toast provider throughout the app.
- Add accessible live-region semantics to toast output.
- Introduce a typed `ApiError`.
- Keep the existing `request<T>` API compatible.
- Normalize user-facing error messages at one boundary.

## Non-Goals

- Do not replace the request client with React Query/SWR.
- Do not redesign the notification visual style.
- Do not change backend error response formats in this spec.

## Proposed Design

Toast:

- Remove the inline `toastMsg` state from `App.tsx`.
- Make app shell callbacks call `useToast().toast(message, type)`.
- Pass a typed toast function only where props are still necessary.
- Add `role="status"` or `role="alert"` and `aria-live` to the provider output depending on toast type.

API errors:

- Add an exported `ApiError` class:

```ts
class ApiError extends Error {
  status?: number;
  code?: string;
  checks: unknown[];
  detail?: unknown;
}
```

- Make `request<T>` throw `ApiError` for non-OK HTTP responses.
- Add helpers such as `getUserErrorMessage(error, fallback)`.
- Keep existing callers working through `error instanceof Error`.

## Acceptance Criteria

- There is only one toast rendering implementation in the app.
- DataSourcesPage, App shell actions, AgentEvalPage, LLM config, and query result features use the same toast system.
- Toasts have accessible live region attributes.
- API non-OK responses throw `ApiError`.
- Callers can branch on `error.code` without unsafe casts.

## Test Plan

- Component test for ToastProvider rendering success/error toasts with live-region attributes.
- Unit tests for `request<T>` error normalization, including FastAPI validation arrays and `detail.code/message`.
- Smoke test datasource create/update/delete failures display through the shared toast.
