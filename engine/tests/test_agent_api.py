import json
import asyncio
from datetime import UTC, datetime

import pytest
from unittest.mock import MagicMock

import engine.api.agent as agent_module
from fastapi import HTTPException

from engine.agent_core.types import AgentResumeRequest, AgentRunRequest, AgentRuntimeEvent
from engine.api.agent import ResultPageRequest, sse_failed_event
from engine.datasource import datasource_connection_dict
from engine.projects.service import resolve_project_id, get_or_create_default_project, Project
from engine.models import DEFAULT_PROJECT_ID, AgentArtifactRecord, AgentRun, AgentSession, DataSource


def _add_pagination_source(db_session, *, safe_sql: str = "SELECT id, amount FROM orders") -> None:
    now = datetime.now(UTC)
    datasource = DataSource(
        id="ds-page",
        name="Page DS",
        db_type="mysql",
        host="localhost",
        port=3306,
        database_name="dbfox",
        username="root",
        password_ciphertext="cipher",
        password_nonce="nonce",
    )
    session = AgentSession(
        id="conv-page",
        datasource_id="ds-page",
        title="Page",
        context_tables_json="[]",
        created_at=now,
        updated_at=now,
    )
    run = AgentRun(
        id="run-page",
        session_id="conv-page",
        datasource_id="ds-page",
        question="Orders",
        status="completed",
        created_at=now,
        updated_at=now,
    )
    artifact = AgentArtifactRecord(
        id="artifact-result-page",
        run_id="run-page",
        session_id="conv-page",
        semantic_id="result_view_1",
        type="result_view",
        title="Orders result",
        payload_json=json.dumps(
            {
                "safeSql": safe_sql,
                "columns": ["id", "amount"],
                "storageMode": "sql_backed",
            }
        ),
        presentation_json=json.dumps({"mode": "both", "priority": 1, "collapsed": False}),
        depends_on_json=json.dumps(["sql_candidate"]),
        status="completed",
        sequence=1,
        created_at=now,
    )
    db_session.add_all([datasource, session, run, artifact])
    db_session.commit()


def test_result_page_rejects_safe_sql_that_differs_from_source_artifact(db_session):
    _add_pagination_source(db_session)

    with pytest.raises(HTTPException) as exc_info:
        agent_module.api_agent_result_page(
            ResultPageRequest(
                datasourceId="ds-page",
                sourceSqlArtifactId="artifact-result-page",
                safeSql="SELECT id FROM users",
                page=1,
                pageSize=20,
            ),
            db_session,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "SOURCE_SQL_MISMATCH"


def test_result_page_uses_persisted_safe_sql_for_derived_query(monkeypatch, db_session):
    _add_pagination_source(db_session)
    executed_sql: dict[str, str] = {}

    def fake_execute_query(_db, datasource_id, sql, safety_decision):
        executed_sql["datasource_id"] = datasource_id
        executed_sql["sql"] = sql
        assert safety_decision.can_execute is True
        return {
            "columns": ["id", "amount"],
            "rows": [{"id": 1, "amount": 20}],
            "latencyMs": 3,
            "warnings": [],
            "notices": [],
        }

    monkeypatch.setattr("engine.sql.executor.execute_query", fake_execute_query)

    response = agent_module.api_agent_result_page(
        ResultPageRequest(
            datasourceId="ds-page",
            sourceSqlArtifactId="artifact-result-page",
            safeSql="SELECT id, amount FROM orders",
            page=1,
            pageSize=20,
            sort=[agent_module.ResultSort(column="id", direction="desc")],
        ),
        db_session,
    )

    assert response.columns == ["id", "amount"]
    assert response.rows == [{"id": 1, "amount": 20}]
    assert response.hasNextPage is False
    assert "orders" in executed_sql["sql"]
    assert "LIMIT" in executed_sql["sql"].upper()


def test_result_page_rejects_persisted_non_select_source_sql(db_session):
    _add_pagination_source(db_session, safe_sql="DELETE FROM orders")

    with pytest.raises(HTTPException) as exc_info:
        agent_module.api_agent_result_page(
            ResultPageRequest(
                datasourceId="ds-page",
                sourceSqlArtifactId="artifact-result-page",
                safeSql="DELETE FROM orders",
                page=1,
                pageSize=20,
            ),
            db_session,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "SOURCE_SQL_VALIDATION_FAILED"


def test_sse_failed_event() -> None:
    event_str = sse_failed_event("evt_123", "run_456", "Test error message", "ERR_CODE")
    assert event_str.startswith("event: agent.run.failed\n")
    
    lines = event_str.strip().split("\n")
    assert len(lines) >= 2
    assert lines[0] == "event: agent.run.failed"
    assert lines[1].startswith("data: ")
    
    data_json = lines[1][6:]
    payload = json.loads(data_json)
    assert payload["event_id"] == "evt_123"
    assert payload["run_id"] == "run_456"
    assert payload["error"] == "Test error message"
    assert payload["code"] == "ERR_CODE"
    assert payload["type"] == "agent.run.failed"


def test_api_agent_run_rolls_back_db_session_on_unhandled_exception(monkeypatch) -> None:
    class FakeDb:
        def __init__(self) -> None:
            self.rollback_calls = 0

        def rollback(self) -> None:
            self.rollback_calls += 1

    class FakeRuntime:
        def __init__(self, _db) -> None:
            pass

        def run(self, _req: AgentRunRequest) -> None:
            raise RuntimeError("boom")

    fake_db = FakeDb()
    monkeypatch.setattr(agent_module, "DBFoxAgentRuntime", FakeRuntime)

    with pytest.raises(HTTPException) as exc_info:
        agent_module.api_agent_run(
            AgentRunRequest(datasource_id="ds-1", question="hello", api_key="test-key"),
            fake_db,  # type: ignore[arg-type]
        )

    assert fake_db.rollback_calls == 1
    assert exc_info.value.status_code == 500


async def _streaming_response_text(response) -> str:
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk))
    return "".join(chunks)


def test_api_agent_run_stream_rolls_back_db_session_on_unhandled_exception(monkeypatch) -> None:
    class FakeDb:
        def __init__(self) -> None:
            self.rollback_calls = 0

        def rollback(self) -> None:
            self.rollback_calls += 1

    class FakeRuntime:
        def __init__(self, _db) -> None:
            pass

        def run_iter(self, _req: AgentRunRequest):
            raise RuntimeError("stream boom")
            yield  # pragma: no cover

    fake_db = FakeDb()
    monkeypatch.setattr(agent_module, "DBFoxAgentRuntime", FakeRuntime)

    response = agent_module.api_agent_run_stream(
        AgentRunRequest(datasource_id="ds-1", question="hello", api_key="test-key"),
        fake_db,  # type: ignore[arg-type]
    )
    body = asyncio.run(_streaming_response_text(response))

    assert fake_db.rollback_calls == 1
    assert "AGENT_RUNTIME_ERROR" in body


def test_api_agent_run_stream_includes_conversation_message_ids(monkeypatch) -> None:
    class FakeDb:
        def rollback(self) -> None:
            pass

    class FakeRuntime:
        def __init__(self, _db) -> None:
            pass

        def run_iter(self, _req: AgentRunRequest):
            yield AgentRuntimeEvent(
                event_id="evt-1",
                run_id="run-1",
                sequence=1,
                created_at_ms=1,
                type="agent.run.started",
            )

    monkeypatch.setattr(agent_module, "DBFoxAgentRuntime", FakeRuntime)
    response = agent_module.api_agent_run_stream(
        AgentRunRequest(
            datasource_id="ds-1",
            question="hello",
            session_id="conv-1",
            conversation_id="conv-1",
            user_message_id="msg-user-1",
            assistant_message_id="msg-assistant-1",
            api_key="test-key",
        ),
        FakeDb(),  # type: ignore[arg-type]
    )
    body = asyncio.run(_streaming_response_text(response))
    data_line = next(line for line in body.splitlines() if line.startswith("data: "))
    payload = json.loads(data_line[6:])

    assert payload["conversation_id"] == "conv-1"
    assert payload["user_message_id"] == "msg-user-1"
    assert payload["assistant_message_id"] == "msg-assistant-1"
    assert payload["message_id"] == "msg-assistant-1"


def test_api_agent_resume_stream_rolls_back_db_session_on_unhandled_exception(monkeypatch) -> None:
    class FakeDb:
        def __init__(self) -> None:
            self.rollback_calls = 0

        def rollback(self) -> None:
            self.rollback_calls += 1

    class FakeRuntime:
        def __init__(self, _db) -> None:
            pass

        def resume_iter(self, _run_id: str, _approval_id: str | None = None):
            raise RuntimeError("resume boom")
            yield  # pragma: no cover

    fake_db = FakeDb()
    monkeypatch.setattr(agent_module, "DBFoxAgentRuntime", FakeRuntime)

    response = agent_module.api_agent_run_resume_stream(
        "run-1",
        AgentResumeRequest(approval_id="approval-1"),
        fake_db,  # type: ignore[arg-type]
    )
    body = asyncio.run(_streaming_response_text(response))

    assert fake_db.rollback_calls == 1
    assert "AGENT_RESUME_ERROR" in body


def test_datasource_connection_dict() -> None:
    mock_ds = MagicMock()
    mock_ds.id = "ds_123"
    mock_ds.host = "localhost"
    mock_ds.port = 3306
    mock_ds.username = "root"
    mock_ds.database_name = "testdb"
    mock_ds.password_ciphertext = "pass_cipher"
    mock_ds.password_nonce = "pass_nonce"
    mock_ds.ssh_enabled = True
    mock_ds.ssh_host = "jump"
    mock_ds.ssh_port = 22
    mock_ds.ssh_username = "sshuser"
    mock_ds.ssh_password_ciphertext = "ssh_pass_cipher"
    mock_ds.ssh_password_nonce = "ssh_pass_nonce"
    mock_ds.ssh_pkey_path = "/path/to/key"
    mock_ds.ssh_pkey_passphrase_ciphertext = "pkey_cipher"
    mock_ds.ssh_pkey_passphrase_nonce = "pkey_nonce"
    mock_ds.ssl_enabled = True
    mock_ds.ssl_ca_path = "/path/to/ca"
    mock_ds.ssl_cert_path = "/path/to/cert"
    mock_ds.ssl_key_path = "/path/to/key"
    mock_ds.ssl_verify_identity = True

    config = datasource_connection_dict(mock_ds)
    assert config["id"] == "ds_123"
    assert config["host"] == "localhost"
    assert config["port"] == 3306
    assert config["username"] == "root"
    assert config["database_name"] == "testdb"
    assert config["password_ciphertext"] == "pass_cipher"
    assert config["password_nonce"] == "pass_nonce"
    assert config["ssh_enabled"] is True
    assert config["ssh_host"] == "jump"
    assert config["ssh_port"] == 22
    assert config["ssh_username"] == "sshuser"
    assert config["ssh_password_ciphertext"] == "ssh_pass_cipher"
    assert config["ssh_password_nonce"] == "ssh_pass_nonce"
    assert config["ssh_pkey_path"] == "/path/to/key"
    assert config["ssh_pkey_passphrase_ciphertext"] == "pkey_cipher"
    assert config["ssh_pkey_passphrase_nonce"] == "pkey_nonce"
    assert config["ssl_enabled"] is True
    assert config["ssl_ca_path"] == "/path/to/ca"
    assert config["ssl_cert_path"] == "/path/to/cert"
    assert config["ssl_key_path"] == "/path/to/key"
    assert config["ssl_verify_identity"] is True


def test_project_id_resolution_fallback(db_session) -> None:
    # Test fallback to default project when project_id is None or empty or DEFAULT_PROJECT_ID
    pid1 = resolve_project_id(db_session, None)
    pid2 = resolve_project_id(db_session, "")
    pid3 = resolve_project_id(db_session, DEFAULT_PROJECT_ID)
    
    assert pid1 == DEFAULT_PROJECT_ID
    assert pid2 == DEFAULT_PROJECT_ID
    assert pid3 == DEFAULT_PROJECT_ID
    
    # Verify default project actually exists in db
    proj = db_session.query(Project).filter(Project.id == DEFAULT_PROJECT_ID).first()
    assert proj is not None
    assert proj.status == "active"
