# Remove Design Demo CSS From Production Bundle Spec

Date: 2026-06-15
Priority: Code Quality
Area: Frontend styling
Primary files: `desktop/src/App.css`

## Problem

`App.css` contains styles that appear to be design-guide or mockup-only classes, such as `.hifi-guide-*` and `.hifi-color-*`. Keeping unused design demo styles in production increases CSS size and makes the stylesheet harder to maintain.

## Goals

- Identify design-demo-only CSS.
- Remove unused demo styles from production bundle.
- Preserve any classes still used by real components.
- Keep a documented archive if the design guide is still valuable.

## Non-Goals

- Do not delete active product UI styles.
- Do not redesign the app.
- Do not combine with broad CSS modularization unless that work is already underway.

## Proposed Design

Run a class usage audit:

- Extract `.hifi-guide-*`, `.hifi-color-*`, and other demo-looking selectors from `App.css`.
- Search `desktop/src` for each class.
- Classify each selector as:
  - used by production component
  - used only by archived/demo page
  - unused

For unused selectors:

- Remove from `App.css`.

For demo-only but still valuable selectors:

- Move into `docs/design/` as static reference CSS or a non-imported archive file.
- Ensure it is not imported by the production app.

## Acceptance Criteria

- Production `App.css` no longer contains unused design-demo selectors.
- No referenced class is removed.
- Build succeeds.
- A short audit note lists removed or archived selector groups.

## Test Plan

- `rg` audit before and after removal.
- `npm run build`.
- Manual visual check of main workbench, datasource tree, SQL console, Agent timeline, and settings views.

## Rollout

Do after or alongside CSS modularization. Keep the removal commit focused so any visual regression is easy to trace.
