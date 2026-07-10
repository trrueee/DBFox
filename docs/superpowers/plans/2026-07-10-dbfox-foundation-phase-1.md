# DBFox Foundation Redesign — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (recommended) or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace unsafe credential, metadata, connection, SQL, and backup paths with the new authoritative boundaries, then destructively reset legacy volatile runtime state.

**Architecture:** Phase 1 establishes the non-negotiable foundations: an OS-backed credential vault, an Alembic-only metadata database, a typed connection factory, authoritative Schema snapshots, native read-only SQL controls, bounded result artifacts, and native-tool-only restore. Every current direct driver connection or serialized secret path is removed rather than adapted.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, keyring, PyMySQL, psycopg2, sqlite3, sqlglot, pytest.

## Global Constraints

- Do not retain compatibility readers, dual writes, or old-format adapters.
- Delete legacy Agent checkpoints, approvals, events, Schema caches, and old credential ciphertext during the versioned reset.
- Preserve only valid non-secret datasource endpoint definitions; require all secrets to be re-entered through the new vault.
- No secret may enter a Pydantic response, event, log, SQLite row, checkpoint, browser storage, or package asset.
- All production changes are TDD: write and run a focused failing regression test before the implementation step.
- Every database operation must use the new connection boundary once the corresponding task is complete.
- Native database tooling is mandatory for restore. A degraded backup must never be restorable.

---

## File Structure

- Create: `engine/security/credential_vault.py`
  - Defines opaque credential IDs, a keyring-backed vault, and an in-memory test vault.
- Create: `engine/security/runtime_reset.py`
  - Owns the one-time destructive v2 reset and reset marker.
- Create: `engine/connectivity/profile.py`
  - Defines immutable datasource, TLS, SSH, database-scope, and fingerprint policy types.
- Create: `engine/connectivity/factory.py`
  - Creates validated driver connections and tunnels through a single path.
- Create: `engine/connectivity/resources.py`
  - Owns pool/tunnel generation invalidation and per-datasource single-flight acquisition.
- Create: `engine/environment/authoritative_inventory.py`
  - Defines complete inspection output and typed inspection errors.
- Create: `engine/sql/result_artifact.py`
  - Defines the bounded result metadata contract used by execution and export.
- Create: `engine/tests/test_credential_vault.py`
- Create: `engine/tests/test_runtime_reset.py`
- Create: `engine/tests/test_connection_factory.py`
- Create: `engine/tests/test_authoritative_schema_sync.py`
- Create: `engine/tests/test_sql_execution_boundaries.py`
- Create: `engine/tests/test_backup_restore_safety.py`
- Modify: `engine/models.py`, `engine/db.py`, `engine/migrations/*`, `engine/crypto.py`
  - Replace legacy credential ciphertext/schema initialization with the new persistent model.
- Modify: `engine/api/datasources/*`, `engine/datasource.py`, `engine/tunnel.py`, `engine/sql/pool_*`
  - Route datasource updates, pools, and tunnels through profile generation.
- Modify: `engine/environment/schema_introspector.py`, `engine/environment/schema_catalog_sync.py`
  - Require authoritative snapshots and factory connections.
- Modify: `engine/sql/guardrail.py`, `engine/sql/row_serializer.py`, `engine/sql/executor.py`, `engine/sql/dialect/*`, `engine/sql/execution/*`
  - Enforce native read-only semantics, cancellation, hard limits, accurate truncation, artifacts, and export safety.
- Modify: `engine/backup.py`, `engine/schemas/backup.py`, `engine/api/backup.py`
  - Remove Python restore fallback and require verified manifests.
- Modify: `desktop/src/lib/llmConfig.ts`, `desktop/src/components/SettingsDialog.tsx`, `desktop/src/components/LlmConfigPanel.tsx`
  - Remove browser credential persistence and introduce explicit draft/save behavior.
- Modify: `requirements*.txt`, `.github/workflows/ci.yml`, `pyproject.toml`
  - Declare build/test dependencies and enforce Phase 1 gates.

## Task 1: Create the CredentialVault and Replace Secret-Bearing Application Contracts

**Files:**

- Create: `engine/security/credential_vault.py`
- Create: `engine/schemas/credentials.py`
- Modify: `engine/models.py`
- Modify: `engine/api/datasources/crud.py`
- Modify: `engine/agent_core/types.py`
- Modify: `engine/agent/app/request_context.py`
- Modify: `desktop/src/lib/llmConfig.ts`
- Modify: `desktop/src/components/SettingsDialog.tsx`
- Test: `engine/tests/test_credential_vault.py`
- Test: `engine/tests/test_agent_secret_boundary.py`
- Test: `desktop/src/lib/__tests__/llmConfig.test.ts`

**Interfaces:**

- Produces `CredentialVault.put(kind, secret) -> credential_id`,
  `get(credential_id) -> secret`, and `delete(credential_id) -> None`.
- Produces `CredentialReference(id: str, kind: CredentialKind)` for API and
  metadata use.
- Replaces `api_key`, encrypted datasource password fields, and SSH password
  fields in serializable contracts with credential IDs.

- [ ] **Step 1: Write failing vault and non-serialization tests**

Create `engine/tests/test_credential_vault.py` with a fake backend and these
tests:

```python
from engine.security.credential_vault import (
    CredentialKind,
    InMemoryCredentialVault,
)


def test_vault_returns_opaque_id_and_not_the_secret() -> None:
    vault = InMemoryCredentialVault()

    credential_id = vault.put(
        kind=CredentialKind.LLM_API_KEY,
        secret="sk-phase1-sentinel",
    )

    assert credential_id.startswith("cred_")
    assert credential_id != "sk-phase1-sentinel"
    assert vault.get(credential_id) == "sk-phase1-sentinel"


def test_vault_rejects_unknown_or_wrong_kind() -> None:
    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="db-password",
    )

    assert vault.get(credential_id, expected_kind=CredentialKind.LLM_API_KEY) is None
    assert vault.get("cred_missing") is None
```

Create `engine/tests/test_agent_secret_boundary.py` with:

```python
from typing import cast

from sqlalchemy.orm import Session

from engine.agent.app.request_context import RequestContext
from engine.agent_core.types import AgentRunRequest
from engine.tools.runtime.registry import ToolRegistry


def test_graph_config_contains_only_opaque_credential_reference() -> None:
    request = AgentRunRequest(
        datasource_id="ds-1",
        question="show orders",
        llm_credential_id="cred_llm_123",
    )
    context = RequestContext(
        cast(Session, object()),
        request,
        registry=cast(ToolRegistry, object()),
    )

    config = context.graph_config("run-1")
    assert config["configurable"]["llm_credential_id"] == "cred_llm_123"
    assert "api_key" not in repr(config)
    assert "request" not in config["configurable"]
```

Create frontend tests that assert `saveStoredApiConfig()` serializes only
`credentialId`, `apiBase`, and `modelName`, and that Cancel leaves storage
unchanged.

- [ ] **Step 2: Run tests and verify red**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests\test_credential_vault.py engine\tests\test_agent_secret_boundary.py -q
npx vitest run src/lib/__tests__/llmConfig.test.ts --maxWorkers=1
```

Expected: import/contract failures because the vault, opaque request field,
and safe frontend storage contract do not exist.

- [ ] **Step 3: Implement the vault with no plaintext fallback**

Create `engine/security/credential_vault.py` with the following concrete
contract:

```python
from __future__ import annotations

from enum import StrEnum
from typing import Protocol
from uuid import uuid4

import keyring


class CredentialKind(StrEnum):
    LLM_API_KEY = "llm_api_key"
    LANGSMITH_API_KEY = "langsmith_api_key"
    DATASOURCE_PASSWORD = "datasource_password"
    SSH_PASSWORD = "ssh_password"
    SSH_KEY_PASSPHRASE = "ssh_key_passphrase"


class CredentialVault(Protocol):
    def put(self, *, kind: CredentialKind, secret: str) -> str:
        raise NotImplementedError

    def get(self, credential_id: str, *, expected_kind: CredentialKind | None = None) -> str | None:
        raise NotImplementedError

    def delete(self, credential_id: str) -> None:
        raise NotImplementedError


class KeyringCredentialVault:
    service_name = "com.dbfox.desktop.credentials"

    def put(self, *, kind: CredentialKind, secret: str) -> str:
        value = secret.strip()
        if not value:
            raise ValueError("Credential secret must not be empty")
        credential_id = f"cred_{kind.value}_{uuid4().hex}"
        keyring.set_password(self.service_name, credential_id, value)
        return credential_id

    def get(self, credential_id: str, *, expected_kind: CredentialKind | None = None) -> str | None:
        if expected_kind is not None and not credential_id.startswith(f"cred_{expected_kind.value}_"):
            return None
        return keyring.get_password(self.service_name, credential_id)

    def delete(self, credential_id: str) -> None:
        try:
            keyring.delete_password(self.service_name, credential_id)
        except keyring.errors.PasswordDeleteError:
            return
```

Add an application-level vault dependency. If keyring is unavailable, return a
typed `CREDENTIAL_VAULT_UNAVAILABLE` error; never write a plaintext fallback
file.

- [ ] **Step 4: Replace serialized secret fields at their boundaries**

Define request/response schemas with `llm_credential_id`,
`password_credential_id`, `ssh_password_credential_id`, and
`ssh_key_passphrase_credential_id`. Do not retain `api_key` on
`AgentRunRequest` or a compatibility alias. Update datasource creation/update
routes to accept a secret only on dedicated enrollment input, write it to the
vault, and persist only the resulting opaque ID.

Update `RequestContext.graph_config()` so its serializable configurable object
contains only `thread_id`, `run_id`, `runtime_id`, and credential IDs. Runtime
objects needed by graph nodes must be resolved through a process-local runtime
registry, not included as `request`, `db`, or `event_store` values.

Update the desktop Settings dialog to hold a local draft. Save calls the
credential enrollment endpoint; Cancel discards the draft. Delete
`API_CONFIG_STORAGE_KEY` values containing `apiKey` during startup and retain
only non-secret configuration.

- [ ] **Step 5: Run focused green tests**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests\test_credential_vault.py engine\tests\test_agent_secret_boundary.py -q
npx vitest run src/lib/__tests__/llmConfig.test.ts --maxWorkers=1
```

Expected: all tests pass; no test fixture needs a real credential.

## Task 2: Make Alembic the Only Metadata Authority and Add the Versioned Reset

**Files:**

- Create: `engine/security/runtime_reset.py`
- Create: `engine/migrations/versions/3c5d7e9f1a2b_foundation_v2.py`
- Modify: `engine/db.py`
- Modify: `engine/models.py`
- Modify: `engine/migrations/env.py`
- Test: `engine/tests/test_runtime_reset.py`
- Test: `engine/tests/test_db_init.py`
- Test: `engine/tests/test_migrations.py`

**Interfaces:**

- Produces `reset_legacy_runtime_state(db_url: str, checkpoint_path: Path) -> ResetResult`.
- Produces `FOUNDATION_RUNTIME_VERSION = "2"` marker semantics.
- Requires `initialize_metadata_database()` to run Alembic upgrade only.

- [ ] **Step 1: Write reset and foreign-key tests**

Create tests that prepare a temporary SQLite metadata DB with legacy Agent run,
approval, checkpoint, Schema catalog, and datasource rows. Assert that reset:

```python
def test_foundation_reset_removes_volatile_legacy_records_but_keeps_endpoint_metadata(tmp_path) -> None:
    result = reset_legacy_runtime_state(metadata_url, checkpoint_path)

    assert result.reset_performed is True
    assert count_rows(metadata_url, "agent_runs") == 0
    assert count_rows(metadata_url, "agent_approvals") == 0
    assert count_rows(metadata_url, "schema_tables") == 0
    assert get_datasource(metadata_url, "ds-1").host == "db.example"
    assert get_datasource(metadata_url, "ds-1").password_credential_id is None
    assert not checkpoint_path.exists()


def test_production_sqlite_connections_enforce_foreign_keys(tmp_path) -> None:
    engine = build_metadata_engine(tmp_path / "metadata.db")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
```

Add a migration test that creates a new empty DB with `alembic upgrade head`,
then runs `alembic check` and expects success.

- [ ] **Step 2: Run reset/migration tests and verify red**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests\test_runtime_reset.py engine\tests\test_migrations.py -q
```

Expected: missing reset module and/or existing schema drift failure.

- [ ] **Step 3: Implement one-way reset and migration authority**

Create `engine/security/runtime_reset.py` with an idempotent marker stored in
the metadata database. Its reset transaction deletes legacy volatile tables in
foreign-key-safe order, clears legacy credential references, and preserves
only explicitly allowlisted non-secret datasource fields. Delete checkpoint
database sidecar files only after verifying their resolved path lies inside the
configured runtime root.

Replace `Base.create_all()` and legacy table-name inference in `engine/db.py`
with:

```python
def initialize_metadata_database() -> None:
    configure_sqlite_pragmas(DATABASE_URL)
    run_alembic_upgrade(DATABASE_URL)
    run_foundation_reset_if_needed(DATABASE_URL)
    verify_database_revision(DATABASE_URL)
```

Set `PRAGMA foreign_keys=ON` in every SQLite DB-API connect hook. Update models
and migrations together, including all intended cascade/SET NULL constraints.
Configure Alembic `include_object` to exclude FTS virtual tables and their
shadow tables from autogenerate drift.

- [ ] **Step 4: Run migration green tests**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests\test_runtime_reset.py engine\tests\test_db_init.py engine\tests\test_migrations.py -q
$env:DBFOX_DATABASE_URL = "sqlite:///$env:TEMP/dbfox-foundation-plan.db"
.\.build_venv\Scripts\python.exe -m alembic upgrade head
.\.build_venv\Scripts\python.exe -m alembic check
```

Expected: all tests and `alembic check` pass on a fresh temporary database.

## Task 3: Replace Direct Driver Access with ConnectionProfile, Factory, and Resource Manager

**Files:**

- Create: `engine/connectivity/profile.py`
- Create: `engine/connectivity/factory.py`
- Create: `engine/connectivity/resources.py`
- Modify: `engine/api/datasources/crud.py`
- Modify: `engine/datasource.py`
- Modify: `engine/tunnel.py`
- Modify: `engine/sql/pool_manager.py`
- Modify: `engine/sql/pool_registry.py`
- Test: `engine/tests/test_connection_factory.py`
- Test: `engine/tests/test_tunnel.py`
- Test: `engine/tests/test_datasource_update.py`

**Interfaces:**

- Produces immutable `ConnectionProfile` and `connection_fingerprint(profile)`.
- Produces `ConnectionFactory.open(profile, purpose)` where `purpose` is one
  of `EXECUTE`, `DRY_RUN`, `INTROSPECT`, `EXPORT`, `BACKUP`, or `RESTORE`.
- Produces `ConnectionResourceManager.invalidate(datasource_id, generation)`.

- [ ] **Step 1: Write connection-policy failures**

Create factory tests covering:

```python
def test_ssh_profile_never_falls_back_to_direct_connection_when_tunnel_fails() -> None:
    profile = ssh_mysql_profile()
    factory = factory_with_tunnel_error()

    with pytest.raises(ConnectionOpenError, match="SSH_TUNNEL_FAILED"):
        factory.open(profile, purpose=ConnectionPurpose.INTROSPECT)

    assert factory.direct_connect_calls == 0


def test_tls_and_ssh_changes_produce_new_resource_fingerprint() -> None:
    assert connection_fingerprint(profile_with_verify_identity(True)) != connection_fingerprint(profile_with_verify_identity(False))
    assert connection_fingerprint(profile_with_ssh_host("a")) != connection_fingerprint(profile_with_ssh_host("b"))


def test_sqlite_read_profile_rejects_missing_or_non_regular_path(tmp_path) -> None:
    with pytest.raises(ConnectionOpenError, match="SQLITE_PATH_INVALID"):
        factory_with_sqlite_policy().open(
            sqlite_read_profile(tmp_path / "missing.db"),
            ConnectionPurpose.EXECUTE,
        )
```

- [ ] **Step 2: Run factory tests and verify red**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests\test_connection_factory.py -q
```

Expected: imports fail because the new boundary does not exist.

- [ ] **Step 3: Implement the typed profile and one connection path**

Define `ConnectionProfile` with all endpoint, TLS, SSH, database scope,
read-only, generation, and credential-reference fields. Its fingerprint must
include every TLS verification setting and SSH host-key policy. Resolve secret
values through `CredentialVault` only inside `ConnectionFactory`.

Use the factory for MySQL, PostgreSQL, and SQLite. Require known-hosts/fixed
fingerprint when SSH is enabled. Make `ResourceManager` use fingerprint plus
generation, per-datasource single-flight locks, and disposal of losing or stale
resources. Update datasource update/delete routes to increment generation and
invalidate resources after a successful metadata transaction.

- [ ] **Step 4: Run factory/update tests**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests\test_connection_factory.py engine\tests\test_tunnel.py engine\tests\test_datasource_update.py -q
```

Expected: pass with no direct driver constructors remaining outside the factory.

## Task 4: Require Authoritative Schema Snapshots

**Files:**

- Create: `engine/environment/authoritative_inventory.py`
- Modify: `engine/environment/schema_introspector.py`
- Modify: `engine/environment/schema_catalog_sync.py`
- Modify: `engine/environment/service.py`
- Test: `engine/tests/test_authoritative_schema_sync.py`
- Test: `engine/tests/test_schema_sync.py`

**Interfaces:**

- Produces `AuthoritativeInventory` only after a fully successful inspection.
- Raises `SchemaInspectionError` for connection/path/credential/SSH/TLS
  failures.
- `SchemaCatalogSync.sync_authoritative(inventory)` is the sole destructive
  catalog synchronization method.

- [ ] **Step 1: Write the catalog preservation regression**

```python
def test_failed_inspection_never_deletes_existing_catalog(db_session, monkeypatch) -> None:
    seed_catalog(db_session, datasource_id="ds-1", table_name="orders")
    monkeypatch.setattr(SchemaIntrospector, "inspect", raise_connect_timeout)

    with pytest.raises(SchemaInspectionError):
        SchemaSyncService(db_session).sync("ds-1")

    assert catalog_table_names(db_session, "ds-1") == ["orders"]
```

- [ ] **Step 2: Run it and verify red**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests\test_authoritative_schema_sync.py -q
```

Expected: current behavior returns an empty inventory and removes the table.

- [ ] **Step 3: Implement authoritative inspection**

Route every inspector through
`ConnectionFactory.open(profile, ConnectionPurpose.INTROSPECT)`. Replace
`_empty_inventory()` error returns with typed failures. Construct
`AuthoritativeInventory` only after all tables/columns/foreign keys are read.
Reject non-authoritative inputs in catalog sync and perform all catalog changes
in one metadata transaction.

- [ ] **Step 4: Run schema sync tests**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests\test_authoritative_schema_sync.py engine\tests\test_schema_sync.py -q
```

Expected: pass; a true empty database still deletes an obsolete catalog only
after successful inspection.

## Task 5: Implement Native Read-Only SQL, Bounded Results, and Safe Export

**Files:**

- Create: `engine/sql/result_artifact.py`
- Modify: `engine/sql/guardrail.py`
- Modify: `engine/sql/row_serializer.py`
- Modify: `engine/sql/executor.py`
- Modify: `engine/sql/dialect/mysql.py`
- Modify: `engine/sql/dialect/postgres.py`
- Modify: `engine/sql/dialect/sqlite.py`
- Modify: `engine/sql/execution/streaming_executor.py`
- Modify: `engine/sql/execution/csv_export.py`
- Test: `engine/tests/test_sql_execution_boundaries.py`
- Test: `engine/tests/test_executor.py`
- Test: `engine/tests/test_csv_export.py`

**Interfaces:**

- Produces `ResultArtifactMetadata` with `rows_truncated`, `columns_truncated`,
  `bytes_truncated`, `original_row_count_known`, and `execution_id`.
- Requires `ExecutionPolicy` to set a hard row limit, deadline, native
  read-only mode, and cancellation registration.

- [ ] **Step 1: Write failing boundary tests**

```python
def test_serializer_marks_a_1001st_row_as_truncated() -> None:
    result = serialize_rows(cursor_with_rows(1001), max_rows=1000)
    assert len(result.rows) == 1000
    assert result.rows_truncated is True


def test_serializer_marks_a_101st_column_as_truncated() -> None:
    result = serialize_rows(cursor_with_columns(101), max_rows=1)
    assert len(result.columns) == 100
    assert result.columns_truncated is True


@pytest.mark.parametrize("sql", [
    "SELECT pg_advisory_lock(42)",
    "SELECT setval('orders_id_seq', 9)",
    "SELECT GET_LOCK('dbfox', 5)",
    "SELECT @session_value := 'mutated'",
])
def test_guardrail_rejects_side_effect_selects(sql: str) -> None:
    assert guardrail_check(sql).allowed is False


def test_csv_escape_blocks_whitespace_prefixed_formula() -> None:
    assert escape_csv_cell("\t=HYPERLINK(\"https://example.invalid\")") == "'\t=HYPERLINK(\"https://example.invalid\")"
```

- [ ] **Step 2: Run tests and verify red**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests\test_sql_execution_boundaries.py engine\tests\test_csv_export.py -q
```

Expected: current serializer and guardrail behavior fails these assertions.

- [ ] **Step 3: Implement a single execution policy**

Fetch `max_rows + 1` rows, retain only `max_rows`, and expose distinct row,
column, and byte truncation flags. Clamp/reject explicit limits above the
global maximum before executing. Use the new factory and resource manager for
all dialect paths. Start native read-only transactions, apply deadlines, and
register every execution before the query starts so cancellation can interrupt
an active query.

Make streaming export consume a `ResultArtifact` or the same `ExecutionPolicy`;
it must not open its own bypass connection. Normalize CSV leading whitespace,
control characters, and BOM before formula-prefix detection.

- [ ] **Step 4: Run focused SQL tests**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests\test_sql_execution_boundaries.py engine\tests\test_executor.py engine\tests\test_csv_export.py -q
```

Expected: pass. Add PostgreSQL/MySQL container tests before accepting native
read-only semantics for those dialects.

## Task 6: Remove Unsafe Restore Fallback and Require Verified Backup Manifests

**Files:**

- Modify: `engine/backup.py`
- Modify: `engine/schemas/backup.py`
- Modify: `engine/api/backup.py`
- Modify: `engine/models.py`
- Test: `engine/tests/test_backup_restore_safety.py`
- Test: `engine/tests/test_backup.py`

**Interfaces:**

- Produces `BackupVerificationStatus = "verified" | "degraded" | "failed"`.
- Allows restore only when `verification_status == "verified"`.

- [ ] **Step 1: Write restore safety tests**

```python
def test_restore_rejects_missing_native_client(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: None)

    with pytest.raises(DBFoxError, match="RESTORE_TOOL_UNAVAILABLE"):
        execute_restore(verified_backup_record(tmp_path))


def test_degraded_python_export_cannot_be_restored(tmp_path) -> None:
    backup = create_degraded_backup_record(tmp_path)

    with pytest.raises(DBFoxError, match="BACKUP_NOT_RESTORABLE"):
        execute_restore(backup)


def test_backup_manifest_requires_object_coverage_and_checksum(tmp_path) -> None:
    manifest = read_manifest(create_verified_fixture_backup(tmp_path))
    assert manifest["verification_status"] == "verified"
    assert manifest["checksum"]
    assert manifest["object_coverage"]["tables"] is True
```

- [ ] **Step 2: Run tests and verify red**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests\test_backup_restore_safety.py -q
```

Expected: fallback defaults and restore eligibility do not meet the new rules.

- [ ] **Step 3: Implement verified/degraded backup semantics**

Set fallback defaults to false. Remove `_pymysql_simple_sql_import()` from the
restore call graph. Native dump creates a manifest with the required fields
and checksum. Any non-native export is explicitly `degraded`; it can be kept
for inspection but cannot be restored. Resolve native executable paths through
an approved configuration rather than an unvalidated PATH lookup, and reject
database identifiers that begin with `-`.

- [ ] **Step 4: Run backup tests**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests\test_backup_restore_safety.py engine\tests\test_backup.py -q
```

Expected: pass with no restore fallback path.

## Task 7: Establish Phase 1 Reproducibility and Safety Gates

**Files:**

- Modify: `requirements.txt`
- Modify: `requirements-dev.txt`
- Create: `requirements-build.txt`
- Create: lock files generated by the selected dependency tool
- Modify: `pyproject.toml`
- Modify: `.github/workflows/ci.yml`
- Test: `engine/tests/test_desktop_icons.py`

- [ ] **Step 1: Write dependency/CI contract checks**

Add a CI verification script or test that asserts Pillow is installed before
icon tests and PyInstaller is installed before sidecar build. Add a CI smoke
step that invokes `alembic check`, full backend tests, and the official npm
audit registry.

- [ ] **Step 2: Verify the current gate is red**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests\test_desktop_icons.py -q
.\.build_venv\Scripts\python.exe -m alembic check
```

Expected: current environment exposes missing Pillow and migration drift.

- [ ] **Step 3: Declare and lock build/test dependencies**

Add Pillow to the development/test dependency set and PyInstaller to the build
dependency set. Pin compatible `sshtunnel`/Paramiko versions or replace
`sshtunnel` before generating locks. Configure mypy to stop ignoring modules
migrated in Phase 1. Update CI to install locked dependencies and run:

```yaml
- run: python -m pytest engine/tests engine/agent/tests engine/evaluation/tests
- run: python -m mypy engine
- run: python -m alembic check
- run: npm audit --registry=https://registry.npmjs.org
  working-directory: desktop
```

- [ ] **Step 4: Run Phase 1 verification**

Run:

```powershell
.\.build_venv\Scripts\python.exe -m pytest engine\tests -q
.\.build_venv\Scripts\python.exe -m mypy engine
.\.build_venv\Scripts\python.exe -m alembic check
npm audit --registry=https://registry.npmjs.org
```

Expected: all Phase 1 gates report the newly enforced safe baseline.

- [ ] **Step 5: Commit Phase 1**

Commit only after the focused and Phase 1 verification commands have fresh
passing evidence:

```powershell
git add engine desktop requirements.txt requirements-dev.txt requirements-build.txt pyproject.toml .github/workflows/ci.yml
git commit -m "refactor: establish secure runtime foundation"
```
