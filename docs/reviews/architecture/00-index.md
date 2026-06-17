# Architecture Review — Verified Findings

Date: 2026-06-15 (review) / 2026-06-17 (verification)

This folder contains the architecture review findings after **re-reading the code
and verifying each claim** against current source. Findings are classified by
status, not just original severity.

## Status Legend

| Mark | Meaning |
|------|---------|
| ✅ RESOLVED | Already fixed in Phase 1, no further action |
| ✅ MOSTLY | Core fixed, minor residuals remain (P3 cleanup) |
| ⚠️ REAL | Confirmed issue, needs work |
| 📐 NARROWED | Real but scope smaller than originally claimed |
| ❌ CLOSED | Not a real issue — design is valid, claim was exaggerated |
| 👁 NEEDS UI | Requires manual UI testing to confirm |
| 📊 NEEDS DATA | Requires real data volume to assess |

---

## Phase 1: Correctness and Consistency

| # | Finding | Original | Verified | Status |
|---|---------|----------|----------|--------|
| 01 | [SQL Console tab state isolation](01-sql-console-tab-state-isolation.md) | P0/P1 | `workspaceStore.sqlConsoleState` per-tab; `openSqlConsole`/`closeTab` isolate state | ✅ RESOLVED |
| 02 | [Conversation storage single source](02-conversation-storage-single-source.md) | P0/P1 | Tauri path is `#[allow(dead_code)]` + DEPRECATED; frontend routes to HTTP API | ✅ RESOLVED |
| 03 | [Datasource API state unification](03-datasource-api-state-unification.md) | P1 | `useDatasourceState.ts` removed; single Zustand store; `EngineDataSource` is type alias | ✅ MOSTLY |
| 04 | [App shell state decomposition](04-app-shell-state-decomposition.md) | P1 | Zustand stores + extracted hooks; App.tsx 580→244 lines | ✅ RESOLVED |
| 05 | [Guardrail bypass policy boundary](05-guardrail-bypass-policy-boundary.md) | P1 | `execute_query` has no `bypass_guardrail` param; `test_executor.py` isolated | ✅ RESOLVED |
| 06 | [Backend duplicate cleanup](06-backend-duplicate-cleanup.md) | P1/P2 | `backup.py` dedup fixed; SSE + project resolution centralized | ✅ RESOLVED |

## Phase 2: Lifecycle, UX, and Hardening

| # | Finding | Original | Verified | Status |
|---|---------|----------|----------|--------|
| 07 | [DB initialization lifecycle](07-db-initialization-lifecycle.md) | P1/P2 | PRAGMA config moved to `init_db()`; engine + token file still import-time; is a smell, not blocker | 📐 NARROWED → P3 |
| 08 | [Toast / API error unification](08-toast-api-error-unification.md) | P2 | App.tsx inline toast already unified to `useToast()`; only DataTable local toast remains | 📐 NARROWED → P3 |
| 09 | [SSH tunnel management](09-ssh-tunnel-management-consistency.md) | P2/P3 | `TunnelManager` and `open_temporary_tunnel()` share `_create_physical_tunnel_forwarder()`; managed vs temp is a deliberate design | ❌ CLOSED |
| 10 | [UX / accessibility polish](10-ux-accessibility-polish.md) | P2/P3 | Small UI gaps — requires actual interface testing to confirm | 👁 NEEDS UI |
| 11 | [Query history search scaling](11-query-history-search-scaling.md) | P3 | Volume-dependent — requires real data to assess impact | 📊 NEEDS DATA |
| 12 | [Maintainability debt triage](12-maintainability-debt-triage.md) | P2/P3 | Large files exist but no architectural blocker; ongoing cleanup | 📐 NARROWED → P3 |

---

## Summary

| Status | Count | Items |
|--------|-------|-------|
| ✅ RESOLVED | 6 | 01, 02, 04, 05, 06 (Phase 1 completed) |
| ✅ MOSTLY | 1 | 03 (P3 residual cleanup) |
| 📐 NARROWED → P3 | 3 | 07, 08, 12 (real but downgraded) |
| ❌ CLOSED | 1 | 09 (valid design pattern) |
| 👁 / 📊 needs verification | 2 | 10, 11 |

### Phase 1: All Clear ✅

All 6 original Phase 1 findings are resolved. Remaining work is P3 cleanup or needs manual verification.

### Residual P3 Cleanup

- **03** — Remove `engineApi.listDatasources()` passthrough wrapper
- **02** — Remove `rusqlite` dependency and dead Tauri conversation commands
- **07** — Move token generation + `.env.local` write into startup function
- **08** — Replace DataTable clipboard toast with `useToast()`
- **12** — Ongoing large-file decomposition

### Residual Cleanup (P3, low priority)

- **03** — Remove `engineApi.listDatasources()` passthrough wrapper
- **02** — Remove `rusqlite` dependency and dead Tauri conversation commands
- **07** — Move engine creation and token generation out of import-time
- **08** — Unify DataTable clipboard toast to `useToast()`
- **12** — Ongoing large-file decomposition

### Closed / Deferred

- **09** — SSH tunnel design is valid; no action needed
- **10** — Deferred until manual UI audit
- **11** — Deferred until real-data benchmark

---

## CodeGraph Review (2026-06-18)

A deep code-level review using CodeGraph identified 86 issues across 14 exploration rounds.
See [codegraph/50-issues.md](../codegraph/50-issues.md) for the full breakdown.

- 23 fixed, 1 intentionally kept, 1 test gap, 61 open
- 3 high, 14 medium, 44 low severity among open issues
