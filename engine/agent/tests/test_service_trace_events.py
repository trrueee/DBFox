from engine.agent.app.event_mapper import trace_to_events
from engine.agent_core.events import EventEmitter


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
