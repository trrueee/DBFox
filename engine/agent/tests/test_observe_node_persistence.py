from __future__ import annotations

from types import SimpleNamespace

from engine.agent.nodes.observe_node import (
    bind_observation_to_state,
    build_tool_history_entry,
    derive_catalog_exploration_state,
    emit_artifacts_from_observation,
    make_observe_working_state,
    merge_catalog_exploration_state,
    observe_tools,
    rebuild_context_pack,
)
from engine.agent.app.service import DBFoxAgentService
from engine.agent_core import persistence as agent_persistence
from engine.agent_core.types import (
    AgentArtifact,
    AgentArtifactPresentation,
    AgentRuntimeEvent,
    ToolObservation,
)
from engine.tools.dbfox_tools import register_dbfox_tools


def test_make_observe_working_state_shallow_copies_mutable_top_level_values():
    source = {
        "items": [1],
        "payload": {"name": "orders"},
        "scalar": "kept",
    }

    working = make_observe_working_state(source)

    assert working == source
    assert working["items"] is not source["items"]
    assert working["payload"] is not source["payload"]
    assert working["scalar"] == source["scalar"]


def test_bind_observation_to_state_strips_legacy_databinding_artifacts():
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
    state = {"artifacts": [{"id": "existing"}]}

    update = bind_observation_to_state(
        state=state,
        tool_name="sql.execute_readonly",
        observation=observation,
        merge_strategy="reuse",
    )

    assert "artifacts" not in update
    assert update["execution"]["success"] is True
    assert update["sql"] == "SELECT 1"
    assert "execution" not in state


def test_build_tool_history_entry_summarizes_output_shape():
    observation = ToolObservation(
        name="db.search",
        status="success",
        input={"query": "orders"},
        output={
            "results": [{"name": "orders"}, {"name": "order_items"}],
            "blocked_reasons": ["unsafe"],
            "returned_rows": 2,
        },
        error=None,
        latency_ms=5,
    )

    entry = build_tool_history_entry("db.search", observation)

    assert entry["name"] == "db.search"
    assert entry["input"] == {"query": "orders"}
    assert entry["status"] == "success"
    assert entry["results_count"] == 2
    assert entry["blocked_reasons"] == ["unsafe"]
    assert entry["returned_rows"] == 2
    assert set(entry["output_keys"]) == {"results", "blocked_reasons", "returned_rows"}


def test_derive_catalog_exploration_state_collects_tables_terms_and_exhausted_paths():
    search_observation = ToolObservation(
        name="db.search",
        status="success",
        input={"query": " Orders "},
        output={
            "results": [
                {"name": "orders"},
                {"table_name": "customers"},
                {"name": ""},
            ],
        },
        error=None,
        latency_ms=3,
    )

    search_update = derive_catalog_exploration_state("db.search", search_observation)

    assert search_update["candidate_tables"] == ["orders", "customers"]
    assert search_update["searched_terms"] == ["orders"]
    assert search_update["exhausted_paths"] == []

    empty_observation = ToolObservation(
        name="db.search",
        status="success",
        input={"query": "missing"},
        output={"results": []},
        error=None,
        latency_ms=4,
    )

    empty_update = derive_catalog_exploration_state("db.search", empty_observation)

    assert empty_update["candidate_tables"] == []
    assert empty_update["searched_terms"] == ["missing"]
    assert len(empty_update["exhausted_paths"]) == 1
    assert empty_update["exhausted_paths"][0].startswith("db.search::")


def test_merge_catalog_exploration_state_deduplicates_existing_values():
    merged = merge_catalog_exploration_state(
        {
            "candidate_tables": ["orders"],
            "searched_terms": ["orders"],
            "exhausted_paths": ["db.search::abc"],
        },
        {
            "candidate_tables": ["orders", "customers"],
            "searched_terms": ["orders", "sales"],
            "exhausted_paths": ["db.search::abc", "db.search::def"],
        },
    )

    assert merged == {
        "candidate_tables": ["orders", "customers"],
        "searched_terms": ["orders", "sales"],
        "exhausted_paths": ["db.search::abc", "db.search::def"],
    }


def test_emit_artifacts_from_observation_resolves_existing_semantic_dependencies():
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
        "datasource_id": "ds-test",
        "execution": {
            "success": True,
            "columns": ["value"],
            "rows": [{"value": 1}],
            "rowCount": 1,
            "safe_sql": "SELECT 1",
        },
        "safety": {"can_execute": True},
        "artifacts": [
            {"id": "sql-physical-id", "semantic_id": "sql_candidate", "type": "sql"},
            {"id": "safety-physical-id", "semantic_id": "safety_report", "type": "safety"},
        ],
    }

    artifacts = emit_artifacts_from_observation(
        "sql.execute_readonly",
        observation,
        state,
        "run-artifacts",
    )

    result_view = next(artifact for artifact in artifacts if artifact.type == "result_view")
    assert result_view.depends_on == ["sql-physical-id", "safety-physical-id"]


def test_rebuild_context_pack_returns_pack_without_mutating_inputs():
    state = {
        "datasource_id": "ds-test",
        "workspace_context": {"selected_table_names": ["orders"]},
        "messages": [{"content": "show orders"}],
    }
    updates = {"sql": "SELECT 1"}

    context_update = rebuild_context_pack(state, updates)

    assert context_update["context_pack"]["workspace"]["selected_tables"] == ["orders"]
    assert context_update["context_pack"]["sql"]["sql"] == "SELECT 1"
    assert "context_pack" not in state
    assert "context_pack" not in updates


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
