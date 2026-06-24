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
    AgentRunRequest,
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
            {"id": "sql-physical-id", "semantic_id": "sql_candidate_b1698e52", "type": "sql"},
            {"id": "safety-physical-id", "semantic_id": "safety_report_b1698e52", "type": "safety"},
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
    assert result_view.payload["sourceSqlSemanticId"] == "sql-physical-id"


def test_emit_artifacts_from_execution_creates_bound_sql_safety_and_result_view():
    observation = ToolObservation(
        name="sql.execute_readonly",
        status="success",
        input={"sql": "SELECT user_id, COUNT(*) AS calls FROM ai_tool_invocations GROUP BY user_id"},
        output={
            "status": "success",
            "success": True,
            "columns": ["user_id", "calls"],
            "rows": [{"user_id": "1", "calls": "12"}],
            "returned_rows": 1,
            "rowCount": 1,
            "safe_sql": "SELECT user_id, COUNT(*) AS calls FROM ai_tool_invocations GROUP BY user_id",
        },
        error=None,
        latency_ms=5,
    )
    state = {
        "datasource_id": "ds-test",
        "sql": "SELECT user_id, COUNT(*) AS calls FROM ai_tool_invocations GROUP BY user_id",
        "execution": {
            "success": True,
            "columns": ["user_id", "calls"],
            "rows": [{"user_id": "1", "calls": "12"}],
            "rowCount": 1,
            "safe_sql": "SELECT user_id, COUNT(*) AS calls FROM ai_tool_invocations GROUP BY user_id",
        },
        "safety": {
            "can_execute": True,
            "safe_sql": "SELECT user_id, COUNT(*) AS calls FROM ai_tool_invocations GROUP BY user_id",
        },
        "artifacts": [],
    }

    artifacts = emit_artifacts_from_observation(
        "sql.execute_readonly",
        observation,
        state,
        "run-bound-artifacts",
    )

    sql_artifact = next(artifact for artifact in artifacts if artifact.type == "sql")
    safety_artifact = next(artifact for artifact in artifacts if artifact.type == "safety")
    result_view = next(artifact for artifact in artifacts if artifact.type == "result_view")
    assert sql_artifact.semantic_id.startswith("sql_candidate_")
    assert safety_artifact.semantic_id.startswith("safety_report_")
    assert result_view.payload["sourceSqlSemanticId"] == sql_artifact.id
    assert result_view.depends_on == [sql_artifact.id, safety_artifact.id]


def test_emit_artifacts_from_observation_skips_empty_sql_execution_results():
    observation = ToolObservation(
        name="sql.execute_readonly",
        status="success",
        input={"sql": "SELECT id FROM users WHERE id = -1"},
        output={
            "status": "success",
            "success": True,
            "columns": ["id"],
            "rows": [],
            "returned_rows": 0,
            "rowCount": 0,
            "safe_sql": "SELECT id FROM users WHERE id = -1",
        },
        error=None,
        latency_ms=5,
    )
    state = {
        "datasource_id": "ds-test",
        "execution": {
            "success": True,
            "columns": ["id"],
            "rows": [],
            "rowCount": 0,
            "safe_sql": "SELECT id FROM users WHERE id = -1",
        },
        "safety": {"can_execute": True},
        "artifacts": [],
    }

    artifacts = emit_artifacts_from_observation(
        "sql.execute_readonly",
        observation,
        state,
        "run-empty-result",
    )

    assert artifacts == []


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


def test_service_persists_artifact_created_events_via_event_store():
    class FakeEventStore:
        def __init__(self):
            self.artifacts = []

        def append_artifact(self, session_id, run_id, artifact, index):
            self.artifacts.append((session_id, run_id, artifact, index))

    store = FakeEventStore()
    service = DBFoxAgentService.__new__(DBFoxAgentService)
    service._persist_events = True
    service.event_store = store

    artifact = AgentArtifact(
        id="artifact-1",
        type="result_view",
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

    assert store.artifacts == [("session-1", "run-1", artifact, 3)]


def test_service_initial_state_exposes_schema_linking_semantic_aliases(monkeypatch):
    def fake_context_bundle(_db, _req):
        return {
            "context_summary": "Datasource demo",
            "schema_linking": {
                "selected_tables": ["users"],
                "semantic_aliases_used": [
                    {"alias": "新注册用户", "target": "users.created_at", "source": "db"}
                ],
            },
            "semantic_context": {"aliases": []},
        }

    monkeypatch.setattr("engine.agent_core.workspace_context.build_agent_context_bundle", fake_context_bundle)
    service = DBFoxAgentService.__new__(DBFoxAgentService)
    service.db = object()
    service.memory_projection = SimpleNamespace(
        load_session_memory=lambda _session_id: None,
        list_reusable_sqls=lambda **_kwargs: [],
    )

    state = service._initial_state(
        AgentRunRequest(datasource_id="ds-test", question="分析新注册用户"),
        "run-semantic",
        "session-semantic",
    )

    assert state["context_summary"] == "Datasource demo"
    assert state["schema_context"]["selected_tables"] == ["users"]
    assert state["semantic_resolution"]["semantic_aliases_used"] == [
        {"alias": "新注册用户", "target": "users.created_at", "source": "db"}
    ]


def test_service_initial_state_exposes_state_namespaces(monkeypatch):
    monkeypatch.setattr(
        "engine.agent_core.workspace_context.build_agent_context_bundle",
        lambda _db, _req: {"context_summary": "Datasource demo"},
    )
    service = DBFoxAgentService.__new__(DBFoxAgentService)
    service.db = object()
    service.memory_projection = SimpleNamespace(
        load_session_memory=lambda _session_id: None,
        list_reusable_sqls=lambda **_kwargs: [],
    )

    state = service._initial_state(
        AgentRunRequest(datasource_id="ds-test", question="分析订单", execute=False),
        "run-namespaced",
        "session-namespaced",
    )

    assert state["run"] == {
        "run_id": "run-namespaced",
        "thread_id": "session-namespaced",
        "session_id": "session-namespaced",
        "datasource_id": "ds-test",
        "parent_run_id": None,
        "execute": False,
        "max_steps": 50,
        "step_count": 0,
        "status": "running",
        "error": None,
    }
    assert state["working"]["context_summary"] == "Datasource demo"
    assert state["working"]["semantic_resolution"] is None
    assert state["working"]["analysis_units"] == []
    assert state["tools"]["execution_mode"] == "suggest_only"
    assert state["tools"]["allowed_tool_groups"]
    assert state["tools"]["last_tool_results"] == []
    assert state["ui"]["artifacts"] == []
    assert state["ui"]["runtime_events"] == []


def test_service_merge_state_keeps_namespaces_in_sync():
    service = DBFoxAgentService.__new__(DBFoxAgentService)
    state = {
        "run_id": "run-sync",
        "thread_id": "session-sync",
        "session_id": "session-sync",
        "datasource_id": "ds-test",
        "execute": True,
        "max_steps": 50,
        "step_count": 0,
        "status": "running",
        "error": None,
        "semantic_resolution": None,
        "analysis_units": [],
        "allowed_tool_groups": ["db"],
        "allowed_tool_calls": [],
        "blocked_tool_calls": [],
        "pending_tool_calls": [],
        "last_tool_results": [],
        "artifacts": [],
        "trace_events": [],
        "runtime_events": [],
        "context_summary": "initial",
    }
    service._merge_state(
        state,
        {
            "step_count": 2,
            "status": "waiting_approval",
            "error": "needs approval",
            "allowed_tool_calls": [{"name": "sql.execute_readonly"}],
            "last_tool_results": [{"name": "sql.validate", "status": "success"}],
            "artifacts": [{"id": "artifact-1", "type": "sql"}],
            "runtime_events": [{"type": "agent.approval.required"}],
        },
    )

    assert state["run"]["step_count"] == 2
    assert state["run"]["status"] == "waiting_approval"
    assert state["run"]["error"] == "needs approval"
    assert state["tools"]["allowed_tool_calls"] == [{"name": "sql.execute_readonly"}]
    assert state["tools"]["last_tool_results"] == [{"name": "sql.validate", "status": "success"}]
    assert state["ui"]["artifacts"] == [{"id": "artifact-1", "type": "sql"}]
    assert state["ui"]["runtime_events"] == [{"type": "agent.approval.required"}]
