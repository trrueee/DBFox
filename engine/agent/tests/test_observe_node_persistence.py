from __future__ import annotations

from types import SimpleNamespace

from engine.agent.nodes.observe_node import observe_tools
from engine.agent.app.service import DBFoxAgentService
from engine.agent_core import persistence as agent_persistence
from engine.agent_core.types import (
    AgentArtifact,
    AgentArtifactPresentation,
    AgentRuntimeEvent,
    ToolObservation,
)
from engine.tools.dbfox_tools import register_dbfox_tools


def test_observe_tools_does_not_write_artifacts_with_graph_db(db_session, monkeypatch):
    calls = []

    def fail_record_artifact(*_args, **_kwargs):
        calls.append((_args, _kwargs))
        raise AssertionError("observe_tools must not persist artifacts with the graph DB session")

    monkeypatch.setattr(agent_persistence, "record_artifact", fail_record_artifact)

    observation = ToolObservation(
        name="sql.execute_readonly",
        status="success",
        input={"sql": "SELECT 1"},
        output={
            "status": "success",
            "success": True,
            "columns": ["value"],
            "rows": [{"value": 1}],
            "returned_rows": 1,
            "safe_sql": "SELECT 1",
        },
        error=None,
        latency_ms=5,
    )
    state = {
        "run_id": "run-observe-no-db-write",
        "thread_id": "session-observe-no-db-write",
        "last_tool_results": [observation.model_dump(mode="json")],
    }
    config = {
        "configurable": {
            "registry": register_dbfox_tools(),
            "db": db_session,
            "request": SimpleNamespace(datasource_id="ds-test", question="q"),
        }
    }

    update = observe_tools(state, config)

    assert update["artifacts"]
    assert calls == []


def test_service_persists_artifact_created_events_via_sink():
    class FakeSink:
        def __init__(self):
            self.artifacts = []

        def record_artifact(self, session_id, run_id, artifact, index):
            self.artifacts.append((session_id, run_id, artifact, index))

    sink = FakeSink()
    service = DBFoxAgentService.__new__(DBFoxAgentService)
    service._persist_events = True
    service.persistence_sink = sink

    artifact = AgentArtifact(
        id="artifact-1",
        type="table",
        title="Rows",
        payload={"rows": []},
        presentation=AgentArtifactPresentation(mode="inline"),
        produced_by_step="execute_readonly",
    )
    event = AgentRuntimeEvent(
        event_id="runtime_run_1_agent_artifact_created",
        run_id="run-1",
        sequence=7,
        created_at_ms=123,
        type="agent.artifact.created",
        artifact=artifact,
    )

    service._persist_artifact_event("session-1", event, index=3)

    assert sink.artifacts == [("session-1", "run-1", artifact, 3)]
