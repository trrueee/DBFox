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
        "status": "running",
        "summary": "我先查看数据库里和 AI 工具相关的表。",
        "tool_calls": ["schema.list_tables"],
    }


def test_model_completed_trace_does_not_stream_thought_prefix(db_session):
    emitter = EventEmitter("run-model")

    events = list(trace_to_events(emitter.emit, {
        "type": "agent.model.completed",
        "content": "Thought: I should inspect the schema.",
        "tool_calls": [{"name": "db.search"}],
    }))

    assert len(events) == 1
    assert events[0].step["summary"] == "准备调用工具：db.search"
