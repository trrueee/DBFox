from __future__ import annotations

from engine.agent import AgentRunRequest, AgentWorkspaceContext, DataBoxAgentRuntime
from engine.agent_contracts.default_tools import build_default_tool_registry
from engine.agent_contracts.registry import AgentToolContext
from engine.agent_contracts.workspace_context import build_agent_context_bundle
from engine.schema_sync import sync_schema


def test_workspace_fix_sql_tool_uses_last_error_and_suggests_editor_sql(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    registry = build_default_tool_registry()
    req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="Fix this SQL error",
        workspace_context=AgentWorkspaceContext(
            datasource_id=demo_datasource.id,
            active_sql="SELECT id, username FROM users LIMIT 10",
            last_error="no such column: usernme",
        ),
    )
    bundle = build_agent_context_bundle(db_session, req)

    obs = registry.get("workspace.fix_sql").execute(
        {"intent": "fix_sql", "context_bundle": bundle},
        AgentToolContext(db=db_session, request=req),
    )

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["intent"] == "fix_sql"
    assert "no such column" in obs.output["answer"]
    assert obs.output["suggestions"][0]["action"] == "apply_to_editor"
    assert obs.output["suggestions"][0]["proposed_sql"].upper().startswith("SELECT")


def test_workspace_explain_result_uses_preview_without_sql_execution(db_session, demo_datasource) -> None:
    req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="Explain the last result",
        workspace_context=AgentWorkspaceContext(
            datasource_id=demo_datasource.id,
            last_query_result_preview={
                "columns": ["status", "count"],
                "rows": [{"status": "active", "count": 2}],
                "rowCount": 1,
            },
        ),
    )
    bundle = build_agent_context_bundle(db_session, req)

    obs = build_default_tool_registry().get("workspace.explain_result").execute(
        {"intent": "explain_result", "context_bundle": bundle},
        AgentToolContext(db=db_session, request=req),
    )

    assert obs.status == "success"
    assert obs.output is not None
    assert "1 rows" in obs.output["answer"]
    assert obs.output["suggestions"] == []


def test_workspace_assist_runtime_records_artifacts_but_does_not_execute(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="Explain this SQL",
        execute=True,
        workspace_context=AgentWorkspaceContext(
            datasource_id=demo_datasource.id,
            active_sql="SELECT id, username FROM users LIMIT 10",
        ),
    )

    res = DataBoxAgentRuntime(db_session).run(req)

    assert res.success is True, res.model_dump()
    assert [step.name for step in res.steps] == ["workspace.explain_sql"]
    assert "execute_sql" not in [step.name for step in res.steps]
    assert res.execution is None
    assert res.answer is not None
    semantic_ids = {artifact.semantic_id for artifact in res.artifacts}
    assert "agent_plan_draft" in semantic_ids
    assert "sql_suggestion" in semantic_ids


def test_workspace_assist_stream_accepts_workspace_context(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="Optimize this SQL",
        workspace_context=AgentWorkspaceContext(
            datasource_id=demo_datasource.id,
            active_sql="SELECT id, username FROM users",
        ),
    )

    events = list(DataBoxAgentRuntime(db_session).run_iter(req))
    final = events[-1]

    assert final.type == "agent.run.completed"
    assert final.response is not None
    assert final.response.success is True
    assert final.response.execution is None
    assert any(event.type == "agent.artifact.created" for event in events)


def test_old_agent_request_without_workspace_context_still_uses_analysis_path(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="list users", execute=False)

    res = DataBoxAgentRuntime(db_session).run(req)

    assert res.success is True
    assert [step.name for step in res.steps][:4] == [
        "build_schema_context",
        "build_query_plan",
        "generate_sql_candidate",
        "validate_sql",
    ]
    assert res.execution == {"reason": "Request execute=false; SQL was not executed."}
