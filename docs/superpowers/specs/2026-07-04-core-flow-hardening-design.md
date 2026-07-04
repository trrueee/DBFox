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

## Flow 3: Agent Question Answering

### Current Intent

The agent flow converts natural language into schema-aware tool usage, safe SQL, result artifacts, and final answers. It streams runtime events to the UI, can request approval, and can resume from checkpoints.

### Hardening Contract

Agent runtime events must become an explicit versioned stream contract. Each persisted or streamed event must include:

- `version`;
- `type`;
- `runId`;
- `sequence`;
- `createdAtMs`;
- typed payload for step, tool, model, policy, approval, artifact, answer, or error.

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

## Flow 4: SQL-Backed Workspace Views

### Current Intent

Workspace views turn query outputs or agent-generated result artifacts into persistent, refreshable data surfaces.

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

### P0: Core Stability

1. Datasource connection and schema sync hardening.
2. Trusted SQL execution hardening.
3. Agent question answering hardening.

### P1: Productization

1. SQL-backed workspace view source metadata and refresh behavior.
2. Desktop smoke test and diagnostics correlation.

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

- whether `OPENAI_BASE_URL` and `OPENAI_API_BASE` are both supported or one is deprecated;
- whether DuckDB support is declared, feature-flagged, or removed;
- where shared event fixtures live so backend and frontend tests can use them without tight build coupling;
- how long query history, agent events, checkpoints, and diagnostics should be retained by default.
