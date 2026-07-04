from __future__ import annotations

from datetime import UTC, datetime

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage

from engine.agent.nodes.turn_node import (
    build_turn_reset_update,
    extract_sql_backed_refs,
    finalize_turn,
    plan_message_compaction,
)
from engine.agent_core.memory import sql_fingerprint
from engine.agent_core.types import AgentApprovalRecord, AgentRunRequest, AgentRunResponse
from engine.tools.runtime import ToolRegistry
from engine.models import AgentSession, AgentSessionMemory, DataSource, ReusableSQL


class Message:
    def __init__(self, id: str, type: str = "human") -> None:
        self.id = id
        self.type = type


class FakeApprovalEventStore:
    def __init__(self) -> None:
        self.created_approvals: list[dict] = []

    def create_approval(self, **kwargs):
        self.created_approvals.append(kwargs)
        return AgentApprovalRecord(
            id="approval-progress-event-store",
            run_id=kwargs["run_id"],
            session_id=kwargs["session_id"],
            step_name=kwargs["step_name"],
            tool_name=kwargs["tool_name"],
            status="pending",
            risk_level=kwargs["risk_level"],
            reason=kwargs["reason"],
            policy_decision=kwargs["policy_decision"],
            requested_action=kwargs["requested_action"],
            created_at=datetime.now(UTC),
        )


class FakeMemoryProjectionStore:
    def __init__(self) -> None:
        self.saved_projection: dict | None = None

    def load_session_memory(self, session_id: str):
        assert session_id == "session_projection_boundary"
        return {
            "datasource_id": "ds_projection_boundary",
            "conversation_summary": "来自 projection store 的摘要",
            "artifact_ref_index": [{"artifact_id": "artifact_projection"}],
            "sql_ref_index": [],
        }

    def list_reusable_sqls(self, *, datasource_id: str, limit: int = 5):
        assert datasource_id == "ds_projection_boundary"
        return [
            {
                "safe_sql": "SELECT 1",
                "tables": [],
                "columns": [],
            }
        ]

    def save_run_projection(self, response, *, final_state, datasource_id):
        self.saved_projection = {
            "response": response,
            "final_state": final_state,
            "datasource_id": datasource_id,
        }


def test_build_turn_reset_update_clears_turn_runtime_without_touching_durable_memory() -> None:
    update = build_turn_reset_update(
        run_id="run_2",
        session_id="session_1",
        datasource_id="ds_1",
        question="continue the analysis",
        execute=True,
        max_steps=50,
    )

    assert update["run_id"] == "run_2"
    assert update["thread_id"] == "session_1"
    assert update["session_id"] == "session_1"
    assert update["messages"] == [{"role": "user", "content": "continue the analysis"}]
    assert update["pending_tool_calls"] == []
    assert update["allowed_tool_calls"] == []
    assert update["blocked_tool_calls"] == []
    assert update["last_tool_results"] == []
    assert update["sql"] is None
    assert update["safety"] is None
    assert update["execution"] is None
    assert update["repair_mode"] is False
    assert update["revision_count"] == 0
    assert update["trace_events"] == [{"__clear__": True}]
    assert "conversation_summary" not in update


def test_plan_message_compaction_waits_until_batch_threshold() -> None:
    messages = [Message(f"m{i}") for i in range(1, 7)]

    plan = plan_message_compaction(messages, keep_recent=4, batch_size=3)

    assert plan.to_summarize == []
    assert plan.remove_messages == []


def test_plan_message_compaction_compacts_oldest_batch_only() -> None:
    messages = [Message(f"m{i}") for i in range(1, 9)]

    plan = plan_message_compaction(messages, keep_recent=4, batch_size=3)

    assert [message.id for message in plan.to_summarize] == ["m1", "m2", "m3"]
    assert [message.id for message in plan.remove_messages] == ["m1", "m2", "m3"]


def test_agent_service_uses_session_id_as_graph_thread(monkeypatch) -> None:
    from engine.agent.app import service as service_module

    captured: dict[str, object] = {}

    class FakeSnapshot:
        interrupts = []
        values = {
            "status": "completed",
            "messages": [],
            "artifacts": [],
            "trace_events": [],
            "runtime_events": [],
        }

    class FakeApp:
        def stream(self, input_value, *, config, stream_mode):
            captured["config"] = config
            yield {"finalize": {"status": "completed"}}

        def get_state(self, config):
            return FakeSnapshot()

    class FakeDb:
        def rollback(self) -> None:
            pass

        def commit(self) -> None:
            pass

    monkeypatch.setattr(service_module, "build_dbfox_react_graph", lambda **_: FakeApp())

    service = service_module.DBFoxAgentService(FakeDb())
    service._persist_events = False
    req = AgentRunRequest(
        datasource_id="ds_1",
        question="hello",
        session_id="session_1",
        conversation_id="session_1",
    )

    list(service.run_iter(req))

    config = captured["config"]
    assert isinstance(config, dict)
    assert config["configurable"]["thread_id"] == "session_1"


def test_extract_sql_backed_refs_keeps_safe_sql_for_follow_up_analysis() -> None:
    state = {
        "run_id": "run_1",
        "datasource_id": "ds_1",
        "artifacts": [
            {
                "id": "art_result_1",
                "type": "result_view",
                "title": "Tool usage trend",
                "payload": {
                    "storageMode": "sql_backed",
                    "datasourceId": "ds_1",
                    "sourceSqlArtifactKey": "art_sql_1",
                    "sourceSqlSemanticKey": "sql_candidate_1",
                    "sourceSql": "SELECT day, usage_count FROM ai_tool_invocations",
                    "safeSql": "SELECT day, usage_count FROM ai_tool_invocations",
                    "columns": ["day", "usage_count"],
                    "previewRows": [{"day": "2026-06-01", "usage_count": 12}],
                    "rowCount": 31,
                    "latencyMs": 27,
                    "used_tables": ["ai_tool_invocations"],
                },
            },
            {
                "id": "art_error_1",
                "type": "error",
                "title": "Failed SQL",
                "payload": {"safeSql": "SELECT broken"},
            },
        ],
    }

    artifact_refs, sql_refs = extract_sql_backed_refs(state, now="2026-06-23T00:00:00Z")

    assert len(artifact_refs) == 1
    assert artifact_refs[0]["id"] == "mem_result_art_result_1"
    assert artifact_refs[0]["artifact_id"] == "art_result_1"
    assert artifact_refs[0]["source_sql_artifact_id"] == "art_sql_1"
    assert artifact_refs[0]["source_sql_semantic_id"] == "sql_candidate_1"
    assert artifact_refs[0]["source_sql"] == "SELECT day, usage_count FROM ai_tool_invocations"
    assert artifact_refs[0]["safe_sql"] == "SELECT day, usage_count FROM ai_tool_invocations"
    assert artifact_refs[0]["columns"] == ["day", "usage_count"]
    assert artifact_refs[0]["row_count"] == 31

    assert len(sql_refs) == 1
    assert sql_refs[0]["kind"] == "sql_ref"
    assert sql_refs[0]["source_sql_artifact_id"] == "art_sql_1"
    assert sql_refs[0]["source_sql_semantic_id"] == "sql_candidate_1"
    assert sql_refs[0]["source_sql"] == "SELECT day, usage_count FROM ai_tool_invocations"
    assert sql_refs[0]["safe_sql"] == "SELECT day, usage_count FROM ai_tool_invocations"
    assert sql_refs[0]["tables"] == ["ai_tool_invocations"]


def test_extract_sql_backed_refs_keeps_semantic_sql_id_separate_from_artifact_id() -> None:
    state = {
        "run_id": "run_semantic_only",
        "datasource_id": "ds_1",
        "artifacts": [
            {
                "id": "art_result_semantic_only",
                "type": "result_view",
                "title": "Semantic only result",
                "payload": {
                    "storageMode": "sql_backed",
                    "datasourceId": "ds_1",
                    "sourceSqlSemanticKey": "sql_candidate_semantic_only",
                    "sourceSql": "SELECT day, usage_count FROM ai_tool_invocations",
                    "safeSql": "SELECT day, usage_count FROM ai_tool_invocations",
                    "columns": ["day", "usage_count"],
                },
            }
        ],
    }

    artifact_refs, sql_refs = extract_sql_backed_refs(state, now="2026-06-23T00:00:00Z")

    assert artifact_refs[0]["source_sql_artifact_id"] is None
    assert artifact_refs[0]["source_sql_semantic_id"] == "sql_candidate_semantic_only"
    assert sql_refs[0]["source_sql_artifact_id"] is None
    assert sql_refs[0]["source_sql_semantic_id"] == "sql_candidate_semantic_only"


def test_extract_sql_backed_refs_accepts_legacy_source_artifact_keys() -> None:
    state = {
        "run_id": "run_legacy",
        "datasource_id": "ds_1",
        "artifacts": [
            {
                "id": "art_result_legacy",
                "type": "result_view",
                "title": "Legacy result",
                "payload": {
                    "storageMode": "sql_backed",
                    "datasourceId": "ds_1",
                    "sourceSqlArtifactId": "legacy_sql_artifact",
                    "sourceSqlSemanticId": "legacy_sql_candidate",
                    "sourceSql": "SELECT id FROM orders",
                    "safeSql": "SELECT id FROM orders",
                    "columns": ["id"],
                },
            }
        ],
    }

    artifact_refs, sql_refs = extract_sql_backed_refs(state, now="2026-06-23T00:00:00Z")

    assert artifact_refs[0]["source_sql_artifact_id"] == "legacy_sql_artifact"
    assert artifact_refs[0]["source_sql_semantic_id"] == "legacy_sql_candidate"
    assert sql_refs[0]["source_sql_artifact_id"] == "legacy_sql_artifact"
    assert sql_refs[0]["source_sql_semantic_id"] == "legacy_sql_candidate"


def test_finalize_turn_upserts_sql_backed_refs_without_duplicate_memory_items() -> None:
    state = {
        "run_id": "run_2",
        "datasource_id": "ds_1",
        "artifact_ref_index": [
            {
                "id": "mem_existing",
                "kind": "result_view_ref",
                "datasource_id": "ds_1",
                "sql_fingerprint": "placeholder",
                "usage_count": 1,
                "last_used_at": "2026-06-22T00:00:00Z",
            }
        ],
        "artifacts": [
            {
                "id": "art_result_2",
                "type": "result_view",
                "title": "Tool usage trend",
                "payload": {
                        "storageMode": "sql_backed",
                        "datasourceId": "ds_1",
                        "sourceSqlArtifactKey": "art_sql_2",
                        "sourceSqlSemanticKey": "sql_candidate_2",
                    "safeSql": "SELECT day, usage_count FROM ai_tool_invocations",
                    "columns": ["day", "usage_count"],
                    "previewRows": [],
                    "rowCount": 31,
                },
            }
        ],
    }
    first_refs, _ = extract_sql_backed_refs(state, now="2026-06-23T00:00:00Z")
    state["artifact_ref_index"][0]["sql_fingerprint"] = first_refs[0]["sql_fingerprint"]

    update = finalize_turn(state)

    refs = [ref for ref in update["artifact_ref_index"] if not ref.get("__clear__")]
    assert refs[0]["id"] == "mem_existing"
    assert refs[0]["usage_count"] == 2
    assert len(refs) == 1


def test_finalize_turn_records_recent_turn_without_artifacts() -> None:
    update = finalize_turn(
        {
            "run_id": "run_recent_1",
            "question": "你刚才干什么了",
            "answer": {"answer": "我刚才分析了工具调用趋势。"},
            "artifacts": [],
            "recent_turns": [],
        }
    )

    recent_turns = [item for item in update["recent_turns"] if not item.get("__clear__")]
    assert recent_turns == [
        {
            "run_id": "run_recent_1",
            "question": "你刚才干什么了",
            "answer": "我刚才分析了工具调用趋势。",
            "sql_fingerprints": [],
            "source_sql_artifact_ids": [],
            "artifact_ids": [],
        }
    ]


def test_finalize_turn_records_result_and_sql_artifact_ids_for_current_task_memory() -> None:
    safe_sql = "SELECT day, usage_count FROM ai_tool_invocations"

    update = finalize_turn(
        {
            "run_id": "run_recent_sql_backed",
            "datasource_id": "ds_1",
            "question": "分析每日调用",
            "answer": {"answer": "完成。"},
            "artifacts": [
                {
                    "id": "art_result_recent",
                    "type": "result_view",
                    "title": "Daily usage",
                    "payload": {
                        "storageMode": "sql_backed",
                        "datasourceId": "ds_1",
                        "sourceSqlArtifactKey": "art_sql_recent",
                        "sourceSql": safe_sql,
                        "safeSql": safe_sql,
                        "columns": [{"name": "day"}, {"name": "usage_count"}],
                        "previewRows": [{"day": "2026-06-01", "usage_count": 12}],
                        "rowCount": 31,
                        "used_tables": ["ai_tool_invocations"],
                    },
                }
            ],
            "recent_turns": [],
        }
    )

    recent_turns = [item for item in update["recent_turns"] if not item.get("__clear__")]
    assert recent_turns[0]["artifact_ids"] == ["art_result_recent"]
    assert recent_turns[0]["source_sql_artifact_ids"] == ["art_sql_recent"]
    assert recent_turns[0]["sql_fingerprints"] == [sql_fingerprint(safe_sql)]

    assert update["active_task"]["current_result_artifact_id"] == "art_result_recent"
    assert update["active_task"]["current_source_sql_artifact_id"] == "art_sql_recent"
    assert update["active_task"]["current_sql_fingerprint"] == sql_fingerprint(safe_sql)


def test_finalize_turn_batch_compacts_old_recent_turns_into_summary() -> None:
    existing_turns = [
        {
            "run_id": f"run_{idx}",
            "question": f"问题 {idx}",
            "answer": f"回答 {idx}",
            "artifact_ids": [f"result_{idx}"],
            "source_sql_artifact_ids": [f"sql_{idx}"],
            "sql_fingerprints": [f"fp_{idx}"],
        }
        for idx in range(1, 7)
    ]

    update = finalize_turn(
        {
            "run_id": "run_7",
            "question": "继续",
            "final_answer": {"answer": "新的回答"},
            "artifacts": [],
            "recent_turns": existing_turns,
            "conversation_summary": "此前用户在分析工具使用。",
        }
    )

    recent_turns = [item for item in update["recent_turns"] if not item.get("__clear__")]
    assert [turn["run_id"] for turn in recent_turns] == ["run_4", "run_5", "run_6", "run_7"]
    assert "此前用户在分析工具使用。" in update["conversation_summary"]
    assert "问题 1 -> 回答 1" in update["conversation_summary"]
    assert "artifact_ids=result_1" in update["conversation_summary"]
    assert "source_sql_artifact_ids=sql_1" in update["conversation_summary"]
    assert "sql_fingerprints=fp_1" in update["conversation_summary"]
    assert "问题 3 -> 回答 3" in update["conversation_summary"]
    assert "问题 4 -> 回答 4" not in update["conversation_summary"]


def test_recent_turn_compaction_prefers_llm_summary(monkeypatch) -> None:
    from engine.agent.nodes import turn_node

    existing_turns = [
        {
            "run_id": f"run_{idx}",
            "question": f"question {idx}",
            "answer": f"answer {idx}",
            "artifact_ids": [f"result_{idx}"],
            "source_sql_artifact_ids": [f"sql_{idx}"],
            "sql_fingerprints": [f"fp_{idx}"],
        }
        for idx in range(1, 8)
    ]
    captured: dict[str, object] = {}

    def fake_summarize(conversation_summary, batch, *, model_name=None, api_key=None, api_base=None):
        captured["conversation_summary"] = conversation_summary
        captured["batch"] = batch
        captured["model_name"] = model_name
        captured["api_key"] = api_key
        captured["api_base"] = api_base
        return "LLM compressed summary"

    monkeypatch.setattr(turn_node, "_llm_summarize_turn_batch", fake_summarize)

    summary, kept = turn_node._compact_recent_turns(
        "Previous summary",
        existing_turns,
        model_name="test-model",
        api_key="sk-test",
        api_base="http://example.test/v1",
    )

    assert summary == "Previous summary\nLLM compressed summary"
    assert [turn["run_id"] for turn in kept] == ["run_4", "run_5", "run_6", "run_7"]
    assert [turn["run_id"] for turn in captured["batch"]] == ["run_1", "run_2", "run_3"]
    assert captured["model_name"] == "test-model"
    assert captured["api_key"] == "sk-test"
    assert captured["api_base"] == "http://example.test/v1"


def test_finalize_turn_removes_old_langgraph_messages_by_batch() -> None:
    messages = [
        HumanMessage(content=f"问题 {idx}", id=f"msg_{idx}")
        if idx % 2
        else AIMessage(content=f"回答 {idx}", id=f"msg_{idx}")
        for idx in range(1, 9)
    ]

    update = finalize_turn(
        {
            "run_id": "run_messages",
            "question": "继续",
            "answer": {"answer": "新的回答"},
            "messages": messages,
            "artifacts": [],
        }
    )

    removals = update["messages"]
    assert [message.id for message in removals] == ["msg_1", "msg_2", "msg_3"]
    assert all(isinstance(message, RemoveMessage) for message in removals)
    assert update["summary_cursor_message_id"] == "msg_3"


def test_agent_service_persists_graph_memory_projection(db_session, monkeypatch) -> None:
    from engine.agent.app import service as service_module

    datasource = DataSource(
        id="ds_service_memory",
        name="Service Memory",
        db_type="sqlite",
        host="localhost",
        port=0,
        database_name=":memory:",
        username="",
        password_ciphertext="",
        password_nonce="",
        password_key_version="v1",
        status="active",
    )
    db_session.add(datasource)
    db_session.commit()

    safe_sql = "SELECT tool_name, COUNT(*) AS usage_count FROM ai_tool_invocations GROUP BY tool_name"
    fingerprint = sql_fingerprint(safe_sql)
    final_state = {
        "status": "completed",
        "messages": [],
        "artifacts": [],
        "trace_events": [],
        "runtime_events": [],
        "answer": {"answer": "完成。"},
        "conversation_summary": "用户正在分析工具调用次数。",
        "artifact_ref_index": [
            {
                "id": "mem_result_1",
                "kind": "result_view_ref",
                "datasource_id": datasource.id,
                "artifact_id": "result_view_1",
                "source_sql_artifact_id": "sql_1",
                "safe_sql": safe_sql,
                "sql_fingerprint": fingerprint,
                "columns": ["tool_name", "usage_count"],
                "last_used_at": "2026-06-23T00:00:00Z",
            }
        ],
        "sql_ref_index": [
            {
                "id": "mem_sql_1",
                "kind": "sql_ref",
                "datasource_id": datasource.id,
                "artifact_id": "result_view_1",
                "source_sql_artifact_id": "sql_1",
                "safe_sql": safe_sql,
                "sql_fingerprint": fingerprint,
                "tables": ["ai_tool_invocations"],
                "columns": ["tool_name", "usage_count"],
                "purpose": "tool usage count",
                "verified": True,
                "last_used_at": "2026-06-23T00:00:00Z",
            }
        ],
    }

    class FakeSnapshot:
        interrupts = []
        values = final_state

    class FakeApp:
        def stream(self, input_value, *, config, stream_mode):
            yield {"finalize": final_state}

        def get_state(self, config):
            return FakeSnapshot()

    monkeypatch.setattr(service_module, "build_dbfox_react_graph", lambda **_: FakeApp())

    service = service_module.DBFoxAgentService(db_session)
    req = AgentRunRequest(
        datasource_id=datasource.id,
        question="分析工具调用次数",
        session_id="session_service_memory",
        conversation_id="session_service_memory",
    )

    list(service.run_iter(req))

    memory = (
        db_session.query(AgentSessionMemory)
        .filter(AgentSessionMemory.session_id == "session_service_memory")
        .one()
    )
    reusable = db_session.query(ReusableSQL).filter(ReusableSQL.data_source_id == datasource.id).one()

    assert memory.conversation_summary == "用户正在分析工具调用次数。"
    assert "artifact_ref_index" in memory.memory_json
    assert reusable.safe_sql == safe_sql
    assert reusable.sql_fingerprint == fingerprint
    assert reusable.source_artifact_id == "result_view_1"
    assert reusable.source_sql_artifact_id == "sql_1"
    assert reusable.usage_count == 1
    assert reusable.verified is True


def test_final_response_persistence_survives_memory_projection_failure() -> None:
    from engine.agent.app.memory_projection import AgentMemoryProjectionCoordinator
    from engine.agent.app.persistence_coordinator import AgentPersistenceCoordinator

    class FakeDb:
        def __init__(self) -> None:
            self.commits = 0
            self.rollbacks = 0

        def commit(self) -> None:
            self.commits += 1

        def rollback(self) -> None:
            self.rollbacks += 1

    class FakeEventStore:
        def __init__(self) -> None:
            self.completed: list[str] = []

        def complete_run(self, response: AgentRunResponse) -> None:
            self.completed.append(response.run_id)

    class FailingMemoryProjectionStore:
        def save_run_projection(self, response, *, final_state, datasource_id):
            raise RuntimeError("memory projection unavailable")

    db = FakeDb()
    event_store = FakeEventStore()
    coordinator = AgentPersistenceCoordinator(
        db,
        event_store,
        AgentMemoryProjectionCoordinator(FailingMemoryProjectionStore()),
        enabled=True,
    )
    response = AgentRunResponse(
        run_id="run-memory-failure",
        session_id="session-memory-failure",
        conversation_id="session-memory-failure",
        success=True,
        status="completed",
        question="分析订单",
        answer={"answer": "完成"},
    )

    event = coordinator.finalize(
        lambda event_type, **kwargs: {"type": event_type, **kwargs},
        response,
        final_state={"status": "completed"},
        datasource_id="ds-memory-failure",
    )

    assert event["type"] == "agent.run.completed"
    assert event_store.completed == ["run-memory-failure"]
    assert db.commits == 1
    assert db.rollbacks == 0


def test_agent_service_initial_state_restores_persisted_session_memory(db_session) -> None:
    from engine.agent.app.service import DBFoxAgentService
    from engine.agent_core.persistence import save_session_memory

    datasource = DataSource(
        id="ds_service_memory_restore",
        name="Service Memory Restore",
        db_type="sqlite",
        host="localhost",
        port=0,
        database_name=":memory:",
        username="",
        password_ciphertext="",
        password_nonce="",
        password_key_version="v1",
        status="active",
    )
    session = AgentSession(
        id="session_service_memory_restore",
        datasource_id=datasource.id,
        title="工具调用分析",
    )
    db_session.add_all([datasource, session])
    db_session.commit()

    safe_sql = "SELECT tool_name, COUNT(*) AS usage_count FROM ai_tool_invocations GROUP BY tool_name"
    fingerprint = sql_fingerprint(safe_sql)
    save_session_memory(
        db_session,
        session_id=session.id,
        datasource_id=datasource.id,
        payload={
            "conversation_summary": "用户正在分析工具调用趋势。",
            "summary_cursor_message_id": "msg_9",
            "artifact_ref_index": [
                {
                    "id": "mem_result_restore",
                    "kind": "result_view_ref",
                    "datasource_id": datasource.id,
                    "artifact_id": "result_restore",
                    "safe_sql": safe_sql,
                    "sql_fingerprint": fingerprint,
                    "columns": ["tool_name", "usage_count"],
                }
            ],
            "sql_ref_index": [
                {
                    "id": "mem_sql_restore",
                    "kind": "sql_ref",
                    "datasource_id": datasource.id,
                    "safe_sql": safe_sql,
                    "sql_fingerprint": fingerprint,
                    "tables": ["ai_tool_invocations"],
                    "columns": ["tool_name", "usage_count"],
                }
            ],
            "active_task": {
                "current_result_ref_id": "mem_result_restore",
                "last_successful_run_id": "run_previous",
            },
        },
    )
    db_session.commit()

    service = DBFoxAgentService(db_session)
    req = AgentRunRequest(
        datasource_id=datasource.id,
        question="继续分析",
        session_id=session.id,
        conversation_id=session.id,
    )

    state = service.context_builder.build_initial_state(
        req,
        run_id="run_restore",
        session_id=session.id,
    )

    assert state["conversation_summary"] == "用户正在分析工具调用趋势。"
    assert state["summary_cursor_message_id"] == "msg_9"
    assert state["artifact_ref_index"][0]["artifact_id"] == "result_restore"
    assert state["sql_ref_index"][0]["safe_sql"] == safe_sql
    assert state["active_task"]["current_result_ref_id"] == "mem_result_restore"
    assert state["question"] == "继续分析"


def test_agent_service_initial_state_recalls_datasource_reusable_sql(db_session) -> None:
    from engine.agent.app.service import DBFoxAgentService
    from engine.agent_core.persistence import upsert_reusable_sql

    datasource = DataSource(
        id="ds_service_reusable_sql",
        name="Service Reusable SQL",
        db_type="sqlite",
        host="localhost",
        port=0,
        database_name=":memory:",
        username="",
        password_ciphertext="",
        password_nonce="",
        password_key_version="v1",
        status="active",
    )
    other = DataSource(
        id="ds_service_reusable_sql_other",
        name="Other Reusable SQL",
        db_type="sqlite",
        host="localhost",
        port=0,
        database_name=":memory:",
        username="",
        password_ciphertext="",
        password_nonce="",
        password_key_version="v1",
        status="active",
    )
    db_session.add_all([datasource, other])
    db_session.commit()

    safe_sql = "SELECT COUNT(*) AS usage_count FROM ai_tool_invocations"
    upsert_reusable_sql(
        db_session,
        datasource_id=datasource.id,
        question="统计工具调用",
        safe_sql=safe_sql,
        purpose="tool invocation count",
        involved_tables=["ai_tool_invocations"],
        result_columns=["usage_count"],
        verified=True,
    )
    upsert_reusable_sql(
        db_session,
        datasource_id=other.id,
        question="其他数据源统计",
        safe_sql="SELECT COUNT(*) FROM users",
        verified=True,
    )
    db_session.commit()

    service = DBFoxAgentService(db_session)
    req = AgentRunRequest(
        datasource_id=datasource.id,
        question="继续看工具调用",
        session_id="session_service_reusable_sql",
        conversation_id="session_service_reusable_sql",
    )

    state = service.context_builder.build_initial_state(
        req,
        run_id="run_reusable",
        session_id=req.session_id,
    )

    assert len(state["reusable_sql_candidates"]) == 1
    assert state["reusable_sql_candidates"][0]["safe_sql"] == safe_sql
    assert state["reusable_sql_candidates"][0]["tables"] == ["ai_tool_invocations"]


def test_agent_service_initial_state_uses_memory_projection_store(monkeypatch) -> None:
    from engine.agent.app.context_builder import AgentContextBuilder
    from engine.agent.app.memory_projection import AgentMemoryProjectionCoordinator
    from engine.agent_core import persistence as agent_persistence

    def fail_load_session_memory(*_args, **_kwargs):
        raise AssertionError("service must not load session memory directly")

    def fail_list_reusable_sqls(*_args, **_kwargs):
        raise AssertionError("service must not list reusable SQLs directly")

    monkeypatch.setattr(agent_persistence, "load_session_memory", fail_load_session_memory)
    monkeypatch.setattr(agent_persistence, "list_reusable_sqls", fail_list_reusable_sqls)

    builder = AgentContextBuilder(
        object(),
        AgentMemoryProjectionCoordinator(FakeMemoryProjectionStore()),
    )

    state = builder.build_initial_state(
        AgentRunRequest(
            datasource_id="ds_projection_boundary",
            question="继续",
            session_id="session_projection_boundary",
        ),
        run_id="run_projection_boundary",
        session_id="session_projection_boundary",
    )

    assert state["conversation_summary"] == "来自 projection store 的摘要"
    assert state["artifact_ref_index"][0]["artifact_id"] == "artifact_projection"
    assert state["reusable_sql_candidates"][0]["safe_sql"] == "SELECT 1"


def test_agent_service_persists_memory_projection_through_store(monkeypatch) -> None:
    from engine.agent.app.memory_projection import AgentMemoryProjectionCoordinator
    from engine.agent_core import persistence as agent_persistence

    def fail_save_session_memory(*_args, **_kwargs):
        raise AssertionError("service must not save session memory directly")

    def fail_upsert_reusable_sql(*_args, **_kwargs):
        raise AssertionError("service must not upsert reusable SQL directly")

    monkeypatch.setattr(agent_persistence, "save_session_memory", fail_save_session_memory)
    monkeypatch.setattr(agent_persistence, "upsert_reusable_sql", fail_upsert_reusable_sql)

    store = FakeMemoryProjectionStore()
    memory_projection = AgentMemoryProjectionCoordinator(store)
    response = AgentRunResponse(
        run_id="run_projection_save",
        session_id="session_projection_save",
        success=True,
        status="completed",
        question="统计用户",
        artifacts=[],
    )
    final_state = {
        "conversation_summary": "保存到 projection store",
        "sql_ref_index": [
            {
                "safe_sql": "SELECT COUNT(*) FROM users",
                "question": "统计用户",
                "tables": ["users"],
                "columns": ["count"],
                "verified": True,
            }
        ],
    }

    memory_projection.save_run_projection(
        response,
        final_state=final_state,
        datasource_id="ds_projection_save",
    )

    assert store.saved_projection is not None
    assert store.saved_projection["response"].run_id == "run_projection_save"
    assert store.saved_projection["datasource_id"] == "ds_projection_save"


def test_progress_routes_confirmation_only_safety_to_approval(monkeypatch) -> None:
    from engine.agent.graph.routes import route_progress_output
    from engine.agent.nodes.progress_node import judge_progress
    from engine.agent_core import persistence as agent_persistence

    def fail_create_approval(*_args, **_kwargs):
        raise AssertionError("progress node must not write approvals directly")

    monkeypatch.setattr(agent_persistence, "create_approval", fail_create_approval)
    store = FakeApprovalEventStore()

    state = {
        "run_id": "run_confirm",
        "thread_id": "session_confirm",
        "session_id": "session_confirm",
        "datasource_id": "ds_confirm",
        "allowed_tool_groups": ["sql"],
        "safety": {
            "can_execute": True,
            "requires_confirmation": True,
            "safe_sql": "SELECT * FROM users LIMIT 1000",
            "original_sql": "SELECT * FROM users",
            "blocked_reasons": ["requires_confirmation"],
            "risk_level": "warning",
        },
    }

    update = judge_progress(
        state,
        {
            "configurable": {
                "thread_id": "session_confirm",
                "registry": ToolRegistry(),
                "db": object(),
                "event_store": store,
                "request": AgentRunRequest(datasource_id="ds_confirm", question="查用户"),
            }
        },
    )

    assert update["status"] == "waiting_approval"
    assert update["pending_approval"]["id"] == "approval-progress-event-store"
    assert update["pending_approval"]["tool_name"] == "sql.execute_readonly"
    action_args = update["pending_approval"]["requested_action"]["args"]
    assert action_args["safe_sql"] == "SELECT * FROM users LIMIT 1000"
    assert "sql" not in action_args
    assert store.created_approvals[0]["run_id"] == "run_confirm"
    routed_state = dict(state)
    routed_state.update(update)
    assert route_progress_output(routed_state) == "approval"
