from engine.agent.app.event_mapper import trace_to_events
from engine.agent.app.service import DBFoxAgentService, _runtime_error_message
from engine.agent_core.events import EventEmitter


def test_event_emitter_can_emit_live_only_answer_delta():
    recorded = []
    emitter = EventEmitter("run-live", recorder=recorded.append)

    event = emitter.emit("agent.answer.delta", content="partial", persist=False)

    assert event.type == "agent.answer.delta"
    assert event.content == "partial"
    assert recorded == []


def test_custom_answer_delta_payload_maps_to_live_only_runtime_event():
    recorded = []
    emitter = EventEmitter("run-custom", recorder=recorded.append)
    service = DBFoxAgentService.__new__(DBFoxAgentService)

    event = service._custom_stream_event(
        emitter.emit,
        {"type": "agent.answer.delta", "content": "partial"},
    )

    assert event is not None
    assert event.type == "agent.answer.delta"
    assert event.content == "partial"
    assert recorded == []


def test_model_completed_trace_streams_visible_model_text(db_session):
    emitter = EventEmitter("run-model")

    events = list(trace_to_events(emitter.emit, {
        "type": "agent.model.completed",
        "content": "我先查看数据库里和 AI 工具相关的表。",
        "tool_calls": [{"name": "schema.list_tables", "args": {}, "id": "call-1"}],
    }))

    assert len(events) == 1
    assert events[0].type == "agent.progress.update"
    assert events[0].step == {
        "name": "model",
        "phase": "understanding",
        "status": "running",
        "summary": "我先查看数据库里和 AI 工具相关的表。",
        "tool_calls": ["schema.list_tables"],
    }


def test_model_completed_trace_streams_sanitized_thought_prefix(db_session):
    emitter = EventEmitter("run-model")

    events = list(trace_to_events(emitter.emit, {
        "type": "agent.model.completed",
        "content": "Thought: I should inspect the schema.",
        "tool_calls": [{"name": "db.search"}],
    }))

    assert len(events) == 1
    assert events[0].step["summary"] == "I should inspect the schema."


def test_tool_trace_events_include_user_visible_phase(db_session):
    emitter = EventEmitter("run-phase")

    events = list(trace_to_events(emitter.emit, {
        "type": "agent.tool.completed",
        "tool_name": "sql.execute_readonly",
        "payload": {
            "status": "success",
            "latency_ms": 42,
            "output": {"rowCount": 128},
        },
    }))

    assert len(events) == 1
    assert events[0].type == "agent.step.completed"
    assert events[0].step["phase"] == "executing"


def test_model_progress_events_include_understanding_phase(db_session):
    emitter = EventEmitter("run-phase")

    events = list(trace_to_events(emitter.emit, {
        "type": "agent.model.completed",
        "content": "我先理解问题。",
        "tool_calls": [{"name": "db.search"}],
    }))

    assert len(events) == 1
    assert events[0].step["phase"] == "understanding"


def test_runtime_llm_timeout_error_is_user_facing():
    message = _runtime_error_message(TimeoutError("Request timed out."))

    assert message == "LLM 响应超时，请检查模型服务网络、API Base 与模型可用性后重试。"


def test_runtime_non_llm_error_keeps_internal_context():
    message = _runtime_error_message(RuntimeError("stream boom"))

    assert message == "Internal agent error: stream boom"
