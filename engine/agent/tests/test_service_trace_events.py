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


def test_model_completed_trace_streams_sanitized_thought_prefix(db_session):
    emitter = EventEmitter("run-model")

    events = list(trace_to_events(emitter.emit, {
        "type": "agent.model.completed",
        "content": "Thought: I should inspect the schema.",
        "tool_calls": [{"name": "db.search"}],
    }))

    assert len(events) == 1
    assert events[0].step["summary"] == "I should inspect the schema."


def test_model_completed_with_empty_content_but_tool_calls_still_emits_summary(db_session):
    """When the LLM returns empty content with tool_calls (common with Qwen),
    the _with_visible_tool_call_content function injects synthetic content
    (e.g. '准备调用工具：db.query').  The trace event must carry a non-empty
    summary even when raw content was blank."""
    emitter = EventEmitter("run-empty")

    events = list(trace_to_events(emitter.emit, {
        "type": "agent.model.completed",
        "content": "准备调用工具：db.query",
        "tool_calls": [{"name": "db.query", "id": "call-1"}],
    }))

    assert len(events) == 1
    assert events[0].type == "agent.progress.update"
    assert events[0].step["summary"] == "准备调用工具：db.query"
    assert events[0].step["tool_calls"] == ["db.query"]


def test_model_completed_with_empty_content_and_no_tool_calls_emits_nothing(db_session):
    """If both content and tool_calls are empty, no progress event should emit."""
    emitter = EventEmitter("run-silent")

    events = list(trace_to_events(emitter.emit, {
        "type": "agent.model.completed",
        "content": "",
        "tool_calls": [],
    }))

    assert len(events) == 0


def test_with_visible_tool_call_content_injects_plan_text(db_session):
    """Unit test for _with_visible_tool_call_content: empty content + tool_calls
    must produce a non-empty content string."""
    from engine.agent.nodes.model_node import _with_visible_tool_call_content
    from langchain_core.messages import AIMessage, ToolCall

    # Simulate Qwen returning empty content with tool_calls
    raw = AIMessage(
        content="",
        tool_calls=[
            ToolCall(name="db.query", args={"sql": "SELECT 1"}, id="call-1"),
            ToolCall(name="db.search", args={"query": "users"}, id="call-2"),
        ],
    )
    result = _with_visible_tool_call_content(raw)
    assert result.content == "准备调用工具：db.query, db.search"


def test_with_visible_tool_call_content_preserves_existing_content(db_session):
    """When the model already returns content, it must not be overwritten."""
    from engine.agent.nodes.model_node import _with_visible_tool_call_content
    from langchain_core.messages import AIMessage, ToolCall

    raw = AIMessage(
        content="我先查看数据库结构。",
        tool_calls=[ToolCall(name="db.observe", args={}, id="call-1")],
    )
    result = _with_visible_tool_call_content(raw)
    assert result.content == "我先查看数据库结构。"
