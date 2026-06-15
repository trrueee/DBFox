# Datasource API and State Unification Spec

Date: 2026-06-15
Priority: P1
Area: Frontend datasource management

## Corrected Judgment

The original "two API clients" framing is too broad. The actual code now shares `request<T>` from `desktop/src/lib/api/client.ts`. The real problem is that datasource state and datasource types still split across feature-specific facades and local component state.

## Code Evidence

- `desktop/src/features/engine/engineApi.ts:1` imports the shared request client, so token injection is not duplicated there.
- `desktop/src/features/engine/engineApi.ts:3-14` defines `EngineDataSource`, a narrower datasource type.
- `desktop/src/lib/api/datasources.ts:4-27` defines the datasource management API facade with create/update/delete/sync.
- `desktop/src/features/datasource/useDatasourceState.ts:1-10` imports datasource list/schema calls from `features/engine/engineApi`, not `lib/api/datasources`.
- `desktop/src/features/datasource/useDatasourceState.ts:44-61` maps `EngineDataSource` into a partial `DataSource`, dropping fields.
- `desktop/src/pages/DataSourcesPage.tsx:90-109` keeps its own datasource list in local component state.

## Problem

The sidebar, SQL workspace, and datasource management page do not share a single datasource truth. Creation/update/delete flows call `onRefreshDatasources`, but the page still owns a separate list and type surface. This can cause stale active datasource labels, mismatched health/sync fields, and duplicate refresh logic.

## Goals

- Use one canonical frontend `DataSource` type.
- Use one datasource API facade for list/create/update/delete/health/sync.
- Use one datasource state owner for sidebar, workspace, and management page.
- Keep schema table/column APIs near datasource state but separate from SQL execution APIs.
- Preserve current UI behavior.

## Non-Goals

- Do not redesign the datasource management UI.
- Do not rewrite all API modules.
- Do not require Zustand immediately. A cohesive hook/store is enough if it removes the split.

## Proposed Design

Make `desktop/src/lib/api/datasources.ts` the canonical datasource API surface.

Refactor `useDatasourceState` to:

- import `DataSource` and `datasourcesApi` from `desktop/src/lib/api`;
- expose `datasources`, `activeDatasource`, `activeDatasourceId`, `setActiveDatasourceId`, `refreshDatasources`, `syncSchema`, and `checkHealth`;
- own table/column loading for the active datasource;
- invalidate API cache after create/update/delete/sync.

Update consumers:

- `DataSourceTree` receives canonical `DataSource[]`.
- `DataSourcesPage` uses the datasource state owner instead of local `datasources` where possible.
- SQL default datasource resolution reads `activeDatasourceId` or the datasource state owner, not `getDefaultDatasource()` from `engineApi`.
- `features/engine/engineApi.ts` should stop exporting datasource list helpers, or re-export the canonical facade only during migration.

## Acceptance Criteria

- A newly created datasource appears in the management page and sidebar without duplicate refresh logic.
- Updating name/host/status is reflected everywhere using the same `DataSource` object shape.
- Deleting the active datasource clears or moves the active datasource in one place.
- `EngineDataSource` is removed or limited to compatibility re-exports.
- No feature calls `/datasources` through `features/engine/engineApi.ts`.

## Test Plan

- Extend `DataSourcesPage` tests to verify create/update/delete refresh global datasource state.
- Add hook/store tests for active datasource preservation after refresh.
- Add a test for deleting the active datasource.
- Run frontend type checking to catch stale `EngineDataSource` imports.
