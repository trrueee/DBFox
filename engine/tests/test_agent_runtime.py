from __future__ import annotations

import pytest

from engine.agent import DataBoxAgentRuntime
from engine.agent_core.types import (
    AgentContextArtifact, AgentFollowUpContext, AgentRunRequest,
    AgentRunResponse, AgentRuntimeEvent,
)
from engine.schema_sync import sync_schema


@pytest.fixture(autouse=True)
def _patch_schema_direct_sql_generate(monkeypatch):
    def fake_generate_sql_from_schema_context(**_kwargs):
        return {
            "sql": "SELECT id, username FROM users LIMIT 3",
            "model": "test",
            "mode": "schema_direct",
            "latencyMs": 1,
            "schemaValidationWarnings": [],
            "metadata": {"generation_source": "schema_direct_llm"},
        }

    monkeypatch.setattr(
        "engine.agent.tools.generate_sql_from_schema_context",
        fake_generate_sql_from_schema_context,
    )


def test_agent_runtime_delegates_run_iter_to_kernel_service(db_session, monkeypatch) -> None:
    calls: list[AgentRunRequest] = []

    class FakeKernelService:
        def __init__(self, db):
            self.db = db

        def run_iter(self, req: AgentRunRequest):
            calls.append(req)
            response = AgentRunResponse(
                run_id="kernel-run",
                session_id=req.session_id or "kernel-session",
                success=True,
                status="success",
                question=req.question,
                context_summary="kernel",
                steps=[],
            )
            yield AgentRuntimeEvent(
                event_id="event-1",
                run_id="kernel-run",
                sequence=1,
                created_at_ms=1,
                type="agent.run.completed",
                response=response,
            )

    monkeypatch.setattr("engine.databox_agent.app.service.DataBoxAgentService", FakeKernelService)

    events = list(DataBoxAgentRuntime(db_session).run_iter(
        AgentRunRequest(datasource_id="ds-test", question="list users", session_id="session-test")
    ))

    assert len(calls) == 1
    assert calls[0].question == "list users"
    assert events[-1].response is not None
    assert events[-1].response.run_id == "kernel-run"


def test_agent_runtime_default_plan_uses_fixed_registered_tools(db_session, demo_datasource) -> None:
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="list users", execute=False)

    plan = DataBoxAgentRuntime(db_session).build_default_plan(req)

    assert [step.name for step in plan] == [
        "build_schema_context",
        "generate_sql_candidate",
        "validate_sql",
        "execute_sql",
        "profile_result",
        "suggest_chart",
        "suggest_followups",
        "answer_synthesizer",
    ]
    assert [step.tool_name for step in plan] == [
        "schema.build_context",
        "sql.generate",
        "sql.validate",
        "sql.execute_readonly",
        "result.profile",
        "chart.suggest",
        "followup.suggest",
        "answer.synthesize",
    ]
    assert not any(step.tool_name.startswith("@") for step in plan)


def test_agent_runtime_execute_false_generates_full_review_response(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="查询所有用户", execute=False)

    res = DataBoxAgentRuntime(db_session).run(req)

    assert res.success is True, res.model_dump()
    assert res.run_id
    assert res.session_id
    assert res.context_summary
    assert res.sql is not None
    assert res.sql.upper().startswith("SELECT")
    assert "SELECT *" not in res.sql.upper()
    assert res.safety is not None
    assert res.safety["can_execute"] is True
    assert res.execution == {"reason": "Request execute=false; SQL was not executed."}
    assert res.explanation
    assert res.chart_suggestion is not None
    assert res.answer is not None
    assert res.answer.evidence
    assert res.artifacts
    artifact_ids = {artifact.id for artifact in res.artifacts}
    artifact_semantic_ids = {artifact.semantic_id for artifact in res.artifacts}
    assert {item.artifact_id for item in res.answer.evidence}.issubset(artifact_ids)
    result_profile_artifact = next(artifact for artifact in res.artifacts if artifact.semantic_id == "result_profile")
    assert "result_profile" in artifact_semantic_ids
    assert any(item.artifact_id == result_profile_artifact.id for item in res.answer.evidence)
    sql_artifact = next(artifact for artifact in res.artifacts if artifact.type == "sql")
    assert sql_artifact.payload["safety_state"]["can_execute"] is True
    assert res.events
    assert res.events[0].type == "agent.narration.completed"
    assert res.events[0].event_id
    assert [event.sequence for event in res.events] == sorted(event.sequence for event in res.events)
    assert res.message_blocks
    assert res.message_blocks[0].type == "text"
    assert any(block.type == "artifact_ref" for block in res.message_blocks)
    assert any(block.type == "answer" for block in res.message_blocks)
    assert [block.sequence for block in res.message_blocks] == sorted(block.sequence for block in res.message_blocks)
    assert res.trace_events
    assert len(res.trace_events) == len(res.steps) * 2
    assert res.trace_events[0].type == "agent.trace.step_started"
    assert res.trace_events[1].type == "agent.trace.step_completed"
    assert res.trace_events[0].step_id == res.trace_events[1].step_id
    assert len({event.event_id for event in res.trace_events}) == len(res.trace_events)
    assert [step.name for step in res.steps] == [
        "build_schema_context",
        "generate_sql_candidate",
        "validate_sql",
        "execute_sql",
        "profile_result",
        "suggest_chart",
        "suggest_followups",
        "answer_synthesizer",
    ]
    assert res.steps[3].status == "skipped"


def test_agent_runtime_run_iter_emits_ordered_events_and_final_response(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="list users",
        execute=False,
        session_id="stream-session",
    )

    events = list(DataBoxAgentRuntime(db_session).run_iter(req))

    assert events
    assert events[0].type == "agent.run.started"
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    final = events[-1]
    assert final.type == "agent.run.completed"
    assert final.response is not None
    assert final.response.success is True
    assert final.response.session_id == "stream-session"
    assert final.response.run_id == final.run_id
    assert all(event.run_id == final.response.run_id for event in events)

    started_steps = [event.step["name"] for event in events if event.type == "agent.step.started" and event.step]
    completed_steps = [event.step["name"] for event in events if event.type == "agent.step.completed" and event.step]
    assert completed_steps == [step.name for step in final.response.steps]
    assert started_steps == completed_steps

    artifact_events = [event for event in events if event.type == "agent.artifact.created"]
    assert [event.artifact.id for event in artifact_events if event.artifact] == [
        artifact.id for artifact in final.response.artifacts
    ]
    answer_index = next(index for index, event in enumerate(events) if event.type == "agent.answer.completed")
    assert answer_index > max(index for index, event in enumerate(events) if event.type == "agent.artifact.created")


def test_agent_runtime_run_iter_streams_artifacts_after_producing_steps(db_session, demo_datasource, monkeypatch) -> None:
    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "SELECT id, username FROM users LIMIT 3",
            "model": "test",
            "mode": "offline",
            "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    monkeypatch.setattr("engine.agent.tools._render_sql_from_query_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_generate_sql)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="list users", execute=True)

    events = list(DataBoxAgentRuntime(db_session).run_iter(req))
    final_response = events[-1].response

    assert final_response is not None
    assert final_response.success is True
    artifact_events = [event for event in events if event.type == "agent.artifact.created"]
    semantic_ids = [event.artifact.semantic_id for event in artifact_events if event.artifact]
    assert {"sql_candidate", "safety_report", "result_table"}.issubset(set(semantic_ids))
    assert all(event.artifact.id.startswith(f"agent/run/{final_response.run_id}/artifact/") for event in artifact_events if event.artifact)

    def step_index(step_name: str, event_type: str) -> int:
        return next(
            index for index, event in enumerate(events)
            if event.type == event_type and event.step and event.step.get("name") == step_name
        )

    def artifact_index(semantic_id: str) -> int:
        return next(
            index for index, event in enumerate(events)
            if event.type == "agent.artifact.created"
            and event.artifact
            and event.artifact.semantic_id == semantic_id
        )

    assert step_index("build_schema_context", "agent.step.completed") < step_index("generate_sql_candidate", "agent.step.started")
    assert step_index("validate_sql", "agent.step.completed") < artifact_index("sql_candidate") < step_index("execute_sql", "agent.step.started")
    assert step_index("validate_sql", "agent.step.completed") < artifact_index("safety_report") < step_index("execute_sql", "agent.step.started")
    assert step_index("execute_sql", "agent.step.completed") < artifact_index("result_table") < step_index("profile_result", "agent.step.started")

    artifacts_by_semantic = {artifact.semantic_id: artifact for artifact in final_response.artifacts}
    result_table = artifacts_by_semantic["result_table"]
    assert artifacts_by_semantic["sql_candidate"].id in result_table.depends_on
    assert artifacts_by_semantic["safety_report"].id in result_table.depends_on
    assert {evidence.artifact_id for evidence in final_response.answer.evidence}.issubset(
        {artifact.id for artifact in final_response.artifacts}
    )


def test_agent_runtime_reuses_validation_safety_decision_for_execution(db_session, demo_datasource, monkeypatch) -> None:
    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "SELECT id, username FROM users LIMIT 3",
            "model": "test",
            "mode": "offline",
            "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    monkeypatch.setattr("engine.agent.tools._render_sql_from_query_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_generate_sql)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="list users", execute=True)

    res = DataBoxAgentRuntime(db_session).run(req)

    assert res.success is True, res.model_dump()
    assert res.safety is not None
    assert res.safety["execution_safety_decision"]["can_execute"] is True
    assert res.execution is not None
    assert res.execution["success"] is True
    assert res.execution["safetyDecision"]["decision_id"] == res.safety["execution_safety_decision"]["decision_id"]


def test_agent_runtime_uses_client_supplied_followup_context(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    context = AgentFollowUpContext(
        session_id="session-test",
        parent_run_id="run-parent",
        previous_question="List users",
        previous_answer="The previous result listed users.",
        artifacts=[
            AgentContextArtifact(
                id="result_table",
                type="table",
                title="Result table",
                summary="rowCount=5; columns=id, username, role",
                payload={"columns": ["id", "username", "role"], "rowCount": 5},
            ),
            AgentContextArtifact(
                id="sql_candidate",
                type="sql",
                title="Validated SQL",
                summary="SELECT id, username, role FROM users LIMIT 5",
                payload={"sql": "SELECT id, username, role FROM users LIMIT 5"},
            ),
        ],
    )
    req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="Break it down by role",
        execute=False,
        follow_up_context=context,
    )

    res = DataBoxAgentRuntime(db_session).run(req)

    assert res.success is True, res.model_dump()
    assert res.session_id == "session-test"
    assert res.parent_run_id == "run-parent"
    assert res.referenced_artifact_ids == ["result_table", "sql_candidate"]
    assert res.context_summary
    assert res.steps[0].name == "load_follow_up_context"
    assert res.steps[0].output is not None
    assert "Previous question" in res.steps[0].output["analysis_question"]
    assert res.steps[1].name == "build_schema_context"
    assert res.steps[1].input is not None
    assert res.steps[1].input["has_follow_up_context"] is True


def test_agent_runtime_blocks_guardrail_failure_without_execution(db_session, demo_datasource, monkeypatch) -> None:
    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "DELETE FROM users",
            "model": "test",
            "mode": "offline",
            "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_generate_sql)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="删除所有用户", execute=True, api_key="sk-test")

    res = DataBoxAgentRuntime(db_session).run(req)

    assert res.success is False
    assert res.safety is not None
    assert res.safety["can_execute"] is False
    assert "execute_sql" not in [step.name for step in res.steps]
    assert [step.name for step in res.steps] == [
        "build_schema_context",
        "generate_sql_candidate",
        "validate_sql",
        "revise_sql",
    ]
    assert res.steps[-1].name == "revise_sql"
    assert res.steps[-1].output is not None
    assert {"can_fix", "fixed_sql", "reason", "changes", "remaining_risks"}.issubset(res.steps[-1].output.keys())
    error_artifact = next(artifact for artifact in res.artifacts if artifact.type == "error")
    assert error_artifact.payload["recovery_guidance"]
    assert error_artifact.payload["safety_state"]["can_execute"] is False


def test_agent_runtime_run_iter_trustgate_failure_streams_error_artifact(db_session, demo_datasource, monkeypatch) -> None:
    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "DELETE FROM users",
            "model": "test",
            "mode": "offline",
            "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_generate_sql)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="delete users", execute=True)

    events = list(DataBoxAgentRuntime(db_session).run_iter(req))
    final = events[-1]

    assert final.type == "agent.run.failed"
    assert final.response is not None
    assert final.response.success is False
    assert final.response.answer is not None
    assert final.response.answer.key_findings == []
    artifact_semantic_ids = [
        event.artifact.semantic_id
        for event in events
        if event.type == "agent.artifact.created" and event.artifact
    ]
    assert "safety_report" in artifact_semantic_ids
    assert "agent_error" in artifact_semantic_ids
    assert "result_table" not in artifact_semantic_ids
    error_artifact = next(artifact for artifact in final.response.artifacts if artifact.semantic_id == "agent_error")
    assert error_artifact.payload["recovery_guidance"]


def test_agent_runtime_execution_failure_returns_revise_suggestion(db_session, demo_datasource, monkeypatch) -> None:
    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "SELECT id FROM users LIMIT 1",
            "model": "test",
            "mode": "offline",
            "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    def fail_execute(*_args, **_kwargs):
        raise RuntimeError("database is busy")

    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_generate_sql)
    monkeypatch.setattr("engine.agent.tools.execute_query", fail_execute)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="查询用户", execute=True)

    res = DataBoxAgentRuntime(db_session).run(req)

    assert res.success is False
    assert res.execution is not None
    assert res.execution["success"] is False
    assert res.execution["revise_suggestion"]
    assert res.steps[-1].name == "revise_sql"


def test_agent_runtime_respects_max_steps_before_validation(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="list products", execute=False, max_steps=2)

    res = DataBoxAgentRuntime(db_session).run(req)

    assert res.success is False
    assert res.error == "Agent stopped before SQL validation because max_steps was reached."
    assert [step.name for step in res.steps] == [
        "build_schema_context",
        "generate_sql_candidate",
    ]
    assert res.answer is not None
    assert res.events
    assert res.message_blocks


def test_agent_runtime_stops_on_schema_hallucination_without_execution(db_session, demo_datasource, monkeypatch) -> None:
    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "SELECT imaginary_column FROM users LIMIT 10",
            "model": "test",
            "mode": "offline",
            "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    def fail_execute(*_args, **_kwargs):
        raise AssertionError("hallucinated SQL must not execute")

    monkeypatch.setattr("engine.agent.tools._render_sql_from_query_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_generate_sql)
    monkeypatch.setattr("engine.agent.tools.execute_query", fail_execute)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="list users", execute=True)

    res = DataBoxAgentRuntime(db_session).run(req)

    assert res.success is False
    assert res.safety is not None
    assert res.safety["schema_warnings"]
    assert "execute_sql" not in [step.name for step in res.steps]
    assert res.steps[-1].name in {"revise_sql", "answer_synthesizer"}


def test_sse_event_format(db_session, demo_datasource) -> None:
    from engine.api.agent import _format_sse_event
    from engine.agent_core.types import AgentRuntimeEvent, AgentArtifact, AgentArtifactPresentation

    artifact = AgentArtifact(
        id="agent/run/test-run/artifact/001/query_plan",
        semantic_id="query_plan",
        type="query_plan",
        title="Query plan",
        payload={"analysis_goal": "test"},
        presentation=AgentArtifactPresentation(mode="dock", priority=80),
    )
    event = AgentRuntimeEvent(
        event_id="evt_1",
        run_id="test-run",
        sequence=1,
        created_at_ms=1700000000000,
        type="agent.artifact.created",
        artifact=artifact,
    )

    formatted = _format_sse_event(event)

    assert formatted.startswith("event: agent.artifact.created\n"), repr(formatted[:200])
    assert "\ndata: " in formatted
    assert formatted.endswith("\n\n")
    parsed = __import__("json").loads(formatted.split("data: ")[1].rstrip("\n"))
    assert parsed["event_id"] == "evt_1"
    assert parsed["type"] == "agent.artifact.created"


def test_stream_and_non_stream_final_response_consistency(db_session, demo_datasource, monkeypatch) -> None:
    from engine.agent import DataBoxAgentRuntime; from engine.agent_core.types import AgentRunRequest
    from engine.schema_sync import sync_schema

    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "SELECT id, username FROM users LIMIT 3",
            "model": "test",
            "mode": "offline",
            "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    monkeypatch.setattr("engine.agent.tools._render_sql_from_query_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_generate_sql)

    req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="list users",
        execute=True,
        session_id="consistency-session",
    )

    non_stream_res = DataBoxAgentRuntime(db_session).run(req)
    stream_events = list(DataBoxAgentRuntime(db_session).run_iter(req))
    stream_res = stream_events[-1].response

    assert stream_res is not None
    assert non_stream_res.success == stream_res.success
    assert stream_res.session_id == "consistency-session"

    comparable_fields = ("session_id", "success", "question", "sql", "explanation")
    for field in comparable_fields:
        assert getattr(non_stream_res, field) == getattr(stream_res, field), f"{field} mismatch"

    assert non_stream_res.answer is not None
    assert stream_res.answer is not None
    assert non_stream_res.answer.answer == stream_res.answer.answer
    assert non_stream_res.answer.key_findings == stream_res.answer.key_findings
    assert len(non_stream_res.answer.evidence) == len(stream_res.answer.evidence)

    non_stream_semantic = {a.semantic_id for a in non_stream_res.artifacts}
    stream_semantic = {a.semantic_id for a in stream_res.artifacts}
    assert non_stream_semantic == stream_semantic

    assert len(non_stream_res.steps) == len(stream_res.steps)
    for ns_step, ss_step in zip(non_stream_res.steps, stream_res.steps):
        assert ns_step.name == ss_step.name
        assert ns_step.status == ss_step.status


# ── Persistence tests ──


def test_persistence_creates_session_and_run(db_session, demo_datasource, monkeypatch) -> None:
    from engine.agent import DataBoxAgentRuntime; from engine.agent_core.types import AgentRunRequest
    from engine.schema_sync import sync_schema
    from engine.models import AgentRun as AgentRunModel, AgentSession as AgentSessionModel

    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "SELECT id FROM users LIMIT 1",
            "model": "test", "mode": "offline", "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    monkeypatch.setattr("engine.agent.tools._render_sql_from_query_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_generate_sql)

    req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="persistence test",
        execute=True,
        session_id="persist-session-1",
    )

    res = DataBoxAgentRuntime(db_session).run(req)

    session_row = db_session.query(AgentSessionModel).filter(AgentSessionModel.id == "persist-session-1").first()
    assert session_row is not None
    assert session_row.datasource_id == demo_datasource.id

    run_row = db_session.query(AgentRunModel).filter(AgentRunModel.id == res.run_id).first()
    assert run_row is not None
    assert run_row.session_id == "persist-session-1"
    assert run_row.status == "success"
    assert run_row.question == "persistence test"
    assert run_row.response_json is not None


def test_persistence_saves_artifacts(db_session, demo_datasource, monkeypatch) -> None:
    from engine.agent import DataBoxAgentRuntime; from engine.agent_core.types import AgentRunRequest
    from engine.schema_sync import sync_schema
    from engine.models import AgentArtifactRecord

    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "SELECT id, username FROM users LIMIT 3",
            "model": "test", "mode": "offline", "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    monkeypatch.setattr("engine.agent.tools._render_sql_from_query_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_generate_sql)

    req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="artifact persistence test",
        execute=True,
        session_id="persist-artifact-session",
    )

    res = DataBoxAgentRuntime(db_session).run(req)
    assert res.success is True

    records = (
        db_session.query(AgentArtifactRecord)
        .filter(AgentArtifactRecord.run_id == res.run_id)
        .order_by(AgentArtifactRecord.sequence)
        .all()
    )
    semantic_ids = {r.semantic_id for r in records}
    assert "query_plan" in semantic_ids
    assert "sql_candidate" in semantic_ids
    assert "safety_report" in semantic_ids
    assert "result_table" in semantic_ids

    for record in records:
        assert record.id.startswith(f"agent/run/{res.run_id}/artifact/")
        assert record.type
        assert record.title
        assert record.payload_json


def test_persistence_get_run_restores_response(db_session, demo_datasource, monkeypatch) -> None:
    from engine.agent import DataBoxAgentRuntime; from engine.agent_core.types import AgentRunRequest
    from engine.agent_core.persistence import get_run
    from engine.schema_sync import sync_schema

    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "SELECT id, username FROM users LIMIT 3",
            "model": "test", "mode": "offline", "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    monkeypatch.setattr("engine.agent.tools._render_sql_from_query_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_generate_sql)

    req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="get_run test",
        execute=True,
        session_id="persist-getrun",
    )

    res = DataBoxAgentRuntime(db_session).run(req)

    restored = get_run(db_session, res.run_id)
    assert restored is not None
    assert restored.run_id == res.run_id
    assert restored.session_id == res.session_id
    assert restored.success == res.success
    assert restored.question == res.question
    assert restored.sql == res.sql
    assert restored.answer is not None
    assert restored.answer.answer == res.answer.answer
    assert len(restored.artifacts) == len(res.artifacts)
    assert restored.steps == res.steps

    evidence_artifact_ids = {e.artifact_id for e in restored.answer.evidence}
    artifact_ids = {a.id for a in restored.artifacts}
    assert evidence_artifact_ids.issubset(artifact_ids)


def test_persistence_followup_server_side_reconstruction(db_session, demo_datasource, monkeypatch) -> None:
    from engine.agent import DataBoxAgentRuntime; from engine.agent_core.types import AgentRunRequest
    from engine.agent_core.persistence import build_followup_context_from_run
    from engine.schema_sync import sync_schema

    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "SELECT id, username FROM users LIMIT 3",
            "model": "test", "mode": "offline", "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    monkeypatch.setattr("engine.agent.tools._render_sql_from_query_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_generate_sql)

    first_req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="first run",
        execute=True,
        session_id="followup-session",
    )
    first_res = DataBoxAgentRuntime(db_session).run(first_req)
    assert first_res.success is True

    followup_req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="break it down further",
        execute=True,
        parent_run_id=first_res.run_id,
    )
    followup_res = DataBoxAgentRuntime(db_session).run(followup_req)
    assert followup_res.success is True

    assert followup_res.session_id == "followup-session"
    assert followup_res.referenced_artifact_ids
    assert followup_res.steps[0].name == "load_follow_up_context"

    ctx = build_followup_context_from_run(db_session, first_res.run_id)
    assert ctx is not None
    assert ctx.session_id == "followup-session"
    assert ctx.parent_run_id == first_res.run_id
    assert ctx.previous_question == "first run"
    assert ctx.previous_answer is not None
    assert len(ctx.artifacts) > 0


def test_persistence_streaming_saves_events(db_session, demo_datasource, monkeypatch) -> None:
    from engine.agent import DataBoxAgentRuntime; from engine.agent_core.types import AgentRunRequest
    from engine.models import AgentRuntimeEventRecord
    from engine.schema_sync import sync_schema

    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "SELECT id FROM users LIMIT 1",
            "model": "test", "mode": "offline", "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    monkeypatch.setattr("engine.agent.tools._render_sql_from_query_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_generate_sql)

    req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="streaming persistence",
        execute=True,
        session_id="stream-persist",
    )

    events = list(DataBoxAgentRuntime(db_session).run_iter(req))
    final_response = events[-1].response
    assert final_response is not None

    saved_events = (
        db_session.query(AgentRuntimeEventRecord)
        .filter(AgentRuntimeEventRecord.run_id == final_response.run_id)
        .order_by(AgentRuntimeEventRecord.sequence)
        .all()
    )
    assert len(saved_events) > 0
    assert saved_events[0].type == "agent.run.started"
    assert saved_events[-1].type == "agent.run.completed"

    artifact_events = [e for e in saved_events if e.type == "agent.artifact.created"]
    assert len(artifact_events) >= 4

    from engine.models import AgentRun as AgentRunModel
    run_row = db_session.query(AgentRunModel).filter(AgentRunModel.id == final_response.run_id).first()
    assert run_row is not None
    assert run_row.status == "success"


def test_persistence_failure_saves_error_artifact(db_session, demo_datasource, monkeypatch) -> None:
    from engine.agent import DataBoxAgentRuntime; from engine.agent_core.types import AgentRunRequest
    from engine.models import AgentRun as AgentRunModel
    from engine.schema_sync import sync_schema

    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "DELETE FROM users",
            "model": "test", "mode": "offline", "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_generate_sql)

    req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="delete users",
        execute=True,
        session_id="persist-fail",
    )

    events = list(DataBoxAgentRuntime(db_session).run_iter(req))
    final = events[-1]
    assert final.type == "agent.run.failed"
    assert final.response is not None

    run_row = db_session.query(AgentRunModel).filter(AgentRunModel.id == final.response.run_id).first()
    assert run_row is not None
    assert run_row.status == "failed"
    assert run_row.error is not None

    from engine.models import AgentArtifactRecord
    error_artifact = (
        db_session.query(AgentArtifactRecord)
        .filter(
            AgentArtifactRecord.run_id == final.response.run_id,
            AgentArtifactRecord.semantic_id == "agent_error",
        )
        .first()
    )
    assert error_artifact is not None

    import json
    payload = json.loads(error_artifact.payload_json)
    assert "error" in payload
    assert "recovery_guidance" in payload


def test_persistence_recent_run_recovery(db_session, demo_datasource, monkeypatch) -> None:
    from engine.agent import DataBoxAgentRuntime; from engine.agent_core.types import AgentRunRequest
    from engine.agent_core.persistence import get_recent_run
    from engine.schema_sync import sync_schema

    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "SELECT id FROM users LIMIT 1",
            "model": "test", "mode": "offline", "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    monkeypatch.setattr("engine.agent.tools._render_sql_from_query_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_generate_sql)

    req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="recent run test",
        execute=True,
    )

    res = DataBoxAgentRuntime(db_session).run(req)
    assert res.success is True

    recent = get_recent_run(db_session, demo_datasource.id)
    assert recent is not None
    assert recent.run_id == res.run_id
    assert recent.question == "recent run test"


# ── Replay tests ──


def test_list_run_artifacts_returns_ordered_artifacts(db_session, demo_datasource, monkeypatch) -> None:
    from engine.agent import DataBoxAgentRuntime; from engine.agent_core.types import AgentRunRequest
    from engine.agent_core.persistence import list_run_artifacts
    from engine.schema_sync import sync_schema

    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "SELECT id, username FROM users LIMIT 3",
            "model": "test", "mode": "offline", "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    monkeypatch.setattr("engine.agent.tools._render_sql_from_query_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_generate_sql)

    req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="ordered artifacts",
        execute=True,
        session_id="replay-artifacts",
    )

    res = DataBoxAgentRuntime(db_session).run(req)
    assert res.success is True

    artifacts = list_run_artifacts(db_session, res.run_id)
    assert len(artifacts) >= 4
    sequences = [a.get("sequence") for a in artifacts if a.get("sequence") is not None]
    assert sequences == sorted(sequences)

    expected_semantic = {"query_plan", "sql_candidate", "safety_report", "result_table"}
    found_semantic = {a["semantic_id"] for a in artifacts}
    assert expected_semantic.issubset(found_semantic)


def test_list_run_events_returns_ordered_runtime_events(db_session, demo_datasource, monkeypatch) -> None:
    from engine.agent import DataBoxAgentRuntime; from engine.agent_core.types import AgentRunRequest
    from engine.agent_core.persistence import list_run_events
    from engine.schema_sync import sync_schema

    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "SELECT id FROM users LIMIT 1",
            "model": "test", "mode": "offline", "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    monkeypatch.setattr("engine.agent.tools._render_sql_from_query_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_generate_sql)

    req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="ordered events",
        execute=True,
        session_id="replay-events",
    )

    res = DataBoxAgentRuntime(db_session).run(req)
    assert res.success is True

    events = list_run_events(db_session, res.run_id)
    assert len(events) > 0
    assert events[0]["type"] == "agent.run.started"
    assert events[-1]["type"] == "agent.run.completed"

    seqs = [e["sequence"] for e in events]
    assert seqs == sorted(seqs)

    types = [e["type"] for e in events]
    assert "agent.step.started" in types
    assert "agent.step.completed" in types
    assert "agent.artifact.created" in types
    assert "agent.answer.completed" in types


def test_list_run_trace_returns_redacted_trace_events(db_session, demo_datasource, monkeypatch) -> None:
    from engine.agent import DataBoxAgentRuntime; from engine.agent_core.types import AgentRunRequest
    from engine.agent_core.persistence import list_run_trace_events
    from engine.schema_sync import sync_schema

    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "SELECT id FROM users LIMIT 1",
            "model": "test", "mode": "offline", "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    monkeypatch.setattr("engine.agent.tools._render_sql_from_query_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_generate_sql)

    req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="redacted trace",
        execute=True,
        api_key="secret-key-12345",
        session_id="replay-trace",
    )

    res = DataBoxAgentRuntime(db_session).run(req)
    assert res.success is True

    trace_events = list_run_trace_events(db_session, res.run_id)
    assert len(trace_events) > 0

    SENSITIVE = {"api_key", "password", "token", "secret", "ciphertext", "nonce", "private_key"}

    def _has_sensitive_key(obj: object, seen: set | None = None) -> set[str]:
        found: set[str] = set()
        if seen is None:
            seen = set()
        obj_id = id(obj)
        if obj_id in seen:
            return found
        seen.add(obj_id)
        if isinstance(obj, dict):
            for k, v in obj.items():
                ks = str(k)
                for s in SENSITIVE:
                    if s == ks:
                        found.add(s)
                found.update(_has_sensitive_key(v, seen))
        elif isinstance(obj, list):
            for item in obj:
                found.update(_has_sensitive_key(item, seen))
        return found

    for event in trace_events:
        found_keys = _has_sensitive_key(event)
        assert not found_keys, f"Sensitive keys {found_keys} found in trace event"


def test_replay_does_not_execute_sql(db_session, demo_datasource, monkeypatch) -> None:
    from engine.agent import DataBoxAgentRuntime; from engine.agent_core.types import AgentRunRequest
    from engine.agent_core.persistence import get_run, list_run_artifacts
    from engine.schema_sync import sync_schema

    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "SELECT id, username FROM users LIMIT 3",
            "model": "test", "mode": "offline", "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    execute_called = False

    def fail_execute(*_args, **_kwargs):
        nonlocal execute_called
        execute_called = True
        raise RuntimeError("must not execute during replay")

    monkeypatch.setattr("engine.agent.tools._render_sql_from_query_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_generate_sql)

    req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="replay no execute",
        execute=True,
        session_id="replay-noexec",
    )

    res = DataBoxAgentRuntime(db_session).run(req)
    run_id = res.run_id

    monkeypatch.setattr("engine.agent.tools.execute_query", fail_execute)

    restored = get_run(db_session, run_id)
    assert restored is not None
    assert restored.run_id == run_id
    assert restored.success == res.success
    assert "SELECT" in (restored.sql or "")

    artifacts = list_run_artifacts(db_session, run_id)
    assert any(a["type"] == "table" for a in artifacts)

    assert not execute_called, "get_run must not trigger SQL execution"


def test_restored_run_can_start_followup(db_session, demo_datasource, monkeypatch) -> None:
    from engine.agent import DataBoxAgentRuntime; from engine.agent_core.types import AgentRunRequest
    from engine.agent_core.persistence import get_run
    from engine.schema_sync import sync_schema

    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "SELECT id, username FROM users LIMIT 3",
            "model": "test", "mode": "offline", "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    monkeypatch.setattr("engine.agent.tools._render_sql_from_query_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_generate_sql)

    first_req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="replay followup parent",
        execute=True,
        session_id="replay-followup",
    )
    first_res = DataBoxAgentRuntime(db_session).run(first_req)
    assert first_res.success is True

    restored = get_run(db_session, first_res.run_id)
    assert restored is not None
    assert restored.session_id == "replay-followup"

    followup_req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="drill down from replay",
        execute=True,
        parent_run_id=restored.run_id,
    )
    followup_res = DataBoxAgentRuntime(db_session).run(followup_req)
    assert followup_res.success is True
    assert followup_res.session_id == "replay-followup"
    assert followup_res.parent_run_id == restored.run_id
    assert followup_res.referenced_artifact_ids
    assert followup_res.steps[0].name == "load_follow_up_context"


def test_missing_run_artifacts_returns_empty(db_session) -> None:
    from engine.agent_core.persistence import list_run_artifacts
    artifacts = list_run_artifacts(db_session, "nonexistent-run-id")
    assert artifacts == []


def test_session_runs_sorted_and_include_status(db_session, demo_datasource, monkeypatch) -> None:
    from engine.agent import DataBoxAgentRuntime; from engine.agent_core.types import AgentRunRequest
    from engine.agent_core.persistence import list_session_runs
    from engine.schema_sync import sync_schema

    sync_schema(db_session, demo_datasource.id)

    def fake_generate_sql(*_args, **_kwargs):
        return {
            "sql": "SELECT id FROM users LIMIT 1",
            "model": "test", "mode": "offline", "latencyMs": 1,
            "schemaValidationWarnings": [],
        }

    monkeypatch.setattr("engine.agent.tools._render_sql_from_query_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_generate_sql)

    session_id = "sorted-session-runs"
    for i in range(3):
        req = AgentRunRequest(
            datasource_id=demo_datasource.id,
            question=f"question {i + 1}",
            execute=True,
            session_id=session_id,
        )
        DataBoxAgentRuntime(db_session).run(req)

    runs = list_session_runs(db_session, session_id)
    assert len(runs) == 3
    for r in runs:
        assert "run_id" in r
        assert "status" in r
        assert "question" in r
        assert "artifact_count" in r
        assert r["status"] in ("success", "failed", "running")

    timestamps = [r["created_at"] for r in runs if r["created_at"]]
    assert timestamps == sorted(timestamps, reverse=True), "runs should be sorted newest first"
