from __future__ import annotations

import pytest

from engine.agent import DataBoxAgentRuntime
from engine.agent_core.types import AgentRunRequest
from engine.agent_core import persistence as agent_persistence
from engine.errors import DataBoxError
from engine.models import AgentRun
from engine.schema_sync import sync_schema


def _fake_select_sql(*_args, **_kwargs):
    return {
        "sql": "SELECT id, username FROM users LIMIT 3",
        "model": "test",
        "mode": "offline",
        "latencyMs": 1,
        "schemaValidationWarnings": [],
    }


def _waiting_run(db_session, demo_datasource, monkeypatch):
    sync_schema(db_session, demo_datasource.id)
    demo_datasource.env = "prod"
    db_session.commit()
    monkeypatch.setattr("engine.tools.sql_tools._render_sql_from_query_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("engine.tools.sql_tools.generate_sql_from_schema_context", _fake_select_sql)

    events = list(DataBoxAgentRuntime(db_session).run_iter(
        AgentRunRequest(
            datasource_id=demo_datasource.id,
            question="list users",
            execute=True,
            session_id="approval-session",
        )
    ))
    final = events[-1]
    assert final.response is not None
    approval = agent_persistence.get_pending_approval_for_run(db_session, final.response.run_id)
    assert approval is not None
    return final.response, approval, events


def test_prod_datasource_enters_waiting_approval_instead_of_failed(db_session, demo_datasource, monkeypatch) -> None:
    response, approval, events = _waiting_run(db_session, demo_datasource, monkeypatch)

    assert response.success is False
    assert response.status == "waiting_approval"
    assert response.error is None
    assert response.approval is not None
    assert response.approval.id == approval.id
    assert [step.name for step in response.steps] == [
        "build_schema_context",
        "generate_sql_candidate",
        "validate_sql",
    ]
    assert "execute_sql" not in [step.name for step in response.steps]
    assert [event.type for event in events][-3:] == [
        "agent.approval.required",
        "agent.checkpoint.saved",
        "agent.run.waiting_approval",
    ]

    run_row = db_session.query(AgentRun).filter(AgentRun.id == response.run_id).first()
    assert run_row is not None
    assert run_row.status == "waiting_approval"
    assert run_row.waiting_approval_id == approval.id

    checkpoints = agent_persistence.list_checkpoints(db_session, response.run_id)
    assert len(checkpoints) == 1
    assert checkpoints[0].status == "waiting_approval"
    assert checkpoints[0].current_step_name == "validate_sql"
    assert checkpoints[0].next_step_name == "execute_sql"


def test_pending_approval_cannot_resume(db_session, demo_datasource, monkeypatch) -> None:
    response, approval, _events = _waiting_run(db_session, demo_datasource, monkeypatch)

    with pytest.raises(DataBoxError) as exc:
        DataBoxAgentRuntime(db_session).resume(response.run_id, approval.id)

    assert exc.value.code == "APPROVAL_PENDING"


def test_rejected_approval_marks_run_failed_and_cannot_resolve_twice(db_session, demo_datasource, monkeypatch) -> None:
    response, approval, _events = _waiting_run(db_session, demo_datasource, monkeypatch)

    rejected = agent_persistence.resolve_approval(
        db_session,
        run_id=response.run_id,
        approval_id=approval.id,
        decision="rejected",
        note="No",
    )
    assert rejected.status == "rejected"

    run_row = db_session.query(AgentRun).filter(AgentRun.id == response.run_id).first()
    assert run_row is not None
    assert run_row.status == "failed"
    assert run_row.error == "Approval rejected"

    with pytest.raises(DataBoxError) as exc:
        agent_persistence.resolve_approval(
            db_session,
            run_id=response.run_id,
            approval_id=approval.id,
            decision="approved",
        )
    assert exc.value.code == "APPROVAL_ALREADY_RESOLVED"


def test_guardrail_and_schema_hard_blockers_do_not_enter_approval(db_session, demo_datasource, monkeypatch) -> None:
    sync_schema(db_session, demo_datasource.id)
    demo_datasource.env = "prod"
    db_session.commit()
    monkeypatch.setattr("engine.tools.sql_tools._render_sql_from_query_plan", lambda *_args, **_kwargs: None)

    monkeypatch.setattr("engine.tools.sql_tools.generate_sql_from_schema_context", lambda *_args, **_kwargs: {
        "sql": "DELETE FROM users",
        "model": "test",
        "mode": "offline",
        "latencyMs": 1,
        "schemaValidationWarnings": [],
    })
    guardrail_response = DataBoxAgentRuntime(db_session).run(
        AgentRunRequest(datasource_id=demo_datasource.id, question="delete users", execute=True)
    )
    assert guardrail_response.success is False
    assert guardrail_response.status == "failed"
    assert guardrail_response.approval is None

    monkeypatch.setattr("engine.tools.sql_tools.generate_sql_from_schema_context", lambda *_args, **_kwargs: {
        "sql": "SELECT imaginary_column FROM users LIMIT 10",
        "model": "test",
        "mode": "offline",
        "latencyMs": 1,
        "schemaValidationWarnings": [],
    })
    schema_response = DataBoxAgentRuntime(db_session).run(
        AgentRunRequest(datasource_id=demo_datasource.id, question="bad column", execute=True)
    )
    assert schema_response.success is False
    assert schema_response.status == "failed"
    assert schema_response.approval is None
