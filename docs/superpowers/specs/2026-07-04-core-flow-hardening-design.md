# Core Flow Hardening Design

## Goal

DBFox already has the main product capabilities for datasource management, schema sync, SQL execution, agent-assisted querying, result views, and desktop packaging. This design hardens those existing capabilities around a small set of end-to-end flows so the product becomes reliable, explainable, and regression-resistant.

The goal is not to rebuild the architecture. The goal is to make the core paths consistently pass through the intended contracts, expose useful state to users, and leave enough diagnostic evidence for developers to reproduce failures.

## Product Position

The hardening work supports DBFox as a local-first AI data workspace:

- users can connect to databases and understand schema safely;
- users can run SQL through a visible trust and safety path;
- users can ask natural-language questions and see how the agent reached SQL and results;
- users can preserve useful query outputs as SQL-backed workspace views;
- developers can verify the above with stable tests and diagnostics before release.

## Scope

The first hardening pass covers five flows:

1. Datasource connection and schema sync.
2. Trusted SQL execution.
3. Agent question answering.
4. SQL-backed workspace views.
5. Desktop release and diagnostics.

The P0 implementation scope is the first three flows. Workspace view productization and desktop release diagnostics are P1 unless they are required to stabilize the P0 flows.

Two enabling fixes are also P0 because they directly affect the core flows:

- LLM configuration must resolve the `OPENAI_BASE_URL` and `OPENAI_API_BASE` naming drift before agent hardening begins.
- DuckDB support must be declared, feature-flagged, or removed before schema-sync hardening treats it as a supported datasource path.

Diagnostic correlation is P0 for the first three flows. Full desktop release diagnostics remain P1, but datasource sync, SQL execution, and agent runs need trace ids early so failures are debuggable while hardening is underway.

## Current Implementation Gaps

The existing implementation already covers much of the intended behavior, but the hardening work must close these gaps:

- `/datasources/{id}/sync` currently calls the catalog sync entrypoint directly and returns counts. The older `sync_schema` wrapper also updates `DataSource.last_sync_status` and `last_sync_error`. Hardening must leave one authoritative sync service so API calls, auto-sync, and internal refreshes share status semantics.
- `SchemaCatalogSync.sync_inventory` removes tables that are absent from the incoming inventory. MySQL and PostgreSQL introspection currently convert connection failures into empty inventories. This can make a failed connection indistinguishable from a real empty schema unless hardening changes the contract.
- `QueryHistory` already stores submitted, generated, safe, and executed SQL, guardrail result/checks, timings, row/column counts, and redacted error. It does not yet have a complete source and decision contract for user SQL, agent SQL, saved view refresh, artifact pagination, and export.
- Agent runtime events already have `event_id`, `run_id`, `sequence`, `created_at_ms`, `type`, and typed payload fields in the Python and TypeScript contracts. They do not yet have an explicit event contract version.
- The current event shape is snake_case end to end. Any hardening must either keep snake_case for v1 or intentionally add API aliases and migration tests.
- `ResultViewService` already verifies persisted SQL artifacts with fingerprints and validates derived pagination/export SQL. A full persistent workspace view model is still separate productization work.
- The LLM factory reads `OPENAI_API_BASE`, while `.env.example` documents `OPENAI_BASE_URL`.
- DuckDB introspection imports `duckdb` at runtime, but `requirements.txt` does not declare the dependency.

## P0 Invariants

These rules must not be broken by later implementation work:

1. Failed introspection must never delete existing schema catalog records.
2. Introspection failure must never be represented as an empty successful inventory.
3. Empty inventory is valid only after a datasource connection succeeds and the database genuinely has no supported tables or views.
4. No executable SQL may reach a dialect executor without an `ExecutionSafetyDecision` or a verified derived-source decision.
5. Every SQL result shown to the user must be traceable to `execution_id` plus `history_id` or `artifact_id`.
6. Every agent runtime event must be replayable in order by `(run_id, sequence)` under a declared event contract version.
7. Approval and resume are normal agent paths, not error-only branches.
8. Diagnostics are redacted by default and must include trace id, phase, datasource or project context when available, decision state, and a user-facing next step.

## Implementation Contract Matrix

| Flow | Current entrypoints | Required contract fields | DB/API changes | Frontend changes | Must-pass tests |
| --- | --- | --- | --- | --- | --- |
| Datasource sync | `/datasources/{id}/sync`, auto schema list refresh, internal `ensure_catalog` calls | `phase`, `sync_status`, `last_usable_catalog`, `tables_created`, `tables_updated`, `tables_removed`, `error` | One authoritative sync service updates `DataSource.last_sync_status`, `last_sync_error`, and preserves previous catalog on failure | Fresh/stale/failed/never-synced badge and "using last catalog" state | Failed MySQL/Postgres/DuckDB introspection preserves existing `SchemaTable` records |
| Trusted SQL execution | SQL console, agent tools, result-view pagination/export, saved view refresh | `source_type`, `decision_state`, `policy`, `decision_id`, `execution_id`, `history_id`, `artifact_id`, timings, row/truncation state, redacted error | Add or embed an execution contract record, either as dedicated columns/table or structured JSON in query/audit payloads | Safety panel and traceable execution metadata on results | Architecture test detects direct dialect executor bypass |
| Agent question answering | `/agent/run`, `/agent/run/stream`, resume, approval, conversation stream | `event_contract_version`, `event_id`, `run_id`, `sequence`, `created_at_ms`, `type`, typed payload | Persist versioned runtime events and fixture-compatible payloads | Replay reducer from saved event fixtures | Backend/frontend shared event fixture, approval/resume replay test |
| Artifact-backed result view | result artifact pagination/export, table preview | source artifact/table id, fingerprint, verified derived SQL, history/execution metadata | Keep persisted artifact fingerprint as authority; do not trust display SQL alone | Source identity visible in result view details | Safe SQL mismatch fails; derived pagination/export validates |
| Workspace view productization | saved result/workspace view entrypoints as they mature | name, source metadata, refresh history, chart/export eligibility | Introduce or extend persistent workspace view model | Saved view list, refresh status, schema-change warning | Refresh preserves source identity and records history |
| Desktop diagnostics | Tauri launch, sidecar health, API boot path | trace id, startup phase, local engine state, redacted error | Smoke path output and diagnostics export include phase-specific failures | Startup failure panel links to diagnostics | Packaged smoke catches sidecar or API startup regression |

## Flow 1: Datasource Connection And Schema Sync

### Current Intent

The datasource flow creates or updates a datasource, verifies connectivity, syncs schema catalog metadata, and lets the user browse or search tables, columns, and relationships.

### Hardening Contract

Datasource operations must expose clear phase state:

- configuration validation;
- credential and tunnel setup;
- connection test;
- schema introspection;
- catalog upsert;
- table browser refresh.

Schema catalog state must distinguish between fresh, stale, failed, and never-synced. A failed sync must preserve the last usable catalog when one exists, and the UI must make that distinction visible.

Introspection failure must be represented as a failed sync result, not as an empty successful inventory. Empty inventory is only valid when connection and introspection complete successfully and the database genuinely contains no supported tables or views.

There must be one authoritative schema-sync service. It must be used by explicit sync endpoints, auto-sync before listing schema, and internal refreshes. It must update datasource sync status consistently and return a structured sync result instead of forcing callers to infer failure from counts.

### Failure Cases

The flow must handle:

- invalid credentials;
- unreachable host or database file;
- SSH or SSL configuration failure;
- schema sync interruption;
- large schema sync timeout;
- unsupported or partially supported database feature;
- stale local catalog after target schema changes.

### Acceptance

This flow is stable when a user can create a datasource, test it, sync schema, browse tables, and recover from common failures without losing the previous usable catalog state.

Required tests:

- existing catalog plus failed MySQL connection keeps all previous tables and marks sync failed;
- existing catalog plus failed PostgreSQL connection keeps all previous tables and marks sync failed;
- DuckDB path is either covered as supported or explicitly skipped behind a feature flag;
- genuine empty schema returns success with zero tables and does not display as a connection failure;
- `/datasources/{id}/sync` and auto-sync share the same status update behavior.

## Flow 2: Trusted SQL Execution

### Current Intent

SQL from the console, result-view refresh, or agent tools must pass through validation and safety before execution. Query history and result-view artifacts should preserve what was executed and why it was allowed or blocked.

### Hardening Contract

All executable SQL paths must use the same ordered contract:

`parse/validate -> policy/safety/trust decision -> execute -> serialize -> persist history/result metadata`

No route, tool, refresh path, export path, or pagination path may call a dialect executor directly unless it is processing SQL already derived from a verified persisted source contract.

Every SQL execution response must expose:

- source type: user SQL, agent SQL, saved view refresh, artifact pagination, or export;
- safety decision: allowed, blocked, or approval required;
- blocked reason or approval reason when applicable;
- execution timings;
- row count and truncation state;
- persisted history or artifact id when created.

Execution-producing endpoints must persist or return a structured execution contract record with:

- `source_type`;
- `decision_state`;
- `policy`;
- `decision_id`;
- `history_id`;
- `artifact_id`;
- `execution_id`;
- timings;
- row and truncation state;
- redacted error.

This can be implemented as dedicated columns, a separate audit table, or a structured JSON payload on the existing history/audit model. The implementation plan must choose the smallest option that makes contract tests possible and keeps diagnostics traceable.

### Failure Cases

The flow must handle:

- unsafe SQL;
- unsupported dialect syntax;
- query timeout;
- user cancellation;
- empty result;
- large result truncation;
- serialization failure;
- datasource disconnect during execution.

### Acceptance

This flow is stable when every SQL-producing feature can prove it passed through the safety chain, users can understand allowed and blocked decisions, and tests fail if any new path bypasses the chain.

Required tests:

- SQL console success persists execution contract metadata;
- blocked SQL persists or returns decision metadata with redacted error;
- result-view pagination/export uses a verified derived-source decision;
- agent SQL execution records source type as agent SQL;
- direct dialect executor bypass is detected by an architecture test.

## Flow 3: Agent Question Answering

### Current Intent

The agent flow converts natural language into schema-aware tool usage, safe SQL, result artifacts, and final answers. It streams runtime events to the UI, can request approval, and can resume from checkpoints.

### Hardening Contract

Agent runtime events must become an explicit versioned stream contract. Each persisted or streamed event must include:

- `event_contract_version`;
- `type`;
- `event_id`;
- `run_id`;
- `sequence`;
- `created_at_ms`;
- typed payload for step, tool, model, policy, approval, artifact, answer, or error.

The v1 event contract keeps the existing snake_case field names. A camelCase API alias can be added later, but only with explicit compatibility tests for SSE parsing, persisted event records, and frontend replay fixtures.

The frontend conversation store must be testable by replaying saved event fixtures. Backend tests must cover the same fixture shape so event changes are intentional.

Tool execution must expose:

- requested tool name;
- policy decision;
- approval state when required;
- produced artifact references;
- error and retry state.

Checkpoint and resume behavior must be covered as a first-class path, not only as an exceptional branch.

### Failure Cases

The flow must handle:

- model call failure;
- malformed tool arguments;
- policy-blocked tool call;
- approval required and later approved;
- approval denied;
- SSE disconnect;
- checkpoint missing or incompatible;
- tool result too large;
- final answer generation failure after SQL succeeds.

### Acceptance

This flow is stable when an agent run can be replayed from events, approval and resume paths are covered by tests, and frontend state remains correct when events arrive incrementally or after recovery.

Required tests:

- backend emits v1 events with monotonic sequence for a normal run;
- frontend reducer replays a saved v1 fixture into the expected draft state;
- approval required -> approved -> resumed -> final answer is a normal passing path;
- approval denied is represented as a controlled terminal state;
- SSE disconnect/recovery does not duplicate or reorder state when persisted events are replayed.

## Flow 4: SQL-Backed Workspace Views

### Current Intent

Workspace views turn query outputs or agent-generated result artifacts into persistent, refreshable data surfaces.

This flow has two layers:

- P0.5 artifact-backed result view contract: pagination and export must continue to use persisted source artifacts, fingerprints, and verified derived SQL.
- P1 workspace view productization: saved workspace views add naming, source metadata, refresh history, chart eligibility, and user-facing lifecycle state.

### Hardening Contract

Every SQL-backed workspace view must preserve source metadata:

- datasource id;
- source SQL or source artifact id;
- creation source: SQL console, agent answer, query history, or manual save;
- safety decision or artifact fingerprint;
- schema sync timestamp or catalog version when available;
- last refresh timestamp;
- row count and truncation state;
- chart/export eligibility.

Refresh must run through the trusted SQL execution contract or a verified result-view source contract. A view must not silently refresh from display-only SQL if a persisted verified source is available.

For the artifact-backed layer, safe SQL or display SQL passed by the client is context only. The backend must load the persisted source artifact, verify the fingerprint, validate derived SQL, and then execute.

### Failure Cases

The flow must handle:

- datasource deleted or unavailable;
- schema changed since view creation;
- source artifact missing;
- saved SQL now blocked by policy;
- refresh returns a different shape;
- export fails after pagination succeeds.

### Acceptance

This flow is stable when a saved result can be refreshed, charted, exported, and traced back to its original SQL or agent artifact.

Required tests:

- artifact-backed pagination fails when requested safe SQL does not match the persisted fingerprint;
- artifact-backed export validates derived SQL before execution;
- table preview identifies the source by datasource id and table id, not display table name alone;
- workspace view refresh records source identity and refresh history once the persistent view model exists.

## Flow 5: Desktop Release And Diagnostics

### Current Intent

DBFox is packaged as a Tauri desktop app with a Python sidecar. The UI communicates with the local engine through localhost and a local token.

### Hardening Contract

Release readiness must include a smoke path:

`launch desktop -> start sidecar -> health check -> retrieve engine config -> call API -> render workspace shell`

Diagnostics must correlate major operations with a stable trace id:

- datasource test and sync;
- SQL validate and execute;
- agent run;
- workspace view refresh;
- sidecar startup.

The diagnostics export must preserve useful timings and errors while redacting credentials, tokens, SQL secrets, and LLM plaintext unless explicitly enabled by existing configuration.

For P0, trace id correlation is required for datasource sync, SQL execution, and agent runs even before the full desktop smoke path is automated.

### Failure Cases

The flow must handle:

- sidecar startup timeout;
- migration failure;
- local token mismatch;
- frontend cannot reach engine;
- packaged asset or custom protocol failure;
- diagnostics collection partial failure.

### Acceptance

This flow is stable when a packaged smoke check catches sidecar or UI startup regressions before release and diagnostics make local failures actionable.

## Testing Strategy

Each hardened flow must have:

- one successful end-to-end or integration path;
- two or more representative failure paths;
- fixture-based contract tests when a frontend/backend boundary is involved;
- regression tests for previous bug classes discovered during hardening;
- clear naming so the test suite reads like the product flow it protects.

Priority tests:

- SQL architecture test that detects executor bypass;
- agent event replay fixtures shared by backend and frontend expectations;
- approval/resume contract tests;
- datasource sync failure tests that preserve previous catalog state;
- result-view refresh tests that verify source identity and safety.

## Diagnostics Strategy

Hardening should add diagnostics where it explains a flow, not where it only adds noise. Every major flow should emit or persist enough information to answer:

- what user action started this;
- which datasource and project were involved;
- which phase failed;
- whether policy allowed, blocked, or required approval;
- which persisted artifact, history row, run, or view was created;
- what the user can try next.

Diagnostic payloads must stay redacted by default.

## Rollout Plan

### P0-Preflight: Contract Decisions

1. Resolve LLM base URL naming: support both `OPENAI_BASE_URL` and `OPENAI_API_BASE`, or pick one canonical name and update code/docs together.
2. Resolve DuckDB support: add the dependency, feature-flag the path, or remove the supported path until it is real.
3. Pick the execution contract storage shape: dedicated columns/table or structured JSON on existing query/audit records.
4. Pick the event contract field naming policy: v1 snake_case, with camelCase only if compatibility aliases are explicitly added.

### P0: Core Stability

1. Datasource connection and schema sync hardening.
2. Trusted SQL execution hardening.
3. Agent question answering hardening.

### P0.5: Result View Contract

1. Artifact-backed result-view source verification.
2. Derived pagination/export SQL validation.
3. Table preview source identity checks.

### P1: Productization

1. Persistent SQL-backed workspace view model, source metadata, and refresh behavior.
2. Full desktop smoke test and diagnostics correlation.

### P2: Polish

1. Coverage reporting and dependency audit.
2. Broader real-database matrix.
3. Long-term retention and cleanup policy for query history, agent events, checkpoints, and diagnostics.

## Non-Goals

This design does not:

- add multi-user authentication or remote hosted deployment;
- replace the local-first Tauri and sidecar architecture;
- redesign the UI visual language;
- introduce new database engines beyond existing planned support;
- rewrite the agent graph from scratch;
- make every diagnostic event a metric or alert.

## Open Decisions

The implementation plan should resolve:

- where shared event fixtures live so backend and frontend tests can use them without tight build coupling;
- how long query history, agent events, checkpoints, and diagnostics should be retained by default.
