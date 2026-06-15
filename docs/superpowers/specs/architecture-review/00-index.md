# Architecture Review Specs Index

Date: 2026-06-15

This folder turns the architecture review findings into independent design specs. Each issue can later become its own implementation plan and development branch.

## Backend

1. [Key management fallback hardening](01-backend-key-management-fallback.md)
2. [Global database connection pool limit](02-backend-connection-pool-global-limit.md)
3. [Agent runtime error boundary](03-backend-agent-runtime-error-boundary.md)
4. [Typed datasource API responses](04-backend-datasource-response-schema.md)
5. [SQL executor profiling refactor](05-backend-sql-executor-profile-refactor.md)
6. [Query history search performance](06-query-history-search-performance.md)

## Frontend

1. [App state decomposition](07-frontend-app-state-decomposition.md)
2. [CSS modularization](08-frontend-css-modularization.md)
3. [Global state store evaluation](09-frontend-state-management-store.md)
4. [API cache and retry layer](10-frontend-api-cache-retry.md)
5. [Agent conversation persistence timing](11-frontend-agent-persist-timeout-documentation.md)
6. [Design token unification](12-frontend-token-system-unification.md)

## Security

1. [Dev token storage hardening](13-security-dev-token-storage.md)
2. [Development CORS origin hardening](14-security-dev-cors-origin-hardening.md)
3. [Guardrail bypass hardening](15-security-guardrail-bypass-hardening.md)

## Code Quality

1. [ORM debug repr methods](16-models-debug-repr.md)
2. [Remove design-demo CSS from production bundle](17-remove-design-demo-css.md)

## Note on Deduplication

The review mentioned query history `ILIKE %term%` twice: once as a backend performance issue and once as a Chinese fuzzy-search quality issue. Both are covered by one spec: [Query history search performance](06-query-history-search-performance.md).
