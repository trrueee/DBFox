# CodeGraph Code Review — 86 Issues

Date: 2026-06-18
Tool: CodeGraph (14 rounds of exploration)
Scope: Full codebase (Python backend + TypeScript frontend + Rust Tauri)

## Summary

| Category | Count |
|----------|-------|
| Fixed | 23 |
| Intentionally kept | 1 (#21) |
| Test coverage gap (not code defect) | 1 (#12) |
| Open | 61 |

---

## Fixed Issues

| # | Issue | Fix |
|---|-------|-----|
| 1 | Dialect normalization duplicated 3x (parser/builder/guardrail) | guardrail + builder import `normalize_dialect` from parser |
| 2 | `datasource→dict` 3x duplicate + field mismatch | dry_run deduped, inspect `_ds_to_dict` inlined |
| 3 | TrustGate double-queries datasource | `evaluate()` accepts optional `datasource=` param |
| 4 | `list_conversations` self-heals on every call | `heal_missing_conversations()` runs once at startup |
| 5 | `test_connection` 214-line 3-branch duplication | Extracted `_setup/_cleanup_test_tunnel` helpers |
| 6 | AuditSession created per-call, duplicated | Extracted `_write_query_history()` shared function |
| 7 | `_SENSITIVE_FALLBACK` late import in except block | Moved to module-level import |
| 8 | `_bootstrap_sensitivity` bare `db.commit()` | Wrapped in `try/except → rollback` |
| 9 | `migrateLegacyConversations` empty shell | Removed entirely |
| 10 | `pool_manager` redundant `has()` + `get_or_create()` | Removed `has()` guard |
| 11 | `_ping_mysql_connection` swallows TypeError | Unified to `ping(reconnect=True)` |
| 13 | `backup.py` uses `setattr` | Changed to direct attribute assignment |
| 14 | `backup.py` function-level logger | Moved to module-level `logger` |
| 15 | `AgentRuntime.resume` double-queries approval | Single query |
| 16 | `datasourceStore` serial column fetching | `Promise.all` parallel fetching |
| 17 | `agentStore` hardcoded 300s timeout | `AGENT_RUN_TIMEOUT_MS` constant |
| 18 | `agentStore` redundant `getState()` calls | Reuse existing `ws` variable |
| 19 | `log_sidecar_error` overwrites log file | `OpenOptions::append` mode |
| 20 | `pool_manager` logger name `"dbfox.sql.executor"` | Corrected to `"dbfox.sql.pool_manager"` |
| 22 | `TRUNCATION_LEN/SUFFIX` late import inside function | Moved to module-level import |
| 23 | `DataRedactor.redact_sql` is `@classmethod` but unused `cls` | Changed to `@staticmethod` |
| 24 | `_vector_cache` no thread safety | Added `_vector_cache_lock` |
| 25 | `hasattr` check for `db_alias_keys` | Initialized in `__init__` as `set()` |

## Intentionally Kept

| # | Issue | Reason |
|---|-------|--------|
| 21 | `_write_query_history` still creates `sessionmaker` inline | Test/prod use different engines; `SessionLocal` not available in test context |

## Test Coverage Gap (Not Code Defect)

| # | Issue | Note |
|---|-------|------|
| 12 | `confirmation_bypass_enabled` has no covering tests | Security bypass logic lacks test coverage; not a code bug |

---

## Open Issues

### Security

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 83 | Restore `confirm_token`/`confirm_text` in URL query string | `engine/api/backup.py:144-146` | **High** |
| 75 | "物理删除表" context menu is mock action (user may think table is deleted) | `desktop/src/features/datasource/DataSourceContextMenu.tsx:66` | **High** |

### Logic Bugs

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 32 | `_build_relationships` `from_table` references stale loop variable `ts` | `engine/environment/database_map.py:342-343` | **High** |
| 38 | `WorkspaceTabs.closeTab` passes extra event arg via `as unknown as` cast | `desktop/src/features/workspace/WorkspaceTabs.tsx:33` | Medium |
| 50 | `TableSchemaPane` uses `resolveTableByName` which reads first datasource, not active | `desktop/src/features/workspace/table/TableSchemaPane.tsx:16` | Medium |
| 80 | `TableWorkspaceTab` hardcodes "id_users" fallback when `tableId` missing | `desktop/src/features/appShell/WorkspaceRouter.tsx:99` | Medium |
| 76 | Schema context menu actions hardcoded to "id_users" | `desktop/src/features/datasource/DataSourceContextMenu.tsx:51-52` | Medium |
| 65 | `App.tsx` calls `getState()` inline in JSX (bypasses React reactivity) | `desktop/src/App.tsx:150-156` | Low |

### Duplicate / Redundant Code

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 26 | `_SENSITIVE_PATTERN_STRINGS` duplicated in `_common.py` and `sensitivity.py` | `engine/tools/db/_common.py:23-33` | Low |
| 40 | `_to_iso` defined in 4 schema files (backup, semantic, query, datasource) | `engine/schemas/*.py` | Low |
| 37 | `DatabaseMapBuilder._sensitive_patterns` overlaps with `sensitivity.py` | `engine/environment/database_map.py:221-225` | Low |
| 34 | `schema_sync.py` 3 near-identical `_build_*_schema_snapshot` functions | `engine/schema_sync.py:25-392` | Medium |
| 62 | `resolveApiBaseForCustomInput` defined in both `LlmConfigPanel.tsx` and `llmPresets.ts` | `desktop/src/components/LlmConfigPanel.tsx:263-271` | Low |
| 78 | `ApiConfig` type defined in `SettingsDialog.tsx`, not shared | `desktop/src/components/SettingsDialog.tsx:10-14` | Low |
| 81 | `SmartQueryHomeTab` and `App.tsx` both hardcode same default question | `WorkspaceRouter.tsx:54`, `App.tsx:21` | Low |
| 58 | `list_run_artifacts` and `restore_artifact` duplicate dict construction | `engine/agent_core/persistence.py:650-665, 706-718` | Low |

### Hardcoded Mock Data

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 46 | `TableHistoryPane` displays hardcoded Chinese text, no API call | `desktop/src/features/workspace/table/TableHistoryPane.tsx:4-6` | Medium |
| 47 | `TableErPane` shows hardcoded table/column names | `desktop/src/features/workspace/table/TableErPane.tsx:9-29` | Medium |
| 73 | `AiSuggest` component has hardcoded diagnostic suggestions | `desktop/src/features/assistant/ContextDrawer.tsx:39-48` | Low |
| 74 | `PropsPanel` has hardcoded table properties (rows, size, engine) | `desktop/src/features/assistant/ContextDrawer.tsx:52-61` | Low |
| 67 | `Header.tsx` may be dead code (unused by App) | `desktop/src/layouts/Header.tsx` | Low |

### Missing Error Handling

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 48 | `api_delete_query_history` / `api_clear_query_history` no try/except rollback | `engine/api/query.py:130-152` | Medium |
| 60 | `save_approval_checkpoint` commit failure silently swallowed | `engine/agent/app/persistence.py:136-141` | Medium |
| 84 | `api_list_projects` runs `get_or_create_default_project` on every request | `engine/api/projects.py:37` | Low |

### Performance

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 39 | `closeTab` calls `set()` 4 times (4 re-renders) | `desktop/src/stores/workspaceStore.ts:86-101` | Low |
| 45 | `api_query_history` search uses 6 `ilike` + `or_`, no FTS index | `engine/api/query.py:112-123` | Medium |
| 52 | `_mysql_tables` N+1 COUNT(*) per table | `engine/environment/schema_introspector.py:200` | Medium |
| 69 | `_kill_mysql_query` opens new connection per cancellation | `engine/query_registry.py:163-170` | Low |
| 82 | `SqlConsoleTab` calls `setState()` during render | `desktop/src/features/appShell/WorkspaceRouter.tsx:125-137` | Low |

### Dead Code / Unreachable Branches

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 36 | `_catalog_status` always returns "fresh"; "stale" branch never triggers | `engine/environment/service.py:274-278` | Low |
| 33 | `_build_columns` FK resolution is `pass` (empty implementation) | `engine/environment/database_map.py:302-305` | Low |
| 77 | `loadConfig` has hardcoded `127.0.0.1:18625` migration hack | `desktop/src/components/SettingsDialog.tsx:30-32` | Low |

### Missing Features / Incomplete

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 33 | `SchemaIntrospector` 4 dialect methods lack SSH tunnel support | `engine/environment/schema_introspector.py` | Medium |
| 51 | `SchemaIntrospector` 4 dialect methods have similar structure (70% shared) | `engine/environment/schema_introspector.py:47-461` | Medium |
| 55 | `GoldenSQLCreateRequest.golden_sql` has no length/format validation | `engine/schemas/ai.py:20-23` | Low |
| 71 | `useSidebarLayout` doesn't persist width to localStorage | `desktop/src/features/appShell/useSidebarLayout.ts:5` | Low |
| 79 | `getStoredApiConfig` has no schema validation for localStorage data | `desktop/src/components/SettingsDialog.tsx:44-46` | Low |

### Unused / Inconsistent Patterns

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 27 | `memory_tools` functions don't use `@tool_handler` decorator | `engine/tools/memory_tools.py` | Low |
| 28 | `_get_datasource_id` returns `""` instead of `None` | `engine/tools/memory_tools.py:187` | Low |
| 29 | `SessionMemoryService._cache` no thread lock | `engine/memory/session_memory.py:23` | Low |
| 35 | `schema_sync.py` uses `setattr` for FK fields | `engine/schema_sync.py:176-178, 269-271, 386-388` | Low |
| 57 | `fail_run` re-raises exceptions; `cancel_run` swallows them | `engine/agent_core/persistence.py:290, 309-310` | Low |
| 59 | `request_from_run` hardcodes `execute=True` and `max_steps=20` | `engine/agent/app/persistence.py:70-71` | Low |
| 61 | `ErrorBoundary.handleReset` uses `window.location.reload()` | `desktop/src/components/ErrorBoundary.tsx:29` | Low |
| 63 | `_redact_response` only removes `api_key` and `follow_up_context` | `engine/agent_core/persistence.py:808-813` | Low |
| 66 | `App.tsx` `showToast` is redundant wrapper around `toast` | `desktop/src/App.tsx:27-29` | Low |
| 68 | `useAppCommands` creates JSX elements inside `useMemo` | `desktop/src/features/appShell/useAppCommands.tsx:40-106` | Low |
| 70 | `QueryRegistry` doesn't auto-clean cancelled queries | `engine/query_registry.py:81-83` | Low |
| 72 | `App.tsx` hardcoded default question string | `desktop/src/App.tsx:21` | Low |
| 86 | `DataSourceTree` uses extensive inline styles | `desktop/src/features/datasource/DataSourceTree.tsx` | Low |

### Delayed Imports (Module-Level Available)

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 30 | `_analyze_data_handler` imports `time` + `profile_result` inside function | `engine/tools/dbfox_tools.py:157-163` | Low |
| 31 | `_chart_suggest_handler` imports `time` + `suggest_plotly_chart` inside function | `engine/tools/dbfox_tools.py:199-202` | Low |
| 41 | `api_llm_test` imports `time` inside function | `engine/api/agent.py:68` | Low |
| 42 | `DatabaseMapBuilder.build` imports `json` + `datetime` inside function | `engine/environment/database_map.py:238-239` | Low |
| 49 | `_query_history_to_dict` imports `QueryHistoryResponse` inside function | `engine/api/query.py:31` | Low |
| 56 | `create_openai_client` docstring placed after import statement | `engine/llm/providers/openai.py:19-20` | Low |
| 64 | `TitleBar` dynamically imports `@tauri-apps/api/window` 4 times | `desktop/src/components/TitleBar.tsx:29,36,54,70` | Low |
| 85 | `_backup_to_dict` / `_project_to_dict` import response schemas inside function | `engine/api/backup.py:33`, `engine/api/projects.py:25` | Low |

---

## Severity Distribution

| Severity | Count |
|----------|-------|
| High | 3 |
| Medium | 14 |
| Low | 44 |
| **Total Open** | **61** |
