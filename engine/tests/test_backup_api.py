from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from engine.app.safe_errors import FixedErrorCode, fixed_error_message
from engine.backup import BackupError, _backup_path, _run_mysqldump, execute_restore
from engine.db import get_db
from engine.main import LOCAL_SECURE_TOKEN, SAFE_DBFOX_ERROR_MESSAGE, app
from engine.models import DEFAULT_PROJECT_ID, BackupRecord, DataSource, Project, RestoreOperation


def _headers() -> dict[str, str]:
    return {"X-Local-Token": LOCAL_SECURE_TOKEN}


def _assert_fixed_dbfox_error(response) -> None:
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "DBFOX_ERROR"
    assert detail["message"] == SAFE_DBFOX_ERROR_MESSAGE


def _runtime_dir(name: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=f"dbfox-{name}-"))


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _ensure_default_project(db_session: Session) -> None:
    if db_session.get(Project, DEFAULT_PROJECT_ID) is None:
        db_session.add(
            Project(
                id=DEFAULT_PROJECT_ID,
                name="Backup API test project",
                description="Project required by the datasource foreign key.",
            )
        )
        db_session.flush()


def _create_mysql_datasource(db_session: Session) -> DataSource:
    _ensure_default_project(db_session)
    datasource = DataSource(
        id="backup-ds",
        project_id=DEFAULT_PROJECT_ID,
        name="backup_test",
        host="127.0.0.1",
        port=3306,
        database_name="analytics",
        username="readonly",
        password_credential_id="cred_datasource_password_backup",
        status="active",
    )
    db_session.add(datasource)
    db_session.commit()
    return datasource


def _write_native_dump(_: DataSource, output_path: Path) -> None:
    output_path.write_text("-- MySQL dump\nCREATE TABLE users (id int);\n", encoding="utf-8")


def _artifact_path(runtime_dir: Path, relative_path: str) -> Path:
    return runtime_dir / "backups" / Path(relative_path)


def test_create_list_and_precheck_backup_uses_private_relative_path(client, db_session, monkeypatch) -> None:
    runtime_dir = _runtime_dir("backup-relative-path")
    monkeypatch.setenv("DBFOX_RUNTIME_DIR", str(runtime_dir))
    datasource = _create_mysql_datasource(db_session)
    monkeypatch.setattr("engine.backup._run_mysqldump", _write_native_dump)

    create_response = client.post(
        "/api/v1/backups",
        json={"datasource_id": datasource.id, "label": "before migration"},
        headers=_headers(),
    )
    assert create_response.status_code == 200, create_response.json()
    backup = create_response.json()
    assert backup["status"] == "success"
    assert backup["file_path"] is not None
    assert not Path(backup["file_path"]).is_absolute()
    assert "\\" not in backup["file_path"]
    assert _artifact_path(runtime_dir, backup["file_path"]).is_file()
    assert backup["source_connection_generation"] == 1
    assert backup["source_database_name"] == "analytics"
    assert backup["source_profile_fingerprint"].startswith("conn_")

    list_response = client.get(f"/api/v1/projects/{DEFAULT_PROJECT_ID}/backups", headers=_headers())
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [backup["id"]]

    precheck_response = client.post(
        f"/api/v1/backups/{backup['id']}/restore-precheck",
        headers=_headers(),
    )
    assert precheck_response.status_code == 200
    precheck = precheck_response.json()
    assert precheck["ok"] is True
    assert precheck["restoreAvailable"] is True
    assert precheck["warnings"] == []


def test_restore_endpoint_requires_explicit_generation_and_confirmation(
    client,
    monkeypatch,
) -> None:
    response = client.post(
        "/api/v1/backups/missing-backup/restore",
        json={"expected_datasource_generation": 1},
        headers=_headers(),
    )
    assert response.status_code == 422

    operation = RestoreOperation(
        id="restore-api",
        backup_id="backup-api",
        datasource_id="datasource-api",
        status="success",
        source_database_name="before",
        target_database_name="after",
        expected_generation=1,
        committed_generation=2,
        validated_table_count=3,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    monkeypatch.setattr("engine.api.backup.execute_restore", lambda *_args, **_kwargs: operation)
    response = client.post(
        "/api/v1/backups/backup-api/restore",
        json={
            "expected_datasource_generation": 1,
            "confirmation": "restore-to-isolated-database",
        },
        headers=_headers(),
    )
    assert response.status_code == 200
    assert response.json()["committed_generation"] == 2


def test_execute_restore_validates_then_atomically_switches_datasource(
    client,
    db_session,
    monkeypatch,
) -> None:
    runtime_dir = _runtime_dir("restore-cutover")
    monkeypatch.setenv("DBFOX_RUNTIME_DIR", str(runtime_dir))
    datasource = _create_mysql_datasource(db_session)
    monkeypatch.setattr("engine.backup._run_mysqldump", _write_native_dump)
    backup = client.post(
        "/api/v1/backups",
        json={"datasource_id": datasource.id},
        headers=_headers(),
    ).json()

    calls: list[str] = []
    monkeypatch.setattr(
        "engine.backup._create_isolated_database",
        lambda *_args: calls.append("create"),
    )
    monkeypatch.setattr(
        "engine.backup._run_mysql_restore",
        lambda *_args: calls.append("restore"),
    )
    monkeypatch.setattr(
        "engine.backup._validate_isolated_database",
        lambda *_args: calls.append("validate") or 4,
    )

    class Lifecycle:
        def replace(self, _previous, _current) -> None:
            calls.append("replace")

    monkeypatch.setattr(
        "engine.backup.get_datasource_resource_lifecycle",
        lambda: Lifecycle(),
    )
    operation = execute_restore(
        db_session,
        backup["id"],
        expected_datasource_generation=1,
        connection_factory=object(),  # type: ignore[arg-type]
    )

    db_session.refresh(datasource)
    assert operation.status == "success"
    assert operation.validated_table_count == 4
    assert datasource.database_name == operation.target_database_name
    assert datasource.connection_generation == 2
    assert calls == ["create", "restore", "validate", "replace"]


def test_restore_rejects_backup_after_datasource_profile_changes(
    client,
    db_session,
    monkeypatch,
) -> None:
    runtime_dir = _runtime_dir("restore-source-mismatch")
    monkeypatch.setenv("DBFOX_RUNTIME_DIR", str(runtime_dir))
    datasource = _create_mysql_datasource(db_session)
    monkeypatch.setattr("engine.backup._run_mysqldump", _write_native_dump)
    backup = client.post(
        "/api/v1/backups",
        json={"datasource_id": datasource.id},
        headers=_headers(),
    ).json()

    datasource.host = "127.0.0.2"
    datasource.connection_generation = 2
    db_session.commit()
    monkeypatch.setattr(
        "engine.backup._create_isolated_database",
        lambda *_args: pytest.fail("source mismatch must fail before creating a database"),
    )

    response = client.post(
        f"/api/v1/backups/{backup['id']}/restore",
        json={
            "expected_datasource_generation": 2,
            "confirmation": "restore-to-isolated-database",
        },
        headers=_headers(),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "BACKUP_SOURCE_MISMATCH"
    assert db_session.query(RestoreOperation).count() == 0


def test_execute_restore_failure_keeps_original_and_drops_isolated_target(
    client,
    db_session,
    monkeypatch,
) -> None:
    runtime_dir = _runtime_dir("restore-failure")
    monkeypatch.setenv("DBFOX_RUNTIME_DIR", str(runtime_dir))
    datasource = _create_mysql_datasource(db_session)
    monkeypatch.setattr("engine.backup._run_mysqldump", _write_native_dump)
    backup = client.post(
        "/api/v1/backups",
        json={"datasource_id": datasource.id},
        headers=_headers(),
    ).json()
    dropped: list[str] = []
    monkeypatch.setattr("engine.backup._create_isolated_database", lambda *_args: None)
    monkeypatch.setattr("engine.backup._run_mysql_restore", lambda *_args: None)
    monkeypatch.setattr(
        "engine.backup._validate_isolated_database",
        lambda *_args: (_ for _ in ()).throw(BackupError("failed", code="TEST_FAILURE")),
    )
    monkeypatch.setattr(
        "engine.backup._drop_isolated_database",
        lambda _factory, _profile, database: dropped.append(database),
    )

    with pytest.raises(BackupError) as exc_info:
        execute_restore(
            db_session,
            backup["id"],
            expected_datasource_generation=1,
            connection_factory=object(),  # type: ignore[arg-type]
        )
    assert exc_info.value.code == "TEST_FAILURE"
    db_session.refresh(datasource)
    assert datasource.database_name == "analytics"
    assert datasource.connection_generation == 1
    operation = db_session.query(RestoreOperation).one()
    assert operation.status == "failed"
    assert operation.error_code == "TEST_FAILURE"
    assert dropped == [operation.target_database_name]


def test_precheck_detects_tampered_managed_artifact(client, db_session, monkeypatch) -> None:
    runtime_dir = _runtime_dir("backup-tamper")
    monkeypatch.setenv("DBFOX_RUNTIME_DIR", str(runtime_dir))
    datasource = _create_mysql_datasource(db_session)
    monkeypatch.setattr("engine.backup._run_mysqldump", _write_native_dump)

    create_response = client.post(
        "/api/v1/backups",
        json={"datasource_id": datasource.id},
        headers=_headers(),
    )
    backup = create_response.json()
    _artifact_path(runtime_dir, backup["file_path"]).write_text(
        "-- MySQL dump\nCREATE TABLE users (id int, extra text);\n",
        encoding="utf-8",
    )

    response = client.post(f"/api/v1/backups/{backup['id']}/restore-precheck", headers=_headers())
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "Backup integrity verification failed." in response.json()["errors"]


def test_legacy_or_external_backup_path_is_hidden_and_rejected(client, db_session, tmp_path) -> None:
    datasource = _create_mysql_datasource(db_session)
    now = datetime.now(UTC)
    external_path = tmp_path / "contains-sensitive-data.sql"
    external_path.write_text("-- external dump", encoding="utf-8")
    record = BackupRecord(
        id="legacy-external-backup",
        project_id=DEFAULT_PROJECT_ID,
        datasource_id=datasource.id,
        backup_type="mysqldump",
        status="success",
        file_path=str(external_path),
        checksum_sha256="0" * 64,
        started_at=now,
        completed_at=now,
        created_at=now,
    )
    db_session.add(record)
    db_session.commit()

    detail_response = client.get(f"/api/v1/backups/{record.id}", headers=_headers())
    assert detail_response.status_code == 200
    assert detail_response.json()["file_path"] is None

    precheck_response = client.post(f"/api/v1/backups/{record.id}/restore-precheck", headers=_headers())
    assert precheck_response.status_code == 200
    assert precheck_response.json()["ok"] is False
    assert "managed backup artifact" in " ".join(precheck_response.json()["errors"]).lower()


def test_precheck_rejects_symlinked_managed_artifact(client, db_session, monkeypatch, tmp_path) -> None:
    runtime_dir = _runtime_dir("backup-link")
    monkeypatch.setenv("DBFOX_RUNTIME_DIR", str(runtime_dir))
    datasource = _create_mysql_datasource(db_session)
    relative_path = "default-project/backup-ds/linked.sql"
    artifact = _artifact_path(runtime_dir, relative_path)
    artifact.parent.mkdir(parents=True)
    external = tmp_path / "external.sql"
    external.write_text("-- external dump", encoding="utf-8")
    try:
        artifact.symlink_to(external)
    except OSError:
        pytest.skip("symlink creation is unavailable on this platform")

    now = datetime.now(UTC)
    db_session.add(
        BackupRecord(
            id="linked-managed-backup",
            project_id=DEFAULT_PROJECT_ID,
            datasource_id=datasource.id,
            backup_type="mysqldump",
            status="success",
            file_path=relative_path,
            checksum_sha256="0" * 64,
            started_at=now,
            completed_at=now,
            created_at=now,
        )
    )
    db_session.commit()

    response = client.post("/api/v1/backups/linked-managed-backup/restore-precheck", headers=_headers())
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "Managed backup artifact is unavailable." in response.json()["errors"]


def test_failed_backup_never_leaves_a_recoverable_artifact(client, db_session, monkeypatch) -> None:
    runtime_dir = _runtime_dir("backup-failure")
    monkeypatch.setenv("DBFOX_RUNTIME_DIR", str(runtime_dir))
    datasource = _create_mysql_datasource(db_session)

    def partial_dump(_: DataSource, output_path: Path) -> None:
        output_path.write_text("partial native dump", encoding="utf-8")
        raise BackupError("native dump error with password='secret'")

    monkeypatch.setattr("engine.backup._run_mysqldump", partial_dump)
    response = client.post("/api/v1/backups", json={"datasource_id": datasource.id}, headers=_headers())
    _assert_fixed_dbfox_error(response)
    assert "secret" not in str(response.json())

    record = db_session.query(BackupRecord).filter(BackupRecord.datasource_id == datasource.id).one()
    assert record.status == "failed"
    assert record.file_path is None
    assert record.error_message == fixed_error_message(FixedErrorCode.BACKUP_OPERATION_FAILED)
    assert list((runtime_dir / "backups").rglob("*.sql")) == []


def test_native_dump_uses_configured_absolute_client_and_minimal_environment(
    db_session,
    monkeypatch,
    tmp_path,
) -> None:
    runtime_dir = _runtime_dir("native-client")
    monkeypatch.setenv("DBFOX_RUNTIME_DIR", str(runtime_dir))
    datasource = _create_mysql_datasource(db_session)
    client_dir = tmp_path / "mysql-client"
    client_dir.mkdir()
    executable = client_dir / ("mysqldump.exe" if os.name == "nt" else "mysqldump")
    executable.write_bytes(b"placeholder")
    executable.chmod(0o700)
    monkeypatch.setenv("DBFOX_MYSQL_CLIENT_DIR", str(client_dir))

    from engine.connectivity.factory import ConnectionFactory, MySQLClientInvocation
    from engine.connectivity.profile import ConnectionPurpose

    @contextmanager
    def fake_mysql_client_scope(
        _factory: ConnectionFactory,
        _profile: object,
        *,
        purpose: ConnectionPurpose,
    ):
        assert purpose is ConnectionPurpose.BACKUP
        yield MySQLClientInvocation(
            host="127.0.0.1",
            port=3306,
            username="backup-user",
            database="analytics",
            _password="native-password",
        )

    monkeypatch.setattr(ConnectionFactory, "mysql_client_scope", fake_mysql_client_scope)

    def fake_run(command, **kwargs) -> None:
        assert command[0] == str(executable)
        assert Path(command[0]).is_absolute()
        assert "--result-file" not in " ".join(command)
        assert "native-password" not in " ".join(command)
        assert kwargs["env"] == {
            "MYSQL_PWD": "native-password",
            "PATH": str(client_dir),
            "LC_ALL": "C",
            "LANG": "C",
        }
        assert kwargs["stdin"] is not None
        assert kwargs["stderr"] is not None
        assert kwargs["text"] is False
        assert kwargs["close_fds"] is True
        kwargs["stdout"].write(b"-- MySQL dump\nCREATE TABLE users (id int);\n")

    monkeypatch.setattr("engine.backup.subprocess.run", fake_run)
    output_path = _backup_path(datasource, "12345678-1234-1234-1234-123456789abc")
    _run_mysqldump(datasource, output_path)
    assert output_path.read_text(encoding="utf-8").startswith("-- MySQL dump")


def test_native_dump_rejects_symlinked_client_before_subprocess(
    db_session,
    monkeypatch,
    tmp_path,
) -> None:
    runtime_dir = _runtime_dir("native-client-link")
    monkeypatch.setenv("DBFOX_RUNTIME_DIR", str(runtime_dir))
    datasource = _create_mysql_datasource(db_session)
    client_dir = tmp_path / "mysql-client"
    client_dir.mkdir()
    executable = client_dir / ("mysqldump.exe" if os.name == "nt" else "mysqldump")
    target = tmp_path / "untrusted-client"
    target.write_bytes(b"placeholder")
    try:
        executable.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable on this platform")
    monkeypatch.setenv("DBFOX_MYSQL_CLIENT_DIR", str(client_dir))
    monkeypatch.setattr(
        "engine.backup.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail("unsafe client must not be launched"),
    )

    output_path = _backup_path(datasource, "12345678-1234-1234-1234-123456789abc")
    with pytest.raises(BackupError) as exc_info:
        _run_mysqldump(datasource, output_path)
    assert exc_info.value.code == FixedErrorCode.BACKUP_CLIENT_NOT_FOUND.value
