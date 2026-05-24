import uuid
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from engine.db import get_db
from engine.main import LOCAL_SECURE_TOKEN, app
from engine.models import DataSource, BackupRecord

@pytest.fixture(autouse=True)
def run_without_bypass():
    old_bypass = os.environ.get("DATABOX_BYPASS_CONFIRMATION")
    old_testing = os.environ.get("DATABOX_TESTING")
    os.environ["DATABOX_BYPASS_CONFIRMATION"] = "0"
    os.environ["DATABOX_TESTING"] = "1"
    yield
    if old_bypass is not None:
        os.environ["DATABOX_BYPASS_CONFIRMATION"] = old_bypass
    else:
        del os.environ["DATABOX_BYPASS_CONFIRMATION"]
    if old_testing is not None:
        os.environ["DATABOX_TESTING"] = old_testing
    else:
        del os.environ["DATABOX_TESTING"]

def _headers() -> dict[str, str]:
    return {"X-Local-Token": LOCAL_SECURE_TOKEN}

def test_two_phase_ddl_execution_flow(db_session, demo_datasource) -> None:
    def override_get_db():
        yield db_session

    tbl_name = f"confirm_table_{uuid.uuid4().hex[:8]}"
    ddl = f"CREATE TABLE `{tbl_name}` (`id` INT PRIMARY KEY);"
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            # Phase 1: Call without token
            resp = client.post(
                "/api/v1/schema/design/execute-ddl",
                headers=_headers(),
                json={
                    "datasource_id": demo_datasource.id,
                    "ddl": ddl
                }
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["requires_confirmation"] is True
            assert "confirm_token" in data
            token = data["confirm_token"]

            # Failure check: Call with invalid confirmation text
            resp_fail = client.post(
                "/api/v1/schema/design/execute-ddl",
                headers=_headers(),
                json={
                    "datasource_id": demo_datasource.id,
                    "ddl": ddl,
                    "confirm_token": token,
                    "confirm_text": "WRONG_DB_NAME"
                }
            )
            assert resp_fail.status_code == 400
            assert "二次确认文本不匹配" in resp_fail.json()["detail"]["message"]

            # Token is single use, so we get a new one for Phase 2
            resp_new = client.post(
                "/api/v1/schema/design/execute-ddl",
                headers=_headers(),
                json={
                    "datasource_id": demo_datasource.id,
                    "ddl": ddl
                }
            )
            token_new = resp_new.json()["confirm_token"]

            # Phase 2: Call with correct confirmation text (datasource name)
            resp_ok = client.post(
                "/api/v1/schema/design/execute-ddl",
                headers=_headers(),
                json={
                    "datasource_id": demo_datasource.id,
                    "ddl": ddl,
                    "confirm_token": token_new,
                    "confirm_text": demo_datasource.name
                }
            )
            assert resp_ok.status_code == 200
            assert resp_ok.json()["success"] is True
    finally:
        app.dependency_overrides.clear()


def test_two_phase_generate_test_data_flow(db_session) -> None:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            # 1. Setup a mockup database datasource
            resp = client.post("/api/v1/datasources", json={
                "name": "test_data_source",
                "host": "demo",
                "port": 3306,
                "database_name": "demo_shop",
                "username": "demo",
                "password": "demo",
            }, headers=_headers())
            assert resp.status_code == 200
            ds_data = resp.json()
            ds_id = ds_data["id"]
            ds_name = ds_data["name"]

            # 2. Sync to populate the metastore
            sync_resp = client.post(f"/api/v1/datasources/{ds_id}/sync", headers=_headers())
            assert sync_resp.status_code == 200

            # Phase 1: Call without token
            resp_data = client.post(
                "/api/v1/schema/generate-test-data",
                headers=_headers(),
                json={
                    "datasource_id": ds_id,
                    "table_name": "users",
                    "row_count": 5
                }
            )
            assert resp_data.status_code == 200
            data = resp_data.json()
            assert data["requires_confirmation"] is True
            assert "confirm_token" in data
            token = data["confirm_token"]

            # Phase 2: Call with correct confirmation text
            resp_ok = client.post(
                "/api/v1/schema/generate-test-data",
                headers=_headers(),
                json={
                    "datasource_id": ds_id,
                    "table_name": "users",
                    "row_count": 5,
                    "confirm_token": token,
                    "confirm_text": ds_name
                }
            )
            assert resp_ok.status_code == 200
            assert resp_ok.json()["success"] is True
    finally:
        app.dependency_overrides.clear()


def test_two_phase_restore_backup_flow(db_session, monkeypatch) -> None:
    def override_get_db():
        yield db_session

    from engine.crypto import encrypt_password
    from engine.models import DEFAULT_PROJECT_ID

    runtime_dir = Path("D:/Project/DataBox/.databox_runtime/test_restore_runtime_confirm") / str(uuid.uuid4())
    runtime_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABOX_RUNTIME_DIR", str(runtime_dir))

    # Create MySQL datasource
    cipher, nonce = encrypt_password("secret")
    datasource = DataSource(
        id="backup-ds-confirm",
        project_id=DEFAULT_PROJECT_ID,
        name="backup_test_confirm",
        host="127.0.0.1",
        port=3306,
        database_name="analytics",
        username="readonly",
        password_ciphertext=cipher,
        password_nonce=nonce,
        status="active",
    )
    db_session.add(datasource)
    db_session.commit()

    # Mock mysqldump
    def fake_dump(ds: DataSource, output_path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("-- MySQL dump\nCREATE TABLE users (id int);\n", encoding="utf-8")

    monkeypatch.setattr("engine.backup._run_mysqldump", fake_dump)

    # Mock mysql restore
    restore_called = False
    def fake_restore(ds: DataSource, sql_file_path: Path) -> None:
        nonlocal restore_called
        restore_called = True
        assert sql_file_path.exists()

    monkeypatch.setattr("engine.backup._run_mysql_restore", fake_restore)

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            # Create backup record
            resp = client.post(
                "/api/v1/backups",
                json={"datasource_id": datasource.id, "label": "to restore"},
                headers=_headers(),
            )
            assert resp.status_code == 200
            backup = resp.json()
            assert backup["status"] == "success"

            # Phase 1: Call without token
            resp_restore = client.post(
                f"/api/v1/backups/{backup['id']}/restore",
                headers=_headers()
            )
            assert resp_restore.status_code == 200
            data = resp_restore.json()
            assert data["requires_confirmation"] is True
            assert "confirm_token" in data
            token = data["confirm_token"]

            # Phase 2: Call with correct confirmation text
            resp_ok = client.post(
                f"/api/v1/backups/{backup['id']}/restore?confirm_token={token}&confirm_text={datasource.name}",
                headers=_headers()
            )
            assert resp_ok.status_code == 200
            assert resp_ok.json()["success"] is True
            assert restore_called is True
    finally:
        app.dependency_overrides.clear()


def test_two_phase_delete_datasource_flow(db_session, demo_datasource) -> None:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            # Phase 1: Call without token
            resp = client.delete(
                f"/api/v1/datasources/{demo_datasource.id}",
                headers=_headers()
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["requires_confirmation"] is True
            assert "confirm_token" in data
            token = data["confirm_token"]

            # Phase 2: Call with correct confirmation text
            resp_ok = client.delete(
                f"/api/v1/datasources/{demo_datasource.id}?confirm_token={token}&confirm_text={demo_datasource.name}",
                headers=_headers()
            )
            assert resp_ok.status_code == 200
            assert resp_ok.json()["success"] is True
    finally:
        app.dependency_overrides.clear()


# =====================================================================
# CONTEXT TAMPERING & SWAPPING SECURITY TESTS (Sprint 1 / P1-4)
# =====================================================================

def test_tampering_ddl_swapping_fails(db_session, demo_datasource) -> None:
    """Security: Token A requested for DDL A, but Phase 2 attempts execution with DDL B. Must fail."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            # Get token for DDL A
            resp = client.post(
                "/api/v1/schema/design/execute-ddl",
                headers=_headers(),
                json={
                    "datasource_id": demo_datasource.id,
                    "ddl": "CREATE TABLE tbl_a (id INT);"
                }
            )
            token = resp.json()["confirm_token"]

            # Try to execute DDL B using token for DDL A
            resp_tampered = client.post(
                "/api/v1/schema/design/execute-ddl",
                headers=_headers(),
                json={
                    "datasource_id": demo_datasource.id,
                    "ddl": "CREATE TABLE tbl_b (id INT);",  # TAMPERED
                    "confirm_token": token,
                    "confirm_text": demo_datasource.name
                }
            )
            assert resp_tampered.status_code == 400
            assert "二次确认参数" in resp_tampered.json()["detail"]["message"]
            assert "ddl_hash" in resp_tampered.json()["detail"]["message"]
    finally:
        app.dependency_overrides.clear()


def test_tampering_datasource_swapping_fails(db_session, demo_datasource) -> None:
    """Security: Token A requested for datasource A, but Phase 2 attempts to apply to datasource B. Must fail."""
    def override_get_db():
        yield db_session

    # Create a second datasource
    ds2 = DataSource(
        id=str(uuid.uuid4()),
        name="another_datasource",
        host="demo",
        port=3306,
        database_name="demo_shop",
        username="demo",
        password_ciphertext="test",
        password_nonce="test",
        status="active",
    )
    db_session.add(ds2)
    db_session.commit()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            # Get token for datasource 1
            resp = client.post(
                "/api/v1/schema/design/execute-ddl",
                headers=_headers(),
                json={
                    "datasource_id": demo_datasource.id,
                    "ddl": "CREATE TABLE tbl_a (id INT);"
                }
            )
            token = resp.json()["confirm_token"]

            # Try to execute on datasource 2 using token for datasource 1
            resp_tampered = client.post(
                "/api/v1/schema/design/execute-ddl",
                headers=_headers(),
                json={
                    "datasource_id": ds2.id,  # TAMPERED
                    "ddl": "CREATE TABLE tbl_a (id INT);",
                    "confirm_token": token,
                    "confirm_text": ds2.name
                }
            )
            assert resp_tampered.status_code == 400
            assert "二次确认数据源不匹配" in resp_tampered.json()["detail"]["message"]
    finally:
        app.dependency_overrides.clear()


def test_tampering_action_swapping_fails(db_session, demo_datasource) -> None:
    """Security: Token requested for generate_test_data, but Phase 2 attempts to use it for execute_ddl. Must fail."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            # 1. Setup datasource and sync it
            resp_ds = client.post("/api/v1/datasources", json={
                "name": "test_swap_action_ds",
                "host": "demo",
                "port": 3306,
                "database_name": "demo_shop",
                "username": "demo",
                "password": "demo",
            }, headers=_headers())
            ds_data = resp_ds.json()
            ds_id = ds_data["id"]

            sync_resp = client.post(f"/api/v1/datasources/{ds_id}/sync", headers=_headers())
            assert sync_resp.status_code == 200

            # 2. Get confirmation token for generating test data
            resp_data = client.post(
                "/api/v1/schema/generate-test-data",
                headers=_headers(),
                json={
                    "datasource_id": ds_id,
                    "table_name": "users",
                    "row_count": 5
                }
            )
            token = resp_data.json()["confirm_token"]

            # 3. Try to use this token to execute a dangerous DDL command
            resp_tampered = client.post(
                "/api/v1/schema/design/execute-ddl",
                headers=_headers(),
                json={
                    "datasource_id": ds_id,
                    "ddl": "DROP TABLE users;",  # DANGEROUS DDL
                    "confirm_token": token,
                    "confirm_text": ds_data["name"]
                }
            )
            assert resp_tampered.status_code == 400
            assert "二次确认操作类型不匹配" in resp_tampered.json()["detail"]["message"]
    finally:
        app.dependency_overrides.clear()


def test_tampering_test_data_params_swapping_fails(db_session) -> None:
    """Security: Token A requested for generating 5 rows, but Phase 2 attempts to generate 100000 rows. Must fail."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            # 1. Setup datasource and sync it
            resp_ds = client.post("/api/v1/datasources", json={
                "name": "test_param_swap_ds",
                "host": "demo",
                "port": 3306,
                "database_name": "demo_shop",
                "username": "demo",
                "password": "demo",
            }, headers=_headers())
            ds_data = resp_ds.json()
            ds_id = ds_data["id"]

            sync_resp = client.post(f"/api/v1/datasources/{ds_id}/sync", headers=_headers())
            assert sync_resp.status_code == 200

            # 2. Get token for 5 rows
            resp_data = client.post(
                "/api/v1/schema/generate-test-data",
                headers=_headers(),
                json={
                    "datasource_id": ds_id,
                    "table_name": "users",
                    "row_count": 5
                }
            )
            token = resp_data.json()["confirm_token"]

            # 3. Try to execute Phase 2 with 100000 rows
            resp_tampered = client.post(
                "/api/v1/schema/generate-test-data",
                headers=_headers(),
                json={
                    "datasource_id": ds_id,
                    "table_name": "users",
                    "row_count": 100000,  # TAMPERED
                    "confirm_token": token,
                    "confirm_text": ds_data["name"]
                }
            )
            assert resp_tampered.status_code == 400
            assert "二次确认参数" in resp_tampered.json()["detail"]["message"]
            assert "row_count" in resp_tampered.json()["detail"]["message"]
    finally:
        app.dependency_overrides.clear()


# =====================================================================
# BYPASS SECURITY BOUNDARY TESTS (Sprint 1 / P1-3)
# =====================================================================

def test_confirmation_bypass_disabled_when_frozen(monkeypatch) -> None:
    """Security: bypass must be completely blocked in packaged/frozen desktop builds."""
    import sys
    from engine.policy.confirmation import confirmation_bypass_enabled
    monkeypatch.setenv("DATABOX_BYPASS_CONFIRMATION", "1")
    monkeypatch.setenv("DATABOX_TESTING", "1")
    # setattr with raising=False: monkeypatch will delete the attr on teardown only if it didn't pre-exist
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert confirmation_bypass_enabled() is False
    # Manually remove before monkeypatch teardown to avoid AttributeError on sys.frozen deletion
    if hasattr(sys, "frozen"):
        monkeypatch.delattr(sys, "frozen", raising=False)


def test_confirmation_bypass_disabled_without_testing_flag(monkeypatch) -> None:
    """Security: bypass must not work when DATABOX_TESTING env is absent."""
    from engine.policy.confirmation import confirmation_bypass_enabled
    monkeypatch.setenv("DATABOX_BYPASS_CONFIRMATION", "1")
    monkeypatch.delenv("DATABOX_TESTING", raising=False)
    assert confirmation_bypass_enabled() is False


def test_confirmation_bypass_disabled_when_only_bypass_set(monkeypatch) -> None:
    """Security: setting only DATABOX_BYPASS_CONFIRMATION without DATABOX_TESTING is not enough."""
    from engine.policy.confirmation import confirmation_bypass_enabled
    monkeypatch.setenv("DATABOX_BYPASS_CONFIRMATION", "1")
    monkeypatch.delenv("DATABOX_TESTING", raising=False)
    assert confirmation_bypass_enabled() is False


def test_confirmation_token_single_use() -> None:
    """Security: a consumed token cannot be reused even with valid confirm_text."""
    from engine.policy.confirmation import ConfirmationManager
    mgr = ConfirmationManager(ttl_seconds=60)
    token = mgr.create_confirmation(
        datasource_id="ds-1",
        action="delete_datasource",
        details={"datasource_id": "ds-1"},
        expected_confirm_text="my_db"
    )
    # First consumption succeeds
    ok, err = mgr.validate_and_consume(
        token, "my_db",
        expected_action="delete_datasource",
        expected_datasource_id="ds-1",
        expected_details={"datasource_id": "ds-1"}
    )
    assert ok is True
    assert err == ""

    # Second attempt with the same token must fail (token was consumed)
    ok2, err2 = mgr.validate_and_consume(
        token, "my_db",
        expected_action="delete_datasource",
        expected_datasource_id="ds-1",
        expected_details={"datasource_id": "ds-1"}
    )
    assert ok2 is False
    assert "无效或已过期" in err2


def test_confirmation_token_confirm_text_whitespace_trim() -> None:
    """confirm_text with surrounding whitespace should still match (strip both sides)."""
    from engine.policy.confirmation import ConfirmationManager
    mgr = ConfirmationManager(ttl_seconds=60)
    token = mgr.create_confirmation(
        datasource_id="ds-1",
        action="delete_datasource",
        details={"datasource_id": "ds-1"},
        expected_confirm_text="my_db"
    )
    ok, err = mgr.validate_and_consume(
        "  " + token.strip() + "  " if False else token,
        "  my_db  ",   # whitespace around confirm_text
        expected_action="delete_datasource",
        expected_datasource_id="ds-1",
        expected_details={"datasource_id": "ds-1"}
    )
    assert ok is True

