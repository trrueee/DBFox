# Frontend Design Token Unification Spec

Date: 2026-06-15
Priority: P6
Area: Frontend design system
Primary files: `desktop/src/App.css`, `desktop/src/components/ui/*`

## Problem

The CSS uses several token systems at once: DataBox variables such as `--color-primary`, shadcn-style `hsl(var(--primary))`, and hard-coded hex values. This makes theme changes harder and can cause light/dark inconsistencies.

## Goals

- Establish one canonical DataBox token layer.
- Map shadcn/Radix-compatible HSL variables to DataBox tokens.
- Reduce hard-coded colors in component CSS.
- Preserve current visual style.

## Non-Goals

- Do not remove Radix or shadcn-derived components.
- Do not redesign the theme.
- Do not convert all classes to Tailwind utilities.

## Proposed Design

Create a token bridge in the root CSS:

```css
:root {
  --primary: 247 84% 68%;
  --destructive: 0 56% 52%;
  --muted: 210 40% 96%;
}
```

Document the canonical mapping:

- DataBox semantic tokens are primary: `--color-primary`, `--color-danger`, `--color-bg`, etc.
- HSL tokens exist only to satisfy imported UI primitives.
- New feature CSS should use DataBox semantic tokens unless a shadcn primitive requires HSL.

Replace hard-coded colors in touched files with tokens:

- `#CBD5E1` -> `var(--color-border-hover)` or add a token.
- `#F1F5F9` -> `var(--bg-hover)`.
- repeated soft backgrounds -> existing `--color-*-soft`.

## Acceptance Criteria

- A documented token map exists near root variables.
- New or modified CSS avoids raw hex values unless explicitly documented.
- Dark mode remains visually coherent.
- shadcn/Radix components still render correctly.

## Test Plan

- Build succeeds.
- Manual light/dark inspection of dialogs, buttons, inputs, datasource tree, and Agent approval UI.
- Stylelint is optional; if added, configure it to warn on raw colors outside token definition files.

## Rollout

Apply gradually as CSS files are touched. Do not perform a huge token rename in the same branch as feature work.
