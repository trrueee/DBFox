# SQL Console Tab State Isolation Spec

Date: 2026-06-15
Priority: P0/P1
Area: Frontend workspace state

## Corrected Judgment

This is a real product bug, more concrete than the general "`App.tsx` is large" complaint. Multiple SQL Console tabs currently share one editor value and can also lose local console history when switching tabs.

## Code Evidence

- `desktop/src/App.tsx:42` owns a single `sqlQuery` state.
- `desktop/src/App.tsx:119-123` opens every SQL tab without tab-local SQL state.
- `desktop/src/App.tsx:422-424` passes the same `sqlQuery` and `setSqlQuery` to every `SqlConsoleWorkspace`.
- `desktop/src/features/workspace/SqlConsoleWorkspace.tsx:29-66` reads and clears the shared `sqlQuery`.
- `desktop/src/features/workspace/SqlConsoleWorkspace.tsx:30-33` keeps console entries in component-local state, which is fragile because only the active tab content is rendered.

## Problem

If a user opens SQL tab A and SQL tab B, editing one tab can overwrite or clear the other tab's draft. Running SQL in one tab calls `onSqlQueryChange("")`, which clears the shared editor value. Console entries are also local to the rendered workspace component, so tab switches can drop execution context depending on mount behavior.

## Goals

- Give every SQL tab independent editor text.
- Keep each SQL tab's result/history entries attached to that tab.
- Keep running/cancel state tab-scoped.
- Preserve existing shortcuts and SQL execution behavior.
- Make closing a SQL tab clean up its state.

## Non-Goals

- Do not redesign the SQL Console UI.
- Do not change backend SQL execution semantics.
- Do not introduce a global state library just for this bug.

## Proposed Design

Add a tab-scoped SQL console state model:

```ts
type SqlConsoleTabState = {
  draftSql: string;
  entries: ConsoleEntry[];
  running: boolean;
  executionId?: string;
};

type SqlConsoleStateByTabId = Record<string, SqlConsoleTabState>;
```

Store it either inside `WorkspaceTab` for SQL tabs or in a dedicated `sqlConsoleByTabId` map owned by the workspace tab hook. The map is preferable if entries become large; `WorkspaceTab` is simpler if the current tab model is already the canonical workspace state.

`SqlConsoleWorkspace` should receive:

- `tabId`
- `state`
- `onPatchState(tabId, patch)`
- `onAppendEntries(tabId, entries)`

The component can keep refs for scrolling/focus, but user data and execution history should live outside the mounted component.

## Acceptance Criteria

- Opening two SQL tabs creates two independent SQL drafts.
- Typing or running SQL in tab A does not mutate tab B.
- Switching away from a SQL tab and returning keeps its editor text and result history.
- Closing a SQL tab removes only that tab's SQL state.
- Existing `F9` and `Ctrl/Cmd+Enter` execution shortcuts still work.
- A query result action that opens SQL sets the draft on the target SQL tab only.

## Test Plan

- Add a frontend test that opens two SQL tabs, types different SQL in each, switches tabs, and verifies both drafts remain.
- Add a test that running one SQL tab clears only that tab's draft.
- Add a test that result entries survive tab switching.
- Run the existing desktop test suite after the change.

## Verification (2026-06-17)

**Status: ✅ RESOLVED**

All acceptance criteria met:

- `workspaceStore.ts:16` — `sqlConsoleState: Record<string, SqlConsoleTabState>` — per-tab state
- `workspaceStore.ts:105-115` — `openSqlConsole(initialSql?)` creates tab with independent `{ draftSql, entries, running }`
- `workspaceStore.ts:92-102` — `closeTab()` cleans up per-tab state (`const { [tabId]: _, ...rest } = s.sqlConsoleState`)
- `WorkspaceRouter.tsx:116-140` — `SqlConsoleTab` reads/writes per-tab state via `onPatchState(tabId, patch)` and `onAppendEntries(tabId, entries)`
- `SqlConsoleWorkspace.tsx:40` — receives `tabId`, `state`, `onPatchState`, `onAppendEntries` — fully tab-scoped
- Editor text, execution history, and running state are all keyed by `tabId`
- Closing a tab removes only that tab's state; switching tabs preserves all state
- F9 / Ctrl+Enter shortcuts remain functional
