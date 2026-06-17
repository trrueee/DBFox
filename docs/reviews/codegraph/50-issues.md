# CodeGraph Code Review — 86 Issues

Date: 2026-06-18 (initial) / 2026-06-19 (verification)
Tool: CodeGraph (14 rounds of exploration)
Scope: Full codebase (Python backend + TypeScript frontend + Rust Tauri)

## Summary

| Category | Count |
|----------|-------|
| Fixed | 37 |
| Partially fixed | 3 |
| Intentionally kept | 1 (#21) |
| Test coverage gap | 1 (#12) |
| Open | 44 |

---

## Fixed Issues

| # | Issue | Fix |
|---|-------|-----|
| 1 | Dialect normalization duplicated 3x | guardrail + builder import `normalize_dialect` from parser |
| 2 | `datasource→dict` 3x duplicate + field mismatch | dry_run deduped, `_datasource_connection_payload` removed |
| 3 | TrustGate double-queries datasource | `evaluate()` accepts optional `datasource=` param |
| 4 | `list_conversations` self-heals on every call | `heal_missing_conversations()` runs once at startup |
| 5 | `test_connection` 214-line 3-branch duplication | Extracted `_setup/_cleanup_test_tunnel` helpers |
| 6 | AuditSession created per-call, duplicated | Extracted `_write_query_history()` shared function |
| 7 | `_SENSITIVE_FALLBACK` late import in except block | Moved to module-level import |
| 8 | `_bootstrap_sensitivity` bare `db.commit()` | Wrapped in `try/except → rollback` |
| 9 | `migrateLegacyConversations` empty shell | Removed entirely |
| 10 | `pool_manager` redundant `has()` + `get_or_create()` | Removed `has()` guard |
| 11 | `_ping_mysql_connection` swallows TypeError | Simplified to `ping(reconnect=True)` |
| 13 | `backup.py` uses `setattr` | Changed to direct attribute assignment |
| 14 | `backup.py` function-level logger | Moved to module-level `logger` |
| 15 | `AgentRuntime.resume` double-queries approval | Single query |
| 16 | `datasourceStore` serial column fetching | `Promise.all` parallel fetching |
| 17 | `agentStore` hardcoded 300s timeout | `AGENT_RUN_TIMEOUT_MS` constant |
| 18 | `agentStore` redundant `getState()` calls | Reuse existing `ws` variable |
| 19 | `log_sidecar_error` overwrites log file | `OpenOptions::append` mode |
| 20 | `pool_manager` logger name wrong | Corrected to `"dbfox.sql.pool_manager"` |
| 22 | `TRUNCATION_LEN/SUFFIX` late import | Moved to module-level import |
| 23 | `DataRedactor.redact_sql` @classmethod unused `cls` | Changed to `@staticmethod` |
| 24 | `_vector_cache` no thread safety | Added `_vector_cache_lock` |
| 25 | `hasattr` check for `db_alias_keys` | Initialized in `__init__` as `set()` |
| 26 | `_SENSITIVE_PATTERN_STRINGS` duplicated in `_common.py` | Removed duplicate, imports from `sensitivity.py` |
| 28 | `_get_datasource_id` returns `""` instead of `None` | Returns `None` when absent |
| 29 | `SessionMemoryService._cache` no thread lock | Added `threading.Lock()` |
| 31 | `_chart_suggest_handler` function-level import | Moved `suggest_plotly_chart` to module-level |
| 44 | `SchemaIntrospector` 4 dialect methods lack SSH tunnel | `inspect()` creates tunnel and passes to dialect methods |
| 45 | `api_query_history` 6 `ilike` + `or_` | FTS5 primary, LIKE fallback |
| 48 | `api_delete_query_history` no try/except rollback | Added `try/except → rollback → raise` |
| 49 | `_query_history_to_dict` function-level import | Moved to module-level import |
| 83 | Restore `confirm_token`/`confirm_text` in URL query string | Changed to `RestoreConfirmRequest` request body |
| 85 | `_backup_to_dict` / `_project_to_dict` function-level imports | Moved to module-level imports |

## Partially Fixed

| # | Issue | Status |
|---|-------|--------|
| 21 | `_write_query_history` still creates `sessionmaker` inline | Test/prod compat — kept intentionally |
| 30 | `_analyze_data_handler` imports `profile_result` inside function | `time` moved to top-level; `profile_result` still inside |
| 84 | `api_list_projects` runs `get_or_create_default_project` on every request | Added existence check, but still runs per-request |
| 33 | `_build_columns` FK resolution empty `pass` | Replaced with comment explaining FK resolution is in `_build_relationships` |
| 36 | `_catalog_status` always returns "fresh" | Docstring explains staleness tracked separately via `last_sync_status` |

## Intentionally Kept

| # | Issue | Reason |
|---|-------|--------|
| 21 | `_write_query_history` creates `sessionmaker` inline | Test/prod use different engines; `SessionLocal` not available in test context |

## Test Coverage Gap

| # | Issue | Note |
|---|-------|------|
| 12 | `confirmation_bypass_enabled` no covering tests | Security bypass logic lacks test coverage |

---

## Open Issues

### Security

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 75 | "物理删除表" context menu is mock (user may think table deleted) | `DataSourceContextMenu.tsx:66` | **High** |

### Logic Bugs

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 32 | `_build_relationships` `from_table=ts.table_name` — `ts` undefined | `database_map.py:331` | **High** |
| 38 | `WorkspaceTabs.closeTab` passes extra event arg via `as unknown as` | `WorkspaceTabs.tsx:33` | Medium |
| 50 | `TableSchemaPane` uses `resolveTableByName` (reads first datasource, not active) | `TableSchemaPane.tsx:16` | Medium |
| 80 | `TableWorkspaceTab` hardcodes "id_users" fallback | `WorkspaceRouter.tsx:99` | Medium |
| 76 | Schema context menu actions hardcoded to "id_users" | `DataSourceContextMenu.tsx:51-52` | Medium |

### Duplicate / Redundant Code

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 34 | `schema_sync.py` 3 near-identical `_build_*_schema_snapshot` functions | `schema_sync.py:25-392` | Medium |
| 40 | `_to_iso` defined in 4 schema files | `engine/schemas/*.py` | Low |
| 37 | `DatabaseMapBuilder._sensitive_patterns` overlaps with `sensitivity.py` | `database_map.py:221-225` | Low |
| 62 | `resolveApiBaseForCustomInput` defined in 2 places | `LlmConfigPanel.tsx:263`, `llmPresets.ts` | Low |
| 78 | `ApiConfig` type defined in `SettingsDialog.tsx`, not shared | `SettingsDialog.tsx:10-14` | Low |
| 81 | Default question hardcoded in both `App.tsx` and `SmartQueryHomeTab` | `App.tsx:21`, `WorkspaceRouter.tsx:54` | Low |
| 58 | `list_run_artifacts` and `restore_artifact` duplicate dict construction | `persistence.py:650-665, 706-718` | Low |

### Hardcoded Mock Data

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 46 | `TableHistoryPane` hardcoded Chinese text | `TableHistoryPane.tsx:4-6` | Medium |
| 47 | `TableErPane` hardcoded table/column names | `TableErPane.tsx:9-29` | Medium |
| 73 | `AiSuggest` hardcoded diagnostic suggestions | `ContextDrawer.tsx:39-48` | Low |
| 74 | `PropsPanel` hardcoded table properties | `ContextDrawer.tsx:52-61` | Low |
| 67 | `Header.tsx` possibly dead code | `Header.tsx` | Low |

### Missing Error Handling

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 60 | `save_approval_checkpoint` commit failure silently swallowed | `persistence.py:136-141` | Medium |

### Performance

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 39 | `closeTab` calls `set()` 4 times | `workspaceStore.ts:86-101` | Low |
| 52 | `_mysql_tables` N+1 COUNT(*) per table | `schema_introspector.py:200` | Medium |
| 69 | `_kill_mysql_query` opens new connection per cancellation | `query_registry.py:163-170` | Low |
| 70 | `QueryRegistry` doesn't auto-clean cancelled queries | `query_registry.py:81-83` | Low |

### Dead Code / Unreachable Branches

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 77 | `loadConfig` hardcoded `127.0.0.1:18625` migration hack | `SettingsDialog.tsx:30-32` | Low |

### Missing Features / Incomplete

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 53 | `SchemaIntrospector` 4 dialect methods share 70% structure | `schema_introspector.py:47-461` | Medium |
| 55 | `GoldenSQLCreateRequest.golden_sql` no length validation | `schemas/ai.py:20-23` | Low |
| 71 | `useSidebarLayout` doesn't persist width | `useSidebarLayout.ts:5` | Low |
| 79 | `getStoredApiConfig` no schema validation | `SettingsDialog.tsx:44-46` | Low |

### Unused / Inconsistent Patterns

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 27 | `memory_tools` functions don't use `@tool_handler` | `memory_tools.py` | Low |
| 35 | `schema_sync.py` uses `setattr` for FK fields | `schema_sync.py:176-178, 269-271, 386-388` | Low |
| 57 | `fail_run` re-raises; `cancel_run` swallows | `persistence.py:290, 309-310` | Low |
| 59 | `request_from_run` hardcodes `execute=True`, `max_steps=20` | `persistence.py:70-71` | Low |
| 61 | `ErrorBoundary.handleReset` uses `window.location.reload()` | `ErrorBoundary.tsx:29` | Low |
| 63 | `_redact_response` only removes `api_key` and `follow_up_context` | `persistence.py:808-813` | Low |
| 65 | `App.tsx` calls `getState()` inline in JSX | `App.tsx:150-156` | Low |
| 66 | `showToast` is redundant wrapper | `App.tsx:27-29` | Low |
| 68 | `useAppCommands` creates JSX inside `useMemo` | `useAppCommands.tsx:40-106` | Low |
| 72 | Hardcoded default question string | `App.tsx:21` | Low |
| 86 | `DataSourceTree` extensive inline styles | `DataSourceTree.tsx` | Low |

### Delayed Imports (Module-Level Available)

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 30 | `_analyze_data_handler` imports `profile_result` inside function | `dbfox_tools.py:163` | Low |
| 41 | `api_llm_test` imports `time` inside function | `agent.py:68` | Low |
| 42 | `DatabaseMapBuilder.build` imports `json` + `datetime` inside function | `database_map.py:238-239` | Low |
| 56 | `create_openai_client` docstring after import | `openai.py:19-20` | Low |
| 64 | `TitleBar` dynamically imports `@tauri-apps/api/window` 4 times | `TitleBar.tsx:29,36,54,70` | Low |
| 新 | `semantic.py` 4 `_*_to_dict` functions import response schemas inside function | `semantic.py:40,45,50,55` | Low |

---

## Severity Distribution

| Severity | Count |
|----------|-------|
| High | 2 |
| Medium | 10 |
| Low | 32 |
| **Total Open** | **44** |
