# Architecture Review Corrected Specs

Date: 2026-06-15

This folder is the corrected spec set after reading the actual code and re-triaging the earlier architecture review. The old review mixed true product risks with already-fixed items, maintenance debt, and over-stated findings. These specs keep only actionable work, downgrade the rest, and cite the current code evidence behind each decision.

## Phase 1: Correctness and Consistency

1. [SQL Console tab state isolation](01-sql-console-tab-state-isolation.md) - P0/P1, real user-facing state leak.
2. [Conversation storage single source](02-conversation-storage-single-source.md) - P0/P1, real local history consistency risk.
3. [Datasource API and state unification](03-datasource-api-state-unification.md) - P1, real datasource truth split.
4. [App shell state decomposition](04-app-shell-state-decomposition.md) - P1, architectural debt that amplifies feature risk.
5. [Guardrail bypass and policy boundary](05-guardrail-bypass-policy-boundary.md) - P1, public executor boundary should not expose test bypass.
6. [Backend duplicate cleanup](06-backend-duplicate-cleanup.md) - P1/P2, low-risk refactors with clear duplicated code.

## Phase 2: Lifecycle, UX, and Hardening

7. [Database initialization lifecycle](07-db-initialization-lifecycle.md) - P1/P2, import-time SQLite side effect.
8. [Toast and API error unification](08-toast-api-error-unification.md) - P2, two toast paths and loose API error typing.
9. [SSH tunnel management consistency](09-ssh-tunnel-management-consistency.md) - P2/P3, not a leak, but two tunnel paths.
10. [UX and accessibility polish](10-ux-accessibility-polish.md) - P2/P3, verified small UI gaps.
11. [Query history search scaling](11-query-history-search-scaling.md) - P3, real but data-volume dependent.
12. [Maintainability debt triage](12-maintainability-debt-triage.md) - P2/P3, large-file and boundary cleanup without treating everything as critical.

## Findings Closed or Downgraded

See [downgraded and removed findings](99-downgraded-and-removed-findings.md) for items that should not remain as standalone high-priority specs. Important corrections:

- Global SQL connection pool limits are already implemented through `engine/sql/pool_registry.py`.
- Datasource API responses already use `DataSourceResponse` response models.
- The frontend API client already has retry, in-flight deduplication, and TTL cache primitives.
- Guardrail bypass already has a strong environment predicate; the remaining issue is the public `execute_query(..., bypass_guardrail=...)` boundary.
- Many ORM models already have `__repr__`; this is no longer a standalone fix.
- Native `<select>`, TitleBar `Ctrl+W`, and Header dead-code claims are product or cleanup questions, not architecture blockers.
