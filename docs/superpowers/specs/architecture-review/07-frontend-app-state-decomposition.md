# Frontend App State Decomposition Spec

Date: 2026-06-15
Priority: P1
Area: Frontend architecture
Primary files: `desktop/src/App.tsx`

## Problem

`desktop/src/App.tsx` owns too many responsibilities: tab management, sidebars, context menus, conversation persistence, Agent wiring, command palette state, datasource state, and layout assembly. This makes feature changes risky because unrelated state and callbacks live in one large component.

## Goals

- Reduce `App.tsx` responsibility without changing behavior.
- Extract cohesive state domains into hooks.
- Keep rendering structure recognizable during migration.
- Preserve existing tests and tab behavior.

## Non-Goals

- Do not introduce a global state library in this spec.
- Do not redesign the tab UI.
- Do not refactor every child component at once.

## Proposed Design

Split `App.tsx` into focused hooks under `desktop/src/features/appShell/`:

- `useWorkspaceTabs`: owns `tabs`, `activeTabId`, open/close/activate helpers, tab sequence refs.
- `useConversationHistory`: owns conversation loading, persistence, deletion.
- `useSidebarLayout`: owns sidebar collapse/resize and resize event lifecycle.
- `useWorkspaceSelection`: owns selected tables and context tables.
- `useCommandItems`: derives command palette items from dependencies.

`App.tsx` remains the composition root:

- calls hooks
- wires callbacks between domains
- renders layout

Move one domain at a time, starting with the lowest-risk domain: sidebar layout.

## Acceptance Criteria

- `App.tsx` line count is reduced meaningfully.
- Hook boundaries are cohesive and named by domain.
- Existing app shell and datasource tab tests pass.
- No user-visible behavior changes.
- Hooks have focused tests where behavior is non-trivial.

## Test Plan

- Existing `appShell` and `datasourceTabs` tests.
- New hook tests for `useWorkspaceTabs` close/activate behavior.
- New hook tests for `useSidebarLayout` resize bounds.

## Rollout

Migrate in small PRs. Do not combine this with feature work such as datasource management UI changes.
