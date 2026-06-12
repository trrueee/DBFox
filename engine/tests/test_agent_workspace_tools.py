from __future__ import annotations

import pytest

from engine.agent_core.types import AgentRunRequest, AgentWorkspaceContext
from engine.agent_core.tool_registry import ToolContext
from engine.tools.workspace_tools import WORKSPACE_HANDLERS
from engine.agent_core.workspace_context import build_agent_context_bundle
from engine.schema_sync import sync_schema
from engine.agent import DataBoxAgentRuntime


def test_workspace_fix_sql_tool_uses_last_error_and_suggests_editor_sql(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    req = AgentRunRequest(
        datasource_id=test_datasource.id,
        question="Fix this SQL error",
        workspace_context=AgentWorkspaceContext(
            datasource_id=test_datasource.id,
            active_sql="SELECT id, username FROM users LIMIT 10",
            last_error="no such column: usernme",
        ),
    )
    bundle = build_agent_context_bundle(db_session, req)
    ctx = ToolContext(db=db_session, request=req)

    handler = WORKSPACE_HANDLERS["workspace.fix_sql"]
    obs = handler({"intent": "fix_sql", "context_bundle": bundle}, ctx)

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["intent"] == "fix_sql"
    assert "no such column" in obs.output["answer"]
    assert obs.output["suggestions"][0]["action"] == "apply_to_editor"
    assert obs.output["suggestions"][0]["proposed_sql"].upper().startswith("SELECT")


def test_workspace_explain_result_uses_preview_without_sql_execution(db_session, test_datasource) -> None:
    req = AgentRunRequest(
        datasource_id=test_datasource.id,
        question="Explain the last result",
        workspace_context=AgentWorkspaceContext(
            datasource_id=test_datasource.id,
            last_query_result_preview={
                "columns": ["status", "count"],
                "rows": [{"status": "active", "count": 2}],
                "rowCount": 1,
            },
        ),
    )
    bundle = build_agent_context_bundle(db_session, req)
    ctx = ToolContext(db=db_session, request=req)

    handler = WORKSPACE_HANDLERS["workspace.explain_result"]
    obs = handler({"intent": "explain_result", "context_bundle": bundle}, ctx)

    assert obs.status == "success"
    assert obs.output is not None
    assert "1 rows" in obs.output["answer"]
    assert obs.output["suggestions"] == []


@pytest.mark.skip(reason="Requires LLM mock — needs db.* ReAct mock adaptation")
def test_workspace_assist_runtime_records_artifacts_but_does_not_execute(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    req = AgentRunRequest(
        datasource_id=test_datasource.id,
        question="Explain this SQL",
        execute=True,
        workspace_context=AgentWorkspaceContext(
            datasource_id=test_datasource.id,
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
    assert "sql_suggestion" in semantic_ids


@pytest.mark.skip(reason="Requires LLM mock — needs db.* ReAct mock adaptation")
def test_workspace_assist_stream_accepts_workspace_context(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    req = AgentRunRequest(
        datasource_id=test_datasource.id,
        question="Optimize this SQL",
        workspace_context=AgentWorkspaceContext(
            datasource_id=test_datasource.id,
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
