"""Contract tests for the one-way, privacy-preserving Foundation reset."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import inspect
import os
from pathlib import Path
from threading import Event

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from engine.db import build_metadata_engine
from engine.models import (
    AgentApproval,
    AgentArtifactRecord,
    AgentEvalCaseResult,
    AgentEvalRun,
    AgentGoldenTask,
    AgentMessage,
    AgentRun,
    AgentSession,
    AgentSessionMemory,
    BackupRecord,
    ConfirmationToken,
    DataSource,
    DatabaseEnvironment,
    DomainTagRule,
    GoldenSQL,
    LLMLog,
    Project,
    QueryHistory,
    QueryHistorySearchDoc,
    ReusableSQL,
    SchemaColumn,
    SchemaSearchDoc,
    SchemaTable,
    SemanticAlias,
    TableDesignDraft,
    WorkspaceTableScope,
)
from engine.security.credential_vault import CredentialKind, InMemoryCredentialVault
from engine.security.runtime_reset import (
    FOUNDATION_RUNTIME_VERSION,
    RuntimeResetCleanupError,
    RuntimeResetPathError,
    RuntimeResetStateError,
    reset_legacy_runtime_state,
    retire_legacy_project_runtime_dir,
    retire_legacy_source_runtime,
)


_PURGED_TABLES = (
    "confirmation_tokens",
    "agent_approvals",
    "agent_artifacts",
    "agent_events",
    "agent_task_plans",
    "agent_evidence",
    "agent_question_requests",
    "agent_observations",
    "agent_tool_invocations",
    "agent_turns",
    "agent_eval_case_results",
    "agent_eval_runs",
    "agent_golden_tasks",
    "agent_runs",
    "agent_session_inputs",
    "agent_session_memories",
    "agent_messages",
    "agent_sessions",
    "schema_search_docs",
    "schema_columns",
    "workspace_table_scopes",
    "schema_tables",
    "query_history_search_docs",
    "query_history",
    "llm_logs",
    "golden_sqls",
    "reusable_sqls",
    "semantic_aliases",
    "domain_tag_rules",
    "backup_records",
    "table_design_drafts",
)

_PRESERVED_TABLES = (
    "projects",
    "data_sources",
    "database_environments",
)


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _alembic_config(database_url: str) -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "engine" / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _create_v2_metadata_db(runtime_root: Path, name: str = "metadata.db") -> tuple[str, Path]:
    runtime_root.mkdir(parents=True, exist_ok=True)
    metadata_path = runtime_root / name
    metadata_url = _sqlite_url(metadata_path)
    command.upgrade(_alembic_config(metadata_url), "head")
    return metadata_url, metadata_path


def _count_rows(metadata_url: str, table_name: str) -> int:
    engine = build_metadata_engine(metadata_url)
    try:
        with engine.connect() as connection:
            return int(connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one())
    finally:
        engine.dispose()


def _marker(metadata_url: str) -> tuple[str, object] | None:
    engine = build_metadata_engine(metadata_url)
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT runtime_version, reset_completed_at "
                    "FROM foundation_runtime_state WHERE id = 1"
                )
            ).one_or_none()
            return None if row is None else (str(row[0]), row[1])
    finally:
        engine.dispose()


def _sqlite_family_bytes(path: Path) -> bytes:
    chunks: list[bytes] = []
    for candidate in (
        path,
        path.with_name(f"{path.name}-wal"),
        path.with_name(f"{path.name}-shm"),
        path.with_name(f"{path.name}-journal"),
    ):
        if candidate.exists():
            chunks.append(candidate.read_bytes())
    return b"".join(chunks)


def _seed_volatile_state(metadata_url: str, vault: InMemoryCredentialVault) -> dict[str, str]:
    datasource_password_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="datasource password",
    )
    ssh_password_id = vault.put(kind=CredentialKind.SSH_PASSWORD, secret="ssh password")
    ssh_passphrase_id = vault.put(
        kind=CredentialKind.SSH_KEY_PASSPHRASE,
        secret="ssh passphrase",
    )
    environment_password_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="environment password",
    )
    llm_credential_id = vault.put(kind=CredentialKind.LLM_API_KEY, secret="do not remove")
    langsmith_credential_id = vault.put(
        kind=CredentialKind.LANGSMITH_API_KEY,
        secret="do not remove either",
    )

    engine = build_metadata_engine(metadata_url)
    try:
        schema_doc_id: int | None = None
        schema_doc_search_text = "customer email sensitive schema cache"
        with Session(engine) as session:
            project = Project(id="project-1", name="Reset project")
            datasource = DataSource(
                id="datasource-1",
                project_id=project.id,
                name="Warehouse endpoint",
                db_type="postgresql",
                host="db.example.test",
                port=5432,
                database_name="warehouse",
                username="reader",
                password_credential_id=datasource_password_id,
                ssh_enabled=True,
                ssh_host="bastion.example.test",
                ssh_port=2222,
                ssh_username="tunnel-user",
                ssh_password_credential_id=ssh_password_id,
                ssh_pkey_path="C:/keys/dbfox.pem",
                ssh_key_passphrase_credential_id=ssh_passphrase_id,
                ssl_enabled=True,
                ssl_ca_path="C:/certs/ca.pem",
                ssl_cert_path="C:/certs/client.pem",
                ssl_key_path="C:/certs/client.key",
                ssl_verify_identity=False,
                connection_mode="ssh",
                is_read_only=True,
                env="production",
                last_test_at=datetime.now(UTC),
                last_test_status="success",
                last_test_error="stale test error",
                last_test_latency_ms=42,
                last_test_readonly=True,
                last_test_server_version="PostgreSQL 16",
                last_test_tables_count=17,
                last_test_warnings='["stale warning"]',
                last_sync_at=datetime.now(UTC),
                last_sync_status="success",
                last_sync_error="stale sync error",
            )
            session.add_all((project, datasource))
            session.flush()

            environment = DatabaseEnvironment(
                id="environment-1",
                project_id=project.id,
                name="Warehouse environment",
                runtime="docker",
                engine_type="postgresql",
                engine_version="16",
                image="postgres:16",
                container_name="dbfox-warehouse",
                host="db.example.test",
                port=5432,
                database_name="warehouse",
                username="reader",
                password_credential_id=environment_password_id,
                status="running",
                last_health_status="healthy",
                last_health_at=datetime.now(UTC),
                last_error="stale health error",
            )
            session.add(environment)
            session.flush()
            datasource.environment_id = environment.id

            schema_table = SchemaTable(
                id="schema-table-1",
                data_source_id=datasource.id,
                table_schema="public",
                table_name="orders",
            )
            schema_column = SchemaColumn(
                id="schema-column-1",
                table_id=schema_table.id,
                column_name="customer_email",
                data_type="text",
            )
            schema_doc = SchemaSearchDoc(
                datasource_id=datasource.id,
                entity_type="column",
                entity_id=schema_column.id,
                table_name="orders",
                column_name="customer_email",
                name="customer_email",
                search_text=schema_doc_search_text,
            )
            session.add_all((schema_table, schema_column, schema_doc))
            session.flush()
            schema_doc_id = schema_doc.id

            history = QueryHistory(
                id="query-history-1",
                data_source_id=datasource.id,
                question="show customer email",
                submitted_sql="SELECT customer_email FROM orders",
                generated_sql="SELECT customer_email FROM orders",
                safe_sql="SELECT customer_email FROM orders",
                executed_sql="SELECT customer_email FROM orders",
                guardrail_result="allowed",
            )
            history_doc = QueryHistorySearchDoc(
                history_id=history.id,
                datasource_id=datasource.id,
                question=history.question,
                submitted_sql=history.submitted_sql,
                generated_sql=history.generated_sql,
                safe_sql=history.safe_sql,
                executed_sql=history.executed_sql,
                search_text="customer email query history cache",
            )
            session.add_all((history, history_doc))

            agent_session = AgentSession(id="agent-session-1", datasource_id=datasource.id)
            agent_message = AgentMessage(
                id="agent-message-1",
                session_id=agent_session.id,
                role="user",
                content="Please expose sensitive output",
                sequence=1,
            )
            agent_run = AgentRun(
                id="agent-run-1",
                session_id=agent_session.id,
                datasource_id=datasource.id,
                llm_credential_id=llm_credential_id,
                api_base="https://example.invalid/v1",
                model_name="test-model",
                user_message_id=agent_message.id,
                question="Please expose sensitive output",
                response_json='{"result":"sensitive"}',
            )
            session.add_all((agent_session, agent_message, agent_run))
            session.add_all(
                (
                    AgentSessionMemory(
                        id="agent-memory-1",
                        session_id=agent_session.id,
                        datasource_id=datasource.id,
                        conversation_summary="sensitive memory",
                    ),
                    AgentApproval(
                        id="agent-approval-1",
                        run_id=agent_run.id,
                        session_id=agent_session.id,
                        step_name="execute",
                        policy_decision_json='{"allow": false}',
                    ),
                    AgentArtifactRecord(
                        id="agent-artifact-1",
                        run_id=agent_run.id,
                        session_id=agent_session.id,
                        message_id=agent_message.id,
                        type="result",
                        title="Sensitive result",
                        payload_json='{"rows": ["sensitive"]}',
                        presentation_json="{}",
                    ),
                )
            )

            eval_task = AgentGoldenTask(
                id="eval-task-1",
                datasource_id=datasource.id,
                project_id=project.id,
                name="Sensitive eval task",
                question="sensitive evaluation question",
            )
            eval_run = AgentEvalRun(
                id="eval-run-1",
                datasource_id=datasource.id,
                project_id=project.id,
            )
            session.add_all((eval_task, eval_run))
            session.flush()
            session.add(
                AgentEvalCaseResult(
                    id="eval-result-1",
                    eval_run_id=eval_run.id,
                    task_id=eval_task.id,
                    run_id=agent_run.id,
                    response_json='{"sensitive": true}',
                )
            )

            session.add_all(
                (
                    ConfirmationToken(
                        token="confirmation-token-1",
                        expires_at=9_999_999_999,
                        datasource_id=datasource.id,
                        action="restore_backup",
                        details_json='{"sensitive":true}',
                        expected_confirm_text="Warehouse endpoint",
                    ),
                    LLMLog(
                        id="llm-log-1",
                        data_source_id=datasource.id,
                        request_type="agent",
                        prompt_hash=LLMLog.fingerprint_request("test", hmac_key=b"t" * 32),
                        model_name="test-model",
                        status="completed",
                    ),
                    GoldenSQL(
                        id="golden-sql-1",
                        data_source_id=datasource.id,
                        question="sensitive query",
                        golden_sql="SELECT customer_email FROM orders",
                    ),
                    ReusableSQL(
                        id="reusable-sql-1",
                        data_source_id=datasource.id,
                        question="sensitive query",
                        safe_sql="SELECT customer_email FROM orders",
                        sql_fingerprint="fingerprint-1",
                    ),
                    BackupRecord(
                        id="backup-record-1",
                        project_id=project.id,
                        datasource_id=datasource.id,
                        environment_id=environment.id,
                        file_path="C:/backups/contains-sensitive-data.sql",
                    ),
                    TableDesignDraft(
                        id="table-design-draft-1",
                        project_id=project.id,
                        table_name="sensitive_draft",
                        columns_json="[]",
                        indexes_json="[]",
                    ),
                    SemanticAlias(
                        id="semantic-alias-1",
                        data_source_id=datasource.id,
                        alias="customer",
                        target_type="table",
                        target="orders",
                    ),
                    WorkspaceTableScope(
                        id="workspace-scope-1",
                        project_id=project.id,
                        data_source_id=datasource.id,
                        table_id=schema_table.id,
                    ),
                    DomainTagRule(
                        id="domain-tag-rule-1",
                        data_source_id=datasource.id,
                        pattern="customer",
                        tag="pii",
                    ),
                )
            )
            session.commit()

        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO schema_search_fts(rowid, search_text) "
                    "VALUES (:row_id, :search_text)"
                ),
                {"row_id": schema_doc_id, "search_text": schema_doc_search_text},
            )
    finally:
        engine.dispose()

    return {
        "datasource_password_id": datasource_password_id,
        "ssh_password_id": ssh_password_id,
        "ssh_passphrase_id": ssh_passphrase_id,
        "environment_password_id": environment_password_id,
        "llm_credential_id": llm_credential_id,
        "langsmith_credential_id": langsmith_credential_id,
    }


def test_foundation_reset_preserves_only_non_secret_endpoint_metadata(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    metadata_url, _metadata_path = _create_v2_metadata_db(runtime_root)
    vault = InMemoryCredentialVault()
    credentials = _seed_volatile_state(metadata_url, vault)

    result = reset_legacy_runtime_state(metadata_url, runtime_root)

    assert result.reset_performed is True
    assert result.runtime_version == FOUNDATION_RUNTIME_VERSION
    assert _marker(metadata_url) is not None
    assert _marker(metadata_url)[0] == FOUNDATION_RUNTIME_VERSION
    assert _marker(metadata_url)[1] is not None
    for table_name in _PURGED_TABLES:
        assert _count_rows(metadata_url, table_name) == 0
    assert _count_rows(metadata_url, "schema_search_fts") == 0
    for table_name in _PRESERVED_TABLES:
        assert _count_rows(metadata_url, table_name) == 1

    engine = build_metadata_engine(metadata_url)
    try:
        with Session(engine) as session:
            project = session.get(Project, "project-1")
            environment = session.get(DatabaseEnvironment, "environment-1")
            datasource = session.get(DataSource, "datasource-1")
            assert project is not None
            assert environment is not None
            assert datasource is not None
            assert datasource.project_id == project.id
            assert datasource.environment_id == environment.id
            assert environment.project_id == project.id
            assert (
                datasource.name,
                datasource.db_type,
                datasource.host,
                datasource.port,
                datasource.database_name,
                datasource.username,
                datasource.ssh_enabled,
                datasource.ssh_host,
                datasource.ssh_port,
                datasource.ssh_username,
                datasource.ssl_enabled,
                datasource.ssl_ca_path,
                datasource.ssl_cert_path,
                datasource.ssl_verify_identity,
                datasource.connection_mode,
                datasource.is_read_only,
                datasource.env,
            ) == (
                "Warehouse endpoint",
                "postgresql",
                "db.example.test",
                5432,
                "warehouse",
                "reader",
                True,
                "bastion.example.test",
                2222,
                "tunnel-user",
                True,
                "C:/certs/ca.pem",
                "C:/certs/client.pem",
                False,
                "ssh",
                True,
                "production",
            )
            assert datasource.password_credential_id is None
            assert datasource.ssh_password_credential_id is None
            assert datasource.ssh_key_passphrase_credential_id is None
            assert datasource.ssh_pkey_path is None
            assert datasource.ssl_key_path is None
            assert environment.password_credential_id is None
            assert (
                datasource.last_test_at,
                datasource.last_test_status,
                datasource.last_test_error,
                datasource.last_test_latency_ms,
                datasource.last_test_readonly,
                datasource.last_test_server_version,
                datasource.last_test_tables_count,
                datasource.last_test_warnings,
                datasource.last_sync_at,
                datasource.last_sync_status,
                datasource.last_sync_error,
            ) == (None,) * 11
            assert (
                environment.last_health_status,
                environment.last_health_at,
                environment.last_error,
            ) == (None,) * 3
            assert environment.status == "created"
            assert datasource.status == "needs_credentials"
    finally:
        engine.dispose()

    engine = build_metadata_engine(metadata_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT COUNT(*) FROM schema_search_fts "
                    "WHERE schema_search_fts MATCH :query"
                ),
                {"query": "sensitive"},
            ).scalar_one() == 0
            assert connection.execute(
                text(
                    "SELECT COUNT(*) FROM query_history_fts "
                    "WHERE query_history_fts MATCH :query"
                ),
                {"query": "sensitive"},
            ).scalar_one() == 0
    finally:
        engine.dispose()

    for credential_name, expected_secret in (
        ("datasource_password_id", "datasource password"),
        ("ssh_password_id", "ssh password"),
        ("ssh_passphrase_id", "ssh passphrase"),
        ("environment_password_id", "environment password"),
        ("llm_credential_id", "do not remove"),
        ("langsmith_credential_id", "do not remove either"),
    ):
        assert vault.get(credentials[credential_name]) == expected_secret

    marker_before_noop = _marker(metadata_url)
    engine = build_metadata_engine(metadata_url)
    try:
        with Session(engine) as session:
            session.add(
                AgentSession(
                    id="agent-session-created-after-reset",
                    datasource_id="datasource-1",
                    title="Must survive the no-op",
                )
            )
            session.commit()
    finally:
        engine.dispose()

    noop_result = reset_legacy_runtime_state(metadata_url, runtime_root)
    assert noop_result.reset_performed is False
    assert _marker(metadata_url) == marker_before_noop
    assert _count_rows(metadata_url, "agent_sessions") == 1


def test_foundation_reset_never_deletes_vault_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Credential IDs are reset in metadata; vault ownership remains global."""
    runtime_root = tmp_path / "runtime"
    metadata_url, _metadata_path = _create_v2_metadata_db(runtime_root)
    vault = InMemoryCredentialVault()
    credentials = _seed_volatile_state(metadata_url, vault)

    import engine.security.runtime_reset as runtime_reset

    def forbidden_vault_access() -> None:
        raise AssertionError("runtime reset must not access the credential vault")

    monkeypatch.setattr(runtime_reset, "get_credential_vault", forbidden_vault_access, raising=False)

    reset_legacy_runtime_state(metadata_url, runtime_root)

    for credential_name, expected_secret in (
        ("datasource_password_id", "datasource password"),
        ("ssh_password_id", "ssh password"),
        ("ssh_passphrase_id", "ssh passphrase"),
        ("environment_password_id", "environment password"),
        ("llm_credential_id", "do not remove"),
        ("langsmith_credential_id", "do not remove either"),
    ):
        assert vault.get(credentials[credential_name]) == expected_secret


def test_foundation_reset_removes_safe_checkpoint_sidecars_and_legacy_backups(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    metadata_url, metadata_path = _create_v2_metadata_db(runtime_root)
    checkpoint_path = metadata_path.with_name("dbfox_agent_core_checkpoints.sqlite")
    checkpoint_path.write_bytes(b"checkpoint")
    checkpoint_path.with_name(f"{checkpoint_path.name}-wal").write_bytes(b"wal")
    checkpoint_path.with_name(f"{checkpoint_path.name}-shm").write_bytes(b"shm")
    checkpoint_path.with_name(f"{checkpoint_path.name}-journal").write_bytes(b"journal")
    checkpoint_path.with_name(f"{checkpoint_path.name}.version").write_text("v1", encoding="utf-8")
    legacy_backup = runtime_root / f"{metadata_path.name}.bak_123456"
    for suffix in ("", "-wal", "-shm", "-journal", ".version"):
        legacy_backup.with_name(f"{legacy_backup.name}{suffix}").write_bytes(b"legacy ciphertext")
    # This is a live-metadata sidecar and is only preflighted, never deleted.
    metadata_version = metadata_path.with_name(f"{metadata_path.name}.version")
    metadata_version.write_text("live metadata sidecar", encoding="utf-8")
    langsmith_env = runtime_root / "config" / "langsmith.env"
    langsmith_env.parent.mkdir(parents=True)
    langsmith_env.write_text("LANGCHAIN_API_KEY=lsv2-sensitive", encoding="utf-8")
    legacy_env = runtime_root / "config" / ".env"
    legacy_env.write_text("OPENAI_API_KEY=legacy-sensitive", encoding="utf-8")
    legacy_secret_key = runtime_root / "secrets" / ".secret_key"
    legacy_secret_key.parent.mkdir()
    legacy_secret_key.write_bytes(b"legacy-local-crypto-key")
    unrelated_secret = runtime_root / "secrets" / "keep.key"
    unrelated_secret.write_bytes(b"keep")
    unrelated_env = runtime_root / "config" / "keep.env"
    unrelated_env.write_text("KEEP=true", encoding="utf-8")
    unrelated_backup = runtime_root / "other-metadata.db.bak_123456"
    unrelated_backup.write_bytes(b"keep me")
    non_timestamp_backup = runtime_root / f"{metadata_path.name}.bak_not-a-timestamp"
    non_timestamp_backup.write_bytes(b"keep me too")
    non_timestamp_backup.with_name(f"{non_timestamp_backup.name}-wal").write_bytes(b"still keep me")

    result = reset_legacy_runtime_state(metadata_url, runtime_root)

    assert result.reset_performed is True
    assert not checkpoint_path.exists()
    assert not checkpoint_path.with_name(f"{checkpoint_path.name}-wal").exists()
    assert not checkpoint_path.with_name(f"{checkpoint_path.name}-shm").exists()
    assert not checkpoint_path.with_name(f"{checkpoint_path.name}-journal").exists()
    assert not checkpoint_path.with_name(f"{checkpoint_path.name}.version").exists()
    for suffix in ("", "-wal", "-shm", "-journal", ".version"):
        assert not legacy_backup.with_name(f"{legacy_backup.name}{suffix}").exists()
    assert metadata_version.exists()
    assert not langsmith_env.exists()
    assert not legacy_env.exists()
    assert not legacy_secret_key.exists()
    assert unrelated_secret.exists()
    assert unrelated_env.exists()
    assert unrelated_backup.exists()
    assert non_timestamp_backup.exists()
    assert non_timestamp_backup.with_name(f"{non_timestamp_backup.name}-wal").exists()

    checkpoint_path.write_bytes(b"created after reset")
    noop = reset_legacy_runtime_state(metadata_url, runtime_root)
    assert noop.reset_performed is False
    assert checkpoint_path.exists()


def test_foundation_reset_has_no_caller_selected_cleanup_target(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    metadata_url, _metadata_path = _create_v2_metadata_db(runtime_root)
    outside_checkpoint = tmp_path / "outside-checkpoint.sqlite"
    outside_checkpoint.write_bytes(b"outside checkpoint")

    assert "checkpoint_path" not in inspect.signature(reset_legacy_runtime_state).parameters
    reset_legacy_runtime_state(metadata_url, runtime_root)
    assert outside_checkpoint.exists()

    outside_root = tmp_path / "outside-runtime"
    outside_metadata_url, outside_metadata_path = _create_v2_metadata_db(outside_root)
    outside_backup = outside_root / f"{outside_metadata_path.name}.bak_unsafe"
    outside_backup.write_bytes(b"outside legacy ciphertext")

    with pytest.raises(RuntimeResetPathError):
        reset_legacy_runtime_state(outside_metadata_url, runtime_root)

    assert outside_backup.exists()
    assert _marker(outside_metadata_url) is None


def test_unsafe_default_checkpoint_sidecar_preflight_leaves_no_marker_and_is_retryable(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    metadata_url, metadata_path = _create_v2_metadata_db(runtime_root)
    checkpoint_path = metadata_path.with_name("dbfox_agent_core_checkpoints.sqlite")
    checkpoint_path.write_bytes(b"checkpoint")
    legacy_secret_key = runtime_root / "secrets" / ".secret_key"
    legacy_secret_key.parent.mkdir()
    legacy_secret_key.write_bytes(b"legacy-local-crypto-key")
    unsafe_sidecar = checkpoint_path.with_name(f"{checkpoint_path.name}-wal")
    unsafe_sidecar.mkdir()
    vault = InMemoryCredentialVault()
    credentials = _seed_volatile_state(metadata_url, vault)

    with pytest.raises(RuntimeResetPathError):
        reset_legacy_runtime_state(metadata_url, runtime_root)

    assert _marker(metadata_url) is None
    assert checkpoint_path.exists()
    assert legacy_secret_key.exists()
    assert unsafe_sidecar.is_dir()
    assert _count_rows(metadata_url, "agent_runs") == 1
    assert vault.get(credentials["datasource_password_id"]) == "datasource password"

    unsafe_sidecar.rmdir()
    retry_result = reset_legacy_runtime_state(metadata_url, runtime_root)

    assert retry_result.reset_performed is True
    assert _marker(metadata_url) is not None
    assert not checkpoint_path.exists()
    assert not legacy_secret_key.exists()


def test_unsafe_matching_backup_sidecar_preflight_leaves_all_external_files_and_db_unchanged(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    metadata_url, metadata_path = _create_v2_metadata_db(runtime_root)
    checkpoint_path = metadata_path.with_name("dbfox_agent_core_checkpoints.sqlite")
    checkpoint_path.write_bytes(b"checkpoint")
    legacy_backup = runtime_root / f"{metadata_path.name}.bak_20260711"
    legacy_backup.write_bytes(b"legacy metadata")
    unsafe_sidecar = legacy_backup.with_name(f"{legacy_backup.name}-journal")
    unsafe_sidecar.mkdir()
    _seed_volatile_state(metadata_url, InMemoryCredentialVault())

    with pytest.raises(RuntimeResetPathError):
        reset_legacy_runtime_state(metadata_url, runtime_root)

    # The whole plan is checked before the first unlink, not just the target
    # that happened to be encountered first.
    assert checkpoint_path.exists()
    assert legacy_backup.exists()
    assert unsafe_sidecar.is_dir()
    assert _marker(metadata_url) is None
    assert _count_rows(metadata_url, "agent_runs") == 1

    unsafe_sidecar.rmdir()
    retry = reset_legacy_runtime_state(metadata_url, runtime_root)
    assert retry.reset_performed is True
    assert not checkpoint_path.exists()
    assert not legacy_backup.exists()


def test_legacy_secret_key_cleanup_rejects_a_link_without_touching_its_target(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    metadata_url, _metadata_path = _create_v2_metadata_db(runtime_root)
    outside_secret = tmp_path / "outside-secret"
    outside_secret.write_bytes(b"must-survive")
    legacy_secret_key = runtime_root / "secrets" / ".secret_key"
    legacy_secret_key.parent.mkdir()
    try:
        legacy_secret_key.symlink_to(outside_secret)
    except OSError:
        pytest.skip("creating a file symlink is not permitted on this host")

    with pytest.raises(RuntimeResetPathError):
        reset_legacy_runtime_state(metadata_url, runtime_root)

    assert _marker(metadata_url) is None
    assert outside_secret.read_bytes() == b"must-survive"
    assert legacy_secret_key.is_symlink()


def test_external_cleanup_failure_is_durably_pending_and_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    metadata_url, metadata_path = _create_v2_metadata_db(runtime_root)
    checkpoint_path = metadata_path.with_name("dbfox_agent_core_checkpoints.sqlite")
    checkpoint_path.write_bytes(b"checkpoint")
    legacy_secret_key = runtime_root / "secrets" / ".secret_key"
    legacy_secret_key.parent.mkdir()
    legacy_secret_key.write_bytes(b"legacy-local-crypto-key")
    vault = InMemoryCredentialVault()
    _seed_volatile_state(metadata_url, vault)

    import engine.security.runtime_reset as runtime_reset

    original_cleanup = runtime_reset._remove_external_files

    def fail_cleanup(_plan: object) -> None:
        raise RuntimeResetCleanupError()

    monkeypatch.setattr(runtime_reset, "_remove_external_files", fail_cleanup)
    with pytest.raises(RuntimeResetCleanupError):
        reset_legacy_runtime_state(metadata_url, runtime_root)

    assert _marker(metadata_url) == (FOUNDATION_RUNTIME_VERSION, None)
    assert checkpoint_path.exists()
    assert legacy_secret_key.exists()
    assert _count_rows(metadata_url, "agent_runs") == 0

    monkeypatch.setattr(runtime_reset, "_remove_external_files", original_cleanup)
    retry_result = reset_legacy_runtime_state(metadata_url, runtime_root)
    assert retry_result.reset_performed is True
    assert _marker(metadata_url)[1] is not None
    assert not checkpoint_path.exists()
    assert not legacy_secret_key.exists()


def test_database_reset_failure_never_starts_external_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    metadata_url, metadata_path = _create_v2_metadata_db(runtime_root)
    checkpoint_path = metadata_path.with_name("dbfox_agent_core_checkpoints.sqlite")
    checkpoint_path.write_bytes(b"checkpoint")

    import engine.security.runtime_reset as runtime_reset

    def fail_database_clear(_connection: object) -> None:
        raise RuntimeError("injected database clear failure")

    monkeypatch.setattr(runtime_reset, "_clear_database_runtime_state", fail_database_clear)
    with pytest.raises(RuntimeError, match="injected database clear failure"):
        reset_legacy_runtime_state(metadata_url, runtime_root)

    assert checkpoint_path.exists()
    assert _marker(metadata_url) is None


@pytest.mark.parametrize("legacy_version", ("2", "3"))
def test_known_legacy_marker_is_upgraded_to_the_v4_strict_reset(
    tmp_path: Path,
    legacy_version: str,
) -> None:
    runtime_root = tmp_path / "runtime"
    metadata_url, _metadata_path = _create_v2_metadata_db(runtime_root)
    _seed_volatile_state(metadata_url, InMemoryCredentialVault())
    legacy_secret_key = runtime_root / "secrets" / ".secret_key"
    legacy_secret_key.parent.mkdir()
    legacy_secret_key.write_bytes(b"legacy-local-crypto-key")
    engine = build_metadata_engine(metadata_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO foundation_runtime_state (id, runtime_version, reset_completed_at) "
                    "VALUES (1, :legacy_version, CURRENT_TIMESTAMP)"
                ),
                {"legacy_version": legacy_version},
            )
    finally:
        engine.dispose()

    result = reset_legacy_runtime_state(metadata_url, runtime_root)

    assert result.reset_performed is True
    assert _marker(metadata_url)[0] == FOUNDATION_RUNTIME_VERSION
    assert _marker(metadata_url)[1] is not None
    assert not legacy_secret_key.exists()
    for table_name in _PURGED_TABLES:
        assert _count_rows(metadata_url, table_name) == 0


def test_runtime_root_cleanup_uses_shared_layout_not_metadata_parent(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    metadata_url, metadata_path = _create_v2_metadata_db(runtime_root / "data")
    checkpoint_path = metadata_path.with_name("dbfox_agent_core_checkpoints.sqlite")
    checkpoint_path.write_bytes(b"checkpoint")
    langsmith_env = runtime_root / "config" / "langsmith.env"
    private_env = runtime_root / "config" / ".env"
    langsmith_env.parent.mkdir(parents=True)
    langsmith_env.write_text("LANGCHAIN_API_KEY=legacy", encoding="utf-8")
    private_env.write_text("OPENAI_API_KEY=legacy", encoding="utf-8")
    legacy_secret_key = runtime_root / "secrets" / ".secret_key"
    legacy_secret_key.parent.mkdir()
    legacy_secret_key.write_bytes(b"legacy-local-crypto-key")

    reset_legacy_runtime_state(metadata_url, runtime_root)

    assert not checkpoint_path.exists()
    assert not langsmith_env.exists()
    assert not private_env.exists()
    assert not legacy_secret_key.exists()


def test_reset_vacuums_deleted_legacy_text_from_metadata_and_wal(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    metadata_url, metadata_path = _create_v2_metadata_db(runtime_root)
    sentinel = "foundation-reset-physical-sentinel-50e00cc8"
    _seed_volatile_state(metadata_url, InMemoryCredentialVault())
    engine = build_metadata_engine(metadata_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO query_history "
                    "(id, data_source_id, question, guardrail_result, created_at) "
                    "VALUES (:id, :datasource_id, :question, :guardrail_result, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": "physical-sentinel-history",
                    "datasource_id": "datasource-1",
                    "question": sentinel,
                    "guardrail_result": "allowed",
                },
            )
    finally:
        engine.dispose()

    assert sentinel.encode("utf-8") in _sqlite_family_bytes(metadata_path)

    reset_legacy_runtime_state(metadata_url, runtime_root)

    assert sentinel.encode("utf-8") not in _sqlite_family_bytes(metadata_path)


def test_runtime_reset_removes_only_regular_files_from_owned_backup_tree(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    metadata_url, _metadata_path = _create_v2_metadata_db(runtime_root)
    managed_backup = runtime_root / "backups" / "project-1" / "datasource-1" / "dump.sql"
    managed_backup.parent.mkdir(parents=True)
    managed_backup.write_text("legacy business data", encoding="utf-8")
    outside_file = tmp_path / "outside.sql"
    outside_file.write_text("must survive", encoding="utf-8")

    reset_legacy_runtime_state(metadata_url, runtime_root)

    assert not managed_backup.exists()
    assert outside_file.read_text(encoding="utf-8") == "must survive"


def test_runtime_reset_rejects_links_in_owned_backup_tree_before_database_reset(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    metadata_url, _metadata_path = _create_v2_metadata_db(runtime_root)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "dump.sql").write_text("must survive", encoding="utf-8")
    backup_link = runtime_root / "backups" / "linked"
    backup_link.parent.mkdir()
    try:
        backup_link.symlink_to(outside_dir, target_is_directory=True)
    except OSError:
        pytest.skip("creating a directory symlink is not permitted on this host")

    with pytest.raises(RuntimeResetPathError):
        reset_legacy_runtime_state(metadata_url, runtime_root)

    assert _marker(metadata_url) is None
    assert (outside_dir / "dump.sql").exists()


def test_retire_legacy_source_runtime_deletes_only_the_historical_artifact_family(
    tmp_path: Path,
) -> None:
    legacy_root = tmp_path / "legacy-source"
    legacy_root.mkdir()
    metadata = legacy_root / "dbfox_local.db"
    checkpoint = legacy_root / "dbfox_agent_core_checkpoints.sqlite"
    backup = legacy_root / "dbfox_local.db.bak_20260711"
    for base in (metadata, checkpoint, backup):
        for suffix in ("", "-wal", "-shm", "-journal", ".version"):
            base.with_name(f"{base.name}{suffix}").write_bytes(b"legacy")
    unrelated = legacy_root / "do-not-delete.txt"
    unrelated.write_text("keep", encoding="utf-8")

    assert retire_legacy_source_runtime(legacy_root) is True

    for base in (metadata, checkpoint, backup):
        for suffix in ("", "-wal", "-shm", "-journal", ".version"):
            assert not base.with_name(f"{base.name}{suffix}").exists()
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert retire_legacy_source_runtime(legacy_root) is False


def test_retire_legacy_project_runtime_dir_removes_only_fixed_historical_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import engine.security.runtime_reset as runtime_reset

    project_root = tmp_path / "project"
    project_root.mkdir()
    legacy_root = project_root / ".dbfox_runtime"
    active_runtime_root = tmp_path / "private-runtime"
    active_runtime_root.mkdir()
    for relative_path in (
        "auth/.local_token",
        "config/legacy.env",
        "data/dbfox_local.db",
        "logs/dbfox-engine.log",
        "memory/long_term_memory.sqlite",
        "secrets/.secret_key",
        "backups/project/datasource/backup.sql",
        "tests/test_backup_runtime/run/backups/project/datasource/dump.sql",
    ):
        path = legacy_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("legacy", encoding="utf-8")
    outside_file = project_root / "do-not-delete.txt"
    outside_file.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(runtime_reset, "PROJECT_DIR", project_root)

    assert retire_legacy_project_runtime_dir(active_runtime_root) is True

    assert not legacy_root.exists()
    assert outside_file.read_text(encoding="utf-8") == "keep"
    assert retire_legacy_project_runtime_dir(active_runtime_root) is False


def test_retire_legacy_project_runtime_dir_rejects_active_or_unknown_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import engine.security.runtime_reset as runtime_reset

    project_root = tmp_path / "project"
    project_root.mkdir()
    legacy_root = project_root / ".dbfox_runtime"
    (legacy_root / "auth").mkdir(parents=True)
    (legacy_root / "auth" / ".local_token").write_text("legacy", encoding="utf-8")
    monkeypatch.setattr(runtime_reset, "PROJECT_DIR", project_root)

    with pytest.raises(RuntimeResetPathError):
        retire_legacy_project_runtime_dir(legacy_root)
    assert (legacy_root / "auth" / ".local_token").exists()

    active_runtime_root = tmp_path / "private-runtime"
    active_runtime_root.mkdir()
    (legacy_root / "unexpected").mkdir()
    with pytest.raises(RuntimeResetPathError):
        retire_legacy_project_runtime_dir(active_runtime_root)
    assert (legacy_root / "auth" / ".local_token").exists()


def test_retire_legacy_project_runtime_dir_rejects_links_before_removal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import engine.security.runtime_reset as runtime_reset

    project_root = tmp_path / "project"
    project_root.mkdir()
    legacy_root = project_root / ".dbfox_runtime"
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_file = outside_dir / "must-survive.txt"
    outside_file.write_text("outside", encoding="utf-8")
    legacy_root.mkdir()
    link = legacy_root / "auth"
    try:
        link.symlink_to(outside_dir, target_is_directory=True)
    except OSError:
        pytest.skip("creating a directory symlink is not permitted on this host")
    monkeypatch.setattr(runtime_reset, "PROJECT_DIR", project_root)

    with pytest.raises(RuntimeResetPathError):
        retire_legacy_project_runtime_dir(tmp_path / "private-runtime")

    assert link.exists()
    assert outside_file.read_text(encoding="utf-8") == "outside"


def test_retire_legacy_project_runtime_dir_cannot_follow_a_raced_child_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import engine.security.runtime_reset as runtime_reset

    project_root = tmp_path / "project"
    project_root.mkdir()
    legacy_root = project_root / ".dbfox_runtime"
    auth_dir = legacy_root / "auth"
    auth_dir.mkdir(parents=True)
    legacy_token = auth_dir / ".local_token"
    legacy_token.write_text("legacy", encoding="utf-8")
    active_runtime_root = tmp_path / "private-runtime"
    active_runtime_root.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_token = outside_dir / ".local_token"
    outside_token.write_text("outside", encoding="utf-8")
    probe = tmp_path / "probe-link"
    try:
        probe.symlink_to(outside_dir, target_is_directory=True)
    except OSError:
        pytest.skip("creating a directory symlink is not permitted on this host")
    else:
        probe.unlink()
    monkeypatch.setattr(runtime_reset, "PROJECT_DIR", project_root)

    original_remove = runtime_reset._remove_external_files
    parked_auth = legacy_root / "auth-parked"

    def replace_child_after_preflight(plan: object) -> None:
        auth_dir.rename(parked_auth)
        auth_dir.symlink_to(outside_dir, target_is_directory=True)
        original_remove(plan)

    monkeypatch.setattr(runtime_reset, "_remove_external_files", replace_child_after_preflight)
    with pytest.raises(RuntimeResetPathError):
        retire_legacy_project_runtime_dir(active_runtime_root)

    assert outside_token.read_text(encoding="utf-8") == "outside"
    assert (parked_auth / ".local_token").read_text(encoding="utf-8") == "legacy"


@pytest.mark.skipif(os.name != "nt", reason="Win32 alias behavior")
def test_windows_metadata_aliases_are_rejected_before_cleanup(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    metadata_url, metadata_path = _create_v2_metadata_db(runtime_root)
    checkpoint_path = metadata_path.with_name("dbfox_agent_core_checkpoints.sqlite")
    checkpoint_path.write_bytes(b"checkpoint")
    protected_sidecar = metadata_path.with_name(f"{metadata_path.name}.version")
    protected_sidecar.write_text("must survive", encoding="utf-8")

    for alias_name in (f"{metadata_path.name}.", f"{metadata_path.name}::$DATA"):
        aliased_url = _sqlite_url(metadata_path.with_name(alias_name))
        with pytest.raises(RuntimeResetPathError):
            reset_legacy_runtime_state(aliased_url, runtime_root)

    assert protected_sidecar.exists()
    assert checkpoint_path.exists()
    assert _marker(metadata_url) is None


@pytest.mark.skipif(os.name != "nt", reason="NTFS is case-insensitive")
def test_windows_case_varied_metadata_url_purges_matching_backup_family(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    _metadata_url, metadata_path = _create_v2_metadata_db(runtime_root, name="metadata.db")
    legacy_backup = runtime_root / "metadata.db.bak_20260711"
    legacy_backup.write_bytes(b"legacy ciphertext")
    aliased_url = _sqlite_url(metadata_path.with_name("METADATA.DB"))

    reset_legacy_runtime_state(aliased_url, runtime_root)

    assert not legacy_backup.exists()


@pytest.mark.skipif(os.name != "nt", reason="requires Win32 reparse-point semantics")
def test_windows_parent_reparse_after_plan_validation_cannot_delete_outside_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    metadata_url, _metadata_path = _create_v2_metadata_db(runtime_root)
    config_dir = runtime_root / "config"
    langsmith_env = config_dir / "langsmith.env"
    config_dir.mkdir()
    langsmith_env.write_text("legacy", encoding="utf-8")
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_env = outside_dir / "langsmith.env"
    outside_env.write_text("outside must survive", encoding="utf-8")

    probe = tmp_path / "probe-link"
    try:
        probe.symlink_to(outside_dir, target_is_directory=True)
    except OSError:
        pytest.skip("creating a directory symlink is not permitted on this Windows host")
    else:
        probe.unlink()

    import engine.security.runtime_reset as runtime_reset

    original_require_root = runtime_reset._require_runtime_root
    call_count = 0
    parked_config = runtime_root / "config-parked"

    def replace_config_after_validation(path: Path) -> Path:
        nonlocal call_count
        result = original_require_root(path)
        call_count += 1
        if call_count == 3:
            config_dir.rename(parked_config)
            config_dir.symlink_to(outside_dir, target_is_directory=True)
        return result

    monkeypatch.setattr(runtime_reset, "_require_runtime_root", replace_config_after_validation)
    with pytest.raises(RuntimeResetPathError):
        reset_legacy_runtime_state(metadata_url, runtime_root)

    assert outside_env.read_text(encoding="utf-8") == "outside must survive"
    assert _marker(metadata_url) == (FOUNDATION_RUNTIME_VERSION, None)

    monkeypatch.setattr(runtime_reset, "_require_runtime_root", original_require_root)
    config_dir.unlink()
    parked_config.rename(config_dir)
    assert reset_legacy_runtime_state(metadata_url, runtime_root).reset_performed is True
    assert not langsmith_env.exists()


def test_first_reset_waits_for_sqlite_writer_before_external_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first-run marker check must be serialized before file deletion."""
    runtime_root = tmp_path / "runtime"
    metadata_url, metadata_path = _create_v2_metadata_db(runtime_root)
    checkpoint_path = metadata_path.with_name("dbfox_agent_core_checkpoints.sqlite")
    checkpoint_path.write_bytes(b"checkpoint")

    import engine.security.runtime_reset as runtime_reset

    cleanup_started = Event()
    original_cleanup = runtime_reset._remove_external_files

    def record_cleanup(plan: object) -> None:
        cleanup_started.set()
        original_cleanup(plan)

    monkeypatch.setattr(runtime_reset, "_remove_external_files", record_cleanup)
    locker_engine = build_metadata_engine(metadata_url)
    try:
        with locker_engine.connect() as locker:
            locker.exec_driver_sql("BEGIN IMMEDIATE")
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    reset_legacy_runtime_state,
                    metadata_url,
                    runtime_root,
                )
                assert not cleanup_started.wait(timeout=0.2)
                locker.rollback()
                result = future.result(timeout=10)
    finally:
        locker_engine.dispose()

    assert result.reset_performed is True
    assert not checkpoint_path.exists()
    assert _marker(metadata_url) is not None


def test_unknown_runtime_marker_fails_closed_without_external_cleanup(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    metadata_url, metadata_path = _create_v2_metadata_db(runtime_root)
    checkpoint_path = metadata_path.with_name("dbfox_agent_core_checkpoints.sqlite")
    checkpoint_path.write_bytes(b"must remain")
    engine = build_metadata_engine(metadata_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO foundation_runtime_state (id, runtime_version) "
                    "VALUES (1, 'future-version')"
                )
            )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeResetStateError):
        reset_legacy_runtime_state(metadata_url, runtime_root)

    assert checkpoint_path.exists()
    assert _marker(metadata_url) is not None
    assert _marker(metadata_url)[0] == "future-version"
