# DBFox Foundation Redesign Design

Date: 2026-07-10  
Status: approved design for implementation planning

## Goal

Replace the current collection of partially overlapping runtime, connection,
Agent, and persistence paths with a small set of authoritative boundaries.
The resulting application must be secure by construction: credentials cannot
enter serializable state, all database access has one validated connection
path, Agent execution is a durable state machine, and local persistence has a
single schema authority.

This is a deliberate clean cutover. The user explicitly authorized discarding
old Agent checkpoint data, Agent run/event data, pending approvals, and Schema
catalog/search-cache data. Do not implement compatibility adapters, dual
formats, dual writes, or old-format readers.

## Decisions

1. Introduce a `CredentialVault` as the only credential authority. Secrets are
   stored in the operating-system secure store; all serializable application
   data contains opaque credential IDs only.
2. Introduce one `ConnectionProfile`, `ConnectionFactory`, and
   `ConnectionResourceManager`. SQL execution, dry runs, introspection,
   exports, backup, and restore use this path exclusively.
3. Replace session-scoped LangGraph checkpoint threads with run-scoped durable
   Agent runs. Approval, cancellation, checkpoint, SSE event, and terminal
   status transitions are guarded by one transactional state machine.
4. Make SQL artifacts the authoritative store for full query results. Graph
   state contains references, summaries, and bounded previews only.
5. Make Alembic the only database-schema authority. New databases use Alembic
   upgrade; application code never calls `Base.create_all()` followed by
   `stamp head`.
6. Remove the Python restore fallback. A backup is either complete and
   restorable through the native database client or explicitly degraded and
   not eligible for restore.
7. Reset legacy volatile local data on first launch of the new runtime version.
   Preserve non-secret datasource definitions where valid, but require every
   database, SSH, LLM, and LangSmith credential to be entered again.

## Global Constraints

- Favor the long-term architecture over a short-term compatibility layer.
- Existing checkpoint, Agent event, approval, and Schema cache data may be
  deleted; no migration bridge is required for them.
- No secret may be present in SQLite, checkpoint metadata, frontend storage,
  logs, diagnostics, SSE payloads, source-control files, or package assets.
- Every externally reachable database operation must fail closed on SSH, TLS,
  credential, path-validation, or catalog-authority failure.
- Every behavior change is developed test-first, with a failing regression
  test observed before its production implementation is written.
- Database write safety is more important than availability. Restore and
  destructive metadata changes must not silently degrade.
- The final system must build, test, type-check, migrate, lint, audit, and
  package from a clean Windows environment.

## Scope

### Included

- Credential storage and LLM configuration.
- Data-source, SSH, TLS, and pool/tunnel lifecycle.
- Schema introspection and catalog synchronization.
- SQL execution, streaming export, guardrails, limits, and result artifacts.
- Backup/restore safety.
- Agent persistence, state, checkpointing, approvals, cancellation, events,
  context compaction, and state-size limits.
- SQLite initialization, Alembic migrations, data reset, and retention.
- Frontend Settings, SSE parsing, cancellation, schema-loading races, CSV
  safety, cache limits, and bundle boundaries.
- Dependency locking, CI, packaged smoke tests, security/performance gates,
  documentation, and observability.

### Excluded

- New database dialects or new LLM providers.
- Multi-user server authentication; DBFox remains a local desktop application.
- Restoring legacy Agent checkpoints or pending approval sessions.
- Silent conversion of old credential ciphertext into the new vault.

## Target Architecture

```text
Tauri renderer
  -> typed local API client
  -> FastAPI boundary (local token + typed request)
  -> application services
       -> CredentialVault (opaque credential IDs only)
       -> ConnectionFactory / ResourceManager
       -> SQL execution and artifact services
       -> AgentRunStateMachine / transactional outbox
       -> Alembic-managed metadata database
  -> database / SSH tunnel / LLM provider
```

### 1. CredentialVault

Create a focused backend module such as `engine/security/credential_vault.py`.
It owns the following interface:

```python
class CredentialVault(Protocol):
    def put(self, *, kind: CredentialKind, secret: str) -> str: ...
    def get(self, credential_id: str) -> str: ...
    def delete(self, credential_id: str) -> None: ...
    def exists(self, credential_id: str) -> bool: ...
```

`CredentialKind` distinguishes LLM API keys, LangSmith keys, datasource
passwords, SSH passwords, and SSH private-key passphrases. The production
implementation uses `keyring`; tests use an in-memory vault. The metadata
database stores only opaque IDs and non-secret endpoint/model metadata.

The frontend stores an `LlmSettingsDraft` while a dialog is open. Only an
explicit Save invokes a narrow Tauri/API command that writes to the vault and
returns a credential ID. Cancel never persists the draft. `localStorage` may
retain non-secret UI preferences but never credentials.

Agent `RunnableConfig`, graph state, events, artifacts, logs, diagnostics,
and exceptions must contain credential IDs rather than secret values. LLM
providers resolve the key immediately before a request and never return it.

### 2. ConnectionProfile and ConnectionFactory

Create a typed immutable `ConnectionProfile` created from datasource metadata
plus vault credentials. It includes the dialect, endpoint, TLS policy,
SSH policy, read-only policy, database/catalog/schema scope, and a stable
configuration fingerprint.

```python
@dataclass(frozen=True)
class ConnectionProfile:
    datasource_id: str
    generation: int
    dialect: Dialect
    endpoint: Endpoint
    tls: TlsPolicy
    ssh: SshPolicy | None
    database_scope: DatabaseScope
    read_only: bool
    fingerprint: str
```

`ConnectionFactory` is the sole creator of database connections. It enforces:

- SSH configuration is fail-closed; tunnel establishment failure never falls
  back to direct access.
- SSH host identity is verified through an explicit known-hosts/fingerprint
  policy.
- Every PostgreSQL/MySQL/SQLite operation receives the same TLS/path policy.
- SQLite read operations use `mode=ro`, require a regular existing file, and
  reject unsafe symlink/path configurations.
- Pool/tunnel keys include the complete profile fingerprint and generation.
- A successful datasource update increments generation and atomically disposes
  old resources.
- Per-datasource single-flight creation prevents duplicate tunnels.

All callers in SQL execution, dry-run, Schema inspection, CSV export, backup,
and restore must use the factory. No module may construct a driver connection
directly.

### 3. Schema Inventory and Catalog Synchronization

Schema inspection returns either a complete authoritative snapshot or a typed
failure. It never represents network, authentication, SSH, TLS, or missing
file errors as an empty database.

```python
@dataclass(frozen=True)
class AuthoritativeInventory:
    datasource_id: str
    generation: int
    tables: tuple[TableInventory, ...]
    captured_at: datetime

class SchemaInspectionError(DBFoxError):
    datasource_id: str
    code: SchemaInspectionErrorCode
```

Catalog synchronization accepts only `AuthoritativeInventory`. It executes all
create/update/remove operations in one transaction. A failed inspection leaves
the prior catalog untouched and records a bounded, redacted sync error/status.

### 4. SQL Execution and Result Artifacts

The existing SQL AST guardrail remains, but it is backed by database-native
controls. Every execution has a generated `execution_id`, deadline, and
cancellation registration.

- PostgreSQL uses read-only transactions and local statement timeout.
- MySQL uses a read-only transaction and an unbuffered/server-side cursor.
- SQLite uses a read-only URI connection and a progress handler/deadline.
- The database account must be least-privilege read-only for product query
  paths.
- Guardrails reject known lock, session-mutating, administrative, and volatile
  functions that can cause side effects in a `SELECT`.
- Explicit query limits are clamped/rejected at a global hard maximum.

`ResultArtifact` is the durable result contract. It stores the complete
permitted result outside graph state, along with columns, original row count,
row/column/byte truncation flags, source SQL fingerprint, execution metrics,
and expiry. The serializer fetches one additional row to determine row
truncation. It never claims a sliced result is complete.

CSV export derives from an artifact and invokes the same execution policy,
deadline, cancellation, audit, and CSV-cell escaping implementation as normal
execution. It cannot bypass the execution registry.

### 5. Backup and Restore

Native database client tooling is required for a restore. The product removes
the Python SQL import fallback completely.

Native backup output includes a manifest containing tool version, source
server version, object coverage, checksum, charset/collation, and verification
status. A backup is either `verified` or `degraded`; only `verified` backups
can enter restore.

Restore operates on a staging target where supported. Validation compares
manifest checksums and required objects before an explicit switch. A failed
restore cannot leave a user-selected target partially modified.

### 6. AgentRunStateMachine and Transactional Outbox

Replace the implicit coupling between LangGraph state, session ID,
`SqliteSaver`, and live SSE with explicit run records.

```text
created -> running -> waiting_approval -> running -> completed
                      |                   |
                      -> cancelled         -> cancelled / failed
```

Each run has its own checkpoint namespace (`run_id`), immutable
`datasource_id`, configuration generation, credential ID, and optimistic
version. A session is a conversational projection, not a LangGraph checkpoint
thread.

Approvals contain `run_id`, `checkpoint_id`, `checkpoint_version`, expiry,
decision, and `consumed_at`. Resume atomically consumes the exact approved
record and transitions the matching waiting run. Duplicate/stale requests
return a conflict or the prior terminal result; they never execute again.

Cancellation writes a durable cancellation request and invokes the active
execution registry. Model and tool nodes check the token between steps. A
terminal status is set with compare-and-swap so completion cannot overwrite a
cancelled run.

Events are first inserted into an `agent_event_outbox` row in the same
transaction as state transitions. A dispatcher streams and marks delivery;
reconnection reads durable ordered events. No event is observable before its
run/event record exists.

The checkpointer is process-scoped, created in FastAPI lifespan and explicitly
closed at shutdown. Its contents are retained only for resumable active runs;
completed runs are compacted or removed according to a bounded retention
policy.

Graph state includes bounded question/context/progress data and references to
artifacts. It excludes complete result rows, full DatabaseMap copies, secrets,
and old user goals. Tool-call compression preserves the original AI/tool
message ordering as atomic groups.

### 7. Metadata Database and Runtime Reset

Alembic owns all schema changes. The application uses `alembic upgrade head`
for a new or existing database and then verifies revision/schema health. It
does not infer head merely from table names and does not create tables through
ORM metadata at runtime.

SQLite connections enable foreign keys, WAL, busy timeout, and an appropriate
synchronous policy. Migrations explicitly model intended foreign keys;
autogenerate excludes FTS virtual tables rather than treating them as ordinary
tables.

The new runtime version uses a reset marker. On first launch it:

1. stops active legacy run processing;
2. deletes legacy checkpoint, WAL, SHM, Agent event/run/approval data, and
   Schema catalog/search cache;
3. removes all legacy credential ciphertext references;
4. preserves only validated non-secret datasource endpoint definitions;
5. requires credentials to be re-entered into `CredentialVault`;
6. runs Alembic to the new revision and records the new reset version.

The reset is explicit in UI diagnostics and release notes. There is no hidden
fallback to legacy state.

### 8. Desktop Runtime

The desktop client receives a typed engine bootstrap configuration and treats
missing authenticated configuration as a startup failure. It must not mount
the full application merely because unauthenticated health succeeds.

All SSE consumption goes through one parser that preserves CR/LF boundaries,
flushes decoder state at EOF, handles an event without a terminal blank line,
and bounds event/buffer size. Its batcher exposes `push`, `flush`, and
`cancel`; terminal rehydration occurs only after `flush`.

Cancellation maps a controller and run ID to exactly one conversation. It
aborts that fetch and calls the backend cancellation endpoint. Datasource
requests use a generation token and abort signal so a stale response cannot
mutate the active datasource state.

CSV generation uses the same formula-injection escaping rule as the backend.
The application removes remote font imports, tightens CSP to local engine
access, removes SmartScreen disable/proxy bypass flags, and treats remote
images/external URLs as explicit allowlisted user actions.

### 9. Build, Test, and Observability

The project has reproducible lock files for Python runtime/dev/build,
JavaScript, and Rust. PyInstaller and Pillow are declared build/test
dependencies. Dependency audit uses an advisory-capable registry and emits an
SBOM.

CI runs full backend tests, type checking, Alembic drift checks, frontend
tests with networking disabled by default, lint/build, Rust fmt/clippy/test,
sidecar build, installer/package smoke, dependency audits, and artifact size
budgets. Actions are pinned to commit SHAs and use least privilege.

Diagnostics redact recursively by semantic key, bound per-entry and total
size, rotate sidecar logs, and clear local and backend logs together. Metrics
cover run transitions, cancellation latency, checkpoint bytes, connection
creation, catalog sync outcomes, export duration, SSE replay, and bundle size.

## Phase Plan and Acceptance Criteria

### Phase 1: Safety and Data Correctness Foundation

Implement CredentialVault, destructive runtime reset, Alembic-only schema
management, SQLite FK enforcement, ConnectionFactory, authoritative Schema
inventory, safe backup/restore, native SQL read-only execution, correct
truncation, and unified export controls.

Acceptance criteria:

- A sentinel secret is absent from all serializable state and runtime files.
- Restore cannot run without a verified native backup.
- Connection failure cannot delete catalog data or direct-connect around SSH.
- All SQL/export paths use the factory and native safety controls.
- A fresh runtime upgrades cleanly with `alembic check` passing.

### Phase 2: Durable Agent and Desktop Runtime

Implement run-scoped state machine/outbox, approval CAS, actual cancellation,
singleton checkpointer, result artifacts, bounded state/retention, correct
message compaction, conversation pagination, robust SSE parsing, targeted
frontend cancellation, datasource generation guards, CSV safety, and bounded
caches.

Acceptance criteria:

- Concurrent or duplicate resume cannot duplicate execution.
- Cancel terminates the active model/query and stays terminal.
- No run can mutate another run's checkpoint state.
- Checkpoint volume and frontend queues remain within configured budgets.
- SSE replay/live ordering is exact and stale datasource data never renders.

### Phase 3: Architectural and Delivery Convergence

Split oversized modules around the new boundaries, eliminate lazy import
cycles, remove obsolete adapters and dead modules, tighten Tauri CSP/startup
lifecycle, add lock files/SBOM, full CI, packaged E2E/fault injection, and
performance/observability budgets.

Acceptance criteria:

- No production path bypasses the new credential, connection, state-machine,
  artifact, or migration boundary.
- Package startup and shutdown are observable and recover from sidecar failure.
- Full clean-environment CI is reproducible and green.
- Bundle, runtime state, connection, and event metrics meet enforced budgets.

## Testing Strategy

Every behavior change follows red-green-refactor. The first test for each
boundary must prove the former failure mode: secret serialization, partial
restore, empty-inventory deletion, SSH direct fallback, approval replay,
cancel/complete race, concurrent same-session runs, incorrect truncation,
side-effect SELECT, malformed SSE chunks, and stale schema response.

Use unit tests for pure policies, temporary SQLite integration tests for
persistence/state transitions, containerized PostgreSQL/MySQL tests for
native connection semantics, and Tauri packaged smoke tests for the desktop
boundary. Tests must use fake credentials and must never rely on a developer's
environment key or a live external LLM.

## Explicit Non-Compatibility Policy

- Old checkpoints, event logs, approvals, and catalog cache are not migrated.
- Old localStorage LLM values are deleted, not read into a new store.
- Old ciphertext credentials are deleted; re-entry is required.
- Old API/event shapes may be removed once all first-party callers are moved.
- No compatibility wrapper remains after a phase reaches acceptance.

## Risks and Controls

- Destructive reset: make it versioned, visible, idempotent, and backed by a
  pre-reset non-secret diagnostic summary.
- OS keyring availability: fail closed with a clear setup error; do not fall
  back to plaintext files.
- Broad refactor regression: use vertical slices with full tests and review at
  every boundary.
- Desktop packaging variance: test on a clean Windows runner and exercise the
  installed artifact rather than development mode only.
- Database-driver differences: verify each native safety rule in a real
  dialect-specific integration suite.
