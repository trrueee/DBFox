# Frontend CSS Modularization Spec

Date: 2026-06-15
Priority: P2
Area: Frontend styling architecture
Primary files: `desktop/src/App.css`

## Problem

`desktop/src/App.css` is a large single stylesheet containing window shell, sidebar, workspace, tables, ER diagrams, assistant UI, chart UI, and design demo styles. The size makes style ownership unclear and increases the risk of accidental regressions.

## Goals

- Split CSS by feature/domain while preserving current visual output.
- Keep global design tokens in one place.
- Make future feature styling easier to locate.
- Avoid a disruptive styling framework migration.

## Non-Goals

- Do not switch to CSS Modules or Tailwind-only styling in this iteration.
- Do not redesign components.
- Do not rename every class.

## Proposed Design

Create `desktop/src/styles/`:

- `tokens.css`: root variables, dark mode variables, shared input/button primitives.
- `shell.css`: app shell, title bar integration, tab frame.
- `sidebar.css`: datasource tree and resize handle.
- `workspace.css`: tabs, workspaces, SQL console, table workspace.
- `agent.css`: assistant/agent timeline and approval UI.
- `datasource.css`: datasource management page styles.
- `data-grid.css` remains close to data-grid components if already separate.
- `legacy-demo.css`: temporary location for design-only classes before deletion.

`App.css` becomes an import aggregator:

```css
@import "./styles/tokens.css";
@import "./styles/shell.css";
...
```

Move styles in chunks, verifying no visual class names change.

## Acceptance Criteria

- `App.css` becomes an import file plus minimal compatibility comments.
- Component classes keep their existing names.
- Build output succeeds.
- No broad visual regressions in app shell, datasource tree, SQL console, and Agent view.

## Test Plan

- `npm run build`.
- Existing frontend tests.
- Manual visual check of main workbench, datasource tree, SQL console, and Agent result view.

## Rollout

Do this after feature work stabilizes. Keep each migration commit domain-specific so regressions are easy to bisect.
