from __future__ import annotations

import json

import pytest

from engine.agent import AgentRunRequest, DataBoxAgentRuntime
from engine.agent import persistence as agent_persistence
from engine.errors import DataBoxError
from engine.models import AgentRun
from engine.schema_sync import sync_schema


def _prepare_waiting_run(db_session, demo_datasource, monkeypatch):
    sync_schema(db_session, demo_datasource.id)
    demo_datasource.env = "prod"
    db_session.commit()
    monkeypatch.setattr("engine.agent.tools._render_sql_from_query_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", lambda *_args, **_kwargs: {
        "sql": "SELECT id, username FROM users LIMIT 3",
        "model": "test",
        "mode": "offline",
        "latencyMs": 1,
        "schemaValidationWarnings": [],
    })
    response = DataBoxAgentRuntime(db_session).run(
        AgentRunRequest(
            datasource_id=demo_datasource.id,
            question="list users",
            execute=True,
            session_id="resume-session",
        )
    )
    approval = agent_persistence.get_pending_approval_for_run(db_session, response.run_id)
    assert approval is not None
    return response, approval


def test_checkpoint_state_restores_sql_safety_and_query_plan(db_session, demo_datasource, monkeypatch) -> None:
    response, _approval = _prepare_waiting_run(db_session, demo_datasource, monkeypatch)

    payload = agent_persistence.get_latest_checkpoint_payload(db_session, response.run_id)
    assert payload is not None
    state = payload["state"]
    assert isinstance(state, dict)
    assert state["sql"] == "SELECT id, username FROM users LIMIT 3"
    assert state["query_plan"]
    assert state["safety"]["requires_confirmation"] is True
    assert state["safety"]["can_execute"] is False


def test_approved_resume_continues_from_execute_sql(db_session, demo_datasource, monkeypatch) -> None:
    response, approval = _prepare_waiting_run(db_session, demo_datasource, monkeypatch)
    resolved = agent_persistence.resolve_approval(
        db_session,
        run_id=response.run_id,
        approval_id=approval.id,
        decision="approved",
        note="Looks good",
    )
    assert resolved.status == "approved"

    events = list(DataBoxAgentRuntime(db_session).resume_iter(response.run_id, approval.id))
    final = events[-1]
    assert final.type == "agent.run.completed"
    assert final.response is not None
    assert final.response.success is True
    assert final.response.status == "success"
    assert final.response.execution is not None
    assert final.response.execution["success"] is True
    assert final.response.result_profile is not None
    assert final.response.chart_suggestion is not None
    assert final.response.answer is not None

    event_types = [event.type for event in events]
    assert event_types[0] == "agent.run.resumed"
    assert "agent.step.started" in event_types
    assert "agent.artifact.created" in event_types
    assert "agent.answer.completed" in event_types
    assert [step.name for step in final.response.steps] == [
        "build_schema_context",
        "generate_sql_candidate",
        "validate_sql",
        "execute_sql",
        "profile_result",
        "suggest_chart",
        "suggest_followups",
        "answer_synthesizer",
    ]
    assert final.response.safety is not None
    assert final.response.safety["requires_confirmation"] is False
    assert final.response.safety["can_execute"] is True

    semantic_ids = {artifact.semantic_id for artifact in final.response.artifacts}
    assert {"query_plan", "sql_candidate", "safety_report", "result_table", "result_profile"}.issubset(semantic_ids)

    run_row = db_session.query(AgentRun).filter(AgentRun.id == response.run_id).first()
    assert run_row is not None
    assert run_row.status == "success"


def test_approval_must_belong_to_run_for_resume(db_session, demo_datasource, monkeypatch) -> None:
    first_response, _first_approval = _prepare_waiting_run(db_session, demo_datasource, monkeypatch)
    second_response, second_approval = _prepare_waiting_run(db_session, demo_datasource, monkeypatch)
    agent_persistence.resolve_approval(
        db_session,
        run_id=second_response.run_id,
        approval_id=second_approval.id,
        decision="approved",
    )

    with pytest.raises(DataBoxError) as exc:
        DataBoxAgentRuntime(db_session).resume(first_response.run_id, second_approval.id)

    assert exc.value.code == "APPROVAL_RUN_MISMATCH"


def test_resume_sse_event_payloads_are_json_serializable(db_session, demo_datasource, monkeypatch) -> None:
    response, approval = _prepare_waiting_run(db_session, demo_datasource, monkeypatch)
    agent_persistence.resolve_approval(
        db_session,
        run_id=response.run_id,
        approval_id=approval.id,
        decision="approved",
    )

    from engine.api.ai import _format_sse_event

    events = list(DataBoxAgentRuntime(db_session).resume_iter(response.run_id, approval.id))
    formatted = [_format_sse_event(event) for event in events]

    assert formatted[0].startswith("event: agent.run.resumed\n")
    assert any(item.startswith("event: agent.step.started\n") for item in formatted)
    assert any(item.startswith("event: agent.artifact.created\n") for item in formatted)
    assert formatted[-1].startswith("event: agent.run.completed\n")
    for item in formatted:
        json.loads(item.split("data: ", 1)[1].strip())
