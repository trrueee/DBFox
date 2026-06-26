# Desktop Productization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the desktop frontend feel less like scattered pages and more like a coherent workspace product.

**Architecture:** First solidify the existing UI primitives as a supported import surface. Then add a WorkspaceShell that owns tab chrome, body framing, and empty/error/loading states. Keep query tables and artifact tables separate products, while sharing lower-level visual language later.

**Tech Stack:** React 19, TypeScript, Vite, Vitest, Testing Library, local CSS with existing design tokens.

---

### Task 1: UI primitive export surface

**Files:**
- Create: `desktop/src/components/ui/index.ts`
- Modify: `desktop/src/components/ui/__tests__/ui-primitives.test.tsx`

- [x] Add a failing test that imports Button/Input/Select/Panel/Toolbar/State components from `../index`.
- [x] Run `npm test -- src/components/ui/__tests__/ui-primitives.test.tsx` and verify it fails because `../index` does not exist.
- [x] Create `desktop/src/components/ui/index.ts` that re-exports the existing primitive modules.
- [x] Re-run the same test and verify it passes.

### Task 2: WorkspaceShell foundation

**Files:**
- Create: `desktop/src/features/appShell/WorkspaceShell.tsx`
- Create: `desktop/src/features/appShell/WorkspaceShell.css`
- Create: `desktop/src/features/appShell/__tests__/WorkspaceShell.test.tsx`

- [x] Add failing tests for a shell with title, description, toolbar, body, and loading/empty/error states.
- [x] Run `npm test -- src/features/appShell/__tests__/WorkspaceShell.test.tsx` and verify it fails because WorkspaceShell does not exist.
- [x] Implement WorkspaceShell with no inline styles, using local CSS classes and existing EmptyState/ErrorState/LoadingState primitives.
- [x] Re-run the WorkspaceShell test and verify it passes.

### Task 3: WorkspaceRouter shell migration

**Files:**
- Modify: `desktop/src/features/appShell/WorkspaceRouter.tsx`
- Modify: `desktop/src/features/appShell/__tests__/WorkspaceRouter.test.tsx`

- [x] Add failing tests that diagnostics, datasource settings, LLM config, and artifact-result tabs render inside WorkspaceShell instead of ad hoc wrapper divs.
- [x] Run `npm test -- src/features/appShell/__tests__/WorkspaceRouter.test.tsx` and verify the new tests fail.
- [x] Replace the wrapper divs with WorkspaceShell in `WorkspaceRouter.tsx`.
- [x] Re-run WorkspaceRouter tests and verify they pass.

### Task 4: Verification

**Files:**
- Verify only.

- [x] Run targeted tests:
  `npm test -- src/components/ui/__tests__/ui-primitives.test.tsx src/features/appShell/__tests__/WorkspaceShell.test.tsx src/features/appShell/__tests__/WorkspaceRouter.test.tsx src/features/workspace/__tests__/SqlConsoleWorkspace.test.tsx`
- [x] Run `npm run build` if targeted tests are green.
- [x] Report changed files and any pre-existing dirty-worktree caveat.

### Task 5: Workspace chrome polish

**Files:**
- Modify: `desktop/src/features/appShell/WorkspaceRouter.tsx`
- Modify: `desktop/src/pages/DiagnosticsPage.tsx`
- Modify: `desktop/src/pages/DataSourcesPage.tsx`
- Modify: `desktop/src/components/LlmConfigPanel.tsx`
- Modify: `desktop/src/features/appShell/WorkspaceShell.css`
- Modify: `desktop/src/App.css`
- Test: `desktop/src/features/appShell/__tests__/WorkspaceRouter.test.tsx`
- Test: `desktop/src/pages/__tests__/DiagnosticsPage.test.tsx`
- Test: `desktop/src/pages/__tests__/DataSourcesPage.test.tsx`
- Test: `desktop/src/components/__tests__/LlmConfigPanel.test.tsx`

- [x] Add failing tests that workspace-embedded pages do not render duplicate page titles.
- [x] Add failing test that WorkspaceRouter passes `chrome="workspace"` into shell-hosted pages.
- [x] Implement `chrome?: "page" | "workspace"` for Diagnostics, DataSources, and LLM config.
- [x] Keep workspace-mode actions visible as compact toolbars.
- [x] Replace the touched LLM inline input style with a CSS class.
- [x] Run targeted tests and desktop build.

### Task 6: Artifact result table v1 polish

**Files:**
- Modify: `desktop/src/features/workspace/artifacts/table/useArtifactTableData.ts`
- Modify: `desktop/src/features/workspace/artifacts/table/ArtifactTableGrid.tsx`
- Modify: `desktop/src/features/workspace/artifacts/TableArtifactView.tsx`
- Modify: `desktop/src/App.css`
- Test: `desktop/src/features/workspace/artifacts/__tests__/TableArtifactView.test.tsx`

- [x] Add failing tests for typed artifact column indicators and clicked-cell selected state.
- [x] Keep artifact result table behavior separate from the base query result table.
- [x] Preserve typed column metadata through `useArtifactTableData`.
- [x] Render compact column type badges without changing sort button semantics.
- [x] Add a selected cell state while keeping click-to-copy behavior.
- [x] Move touched artifact table alignment/copy/selection styling into CSS classes.
- [x] Run artifact table tests, desktop productization test set, and desktop build.

### Task 7: Base query table v1 polish

**Files:**
- Modify: `desktop/src/features/workspace/table/TablePreviewPane.tsx`
- Modify: `desktop/src/App.css`
- Test: `desktop/src/features/workspace/table/__tests__/TablePreviewPane.test.tsx`

- [x] Add failing tests for query preview cell copy, selected state, and stable NULL display.
- [x] Keep the base query table implementation separate from the artifact result table.
- [x] Add click-to-copy for preview cells with toast feedback.
- [x] Add selected cell state for the active preview cell.
- [x] Render NULL values as a stable pill while copying the displayed `NULL` value.
- [x] Move touched preview table cell, skeleton, pager button, and page-size styles into CSS classes.
- [x] Run the TablePreviewPane test before broader verification.

### Task 8: Base query table toolbar primitive migration

**Files:**
- Modify: `desktop/src/features/workspace/table/TablePreviewPane.tsx`
- Modify: `desktop/src/App.css`
- Test: `desktop/src/features/workspace/table/__tests__/TablePreviewPane.test.tsx`

- [x] Add failing tests that table preview toolbar, filter/sort controls, pagination, and empty actions use UI primitives.
- [x] Replace the main preview toolbar with `Toolbar`, `ToolbarGroup`, `Button`, and `Input`.
- [x] Replace filter and sort row native controls with `Select`, `Input`, and `Button`.
- [x] Replace pagination and empty-state action controls with `Button` and `Select`.
- [x] Move touched toolbar/search/control-row styles into CSS classes.
- [x] Verify `TablePreviewPane.tsx` has no old `hifi-toolbar-btn`, raw `select/input`, inline style, or Tailwind utility residue in the migrated areas.
- [x] Run `TablePreviewPane` tests before broader verification.

### Task 9: TablePreviewPane local style ownership

**Files:**
- Create: `desktop/src/features/workspace/table/TablePreviewPane.css`
- Modify: `desktop/src/features/workspace/table/TablePreviewPane.tsx`
- Modify: `desktop/src/App.css`
- Test: `desktop/src/features/workspace/table/__tests__/TablePreviewPane.styles.test.ts`

- [x] Add a failing style-boundary test proving TablePreviewPane imports local CSS and App.css does not own its business selectors.
- [x] Create `TablePreviewPane.css` beside the feature component.
- [x] Move TablePreviewPane-specific toolbar, search, control row, cell, null pill, skeleton row, footer notice, and pager styles from `App.css`.
- [x] Keep shared global table primitives in `App.css` for now.
- [x] Run style-boundary and TablePreviewPane behavior tests.

### Task 10: Artifact table local style ownership

**Files:**
- Create: `desktop/src/features/workspace/artifacts/table/ArtifactTable.css`
- Modify: `desktop/src/features/workspace/artifacts/TableArtifactView.tsx`
- Modify: `desktop/src/App.css`
- Test: `desktop/src/features/workspace/artifacts/__tests__/TableArtifactView.styles.test.ts`

- [x] Add a failing style-boundary test proving TableArtifactView imports local artifact table CSS.
- [x] Move artifact table grid, column type badge, cell selection, NULL pill, and inline meta styles from `App.css`.
- [x] Keep shared artifact and global result workspace styles in `App.css` for now.
- [x] Run style-boundary and artifact table behavior tests.

### Task 11: Artifact table toolbar/footer primitive migration

**Files:**
- Modify: `desktop/src/features/workspace/artifacts/table/ArtifactTableToolbar.tsx`
- Modify: `desktop/src/features/workspace/artifacts/table/ArtifactTableFooter.tsx`
- Modify: `desktop/src/features/workspace/artifacts/table/ArtifactTable.css`
- Modify: `desktop/src/App.css`
- Test: `desktop/src/features/workspace/artifacts/__tests__/TableArtifactView.styles.test.ts`
- Test: `desktop/src/features/workspace/artifacts/__tests__/TableArtifactView.test.tsx`

- [x] Add a failing style-boundary test that artifact table controls use UI primitives instead of raw `button`, `input`, and `select` elements.
- [x] Replace artifact table toolbar controls with `Toolbar`, `ToolbarGroup`, `Button`, `Input`, and `Select`.
- [x] Replace artifact table footer controls with `Button` and `Select`.
- [x] Move artifact toolbar/search/footer/page styles into `ArtifactTable.css`.
- [x] Remove now-unused artifact result toolbar/search/footer/page business styles from `App.css`.
- [x] Run style-boundary and artifact table behavior tests.

### Task 12: TableArtifactView shell/action style cleanup

**Files:**
- Modify: `desktop/src/features/workspace/artifacts/TableArtifactView.tsx`
- Modify: `desktop/src/features/workspace/artifacts/table/ArtifactTable.css`
- Test: `desktop/src/features/workspace/artifacts/__tests__/TableArtifactView.styles.test.ts`
- Test: `desktop/src/features/workspace/artifacts/__tests__/TableArtifactView.test.tsx`

- [x] Add a failing style-boundary test that `TableArtifactView` itself uses `Button` primitives and no raw `button` elements.
- [x] Replace workspace shell, alert, loading, table container, inline error, inline table, and action utility classes with local `artifact-table-*` classes.
- [x] Replace inline artifact action buttons with `Button`.
- [x] Keep shared artifact card pill styling untouched for a later focused migration.
- [x] Run style-boundary and artifact table behavior tests.

### Task 13: Base table pagination and datetime polish

**Files:**
- Modify: `desktop/src/features/workspace/table/TablePreviewPane.tsx`
- Modify: `desktop/src/features/workspace/table/TablePreviewPane.css`
- Modify: `desktop/src/App.css`
- Test: `desktop/src/features/workspace/table/__tests__/TablePreviewPane.test.tsx`
- Test: `desktop/src/features/workspace/table/__tests__/TablePreviewPane.styles.test.ts`

- [x] Add failing tests for stable displayed page/footer while loading the next page.
- [x] Add failing test for readable datetime cell display without timezone shifting.
- [x] Keep the currently loaded page visible until the requested page resolves.
- [x] Move preview footer and pagination business styles from `App.css` into `TablePreviewPane.css`.
- [x] Use a stable footer layout so pagination controls do not move when status text changes.
- [x] Run TablePreviewPane behavior and style-boundary tests.

### Task 14: Datasource AI enrichment uses saved LLM config

**Files:**
- Modify: `desktop/src/pages/DataSourcesPage.tsx`
- Modify: `desktop/src/lib/api/types.ts`
- Test: `desktop/src/pages/__tests__/DataSourcesPage.test.tsx`

- [x] Add failing test that AI schema sync includes the locally saved LLM API key, API base, and model.
- [x] Reuse `getStoredApiConfig()` when building schema sync options.
- [x] Preserve the no-key behavior by not sending default endpoint/model noise when only defaults exist.
- [x] Run DataSourcesPage tests.

### Task 15: Datasource management local style cleanup

**Files:**
- Create: `desktop/src/features/datasource-management/DataSourceManagement.css`
- Modify: `desktop/src/features/datasource-management/DataSourceList.tsx`
- Modify: `desktop/src/features/datasource-management/SchemaSyncPanel.tsx`
- Test: `desktop/src/features/datasource-management/__tests__/DataSourceManagement.styles.test.ts`

- [x] Add failing style-boundary test for datasource list and schema sync panel local CSS ownership.
- [x] Move datasource search, list item, badge, health dot, and schema sync panel styles into feature-local CSS.
- [x] Replace the datasource list search input with the shared `Input` primitive.
- [x] Run datasource-management style-boundary and DataSourcesPage regression tests.

### Task 16: Datasource detail local style and action controls

**Files:**
- Modify: `desktop/src/features/datasource-management/DataSourceDetail.tsx`
- Modify: `desktop/src/features/datasource-management/DataSourceManagement.css`
- Modify: `desktop/src/features/datasource-management/__tests__/DataSourceManagement.styles.test.ts`
- Modify: `desktop/src/pages/__tests__/DataSourcesPage.test.tsx`

- [x] Add failing style-boundary test that DataSourceDetail imports local CSS and has no inline styles.
- [x] Replace detail action and tab controls with the shared `Button` primitive.
- [x] Move detail header, badges, actions, tabs, summary tiles, sync feedback, health state, and error block styles into local CSS.
- [x] Update DataSourcesPage behavior tests to query action buttons by role/name instead of legacy button class.
- [x] Run datasource-management style-boundary and DataSourcesPage regression tests.

### Task 17: Datasource form primitive and local style migration

**Files:**
- Modify: `desktop/src/features/datasource-management/DataSourceForm.tsx`
- Modify: `desktop/src/features/datasource-management/DataSourceManagement.css`
- Modify: `desktop/src/features/datasource-management/__tests__/DataSourceManagement.styles.test.ts`

- [x] Add failing style-boundary test that DataSourceForm imports local CSS, has no inline styles, and uses shared form primitives.
- [x] Replace datasource form text inputs, environment select, database type controls, and form actions with `Input`, `Select`, and `Button`.
- [x] Move datasource form layout, checkbox rows, nested SSH/SSL panels, test result, sync section, and action styles into local CSS.
- [x] Preserve existing field labels, placeholders, conditional SQLite/SSH/SSL rendering, port defaults, and submit/test actions.
- [x] Run datasource-management style-boundary and DataSourcesPage regression tests.

### Task 18: Datasource page shell local ownership

**Files:**
- Modify: `desktop/src/pages/DataSourcesPage.tsx`
- Modify: `desktop/src/features/datasource-management/DataSourceManagement.css`
- Modify: `desktop/src/features/datasource-management/__tests__/DataSourceManagement.styles.test.ts`
- Modify: `desktop/src/pages/__tests__/DataSourcesPage.test.tsx`
- Modify: `desktop/src/App.css`

- [x] Add failing style-boundary test that DataSourcesPage uses `Button` and `EmptyState`, has no inline styles, and imports datasource local CSS.
- [x] Replace page/workspace header actions and empty state action with shared primitives.
- [x] Move datasource page shell, console, list, form, and detail layout styles from `App.css` into `DataSourceManagement.css`.
- [x] Keep legacy datasource class names only where existing components/tests still need them, with style ownership local to the datasource feature.
- [x] Run datasource-management style-boundary and DataSourcesPage regression tests.

### Task 19: Diagnostics page local style and state primitives

**Files:**
- Create: `desktop/src/pages/DiagnosticsPage.css`
- Modify: `desktop/src/pages/DiagnosticsPage.tsx`
- Modify: `desktop/src/pages/__tests__/DiagnosticsPage.test.tsx`
- Create: `desktop/src/pages/__tests__/DiagnosticsPage.styles.test.ts`
- Modify: `desktop/src/App.css`

- [x] Add failing style-boundary test that DiagnosticsPage imports local CSS and App.css does not own diagnostics selectors.
- [x] Replace diagnostics action buttons and log-group dropdown buttons with the shared `Button` primitive.
- [x] Replace inline diagnostic error and empty-log affordances with `ErrorState` and `EmptyState`.
- [x] Move diagnostics page, summary, source picker, source cards, status pills, and log content styles into `DiagnosticsPage.css`.
- [x] Update DiagnosticsPage behavior tests to assert new local classes while preserving role/aria behavior.
- [x] Run DiagnosticsPage behavior and style-boundary tests.

### Task 20: SQL console workspace local style ownership

**Files:**
- Create: `desktop/src/features/workspace/SqlConsoleWorkspace.css`
- Modify: `desktop/src/features/workspace/SqlConsoleWorkspace.tsx`
- Create: `desktop/src/features/workspace/__tests__/SqlConsoleWorkspace.styles.test.ts`
- Modify: `desktop/src/App.css`

- [x] Add failing style-boundary test that SQL console workspace imports local CSS and App.css does not own SQL console selectors.
- [x] Move SQL console toolbar, scroll pane, prompt, editor inline shell, entries, result table, null, and empty-result styles into feature-local CSS.
- [x] Remove Tailwind utility classes from the SQL console workspace source in favor of local selectors.
- [x] Remove old SQL workspace/editor/output/console business styles from `App.css`.
- [x] Run SQL console behavior and style-boundary tests.

### Task 21: Workspace schema/context drawer style cleanup

**Files:**
- Create: `desktop/src/features/assistant/ContextDrawer.css`
- Create: `desktop/src/features/assistant/__tests__/ContextDrawer.styles.test.ts`
- Create: `desktop/src/features/workspace/TableWorkspace.css`
- Create: `desktop/src/features/workspace/table/TableSchemaPane.css`
- Create: `desktop/src/features/workspace/smartQuery/AskContextDropZone.css`
- Create: `desktop/src/features/workspace/__tests__/WorkspaceLocalStyles.test.ts`
- Modify: `desktop/src/features/assistant/ContextDrawer.tsx`
- Modify: `desktop/src/features/workspace/TableWorkspace.tsx`
- Modify: `desktop/src/features/workspace/table/TableSchemaPane.tsx`
- Modify: `desktop/src/features/workspace/smartQuery/AskContextDropZone.tsx`
- Modify: `desktop/src/App.css`

- [x] Add failing style-boundary tests for ContextDrawer, table workspace tabs, schema pane, and smart-query context drop zone.
- [x] Move ContextDrawer width/header/body/info-list styles into feature-local CSS and remove its hifi assistant selector usage.
- [x] Move table workspace tab layout into `TableWorkspace.css` and replace clickable tab divs with tab buttons.
- [x] Move schema pane table, constraint badge, AI confidence, and semantic tag styles into `TableSchemaPane.css`; remove inline styles.
- [x] Move smart-query context drop zone/chip styles and animation into local CSS.
- [x] Remove migrated and unused schema, ER, assistant, table workspace, and drop-zone business styles from `App.css`.
- [x] Run the new style-boundary tests.

### Task 22: Smart query home local style ownership

**Files:**
- Create: `desktop/src/features/workspace/SmartQueryHome.css`
- Create: `desktop/src/features/workspace/__tests__/SmartQueryHome.styles.test.ts`
- Modify: `desktop/src/features/workspace/SmartQueryHome.tsx`
- Modify: `desktop/src/features/workspace/smartQuery/SmartQueryHero.tsx`
- Modify: `desktop/src/features/workspace/smartQuery/AskInputBox.tsx`
- Modify: `desktop/src/App.css`

- [x] Add failing style-boundary test for smart-query home, hero, and ask input local CSS ownership.
- [x] Move smart-query home shell, hero, gradient text, and ask input styles into `SmartQueryHome.css`.
- [x] Replace the ask send raw `button` with the shared `Button` primitive.
- [x] Remove migrated smart-query home styles and unused recommendation/recent-visit blocks from `App.css`.
- [x] Run the smart-query style-boundary test.

### Task 23: Workspace tab chrome local style and semantic controls

**Files:**
- Create: `desktop/src/features/workspace/WorkspaceTabs.css`
- Create: `desktop/src/features/workspace/__tests__/WorkspaceTabs.styles.test.ts`
- Create: `desktop/src/features/workspace/__tests__/WorkspaceTabs.test.tsx`
- Modify: `desktop/src/features/workspace/WorkspaceTabs.tsx`
- Modify: `desktop/src/App.css`

- [x] Add failing style and behavior tests for WorkspaceTabs local style ownership, tab activation, close behavior, and add action.
- [x] Move workspace tab bar, scroll area, tab item, close button, and add button styles into `WorkspaceTabs.css`.
- [x] Replace clickable tab `div`, SVG close handlers, and raw add `button` with semantic `Button` controls.
- [x] Remove inline styles and Tailwind utility classes from `WorkspaceTabs.tsx`.
- [x] Remove migrated workspace tab chrome selectors from `App.css` while leaving right-drawer toggle styles for a later focused migration.
- [x] Run the WorkspaceTabs style and interaction tests.

### Task 24: Table ER pane local style and state primitives

**Files:**
- Create: `desktop/src/features/workspace/table/TableErPane.css`
- Create: `desktop/src/features/workspace/table/__tests__/TableErPane.styles.test.ts`
- Modify: `desktop/src/features/workspace/table/TableErPane.tsx`

- [x] Add a failing style-boundary test that TableErPane imports local CSS, uses shared EmptyState/ErrorState/LoadingState primitives, and has no Tailwind utility residue.
- [x] Replace ER pane loading, error, and empty ad hoc divs with shared state primitives.
- [x] Move ER pane layout, caption, canvas, node, field, relation, and muted styles into `TableErPane.css`.
- [x] Keep ER diagram data loading and relationship filtering behavior unchanged.
- [x] Run `TableErPane.styles.test.ts`, the desktop productization regression test set, and `npm run build`.

### Task 25: Remove unused right drawer toggle business styles

**Files:**
- Modify: `desktop/src/features/workspace/__tests__/WorkspaceTabs.styles.test.ts`
- Modify: `desktop/src/App.css`

- [x] Add a failing style-boundary assertion that `App.css` no longer contains the retired `.hifi-right-drawer-toggle-btn` selector.
- [x] Confirm the selector is no longer referenced by source files.
- [x] Remove the unused right drawer toggle button, hover, and active styles from `App.css`.
- [x] Run the WorkspaceTabs style-boundary test before broader verification.

### Task 26: Make table ER tab real instead of placeholder cards

**Files:**
- Modify: `desktop/src/features/workspace/table/TableErPane.tsx`
- Modify: `desktop/src/features/workspace/table/TableErPane.css`
- Modify: `desktop/src/features/workspace/table/__tests__/TableErPane.styles.test.ts`
- Create: `desktop/src/features/workspace/table/__tests__/TableErPane.test.tsx`

- [x] Verify `/schema/er-diagram` already returns `label/source/target` ER data with real and inferred edges.
- [x] Add failing tests proving the table ER tab renders the real `ErDiagram` component, exposes focus/module/full controls, supports one-hop/two-hop focus depth, and toggles inferred relationships.
- [x] Add failing test that no-edge schema data shows an explicit empty state instead of fake static cards.
- [x] Replace the local placeholder card graph with the existing React Flow `ErDiagram` component.
- [x] Use shared `Toolbar`, `Select`, and `Button` primitives for ER controls.
- [x] Keep ER tab style ownership local in `TableErPane.css`.
- [x] Run ER tests, the desktop productization regression test set, and `npm run build`.

### Task 27: Lazy-load the heavy ER diagram runtime

**Files:**
- Modify: `desktop/src/features/workspace/table/TableErPane.tsx`
- Modify: `desktop/src/features/workspace/table/TableErPane.css`
- Modify: `desktop/src/features/workspace/table/__tests__/TableErPane.styles.test.ts`

- [x] Add a failing style-boundary test proving `TableErPane` no longer statically imports `ErDiagram`.
- [x] Convert `ErDiagram` usage to `React.lazy` with a `Suspense` loading state inside the ER canvas.
- [x] Keep existing ER view mode, depth, inferred-edge toggle, and node-focus behavior unchanged.
- [x] Run ER behavior/style tests, the desktop productization regression test set, and `npm run build`.
- [x] Verify the build emits separate `ErDiagram` JS/CSS chunks and the main JS bundle returns to the pre-ER size range.

### Task 28: Productize the React Flow ER diagram internals

**Files:**
- Create: `desktop/src/components/ErDiagram.css`
- Create: `desktop/src/components/__tests__/ErDiagram.styles.test.ts`
- Modify: `desktop/src/components/ErDiagram.tsx`

- [x] Add a failing style-boundary test that `ErDiagram` imports local CSS and no longer uses JSX inline styles or imperative hover style mutation.
- [x] Move table node card, field marker, toggle row, comment footer, relation edge, edge label, controls, and minimap presentation into `ErDiagram.css`.
- [x] Replace ad hoc hover mutation and clickable `div` toggle with CSS hover states and a semantic `button`.
- [x] Clean ER diagram microcopy for annotation, collapsed fields, and inferred relation labels.
- [x] Keep React Flow ER runtime lazy-loaded through `TableErPane`.
- [x] Run ER behavior/style tests, the table productization regression subset, and `npm run build`.

### Task 29: Move Agent evaluation page styles out of App.css

**Files:**
- Create: `desktop/src/pages/AgentEvalPage.css`
- Create: `desktop/src/pages/__tests__/AgentEvalPage.styles.test.ts`
- Modify: `desktop/src/pages/AgentEvalPage.tsx`
- Modify: `desktop/src/App.css`

- [x] Add a failing style-boundary test that `AgentEvalPage` imports local CSS, uses shared UI primitives, and leaves no `hifi-eval` business styles in `App.css`.
- [x] Replace raw page buttons, text inputs, panels, empty/loading blocks with shared `Button`, `Input`, `Panel`, `EmptyState`, and `LoadingState` primitives.
- [x] Rename page-owned classes from `hifi-eval-*` to `agent-eval-*` and move presentation into `AgentEvalPage.css`.
- [x] Remove the old Agent evaluation style block and user-select eval chip references from `App.css`.
- [x] Run the AgentEvalPage style-boundary test, page/router regression subset, and `npm run build`.

### Task 30: Productize the multi-table workspace tab

**Files:**
- Create: `desktop/src/features/workspace/MultiTableWorkspace.css`
- Create: `desktop/src/features/workspace/__tests__/MultiTableWorkspace.styles.test.ts`
- Create: `desktop/src/features/workspace/__tests__/MultiTableWorkspace.test.tsx`
- Modify: `desktop/src/features/workspace/MultiTableWorkspace.tsx`
- Modify: `desktop/src/App.css`

- [x] Add failing style and interaction tests that MultiTableWorkspace uses `WorkspaceShell`, shared `Button`/`Input`/`EmptyState`, local CSS, and no Tailwind or `hifi-*` classes.
- [x] Replace the ad hoc tab pane with `WorkspaceShell` header/body and a clear empty state when no tables are selected.
- [x] Convert clickable cards into semantic buttons and keep canned multi-table query actions intact.
- [x] Make the custom joint-analysis input controlled; support Enter and button submit, clear after submit, and toast on empty input.
- [x] Move MultiTableWorkspace presentation into `MultiTableWorkspace.css` and remove `.hifi-multi-table-workspace` from `App.css`.
- [x] Run MultiTableWorkspace style/behavior tests, workspace/router regression subset, and `npm run build`.

### Task 31: Productize the conversation history workspace tab

**Files:**
- Create: `desktop/src/features/conversation/ConversationHistoryPanel.css`
- Create: `desktop/src/features/conversation/__tests__/ConversationHistoryPanel.styles.test.ts`
- Create: `desktop/src/features/conversation/__tests__/ConversationHistoryPanel.test.tsx`
- Modify: `desktop/src/features/conversation/ConversationHistoryPanel.tsx`
- Modify: `desktop/src/App.css`

- [x] Add failing style and behavior tests that ConversationHistoryPanel uses `WorkspaceShell`, shared `Button`/`EmptyState`, local CSS, and no Tailwind or global guide chip classes.
- [x] Replace the ad hoc Tailwind layout with a `WorkspaceShell` header, toolbar count badge, body, and shared empty state.
- [x] Convert the delete affordance from a non-semantic span into an accessible icon button with an explicit label.
- [x] Keep open-conversation behavior and relative/invalid time display behavior intact.
- [x] Move conversation history presentation into `ConversationHistoryPanel.css` and remove `.hifi-guide-chip-prod` from `App.css`.
- [x] Run ConversationHistoryPanel style/behavior tests, workspace/router regression subset, and `npm run build`.

### Task 32: Tighten the ER diagram product scope

**Files:**
- Modify: `desktop/src/features/workspace/table/TableErPane.tsx`
- Modify: `desktop/src/features/workspace/table/__tests__/TableErPane.test.tsx`
- Modify: `desktop/src/components/ErDiagram.tsx`
- Modify: `desktop/src/components/__tests__/ErDiagram.styles.test.ts`

- [x] Revert the attempted backend module tag grouping direction; ER scope should not depend on synthetic business tags.
- [x] Add a failing ER tab test proving the unsupported "模块" view is not exposed.
- [x] Remove the module view option and narrow ER view modes to focused relationships or full graph.
- [x] Replace full-graph layout's module-tag grouping with a tag-independent multi-column layout.
- [x] Run ER frontend tests, schema sync regression tests, and `npm run build`.

### Task 33: Localize artifact card and artifact view styles

**Files:**
- Create: `desktop/src/features/workspace/artifacts/ArtifactCard.css`
- Create: `desktop/src/features/workspace/artifacts/ArtifactViews.css`
- Create: `desktop/src/features/workspace/artifacts/__tests__/ArtifactViews.styles.test.ts`
- Modify: `desktop/src/features/workspace/artifacts/ArtifactCard.tsx`
- Modify: `desktop/src/features/workspace/artifacts/SqlArtifactView.tsx`
- Modify: `desktop/src/features/workspace/artifacts/MarkdownArtifactView.tsx`
- Modify: `desktop/src/features/workspace/artifacts/ChartArtifactView.tsx`
- Modify: `desktop/src/features/workspace/artifacts/TableArtifactView.tsx`
- Modify: `desktop/src/features/workspace/artifacts/table/ArtifactTableGrid.tsx`
- Modify: `desktop/src/features/workspace/artifacts/table/ArtifactTable.css`
- Modify: `desktop/src/features/conversation/workspace/conversationWorkspace.css`
- Modify: `desktop/src/features/conversation/workspace/__tests__/ArtifactEvidencePanel.test.tsx`
- Modify: `desktop/src/App.css`

- [x] Add failing style-boundary tests that ArtifactCard/SQL/Markdown/Chart use local CSS and shared `Button` primitives instead of global `hifi-*`, Tailwind utility classes, or chart inline styles.
- [x] Move shared artifact card, badge, pill, action, SQL editor, and chart body styles out of `App.css` into artifact-local stylesheets.
- [x] Replace SQL, Markdown, and chart raw action buttons with shared `Button`.
- [x] Rename artifact table metadata pills, sort indicator, and empty state to artifact-local classes.
- [x] Update conversation artifact evidence preview selectors for the chart card rename.
- [x] Run artifact style/behavior regression tests and `npm run build`.

### Task 34: Migrate command palette behavior to cmdk

**Files:**
- Create: `desktop/src/components/CommandPalette.css`
- Create: `desktop/src/components/__tests__/CommandPalette.styles.test.ts`
- Create: `desktop/src/components/__tests__/CommandPalette.test.tsx`
- Modify: `desktop/src/components/CommandPalette.tsx`
- Modify: `desktop/src/App.css`
- Modify: `desktop/package.json`
- Modify: `desktop/package-lock.json`

- [x] Add `cmdk` as the mature headless command palette foundation.
- [x] Add failing style/foundation tests requiring `CommandPalette` to use `cmdk`, local CSS, and no manual selected-index/window-keydown command logic.
- [x] Replace the handwritten search, filtered list, selected index, keyboard navigation, and scroll management with `cmdk` primitives.
- [x] Keep the DBFox command item API and visual presentation local through `CommandPalette.css`.
- [x] Move command palette styles out of `App.css`.
- [x] Add behavior tests for rendering, command selection, and Escape close.
- [x] Run command palette tests and `npm run build`.

### Task 35: Migrate conversation artifact split pane to react-resizable-panels

**Files:**
- Create: `desktop/src/features/conversation/workspace/__tests__/ConversationWorkspaceSplitPane.styles.test.ts`
- Modify: `desktop/src/features/conversation/workspace/ConversationWorkspace.tsx`
- Modify: `desktop/src/features/conversation/workspace/ArtifactDock.tsx`
- Modify: `desktop/src/features/conversation/workspace/conversationWorkspace.css`
- Modify: `desktop/src/features/conversation/workspace/__tests__/ConversationWorkspace.test.tsx`
- Modify: `desktop/src/features/conversation/workspace/__tests__/ArtifactDock.test.tsx`
- Modify: `desktop/package.json`
- Modify: `desktop/package-lock.json`

- [x] Add `react-resizable-panels` as the mature desktop split-pane foundation.
- [x] Add failing source/style tests requiring `ConversationWorkspace` to own the split pane through panel primitives and forbidding `ArtifactDock` from reintroducing pointermove/dock-width state.
- [x] Move artifact dock resize ownership from `ArtifactDock` into `ConversationWorkspace` via `PanelGroup`, `Panel`, and `PanelResizeHandle` aliases.
- [x] Remove inline width variables, manual pointer listeners, keyboard width math, and clamp helpers from `ArtifactDock`.
- [x] Update local conversation workspace CSS for panel group, main panel, dock panel, resize handle, and mobile hiding behavior.
- [x] Run split-pane style/behavior tests and `npm run build`.

### Task 36: Migrate table rendering cores and visual frames to TanStack Table

**Files:**
- Modify: `desktop/src/features/workspace/artifacts/table/ArtifactTableGrid.tsx`
- Modify: `desktop/src/features/workspace/artifacts/table/ArtifactTable.css`
- Modify: `desktop/src/features/workspace/artifacts/__tests__/TableArtifactView.styles.test.ts`
- Modify: `desktop/src/features/workspace/table/TablePreviewPane.tsx`
- Modify: `desktop/src/features/workspace/table/TablePreviewPane.css`
- Modify: `desktop/src/features/workspace/table/__tests__/TablePreviewPane.styles.test.ts`
- Modify: `desktop/src/features/workspace/table/__tests__/TablePreviewPane.test.tsx`
- Modify: `desktop/package.json`
- Modify: `desktop/package-lock.json`

- [x] Add `@tanstack/react-table` as the mature headless table foundation.
- [x] Add failing source/style tests requiring both artifact result tables and base table previews to use `useReactTable`, `getCoreRowModel`, and `flexRender`.
- [x] Migrate `ArtifactTableGrid` from manual column/row loops to TanStack row and column models while keeping DBFox sorting, selection, copy, NULL, numeric alignment, and column type badges.
- [x] Migrate `TablePreviewPane` table body from manual rendering to TanStack row and column models while keeping server-side search/filter/sort, page-stability-on-next-load, temporal display formatting, image cells, copy, and NULL behavior.
- [x] Replace the old inherited `hifi-table` visual frame with local `artifact-table-*` and `table-preview-*` border, header, row, cell, selection, type badge, and NULL pill styling.
- [x] Run artifact table tests, base preview table tests, and `npm run build`.

### Task 37: Move table filter and sort panels to DBFox Radix Popover

**Files:**
- Create: `desktop/src/components/ui/popover.tsx`
- Modify: `desktop/src/components/ui/index.ts`
- Modify: `desktop/src/components/ui/__tests__/ui-primitives.test.tsx`
- Modify: `desktop/src/features/workspace/artifacts/table/ArtifactTableToolbar.tsx`
- Modify: `desktop/src/features/workspace/artifacts/table/ArtifactTable.css`
- Modify: `desktop/src/features/workspace/artifacts/__tests__/TableArtifactView.styles.test.ts`
- Modify: `desktop/src/features/workspace/table/TablePreviewPane.tsx`
- Modify: `desktop/src/features/workspace/table/TablePreviewPane.css`
- Modify: `desktop/src/features/workspace/table/__tests__/TablePreviewPane.styles.test.ts`
- Modify: `desktop/src/features/workspace/table/__tests__/TablePreviewPane.test.tsx`
- Modify: `desktop/package.json`
- Modify: `desktop/package-lock.json`

- [x] Add `@radix-ui/react-popover` behind a DBFox `Popover`, `PopoverTrigger`, and `PopoverContent` primitive exported from `components/ui`.
- [x] Add failing primitive and table style tests requiring table filter/sort controls to use DBFox Popover wrappers instead of direct Radix imports or handwritten `filterOpen`/`sortOpen` toggles.
- [x] Move artifact result filter and sort controls from inline expanded rows into local `artifact-table-popover-*` floating surfaces.
- [x] Move base table preview filter and sort controls from inline expanded rows into local `table-preview-popover-*` floating surfaces.
- [x] Preserve server-side SQL filter/sort behavior, UI primitive control styling, and existing table regression behavior.
- [x] Run UI primitive tests, table style/behavior tests, and `npm run build`.

### Task 38: Move image and long-content table previews to DBFox HoverCard/Dialog

**Files:**
- Create: `desktop/src/components/ui/hover-card.tsx`
- Create: `desktop/src/components/ImageCell.css`
- Create: `desktop/src/components/data-grid/__tests__/DataGridCell.styles.test.ts`
- Create: `desktop/src/components/data-grid/__tests__/DataGridCell.test.tsx`
- Modify: `desktop/src/components/ui/index.ts`
- Modify: `desktop/src/components/ui/dialog.tsx`
- Modify: `desktop/src/components/ui/__tests__/ui-primitives.test.tsx`
- Modify: `desktop/src/components/ImageCell.tsx`
- Modify: `desktop/src/components/__tests__/ImageCell.styles.test.ts`
- Modify: `desktop/src/components/__tests__/ImageCell.test.tsx`
- Modify: `desktop/src/components/DataTable.tsx`
- Modify: `desktop/src/components/data-grid/DataGridCell.tsx`
- Modify: `desktop/src/components/data-grid/data-grid.css`
- Modify: `desktop/src/App.css`
- Modify: `desktop/package.json`
- Modify: `desktop/package-lock.json`

- [x] Add `@radix-ui/react-hover-card` behind a DBFox `HoverCard`, `HoverCardTrigger`, and `HoverCardContent` primitive exported from `components/ui`.
- [x] Add failing tests requiring image previews to use DBFox HoverCard/Dialog and forbidding manual portal, viewport, and popover position state.
- [x] Move `ImageCell` hover preview and lightbox from handwritten `createPortal` overlays into DBFox HoverCard and Dialog, with local `ImageCell.css`.
- [x] Fix DBFox Dialog title/description wrappers to use Radix title/description primitives so dialog names are accessible.
- [x] Add failing tests requiring long text/JSON cell previews to live in `DataGridCell` instead of parent `DOMRect` preview state.
- [x] Move long text/JSON previews into DataGridCell HoverCard content, preserving selection, copy, and double-click inspect behavior.
- [x] Remove DataTable parent preview state and old fixed `.data-grid-preview` overlay styling.
- [x] Run UI primitive, image cell, data-grid cell, artifact table, base table preview tests, and `npm run build`.

### Task 39: Move DataGrid column actions to DBFox Radix DropdownMenu

**Files:**
- Create: `desktop/src/components/ui/dropdown-menu.tsx`
- Create: `desktop/src/components/data-grid/__tests__/DataGridColumnMenu.styles.test.ts`
- Create: `desktop/src/components/data-grid/__tests__/DataGridHeaderCell.test.tsx`
- Modify: `desktop/src/components/ui/index.ts`
- Modify: `desktop/src/components/ui/__tests__/ui-primitives.test.tsx`
- Modify: `desktop/src/components/DataTable.tsx`
- Modify: `desktop/src/components/data-grid/DataGridHeaderCell.tsx`
- Modify: `desktop/src/components/data-grid/DataGridColumnMenu.tsx`
- Modify: `desktop/src/components/data-grid/data-grid.css`
- Modify: `desktop/package.json`
- Modify: `desktop/package-lock.json`

- [x] Add `@radix-ui/react-dropdown-menu` behind DBFox `DropdownMenu`, `DropdownMenuTrigger`, `DropdownMenuContent`, `DropdownMenuItem`, and `DropdownMenuSeparator` primitives.
- [x] Add failing primitive and DataGrid tests requiring column actions to use DBFox DropdownMenu wrappers.
- [x] Move DataGrid column action opening/positioning out of `DataTable` state and into Radix DropdownMenu.
- [x] Remove `openColumnMenu`, `setOpenColumnMenu`, `menuOpen`, and `onToggleMenu` from the DataGrid column menu path.
- [x] Keep column sort, filter, copy column name, copy SELECT, and hide-column behavior.
- [x] Remove Tailwind utility styling from `DataGridHeaderCell` menu controls and move the visual state into local `data-grid.css`.
- [x] Run UI primitive, DataGrid column menu/header, DataGrid cell, artifact table, base table preview tests, and `npm run build`.

### Task 40: Move DataGrid right-click actions to DBFox Radix ContextMenu

**Files:**
- Create: `desktop/src/components/ui/context-menu.tsx`
- Create: `desktop/src/components/data-grid/__tests__/DataGridContextMenu.styles.test.ts`
- Create: `desktop/src/components/data-grid/__tests__/DataTableContextMenu.test.tsx`
- Modify: `desktop/src/components/ui/index.ts`
- Modify: `desktop/src/components/ui/__tests__/ui-primitives.test.tsx`
- Modify: `desktop/src/components/DataTable.tsx`
- Modify: `desktop/src/components/data-grid/DataGridContextMenu.tsx`
- Modify: `desktop/src/components/data-grid/types.ts`
- Modify: `desktop/src/components/data-grid/data-grid.css`
- Modify: `desktop/package.json`
- Modify: `desktop/package-lock.json`

- [x] Add `@radix-ui/react-context-menu` behind DBFox `ContextMenu`, `ContextMenuTrigger`, `ContextMenuContent`, `ContextMenuItem`, and `ContextMenuSeparator` primitives.
- [x] Add failing primitive and DataGrid tests requiring right-click actions to use DBFox ContextMenu wrappers.
- [x] Move cell and row right-click opening out of parent x/y state and into ContextMenu trigger/content ownership.
- [x] Preserve cell copy, value filter, non-null filter, clear-column-filter, row JSON copy, and INSERT SQL copy actions.
- [x] Preserve the row more button with DBFox DropdownMenu for click-based row actions.
- [x] Remove `DataGridContextMenuState`, `setContextMenu`, `clientX/clientY`, `getBoundingClientRect`, fixed backdrop, and left/top menu styles from the right-click path.
- [x] Run UI primitive, DataGrid context menu, related table tests, static legacy-positioning scan, and `npm run build`.

### Task 41: Share long-content table previews across result tables

**Files:**
- Create: `desktop/src/components/data-grid/CellValuePreview.tsx`
- Create: `desktop/src/components/data-grid/CellValuePreview.css`
- Create: `desktop/src/components/data-grid/__tests__/CellValuePreview.test.tsx`
- Modify: `desktop/src/components/data-grid/DataGridCell.tsx`
- Modify: `desktop/src/components/data-grid/data-grid.css`
- Modify: `desktop/src/components/data-grid/__tests__/DataGridCell.styles.test.ts`
- Modify: `desktop/src/components/data-grid/__tests__/DataGridCell.test.tsx`
- Modify: `desktop/src/features/workspace/artifacts/table/ArtifactTableGrid.tsx`
- Modify: `desktop/src/features/workspace/artifacts/__tests__/TableArtifactView.styles.test.ts`
- Modify: `desktop/src/features/workspace/artifacts/__tests__/TableArtifactView.test.tsx`
- Modify: `desktop/src/features/workspace/table/TablePreviewPane.tsx`
- Modify: `desktop/src/features/workspace/table/__tests__/TablePreviewPane.styles.test.ts`

- [x] Extract long text and JSON cell preview rendering into shared `CellValuePreview` powered by DBFox HoverCard.
- [x] Add failing component/style tests requiring the shared preview to own hover positioning, bounded card sizing, stats, and footer hints.
- [x] Keep short values lightweight while long text, JSON, key/value strings, and list-like values get structured preview rendering.
- [x] Connect the shared preview to DataGrid cells, base table preview cells, and artifact result table cells.
- [x] Preserve table-specific copy, selection, NULL, temporal display formatting, image-cell, and inspect behavior.
- [x] Remove obsolete DataGrid-only preview classes from `data-grid.css`.
- [x] Run CellValuePreview, DataGrid cell, artifact table, base table preview tests, static legacy-preview scan, and `npm run build`.

### Task 42: Move datasource connection form validation to react-hook-form and zod

**Files:**
- Create: `desktop/src/features/datasource-management/__tests__/DataSourceForm.test.tsx`
- Modify: `desktop/src/features/datasource-management/DataSourceForm.tsx`
- Modify: `desktop/src/features/datasource-management/__tests__/DataSourceManagement.styles.test.ts`
- Modify: `desktop/src/pages/DataSourcesPage.tsx`
- Modify: `desktop/package.json`
- Modify: `desktop/package-lock.json`

- [x] Add `react-hook-form`, `@hookform/resolvers`, and `zod` for complex datasource form validation.
- [x] Add failing behavior and source-boundary tests requiring datasource form submission to go through RHF/Zod instead of direct click handlers and parent-page `validateForm`.
- [x] Define `datasourceFormSchema` with DB-type-aware validation for MySQL/PostgreSQL and SQLite required fields.
- [x] Move form field registration, submit validation, and test-connection validation into `DataSourceForm`.
- [x] Pass validated form values back to `DataSourcesPage` so existing create/update/test/sync flows keep their business ownership.
- [x] Remove parent-page handwritten `validateForm` while preserving datasource create, edit, connection test, schema sync, and AI enrichment behavior.
- [x] Run datasource form tests, datasource page regression tests, static legacy-validation scan, and `npm run build`.

### Task 43: Move workspace tab strip to DBFox Radix Tabs

**Files:**
- Create: `desktop/src/components/ui/tabs.tsx`
- Modify: `desktop/src/components/ui/index.ts`
- Modify: `desktop/src/components/ui/__tests__/ui-primitives.test.tsx`
- Modify: `desktop/src/features/workspace/WorkspaceTabs.tsx`
- Modify: `desktop/src/features/workspace/WorkspaceTabs.css`
- Modify: `desktop/src/features/workspace/__tests__/WorkspaceTabs.styles.test.ts`
- Modify: `desktop/package.json`
- Modify: `desktop/package-lock.json`

- [x] Add `@radix-ui/react-tabs` behind DBFox `Tabs`, `TabsList`, `TabsTrigger`, and `TabsContent` primitives.
- [x] Add failing primitive and workspace tab tests requiring the tab strip to use DBFox Tabs wrappers.
- [x] Move WorkspaceTabs tablist and trigger semantics from manual `role="tablist"` / `role="tab"` markup into Radix Tabs.
- [x] Preserve active-tab switching, table context selection, close-button behavior, add-SQL button, and local tab chrome styling.
- [x] Keep direct Radix imports contained inside `components/ui/tabs.tsx`.
- [x] Run UI primitive, WorkspaceTabs behavior/style tests, static manual-role scan, and `npm run build`.

### Task 44: Move DBFox Select to Radix Select and polish long-cell summaries

**Files:**
- Create: `desktop/src/components/ui/select.css`
- Create: `desktop/src/components/ui/__tests__/select.styles.test.ts`
- Create: `desktop/src/test/setup.ts`
- Modify: `desktop/src/components/ui/select.tsx`
- Modify: `desktop/src/components/ui/__tests__/ui-primitives.test.tsx`
- Modify: `desktop/src/components/data-grid/CellValuePreview.tsx`
- Modify: `desktop/src/components/data-grid/CellValuePreview.css`
- Modify: `desktop/src/components/data-grid/__tests__/CellValuePreview.test.tsx`
- Modify: `desktop/src/features/workspace/artifacts/__tests__/TableArtifactView.test.tsx`
- Modify: `desktop/src/features/workspace/table/__tests__/TablePreviewPane.test.tsx`
- Modify: `desktop/src/features/workspace/table/__tests__/TableErPane.test.tsx`
- Modify: `desktop/vitest.config.ts`
- Modify: `desktop/package.json`
- Modify: `desktop/package-lock.json`

- [x] Add `@radix-ui/react-select` behind the DBFox `Select` primitive with local `.dbfox-select-*` styling.
- [x] Preserve the existing `<Select><option /></Select>` call-site API while rendering Radix `Root`, `Trigger`, `Content`, and `Item`.
- [x] Adapt Radix `onValueChange` back to the existing event-like `onChange({ target.value })` contract.
- [x] Add jsdom pointer-capture setup so Radix pointer interactions are testable.
- [x] Update table, artifact, ER, datasource, and primitive tests to use combobox/option interactions instead of native select `change`.
- [x] Replace long text table triggers with compact typed summaries (`键值` / `列表` / `文本`) while keeping HoverCard full previews and full-value copy behavior.
- [x] Run UI primitive, DataGrid preview, artifact table, base table preview, ER pane, datasource form/page tests, and `npm run build`.

### Task 45: Normalize DBFox Tooltip on Radix and migrate icon-only actions

**Files:**
- Create: `desktop/src/components/ui/tooltip.css`
- Create: `desktop/src/components/ui/__tests__/tooltip.styles.test.ts`
- Modify: `desktop/src/components/ui/tooltip.tsx`
- Modify: `desktop/src/components/ui/__tests__/ui-primitives.test.tsx`
- Modify: `desktop/src/components/data-grid/DataGridHeaderCell.tsx`
- Modify: `desktop/src/components/data-grid/__tests__/DataGridColumnMenu.styles.test.ts`
- Modify: `desktop/src/components/data-grid/__tests__/DataGridHeaderCell.test.tsx`
- Modify: `desktop/src/features/workspace/WorkspaceTabs.tsx`
- Modify: `desktop/src/features/workspace/__tests__/WorkspaceTabs.styles.test.ts`
- Modify: `desktop/src/features/workspace/__tests__/WorkspaceTabs.test.tsx`
- Modify: `desktop/src/test/setup.ts`

- [x] Keep `@radix-ui/react-tooltip` behind the DBFox `Tooltip`, `TooltipTrigger`, `TooltipContent`, and `TooltipProvider` API.
- [x] Move Tooltip visual styling from TSX utility strings into local `tooltip.css`.
- [x] Add tooltip arrow, bounded width, elevation, and open/closed animation states using DBFox tokens.
- [x] Add jsdom `ResizeObserver` setup for Radix Tooltip positioning tests.
- [x] Migrate DataGrid column action menu trigger from a bare icon button to DBFox Tooltip + DropdownMenu.
- [x] Migrate WorkspaceTabs close and add icon-only actions from native `title` to DBFox Tooltip while preserving tab switching and close/add behavior.
- [x] Run Tooltip primitive tests, DataGrid header/menu tests, WorkspaceTabs tests, and `npm run build`.

### Task 46: Add TanStack Virtual to the shared DataTable row body

**Files:**
- Create: `desktop/src/components/data-grid/__tests__/DataTableVirtualization.styles.test.ts`
- Modify: `desktop/src/components/DataTable.tsx`
- Modify: `desktop/src/components/data-grid/data-grid.css`
- Modify: `desktop/src/components/data-grid/__tests__/DataTableContextMenu.test.tsx`
- Modify: `desktop/src/components/data-grid/__tests__/DataGridContextMenu.styles.test.ts`
- Modify: `desktop/package.json`
- Modify: `desktop/package-lock.json`

- [x] Add `@tanstack/react-virtual` for large DataTable row rendering.
- [x] Replace full `visibleRows.map` body rendering with `rowVirtualizer` + `virtualRows.map`.
- [x] Keep semantic table markup and existing sticky header, row index, cell context menu, row dropdown, copy, filter, and inspect behavior.
- [x] Use virtual spacer rows to preserve scroll height while rendering only the visible row window.
- [x] Add a bounded observer fallback so TanStack Virtual has stable dimensions in jsdom and zero-layout edge cases.
- [x] Keep DBFox visual ownership in local `data-grid.css`.
- [x] Run DataTable virtualization/context-menu tests, DataGrid surrounding tests, and `npm run build`.

### Task 47: Move datasource sidebar scrolling and picker to DBFox Radix primitives

**Files:**
- Create: `desktop/src/components/ui/scroll-area.css`
- Create: `desktop/src/components/ui/__tests__/scroll-area.styles.test.ts`
- Create: `desktop/src/features/datasource/__tests__/DataSourceTree.styles.test.ts`
- Create: `desktop/src/features/datasource/__tests__/DataSourceTree.test.tsx`
- Modify: `desktop/src/components/ui/scroll-area.tsx`
- Modify: `desktop/src/components/ui/__tests__/ui-primitives.test.tsx`
- Modify: `desktop/src/features/datasource/DataSourceTree.tsx`
- Modify: `desktop/src/features/datasource/DataSourceTree.css`

- [x] Move ScrollArea utility styling into local `.dbfox-scroll-area-*` CSS classes.
- [x] Default DBFox ScrollArea to stable Radix `type="always"` rendering so desktop scroll boundaries do not depend on hover-only mounting.
- [x] Replace the datasource picker's manual open state and document mousedown listener with DBFox `DropdownMenu`.
- [x] Replace sidebar icon-only native `title` hints with DBFox `Tooltip`.
- [x] Wrap the schema/table tree body in DBFox `ScrollArea` and keep tree status, schema, group, table, and quick-nav styling local.
- [x] Remove the touched inline refresh style and Tailwind residue from the datasource tree interaction controls.
- [x] Run ScrollArea primitive tests, DataSourceTree behavior/style tests, adjacent datasource/workspace regressions, and `npm run build`.

### Task 48: Move DBFox DropdownMenu visual styling into local CSS

**Files:**
- Create: `desktop/src/components/ui/dropdown-menu.css`
- Create: `desktop/src/components/ui/__tests__/dropdown-menu.styles.test.ts`
- Modify: `desktop/src/components/ui/dropdown-menu.tsx`
- Modify: `desktop/src/components/ui/__tests__/ui-primitives.test.tsx`

- [x] Keep `@radix-ui/react-dropdown-menu` behind the DBFox `DropdownMenu` primitive API.
- [x] Replace TSX utility styling strings with `.dbfox-dropdown-menu-*` classes.
- [x] Move content elevation, border, animation, item focus, disabled, and separator styles into `dropdown-menu.css`.
- [x] Add failing static and rendered primitive tests that guard against reintroducing utility strings in DropdownMenu.
- [x] Run DropdownMenu primitive tests, DataGrid column/row menu tests, DataSourceTree dropdown tests, and `npm run build`.

### Task 49: Move DBFox ContextMenu visual styling into local CSS

**Files:**
- Create: `desktop/src/components/ui/context-menu.css`
- Create: `desktop/src/components/ui/__tests__/context-menu.styles.test.ts`
- Modify: `desktop/src/components/ui/context-menu.tsx`
- Modify: `desktop/src/components/ui/__tests__/ui-primitives.test.tsx`

- [x] Keep `@radix-ui/react-context-menu` behind the DBFox `ContextMenu` primitive API.
- [x] Replace TSX utility styling strings with `.dbfox-context-menu-*` classes.
- [x] Move content elevation, border, animation, item focus, disabled, and separator styles into `context-menu.css`.
- [x] Add failing static and rendered primitive tests that guard against reintroducing utility strings in ContextMenu.
- [x] Run ContextMenu primitive tests, DataGrid right-click menu tests, static context menu style tests, and `npm run build`.

### Task 50: Move DBFox HoverCard visual styling into local CSS

**Files:**
- Create: `desktop/src/components/ui/hover-card.css`
- Create: `desktop/src/components/ui/__tests__/hover-card.styles.test.ts`
- Modify: `desktop/src/components/ui/hover-card.tsx`
- Modify: `desktop/src/components/ui/__tests__/ui-primitives.test.tsx`

- [x] Keep `@radix-ui/react-hover-card` behind the DBFox `HoverCard` primitive API.
- [x] Replace TSX utility styling strings with `.dbfox-hover-card-*` classes.
- [x] Move content elevation, border, animation, and arrow styling into `hover-card.css`.
- [x] Add a DBFox HoverCard arrow so long-cell previews read as anchored desktop popovers.
- [x] Add failing static and rendered primitive tests that guard against reintroducing utility strings in HoverCard.
- [x] Run HoverCard primitive tests, CellValuePreview tests, DataGrid cell tests, base table preview tests, artifact table tests, and `npm run build`.

### Task 51: Move DBFox Popover visual styling into local CSS

**Files:**
- Create: `desktop/src/components/ui/popover.css`
- Create: `desktop/src/components/ui/__tests__/popover.styles.test.ts`
- Modify: `desktop/src/components/ui/popover.tsx`
- Modify: `desktop/src/components/ui/__tests__/ui-primitives.test.tsx`

- [x] Keep `@radix-ui/react-popover` behind the DBFox `Popover` primitive API.
- [x] Replace TSX utility styling strings with `.dbfox-popover-*` classes.
- [x] Move content elevation, border, animation, and arrow styling into `popover.css`.
- [x] Add a DBFox Popover arrow so filter and table toolbar popovers feel anchored to their trigger.
- [x] Add failing static and rendered primitive tests that guard against reintroducing utility strings in Popover.
- [x] Run Popover primitive tests, base table preview tests, artifact table tests, and `npm run build`.

### Task 52: Move DBFox Dialog visual styling into local CSS

**Files:**
- Create: `desktop/src/components/ui/dialog.css`
- Create: `desktop/src/components/ui/__tests__/dialog.styles.test.ts`
- Modify: `desktop/src/components/ui/dialog.tsx`
- Modify: `desktop/src/components/ui/__tests__/ui-primitives.test.tsx`

- [x] Keep `@radix-ui/react-dialog` behind the DBFox `Dialog` primitive API.
- [x] Replace TSX utility styling strings with `.dbfox-dialog-*` classes.
- [x] Move overlay, content, close button, header, footer, title, and description styling into `dialog.css`.
- [x] Preserve the shared dialog container hook for desktop canvas rendering.
- [x] Add failing static and rendered primitive tests that guard against reintroducing utility strings in Dialog.
- [x] Run Dialog primitive tests, ImageCell dialog tests, ImageCell style tests, and `npm run build`.

### Task 53: Move DBFox Tabs visual styling into local CSS

**Files:**
- Create: `desktop/src/components/ui/tabs.css`
- Create: `desktop/src/components/ui/__tests__/tabs.styles.test.ts`
- Modify: `desktop/src/components/ui/tabs.tsx`
- Modify: `desktop/src/components/ui/__tests__/ui-primitives.test.tsx`

- [x] Keep `@radix-ui/react-tabs` behind the DBFox `Tabs` primitive API.
- [x] Replace TSX utility styling strings with `.dbfox-tabs-*` classes.
- [x] Move list, trigger, disabled, focus, and content outline styles into `tabs.css`.
- [x] Keep product-specific workspace tab visuals in `WorkspaceTabs.css`.
- [x] Add failing static and rendered primitive tests that guard against reintroducing utility strings in Tabs.
- [x] Run Tabs primitive tests, WorkspaceTabs behavior/style tests, and `npm run build`.

### Task 54: Wrap cmdk behind DBFox Command primitives

**Files:**
- Create: `desktop/src/components/ui/command.tsx`
- Create: `desktop/src/components/ui/command.css`
- Create: `desktop/src/components/ui/__tests__/command.styles.test.ts`
- Modify: `desktop/src/components/CommandPalette.tsx`
- Modify: `desktop/src/components/CommandPalette.css`
- Modify: `desktop/src/components/__tests__/CommandPalette.styles.test.ts`
- Modify: `desktop/src/components/ui/index.ts`
- Modify: `desktop/src/components/ui/__tests__/ui-primitives.test.tsx`
- Modify: `desktop/src/test/setup.ts`

- [x] Keep `cmdk` as the command palette behavior engine.
- [x] Move direct `cmdk` imports out of `CommandPalette` and behind DBFox `Command` primitives.
- [x] Move command panel, search, input, list, empty, group, item, icon, label, and keyboard hint styling into `components/ui/command.css`.
- [x] Keep CommandPalette-specific overlay and footer styling in `CommandPalette.css`.
- [x] Add jsdom `scrollIntoView` setup for cmdk selection behavior.
- [x] Add failing static and rendered primitive tests that guard against direct business-level `cmdk` imports and missing DBFox command classes.
- [x] Run Command primitive tests, CommandPalette tests, useAppCommands tests, and `npm run build`.

### Task 55: Wrap react-resizable-panels behind DBFox Resizable primitives

**Files:**
- Create: `desktop/src/components/ui/resizable.tsx`
- Create: `desktop/src/components/ui/resizable.css`
- Create: `desktop/src/components/ui/__tests__/resizable.styles.test.ts`
- Create: `desktop/src/__tests__/AppResizableShell.styles.test.ts`
- Modify: `desktop/src/components/ui/index.ts`
- Modify: `desktop/src/components/ui/__tests__/ui-primitives.test.tsx`
- Modify: `desktop/src/App.tsx`
- Modify: `desktop/src/App.css`
- Modify: `desktop/src/__tests__/appShell.test.ts`
- Modify: `desktop/src/features/datasource/DataSourceTree.tsx`
- Modify: `desktop/src/features/datasource/DataSourceTree.css`
- Modify: `desktop/src/features/datasource/__tests__/DataSourceTree.test.tsx`
- Delete: `desktop/src/features/appShell/useSidebarLayout.ts`

- [x] Keep `react-resizable-panels` behind a DBFox `ResizablePanelGroup`, `ResizablePanel`, and `ResizableHandle` primitive API.
- [x] Move resize handle rail, grip, focus, hover, and active visuals into `components/ui/resizable.css`.
- [x] Replace the App shell's hand-rolled `mousemove`/`mouseup` sidebar dragger with a mature panel group.
- [x] Remove inline sidebar width plumbing from `DataSourceTree`; the split panel is now the single width owner.
- [x] Add failing static and rendered primitive tests that guard against reintroducing `app-resizer`, `handleResizeStart`, and `sidebarWidth`.
- [x] Run resizable primitive tests, app shell tests, DataSourceTree tests, and `npm run build`.

### Task 56: Move shared DataTable state core to TanStack Table

**Files:**
- Create: `desktop/src/components/data-grid/__tests__/DataTableTanStackCore.styles.test.ts`
- Modify: `desktop/src/components/DataTable.tsx`
- Modify: `desktop/src/components/data-grid/types.ts`
- Modify: `desktop/src/components/data-grid/DataGridHeaderCell.tsx`
- Modify: `desktop/src/components/data-grid/DataGridColumnMenu.tsx`
- Modify: `desktop/src/components/data-grid/DataGridToolbar.tsx`
- Modify: `desktop/src/components/data-grid/data-grid.css`
- Modify: `desktop/src/components/data-grid/__tests__/DataTableContextMenu.test.tsx`
- Delete: `desktop/src/hooks/useDataTableView.ts`

- [x] Replace the hand-written `useDataTableView` sorting, filtering, and column visibility core with `@tanstack/react-table`.
- [x] Keep DBFox's existing header, toolbar, cell preview, context menu, copy, inspect, and virtualized rendering surfaces.
- [x] Preserve current filter modes (`contains`, `is_null`, `is_not_null`) through TanStack filter functions.
- [x] Preserve natural/date/numeric sorting through a TanStack sorting function.
- [x] Move shared grid state types into `components/data-grid/types.ts` so no component imports the deleted hook.
- [x] Improve the shared data grid visual frame with a local border, radius, shadow, and `border-collapse: separate`.
- [x] Add failing static and rendered tests that guard against reintroducing `useDataTableView` and missing table boundary styling.
- [x] Run DataTable core/context/virtualization/cell preview tests and `npm run build`.

### Task 57: Move LLM configuration form to react-hook-form and zod

**Files:**
- Create: `desktop/src/components/LlmConfigPanel.css`
- Create: `desktop/src/components/__tests__/LlmConfigPanel.styles.test.ts`
- Modify: `desktop/src/components/LlmConfigPanel.tsx`
- Modify: `desktop/src/components/__tests__/LlmConfigPanel.test.tsx`

- [x] Replace the LLM configuration form's hand-written submit handling with `react-hook-form`.
- [x] Add `zod` schema validation through `zodResolver` for API Base URL safety.
- [x] Preserve the existing parent `onChange` live-sync behavior for API key, endpoint, model presets, and custom model input.
- [x] Route "保存配置" and "测试连接" through form validation.
- [x] Move LLM panel-specific utility styling into `LlmConfigPanel.css` classes.
- [x] Add failing static and rendered tests that guard against utility class regression and invalid endpoint saves.
- [x] Run LlmConfigPanel tests, LLM preset tests, and `npm run build`.

### Task 58: Move dialog business surfaces to local CSS

**Files:**
- Create: `desktop/src/components/SettingsDialog.css`
- Create: `desktop/src/components/ConfirmDialog.css`
- Create: `desktop/src/components/DangerConfirmDialog.css`
- Create: `desktop/src/components/__tests__/DialogSurfaces.styles.test.ts`
- Modify: `desktop/src/components/SettingsDialog.tsx`
- Modify: `desktop/src/components/ConfirmDialog.tsx`
- Modify: `desktop/src/components/DangerConfirmDialog.tsx`

- [x] Keep Settings, Confirm, and DangerConfirm surfaces on top of the DBFox/Radix Dialog primitive.
- [x] Move business dialog width, spacing, icon tone, danger state, summary preview, input validity, and loading animation styles out of JSX utility classes.
- [x] Preserve the current dialog behavior, copy, confirmation validation, and LLM settings actions.
- [x] Add a failing static style test that guards the local CSS imports and semantic selectors.
- [x] Run dialog surface tests, Dialog primitive tests, WorkspaceRouter/DataSourcesPage integration tests, LlmConfigPanel tests, and `npm run build`.

### Task 59: Move base primitive styles to local CSS

**Files:**
- Create: `desktop/src/components/ui/button.css`
- Create: `desktop/src/components/ui/input.css`
- Create: `desktop/src/components/ui/label.css`
- Create: `desktop/src/components/ui/state.css`
- Create: `desktop/src/components/ui/__tests__/base-primitives.styles.test.ts`
- Modify: `desktop/src/components/ui/button.tsx`
- Modify: `desktop/src/components/ui/input.tsx`
- Modify: `desktop/src/components/ui/label.tsx`
- Modify: `desktop/src/components/ui/state.tsx`

- [x] Keep DBFox-owned Button, Input, Label, EmptyState, ErrorState, and LoadingState APIs stable.
- [x] Move variant, size, focus, disabled, icon, empty/error/loading, and retry presentation out of JSX utility class strings.
- [x] Preserve `buttonVariants` as a compatibility helper while returning semantic DBFox class names.
- [x] Add a failing static style test that guards local CSS imports and prevents utility class regression in base primitives.
- [x] Run base primitive tests, UI primitive render tests, LlmConfigPanel/Dialog surface tests, representative workspace/form tests, and `npm run build`.

### Task 60: Move Panel and Toolbar primitive styles to local CSS

**Files:**
- Create: `desktop/src/components/ui/panel.css`
- Create: `desktop/src/components/ui/toolbar.css`
- Create: `desktop/src/components/ui/__tests__/panel-toolbar.styles.test.ts`
- Modify: `desktop/src/components/ui/panel.tsx`
- Modify: `desktop/src/components/ui/toolbar.tsx`
- Modify: `desktop/src/features/workspace/table/__tests__/TablePreviewPane.test.tsx`

- [x] Keep DBFox Panel and Toolbar APIs stable for workspace surfaces.
- [x] Move panel frame, header, title, description, body, footer, toolbar, toolbar title, and toolbar group presentation out of JSX utility class strings.
- [x] Preserve existing accessibility behavior: labeled Panels still render as regions and Toolbar still exposes `role="toolbar"`.
- [x] Update workspace table preview tests to recognize the semantic `dbfox-button` primitive class instead of the old utility implementation detail.
- [x] Run Panel/Toolbar style tests, base primitive tests, UI primitive render tests, representative workspace/table tests, and `npm run build`.

### Task 61: Move Toast interaction core to Radix Toast

**Files:**
- Create: `desktop/src/components/Toast.css`
- Create: `desktop/src/components/__tests__/ToastRadix.styles.test.ts`
- Modify: `desktop/package.json`
- Modify: `desktop/package-lock.json`
- Modify: `desktop/src/components/Toast.tsx`

- [x] Add `@radix-ui/react-toast` as the mature headless interaction layer for notifications.
- [x] Preserve DBFox's existing `useToast()` API, `toast(message, type)` call shape, and `setToastRoot()` desktop canvas placement hook.
- [x] Replace hand-written timers, GSAP entrance/exit animation, hover mutation handlers, and inline toast styles with Radix duration/close/swipe behavior and `Toast.css`.
- [x] Preserve success/error/warning/info visual tones, error `alert` role, and polite non-error live regions.
- [x] Add a failing static style test that guards the Radix dependency, DBFox local CSS selectors, and removal of the old hand-written implementation details.
- [x] Run Toast tests, App/DataSources calling tests, and `npm run build`.

### Task 62: Move Badge primitive styles to local CSS

**Files:**
- Create: `desktop/src/components/ui/badge.css`
- Create: `desktop/src/components/ui/__tests__/badge.styles.test.ts`
- Modify: `desktop/src/components/ui/badge.tsx`

- [x] Keep the DBFox `Badge` API and `badgeVariants` compatibility helper stable.
- [x] Replace CVA/Tailwind style strings with semantic `dbfox-badge` variant classes.
- [x] Move default, secondary, success, warning, destructive, outline, focus, spacing, and typography styling into `badge.css`.
- [x] Add a failing static style test that guards the local CSS import and prevents utility/CVA regression.
- [x] Run Badge style tests, UI primitive tests, LlmConfigPanel tests, and `npm run build`.
