# Query History Search Scaling Spec

Date: 2026-06-15
Priority: P3
Area: Backend query history

## Corrected Judgment

This is a real performance concern, but it is data-volume dependent. It should not block the first datasource-management or workspace-state fixes.

## Code Evidence

- `engine/api/query.py:141-153` builds a `%term%` pattern and searches six `QueryHistory` fields with `ILIKE`.
- `engine/api/query.py:123` caps the response limit at 200, but filtering still scans matching rows before the limit.
- `engine/models.py:242-247` indexes datasource and created time, not full-text search columns.

## Problem

As query history grows, wildcard text search across multiple fields can become slow. Chinese text search quality may also be poor with generic substring matching. The current implementation is acceptable for small local histories but should have a scaling path.

## Goals

- Keep current simple search for small local histories.
- Add a clear threshold for when to introduce indexed search.
- Avoid overbuilding before history volume requires it.
- Preserve current API shape.

## Non-Goals

- Do not introduce an external search service.
- Do not change history retention policy in this spec.
- Do not implement advanced semantic search here.

## Proposed Design

Short term:

- Keep current endpoint.
- Add tests for filters and limit behavior.
- Consider reducing searched fields if UI only needs question, submitted SQL, and error message.

Medium term:

- For SQLite, add FTS5 virtual table if packaged SQLite supports it.
- For other future metastores, use their native text-search capability or a normalized search table.
- Maintain the existing `/query/history?search=` API.

## Acceptance Criteria

- Current search behavior is covered by tests.
- A documented threshold exists, for example "when local history exceeds 10k rows or search p95 exceeds 300ms".
- No FTS migration is introduced until the threshold is met or product requires better Chinese search.

## Test Plan

- Backend tests for datasource filter, status filter, search term filter, and limit.
- Optional benchmark script using synthetic history rows before deciding on FTS work.
