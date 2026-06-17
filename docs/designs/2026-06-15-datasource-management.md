# Data Source Management Console Design

Date: 2026-06-15

## Summary

Rebuild the data source settings page as a management-first console that matches the existing DBFox desktop workbench style. The page should default to managing saved data sources instead of showing only a creation form.

The approved direction is layout A: a left connection list and a right detail area. The first implementation includes switching the active data source, testing connections, syncing Schema metadata, creating connections, editing connections, deleting connections, and viewing configuration summaries.

## Goals

- Make "data source management" and "new connection" feel like two clear states inside one console.
- Keep the UI aligned with DBFox's existing high-density desktop style: pale blue-gray shell, white panels, purple primary actions, compact controls, and 8px control radius.
- Prevent the reused `datasource-settings` tab from leaking stale "new connection" state into management mode.
- Support the full confirmed management scope: select, activate, test, sync, create, edit, and delete.
- Preserve existing backend safety behavior for dangerous delete operations.

## Non-Goals

- No batch operations in the first version.
- No redesign of the left workspace `DataSourceTree`.
- No new project or environment management screens.
- No advanced connection history beyond a compact recent status and warning summary from fields already returned by the API.

## Current Context

`desktop/src/pages/DataSourcesPage.tsx` is currently simplified to a pure add form. It has a header and an optional `hifi-datasource-form`, but no saved connection list, detail view, or management actions.

`desktop/src/App.tsx` opens both "data source management" and "new connection" through the same `datasource-settings` tab. It currently uses the tab title to drive `initialShowAddForm`, which helped remove DOM click hacks but still leaves the page without a real management surface.

The frontend API already supports:

- `listDatasources(projectId?)`
- `testConnection(payload)`
- `createDatasource(payload)`
- `checkDatasourceHealth(id)`
- `deleteDatasource(id, confirm?)`
- `syncSchema(id)`

The backend already supports delete confirmation through `DELETE /datasources/{id}`. It does not currently expose an update endpoint for saved data sources.

## UX Design

### Page Shell

The settings tab shows one full-height console inside the existing `hifi-settings-tab-frame`. The console uses a two-column layout:

- Left column: saved connection list.
- Right column: selected connection detail or connection form.

The page should avoid nested decorative cards. Use framed panels only for the connection list, status summary, configuration summary, and compact activity/status area.

### Left Connection List

The left column contains:

- Page label and title: "连接管理".
- Primary action: "新建".
- Search input for connection name, host, database name, and type.
- Saved connection rows with name, database type, environment, host or SQLite path, and status badge.
- Clear active styling for the selected row.
- A distinct marker for the current workbench data source.

Clicking a row changes only the selected detail record. It must not change the active workbench data source. The user must click "设为当前" to change the active data source.

### Right Detail View

Detail mode shows:

- Connection title, status badges, and endpoint summary.
- Actions: "设为当前", "测试连接", "同步 Schema", "编辑", "删除".
- Metric strip for health, latency, Schema table count, last test time, last sync time, and connection mode.
- Configuration summary: type, host/path, port, database, username, environment, read-only state, SSH state, and SSL/TLS state.
- Recent status panel using existing fields such as `last_test_status`, `last_test_error`, `last_sync_status`, and `last_sync_error`.

For empty state, show a compact prompt in the right panel with "新建连接" as the primary action.

### Create and Edit Form

The right panel switches to form mode for create and edit:

- `create`: blank defaults based on the current existing form behavior.
- `edit`: prefilled from the selected data source.

The form keeps the existing fields:

- database type: MySQL, PostgreSQL, SQLite
- name
- host, port, database name, username, password
- environment label
- read-only mode
- SSH tunnel settings
- MySQL SSL/TLS settings

Edit mode uses the same layout and validation as create mode. Password and SSH secret fields are blank by default in edit mode. Leaving a secret blank means "keep the existing saved secret"; typing a new value replaces it.

Form actions:

- Create: "测试连接", "保存并同步 Schema", "取消".
- Edit: "测试连接", "保存修改", "取消".

After successful create, the app syncs Schema, refreshes the list, selects the created data source, and sets it as the active workbench data source.

After successful edit, the app refreshes the list and returns to detail mode for the updated data source. It should not force a Schema sync unless the user explicitly clicks "同步 Schema".

### Delete Flow

Delete uses the existing dangerous operation contract:

1. Click "删除".
2. Call `deleteDatasource(id)` without confirmation.
3. If the response requires confirmation, show the existing danger confirmation dialog with the returned token, expected text, and impact summary.
4. Submit `deleteDatasource(id, { token, text })`.
5. Refresh the list.
6. If the deleted source was active, select the next available data source as active or clear active state when none remain.

## State Model

`DataSourcesPage` should use an explicit mode:

```ts
type DataSourcePageMode = "detail" | "create" | "edit";
```

Core state:

- `datasources`
- `selectedDataSourceId`
- `mode`
- `form`
- `loading`
- `actionState`
- `search`
- `formError`
- `testResult`
- pending delete confirmation state

The selected data source is separate from the active workbench data source passed through `activeDataSource`. This distinction is required so browsing management details does not accidentally switch the workspace context.

`initialShowAddForm` remains as a compatibility prop from `App.tsx`, but the page should convert it into `mode = "create"` when the reused settings tab is opened as "新建数据源". When it changes back to management mode, the page should return to `detail` unless there are no data sources.

## API Design

Add frontend API:

```ts
updateDatasource(id: string, params: unknown): Promise<DataSource>
```

Add backend endpoint:

```http
PUT /api/v1/datasources/{id}
```

The request can reuse most `DataSourceCreateRequest` fields. A separate update schema is preferred so secret fields can be optional without ambiguity:

- Required non-secret fields: name, db_type, host/path, port, database_name, username, connection_mode, is_read_only, env, SSH flags and public SSH fields, SSL flags and paths.
- Optional secret fields: password, ssh_password, ssh_pkey_passphrase.

Secret update semantics:

- Missing or empty secret field: keep the existing encrypted value.
- Non-empty secret field: encrypt and replace the saved value.

The endpoint validates SSL settings in the same way create does. It updates the record, commits, refreshes, and returns `_datasource_to_dict(datasource)`.

## Error Handling

- List load failure: show a compact error in the list/detail area and keep the page usable.
- Health check failure: show the returned message, persist the backend status, and refresh the datasource row.
- Sync failure: show the returned error and keep the user in detail mode.
- Create/edit validation failure: keep form values and show inline error near actions.
- Delete confirmation failure: keep the dialog open with the returned error.
- Deleting the last data source: clear selected and active data source, then show the empty state.

## Styling

Add focused classes in `desktop/src/App.css` rather than expanding inline styles:

- `hifi-datasource-console`
- `hifi-datasource-list`
- `hifi-datasource-list-item`
- `hifi-datasource-detail`
- `hifi-datasource-metrics`
- `hifi-datasource-config-grid`
- `hifi-datasource-status-panel`
- `hifi-datasource-form-grid`

The visual style should use existing tokens:

- `--app-bg`, `--sidebar-bg`, `--color-panel`
- `--color-primary`, `--color-primary-soft`
- `--color-success`, `--color-danger`, `--color-warning`
- `--color-border`, `--hairline`
- `--radius-control` and existing 8px control radius

Avoid new color systems, oversized hero typography, and marketing-page spacing.

## Testing

Frontend tests:

- Management mode renders list and detail by default, not the create form.
- Reused settings tab switching to "new connection" sets create mode; switching back returns to detail mode.
- Selecting a list item updates detail without calling `onSelectDataSource`.
- "设为当前" calls `onSelectDataSource` with the selected record.
- Create mode saves, syncs Schema, refreshes, selects the created data source, and activates it.
- Edit mode pre-fills non-secret fields and calls `updateDatasource`.
- Delete flow handles confirmation-required responses and refreshes after confirmed delete.
- Empty state appears when no data sources exist.

Backend tests:

- `PUT /datasources/{id}` updates non-secret fields.
- Empty secret fields preserve existing encrypted secrets.
- Non-empty secret fields replace existing encrypted secrets.
- Missing data source returns 404.
- SSL validation errors follow create behavior.

## Implementation Notes

The form code is currently large inside `DataSourcesPage.tsx`. During implementation, extract small local helpers where they reduce risk:

- default form factory
- data source to form mapper
- validation helper
- payload builder for create/update

Keep the first implementation scoped to the existing page and API files. Do not introduce a new global state library or a new design system abstraction.
