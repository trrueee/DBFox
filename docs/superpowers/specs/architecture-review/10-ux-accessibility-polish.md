# UX and Accessibility Polish Spec

Date: 2026-06-15
Priority: P2/P3
Area: Frontend UX quality

## Corrected Judgment

These are real small issues, but they are not architecture blockers. They should be batched as polish work after the consistency bugs. Product-decision items such as native `<select>` styling and TitleBar shortcut behavior are not included as bugs.

## Code Evidence

- `desktop/src/components/Toast.tsx:106-168` renders toasts without explicit live-region role/ARIA attributes.
- `desktop/src/components/LabCard.tsx:23-27` renders a clickable `div` when `onClick` is provided, without keyboard semantics.
- `desktop/src/components/AiQueryInput.tsx:59-74` uses an editable textarea for generated-query input; this is acceptable only if product wants the user to edit before submit.
- `desktop/src/features/workspace/queryResult/FollowUpInput.tsx:22-33` uses keyboard Enter and a labeled send button, which is acceptable and not a bug.

## Problem

Small inconsistencies in accessibility and interaction semantics accumulate. Toast announcements may not be read by assistive tech. Clickable non-button cards may not be reachable by keyboard. Some text input behavior needs a product decision rather than an automatic bug label.

## Goals

- Fix verified accessibility gaps.
- Keep native controls when they are appropriate.
- Avoid treating product choices as defects without evidence.
- Add tests for keyboard interaction where components behave like buttons.

## Non-Goals

- Do not replace all native controls with custom components.
- Do not redesign the visual system.
- Do not change AI input editability until product confirms the intended workflow.

## Proposed Design

Toast accessibility:

- Add `role="status"` and `aria-live="polite"` for info/success toasts.
- Add `role="alert"` or `aria-live="assertive"` for error toasts.

Clickable cards:

- If `LabCard` has `onClick`, render a `<button>` or add `role="button"`, `tabIndex={0}`, and Enter/Space handling.
- Prefer rendering a semantic `<button>` when styling permits.

Product-decision items:

- Keep native `<select>` unless there is a concrete design-system inconsistency.
- Treat TitleBar `Ctrl+W` as a shortcut enhancement, not a bug.
- Treat AI input editability as a product decision: editable draft input is valid if users are expected to revise generated prompts.

## Acceptance Criteria

- Toasts expose appropriate live-region semantics.
- Clickable `LabCard` instances are keyboard reachable and screen-reader understandable.
- No broad replacement of native controls happens in this batch.
- Product-decision items are documented but not implemented as bug fixes.

## Test Plan

- Component test for ToastProvider ARIA attributes.
- Component test for clickable `LabCard` keyboard activation.
- Manual keyboard navigation smoke test across datasource management and workspace cards.
