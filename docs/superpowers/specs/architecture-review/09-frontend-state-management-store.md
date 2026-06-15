# Frontend Global State Store Evaluation Spec

Date: 2026-06-15
Priority: P3
Area: Frontend state architecture
Primary files: `desktop/src/App.tsx`, `desktop/src/features/*`

## Problem

Large portions of global UI state are held in `App.tsx` and passed through props. As more features are added, this creates deep callback wiring and makes unrelated UI areas re-render together.

## Goals

- Decide whether DataBox needs a small global state store.
- Reduce props drilling for cross-cutting state.
- Keep server/cache state separate from UI state.
- Avoid over-centralizing local component state.

## Non-Goals

- Do not migrate all state at once.
- Do not store transient form state globally.
- Do not replace React state where a local hook is enough.

## Proposed Design

Run an evaluation spike comparing Zustand and Jotai against current needs.

Candidate store slices:

- workspace tabs
- active datasource id
- selected/context tables
- command palette visibility
- conversation list metadata

Decision criteria:

- TypeScript ergonomics
- testability
- minimal boilerplate
- compatibility with Tauri desktop lifecycle
- ability to isolate re-renders

Recommended default if adopted: Zustand, because DataBox state is mostly domain slices with imperative actions.

Migration path:

1. Extract hooks first as described in the App decomposition spec.
2. Move only one mature hook into a store slice.
3. Measure whether component wiring and tests improve.

## Acceptance Criteria

- A short decision record documents adopt/defer and why.
- If adopted, only one low-risk slice migrates first.
- No feature behavior changes.
- Tests cover store actions and selectors.

## Test Plan

- Unit tests for chosen store slice actions.
- Existing app shell and tab tests.
- Render test proving unrelated selector consumers do not update unnecessarily where practical.

## Rollout

Treat this as an architecture decision, not a prerequisite for current features. Prefer deferring if hook decomposition already solves most pain.
