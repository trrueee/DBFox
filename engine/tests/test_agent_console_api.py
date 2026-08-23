import json
import logging

import pytest
from fastapi import HTTPException

import engine.agent.console as console_module
import engine.api.agent as agent_module
from engine.agent.resource_refs import load_resource_refs
from engine.models import (
    AgentArtifactRecord,
    AgentEventRecord,
    AgentRun,
    AgentSessionInput,
    AgentSessionMemory,
    DataSource,
)
from dlcs.dbfox_data.backend.sql.safety_contracts import ExecutionSafetyDecision


def _console_decision(datasource_id: str, sql: str) -> ExecutionSafetyDecision:
    return ExecutionSafetyDecision(
        datasource_id=datasource_id,
        policy="user_readonly",
        original_sql=sql,
        safe_sql=sql,
        passed=True,
        can_execute=True,
        requires_confirmation=False,
        guardrail={
            "result": "pass",
            "originalSql": sql,
            "safeSql": sql,
            "checks": [],
            "message": "ok",
        },
        schema_warnings=[],
        scope_state={"source": "sql_console"},
        messages=[],
    )

def _add_console_datasource(db_session, *, datasource_id: str = "ds-console") -> None:
    db_session.add(
        DataSource(
            id=datasource_id,
            name="Console DS",
            db_type="mysql",
            host="localhost",
            port=3306,
            database_name="dbfox",
            username="root",
            connection_generation=11,
        )
    )
    db_session.commit()


def test_console_execute_persists_sql_backed_artifact_chain(monkeypatch, db_session):
    _add_console_datasource(db_session)
    request_model = getattr(agent_module, "ConsoleExecuteRequest", None)
    assert request_model is not None
    execute_api = getattr(agent_module, "api_agent_console_execute", None)
    assert execute_api is not None
    sql = "SELECT id, name FROM users"

    def fake_build_execution_decision(_self, requested_sql, ctx, policy):
        assert policy == "user_readonly"
        assert ctx.resource_id == "ds-console"
        return _console_decision("ds-console", requested_sql)

    def fake_execute_query(_db, datasource_id, requested_sql, question=None, execution_id=None, **kwargs):
        safety_decision = kwargs["safety_decision"]
        assert datasource_id == "ds-console"
        assert requested_sql == sql
        assert question == "SQL Console"
        assert safety_decision.safe_sql == sql
        return {
            "success": True,
            "columns": ["id", "name"],
            "rows": [{"id": 1, "name": "Ada"}],
            "rowCount": 1,
            "latencyMs": 5,
            "warnings": ["preview warning"],
            "notices": ["preview notice"],
            "truncated": False,
            "historyId": "history-console-1",
            "executionId": execution_id,
            "safetyDecision": safety_decision.model_dump(mode="json"),
        }

    monkeypatch.setattr(
        console_module.SqlSafetyService,
        "build_execution_decision",
        fake_build_execution_decision,
    )
    monkeypatch.setattr(console_module, "execute_query", fake_execute_query)

    # Production SessionLocal is configured with autoflush=False; the console
    # path must still create exactly one AgentSessionMemory row before the v4
    # shadow projection runs.
    db_session.autoflush = False
    response = execute_api(
        request_model(
            datasourceId="ds-console",
            sql=sql,
            question="SQL Console",
            sessionId="console-session",
            executionId="console-exec-1",
        ),
        db_session,
    )

    assert response.sessionId == "console-session"
    assert response.sqlArtifactId
    assert response.safetyArtifactId
    assert response.resultArtifactId
    assert response.warnings == ["preview warning"]
    assert response.notices == ["preview notice"]
    memory_rows = (
        db_session.query(AgentSessionMemory)
        .filter(AgentSessionMemory.session_id == "console-session")
        .all()
    )
    assert len(memory_rows) == 1

    records = (
            db_session.query(AgentArtifactRecord)
            .filter(AgentArtifactRecord.run_id == response.runId)
            .order_by(AgentArtifactRecord.sequence)
        .all()
    )
    assert [record.type for record in records] == ["safety", "sql", "result_view"]
    result_record = next(record for record in records if record.type == "result_view")
    sql_record = next(record for record in records if record.type == "sql")
    safety_record = next(record for record in records if record.type == "safety")
    result_payload = json.loads(result_record.payload_json)

    assert result_payload["sourceSqlArtifactId"] == sql_record.id
    assert safety_record.id
    assert "rows" not in result_payload
    assert "previewRows" not in result_payload
    assert result_payload["queryFingerprint"]
    assert result_payload["evidenceKind"] == "query_result"
    assert set(result_payload) == {
        "sourceSqlArtifactId", "queryFingerprint", "datasourceGeneration", "columns",
        "rowCount", "returnedRows", "latencyMs", "executedAt", "truncated",
        "evidenceKind",
    }

    run = db_session.get(AgentRun, response.runId)
    assert run is not None
    assert run.status == "completed"
    assert not hasattr(run, "datasource_id")
    assert not hasattr(run, "datasource_generation")
    admitted_input = db_session.get(AgentSessionInput, run.input_id)
    assert admitted_input is not None
    refs = load_resource_refs(str(admitted_input.resource_refs_json))
    assert refs is not None
    assert [(ref.kind, ref.id, ref.version) for ref in refs] == [
        ("dbfox.data.database", "ds-console", 11)
    ]
    run_payload = json.loads(run.result_json)
    assert "rows" not in (run_payload.get("execution") or {})
    completed_event = (
        db_session.query(AgentEventRecord)
        .filter(
            AgentEventRecord.run_id == response.runId,
            AgentEventRecord.type == "run.completed",
        )
        .one()
    )
    event_run = json.loads(completed_event.payload_json)["run"]
    assert event_run["id"] == response.runId
    assert event_run["session_id"] == response.sessionId
    assert event_run["status"] == "completed"
    assert event_run["version"] == run.version


def test_console_unexpected_error_never_leaks_exception_text(monkeypatch, db_session, caplog) -> None:
    _add_console_datasource(db_session, datasource_id="ds-console-boundary")
    sentinel = "console-execution-secret-sentinel"

    def fail_policy(*_args, **_kwargs):
        raise RuntimeError(f"database password={sentinel}")

    monkeypatch.setattr(
        console_module.PolicyEngine,
        "enforce_query_policy",
        staticmethod(fail_policy),
    )

    capture_logger = logging.Logger("test.agent_console_boundary")
    capture_logger.setLevel(logging.ERROR)
    capture_logger.propagate = False
    capture_logger.addHandler(caplog.handler)
    try:
        with monkeypatch.context() as scoped_monkeypatch:
            scoped_monkeypatch.setattr(agent_module, "logger", capture_logger)
            with pytest.raises(HTTPException) as exc_info:
                agent_module.api_agent_console_execute(
                    agent_module.ConsoleExecuteRequest(
                        datasourceId="ds-console-boundary",
                        sql="SELECT 1",
                    ),
                    db_session,
                )
    finally:
        capture_logger.removeHandler(caplog.handler)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "CONSOLE_EXECUTION_ERROR",
        "message": "The SQL Console request could not be completed.",
    }
    assert sentinel not in repr(exc_info.value.detail)
    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "agent_sql_console_execution" in caplog.text
