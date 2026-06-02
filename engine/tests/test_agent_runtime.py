from __future__ import annotations

from engine.agent import AgentContextArtifact, AgentFollowUpContext, AgentRunRequest, DataBoxAgentRuntime
from engine.schema_sync import sync_schema


def test_agent_runtime_execute_false_generates_full_review_response(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="查询所有用户", execute=False)

    res = DataBoxAgentRuntime(db_session).run(req)

    assert res.success is True, res.model_dump()
    assert res.run_id
    assert res.session_id
    assert res.context_summary
    assert res.query_plan is not None
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
    assert {item.artifact_id for item in res.answer.evidence}.issubset(artifact_ids)
    assert any(item.artifact_id == "result_profile" for item in res.answer.evidence)
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
        "build_query_plan",
        "generate_sql_candidate",
        "validate_sql",
        "execute_sql",
        "profile_result",
        "suggest_chart",
        "suggest_followups",
        "answer_synthesizer",
    ]
    assert res.steps[4].status == "skipped"


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
    monkeypatch.setattr("engine.agent.tools.generate_sql", fake_generate_sql)
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

    monkeypatch.setattr("engine.agent.tools.generate_sql", fake_generate_sql)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="删除所有用户", execute=True)

    res = DataBoxAgentRuntime(db_session).run(req)

    assert res.success is False
    assert res.safety is not None
    assert res.safety["can_execute"] is False
    assert "execute_sql" not in [step.name for step in res.steps]
    assert [step.name for step in res.steps] == [
        "build_schema_context",
        "build_query_plan",
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

    monkeypatch.setattr("engine.agent.tools.generate_sql", fake_generate_sql)
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
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="list products", execute=False, max_steps=3)

    res = DataBoxAgentRuntime(db_session).run(req)

    assert res.success is False
    assert res.error == "Agent stopped before SQL validation because max_steps was reached."
    assert [step.name for step in res.steps] == [
        "build_schema_context",
        "build_query_plan",
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
    monkeypatch.setattr("engine.agent.tools.generate_sql", fake_generate_sql)
    monkeypatch.setattr("engine.agent.tools.execute_query", fail_execute)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="list users", execute=True)

    res = DataBoxAgentRuntime(db_session).run(req)

    assert res.success is False
    assert res.safety is not None
    assert res.safety["schema_warnings"]
    assert "execute_sql" not in [step.name for step in res.steps]
    assert res.steps[-1].name == "revise_sql"
