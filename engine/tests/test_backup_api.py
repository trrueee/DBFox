import uuid
from pathlib import Path

from fastapi.testclient import TestClient

import pytest

from engine.crypto import encrypt_password
from engine.db import get_db
from engine.main import LOCAL_SECURE_TOKEN, app
from engine.models import DEFAULT_PROJECT_ID, DataSource


def _headers():
    return {"X-Local-Token": LOCAL_SECURE_TOKEN}


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _create_mysql_datasource(db_session) -> DataSource:
    cipher, nonce = encrypt_password("secret")
    ds = DataSource(
        id="backup-ds",
        project_id=DEFAULT_PROJECT_ID,
        name="backup_test",
        host="127.0.0.1",
        port=3306,
        database_name="analytics",
        username="readonly",
        password_ciphertext=cipher,
        password_nonce=nonce,
        status="active",
    )
    db_session.add(ds)
    db_session.commit()
    return ds


def test_create_list_and_precheck_backup(client, db_session, monkeypatch) -> None:
    runtime_dir = Path("D:/Project/DataBox/.databox_runtime/test_backup_runtime") / str(uuid.uuid4())
    runtime_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABOX_RUNTIME_DIR", str(runtime_dir))
    datasource = _create_mysql_datasource(db_session)

    def fake_dump(ds: DataSource, output_path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("-- MySQL dump\nCREATE TABLE users (id int);\n", encoding="utf-8")

    monkeypatch.setattr("engine.backup._run_mysqldump", fake_dump)

    resp = client.post(
        "/api/v1/backups",
        json={"datasource_id": datasource.id, "label": "before migration"},
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.json()
    backup = resp.json()
    assert backup["status"] == "success"
    assert backup["label"] == "before migration"
    assert backup["file_size_bytes"] > 0
    assert backup["checksum_sha256"]

    resp = client.get(f"/api/v1/projects/{DEFAULT_PROJECT_ID}/backups", headers=_headers())
    assert resp.status_code == 200
    backups = resp.json()
    assert len(backups) == 1
    assert backups[0]["id"] == backup["id"]

    resp = client.post(f"/api/v1/backups/{backup['id']}/restore-precheck", headers=_headers())
    assert resp.status_code == 200
    precheck = resp.json()
    assert precheck["ok"] is True
    assert precheck["errors"] == []


def test_backup_rejects_builtin_mock_demo_datasource(client, db_session) -> None:
    cipher, nonce = encrypt_password("demo")
    ds = DataSource(
        id="mock-demo-ds",
        project_id=DEFAULT_PROJECT_ID,
        name="mock_demo",
        host="demo",
        port=3306,
        database_name="demo_shop",
        username="demo",
        password_ciphertext=cipher,
        password_nonce=nonce,
        status="active",
    )
    db_session.add(ds)
    db_session.commit()

    resp = client.post(
        "/api/v1/backups",
        json={"datasource_id": ds.id},
        headers=_headers(),
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "BACKUP_UNSUPPORTED_DATASOURCE"


def test_execute_restore_endpoints(client, db_session, monkeypatch) -> None:
    runtime_dir = Path("D:/Project/DataBox/.databox_runtime/test_restore_runtime") / str(uuid.uuid4())
    runtime_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABOX_RUNTIME_DIR", str(runtime_dir))
    datasource = _create_mysql_datasource(db_session)

    # 1. Mock mysqldump
    def fake_dump(ds: DataSource, output_path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("-- MySQL dump\nCREATE TABLE users (id int);\n", encoding="utf-8")

    monkeypatch.setattr("engine.backup._run_mysqldump", fake_dump)

    # 2. Mock mysql restore
    restore_called = False
    def fake_restore(ds: DataSource, sql_file_path: Path) -> None:
        nonlocal restore_called
        restore_called = True
        assert sql_file_path.exists()

    monkeypatch.setattr("engine.backup._run_mysql_restore", fake_restore)

    # Create backup record
    resp = client.post(
        "/api/v1/backups",
        json={"datasource_id": datasource.id, "label": "to restore"},
        headers=_headers(),
    )
    assert resp.status_code == 200
    backup = resp.json()
    assert backup["status"] == "success"

    # Test Restore
    resp = client.post(f"/api/v1/backups/{backup['id']}/restore", headers=_headers())
    assert resp.status_code == 200, resp.json()
    res = resp.json()
    assert res["success"] is True
    assert restore_called is True

    # Test Read-Only protection
    datasource.is_read_only = True
    db_session.add(datasource)
    db_session.commit()

    resp = client.post(f"/api/v1/backups/{backup['id']}/restore", headers=_headers())
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "RESTORE_READONLY_ERROR"


def test_restore_anti_tamper_checksum_failure(client, db_session, monkeypatch) -> None:
    runtime_dir = Path("D:/Project/DataBox/.databox_runtime/test_restore_anti_tamper") / str(uuid.uuid4())
    runtime_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABOX_RUNTIME_DIR", str(runtime_dir))
    datasource = _create_mysql_datasource(db_session)

    # 1. Mock mysqldump
    def fake_dump(ds: DataSource, output_path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("-- MySQL dump\nCREATE TABLE users (id int);\n", encoding="utf-8")

    monkeypatch.setattr("engine.backup._run_mysqldump", fake_dump)

    # Create backup record
    resp = client.post(
        "/api/v1/backups",
        json={"datasource_id": datasource.id, "label": "to tamper"},
        headers=_headers(),
    )
    assert resp.status_code == 200
    backup = resp.json()
    assert backup["status"] == "success"

    # Now tamper with the file contents
    file_path = Path(backup["file_path"])
    file_path.write_text("-- MySQL dump (Tampereeeeeeed)\nCREATE TABLE users (id int, extra text);\n", encoding="utf-8")

    # Verify that restore fails due to checksum verification mismatch!
    resp = client.post(f"/api/v1/backups/{backup['id']}/restore", headers=_headers())
    assert resp.status_code == 400
    assert "tampered" in resp.json()["detail"]["message"]
    assert resp.json()["detail"]["code"] == "RESTORE_PRECHECK_FAILED"


def test_backup_strict_mode_missing_tool(client, db_session, monkeypatch) -> None:
    runtime_dir = Path("D:/Project/DataBox/.databox_runtime/test_backup_strict") / str(uuid.uuid4())
    runtime_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABOX_RUNTIME_DIR", str(runtime_dir))
    datasource = _create_mysql_datasource(db_session)

    # Mock _run_mysqldump to raise FileNotFoundError to simulate missing binary
    from engine.backup import BackupError
    def fake_dump_missing(ds: DataSource, output_path) -> None:
        raise BackupError("mysqldump was not found. Please install MySQL client tools and ensure mysqldump is in PATH.")

    monkeypatch.setattr("engine.backup._run_mysqldump", fake_dump_missing)

    # Under strict mode (allow_fallback=False), backup must fail directly!
    resp = client.post(
        "/api/v1/backups",
        json={"datasource_id": datasource.id, "allow_fallback": False},
        headers=_headers(),
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "MYSQLDUMP_NOT_FOUND"


def test_restore_strict_mode_missing_tool(client, db_session, monkeypatch) -> None:
    runtime_dir = Path("D:/Project/DataBox/.databox_runtime/test_restore_strict") / str(uuid.uuid4())
    runtime_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABOX_RUNTIME_DIR", str(runtime_dir))
    datasource = _create_mysql_datasource(db_session)

    def fake_dump(ds: DataSource, output_path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("-- MySQL dump\nCREATE TABLE users (id int);\n", encoding="utf-8")

    monkeypatch.setattr("engine.backup._run_mysqldump", fake_dump)

    # Create backup record
    resp = client.post(
        "/api/v1/backups",
        json={"datasource_id": datasource.id},
        headers=_headers(),
    )
    assert resp.status_code == 200
    backup = resp.json()

    # Mock _run_mysql_restore to simulate missing mysql binary
    from engine.backup import BackupError
    def fake_restore_missing(ds: DataSource, sql_file_path: Path) -> None:
        raise BackupError("mysql client command was not found. Please install MySQL client tools and ensure mysql is in PATH.")

    monkeypatch.setattr("engine.backup._run_mysql_restore", fake_restore_missing)

    # Under strict mode, restore must fail directly without fallback!
    resp = client.post(f"/api/v1/backups/{backup['id']}/restore?allow_fallback=false", headers=_headers())
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "MYSQL_CLIENT_NOT_FOUND"


def test_restore_env_mismatch_protection(client, db_session, monkeypatch) -> None:
    runtime_dir = Path("D:/Project/DataBox/.databox_runtime/test_restore_env_mismatch") / str(uuid.uuid4())
    runtime_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABOX_RUNTIME_DIR", str(runtime_dir))
    
    # 1. Create a dev datasource and backup
    datasource = _create_mysql_datasource(db_session)
    datasource.env = "dev"
    datasource.environment_id = "env-dev"
    db_session.add(datasource)
    db_session.commit()

    def fake_dump(ds: DataSource, output_path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("-- MySQL dump\nCREATE TABLE users (id int);\n", encoding="utf-8")

    monkeypatch.setattr("engine.backup._run_mysqldump", fake_dump)

    resp = client.post(
        "/api/v1/backups",
        json={"datasource_id": datasource.id},
        headers=_headers(),
    )
    assert resp.status_code == 200
    backup = resp.json()

    # 2. Make the datasource environment 'staging' and change environment_id to mismatch
    datasource.env = "staging"
    datasource.environment_id = "env-staging"
    db_session.add(datasource)
    db_session.commit()

    # Restore must fail due to environment tier mismatch safety guardrail!
    resp = client.post(f"/api/v1/backups/{backup['id']}/restore", headers=_headers())
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "RESTORE_ENV_MISMATCH"

