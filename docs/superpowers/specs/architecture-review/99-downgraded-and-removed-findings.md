# Downgraded and Removed Findings

Date: 2026-06-15

This document records review findings that should not remain as high-priority specs after checking the current code.

## Already Implemented or Substantially Addressed

### Global connection pool limit

Original claim: MySQL/PostgreSQL pools have no global limit.

Current code: `engine/sql/pool_registry.py` defines `MAX_POOLS`, `MAX_CONNECTIONS`, LRU eviction, and `get_pool_registry()`. `engine/sql/executor.py` uses it from `get_mysql_pool()` and `get_postgres_pool()`.

Disposition: close as standalone P2. Future work can tune defaults, but the core mechanism exists.

### Datasource response schemas

Original claim: datasource responses are untyped `dict[str, Any]`.

Current code: `engine/schemas/datasource.py` defines `DataSourceResponse`, and `engine/api/datasources.py` uses `response_model=DataSourceResponse` and `response_model=list[DataSourceResponse]`.

Disposition: close as standalone spec. `_datasource_to_dict` can still be replaced with Pydantic serialization later, but response validation exists.

### Frontend API cache and retry

Original claim: frontend API client has no retry or cache.

Current code: `desktop/src/lib/api/client.ts` has retry policy, TTL cache, in-flight deduplication, and cache invalidation.

Disposition: rewrite as adoption/error-unification work, covered by `08-toast-api-error-unification.md` and `03-datasource-api-state-unification.md`.

### Guardrail bypass env gate

Original claim: bypass needs stronger environment gating.

Current code: `guardrail_bypass_allowed()` requires both test env vars and denies frozen builds.

Disposition: keep only the boundary issue: normal `execute_query` should not expose a bypass parameter. Covered by `05-guardrail-bypass-policy-boundary.md`.

### ORM `__repr__`

Original claim: ORM models lack debug repr methods.

Current code: many important models already have `__repr__`.

Disposition: remove as standalone spec. Model organization is covered by `12-maintainability-debt-triage.md`.

## Downgraded to Low Priority

### Token comparison timing

Using `hmac.compare_digest()` would be a low-cost hardening improvement, but treating `token_header != LOCAL_SECURE_TOKEN` as a high-severity localhost desktop timing vulnerability is overstatement.

Disposition: P3 opportunistic hardening, not a main spec.

### Dev token storage and CORS

Development token and localhost CORS settings are worth reviewing before release packaging, but current production checks include local token auth and frozen-origin validation. These are not the same priority as conversation/data consistency bugs.

Disposition: P3 release-hardening checklist item.

### Keyring fallback permissions

File fallback permissions are a valid hardening concern, especially on Windows, but the current triage does not justify treating it above state consistency and SQL safety boundary work.

Disposition: P3 platform hardening item.

### Query history search

The `ILIKE %term%` concern is real but volume-dependent.

Disposition: retained as a P3 spec in `11-query-history-search-scaling.md`.

## Removed as Bugs

### MySQL SSH tunnel leak

Current code stops temporary tunnels in `finally`. The real issue is not a proven leak but two tunnel lifecycle paths: temporary test tunnels and managed execution tunnels.

Disposition: replaced by `09-ssh-tunnel-management-consistency.md`.

### PolicyEngine and Guardrail overlap

Layered security checks are normal. Overlap is only a problem if policy order is unclear or paths can bypass the stronger layer.

Disposition: folded into `05-guardrail-bypass-policy-boundary.md`.

### Native `<select>` is automatically a UX/accessibility bug

Native select controls are often better for accessibility. This is only a design-system consistency question if visual/interaction requirements demand a custom select.

Disposition: removed as a bug.

### TitleBar lacks `Ctrl+W`

`Ctrl+W` behavior is a product shortcut decision, not a baseline accessibility defect.

Disposition: removed as a bug; can be a feature enhancement.

### Header dead code

`desktop/src/layouts/Header.tsx` appears to be a legacy or unused component, but this requires an unused-export check before deletion.

Disposition: cleanup candidate only, not an architecture spec.

### AgentEvalPage tab state loss

The current page has local state for expanded runs and form fields. Whether losing it on unmount is a bug depends on product expectations for tab persistence.

Disposition: not a spec until a user path proves this state must persist.
