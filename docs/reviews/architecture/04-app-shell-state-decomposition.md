# App Shell State Decomposition Spec

Date: 2026-06-15
Priority: P1
Area: Frontend architecture

## Corrected Judgment

`App.tsx` being large is a real architecture debt, but it is not a P0 by itself. It becomes high priority because it currently centralizes tab state, datasource state wiring, conversation persistence, Agent runtime wiring, command palette construction, selection state, context menus, and inline toast state. One extraction, `useSidebarLayout`, already exists, so the spec should continue that direction rather than claim no decomposition has started.

## Code Evidence

- `desktop/src/App.tsx:30-580` contains the main app shell and most global state.
- `desktop/src/App.tsx:33-43` owns tabs, table selection, drawer state, context menu, toast, SQL draft, and conversations.
- `desktop/src/App.tsx:77-97` loads and persists conversation history.
- `desktop/src/App.tsx:204-251` wires Agent runtime callbacks.
- `desktop/src/App.tsx:317-399` derives command palette items.
- `desktop/src/App.tsx:401-473` routes active tab rendering.
- `desktop/src/App.tsx:28` already imports `useSidebarLayout`, so layout extraction has started.

## Problem

Feature changes require touching the app composition root. This increases regression risk, makes state ownership unclear, and encourages new features to add more callbacks to `App.tsx`.

## Goals

- Make `App.tsx` a composition shell, not a state warehouse.
- Extract cohesive state domains into hooks or small providers.
- Keep existing tab UI and app behavior.
- Support the SQL tab state isolation and datasource unification specs.
- Make each extracted domain independently testable.

## Non-Goals

- Do not migrate to a global state library as the first step.
- Do not redesign navigation.
- Do not combine this with large CSS or visual redesign work.

## Proposed Design

Extract domains in this order:

1. `useWorkspaceTabs`
   - owns `tabs`, `activeTabId`, open/close/activate helpers, tab sequences, and tab patch helpers.
   - includes SQL tab state or composes with `useSqlConsoleTabs`.

2. `useConversationHistory`
   - owns `conversations`, load/save/delete, and tab cleanup for deleted conversations.

3. `useWorkspaceSelection`
   - owns selected tables, context tables, table sub-tabs, and multi-table workspace creation helpers.

4. `useAppCommands`
   - builds command palette items from tab and datasource dependencies.

5. `WorkspaceRouter`
   - renders active tab content from a clear props contract.

`App.tsx` should keep:

- providers and top-level layout;
- composition of hooks;
- cross-domain wiring that cannot live inside one domain.

Introduce Zustand only if, after these extractions, callback plumbing remains excessive or multiple distant components need direct write access to the same state.

## Acceptance Criteria

- `App.tsx` no longer owns raw tab mutation helpers inline.
- Conversation persistence code is outside `App.tsx`.
- Command palette construction is outside `App.tsx`.
- Active tab rendering lives in a `WorkspaceRouter` or equivalent component.
- Existing app shell behavior remains unchanged.
- New hooks have focused tests for non-trivial behavior.

## Test Plan

- Hook tests for tab close/activate/open behavior.
- Hook tests for conversation load/save/delete failure toasts.
- Existing app shell rendering tests.
- Manual smoke: open SQL, table, datasource, LLM config, Agent eval, and conversation history tabs.

## Verification (2026-06-17)

**Status: ✅ RESOLVED**

Decomposition complete:

| Concern | Extracted To |
|---------|-------------|
| Datasource state | `stores/datasourceStore.ts` (Zustand) |
| Tab/workspace state | `stores/workspaceStore.ts` (Zustand) |
| Agent runtime state | `stores/agentStore.ts` (Zustand) |
| Sidebar layout | `features/appShell/useSidebarLayout.ts` |
| Command palette items | `features/appShell/useAppCommands.ts` |
| Active tab routing | `features/appShell/WorkspaceRouter.tsx` |
| Toast system | `components/Toast.tsx` (`useToast()`) |

App.tsx is now 244 lines (down from ~580), acting as a pure composition shell:
- Provider setup (Dialog container, Toast root)
- Store initialization (`loadDatasources()`, `initConversations()`)
- Cross-domain wiring (keyboard shortcuts, context menu, command palette)
- Layout assembly (sidebar + main + drawer)
