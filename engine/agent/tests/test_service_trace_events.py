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


def test_with_visible_tool_call_content_injects_when_content_empty(db_session):
    """When the LLM returns empty content but has tool_calls (Qwen behavior),
    _with_visible_tool_call_content must inject a fallback text."""
    from engine.agent.nodes.model_node import _with_visible_tool_call_content
    from langchain_core.messages import AIMessage, ToolCall

    raw = AIMessage(
        content="",
        tool_calls=[
            ToolCall(name="db_observe", args={"mode": "overview"}, id="c1"),
            ToolCall(name="db_preview", args={"table": "users", "limit": 5}, id="c2"),
        ],
    )
    result = _with_visible_tool_call_content(raw)
    assert "准备调用工具" in result.content
    assert "observe" in result.content
    assert "preview" in result.content


def test_with_visible_tool_call_content_preserves_existing_content(db_session):
    """When the model already returns natural language content, keep it."""
    from engine.agent.nodes.model_node import _with_visible_tool_call_content
    from langchain_core.messages import AIMessage, ToolCall

    raw = AIMessage(
        content="连接超时了。让我尝试查看数据库的整体结构，看看有哪些表可用。",
        tool_calls=[ToolCall(name="db_observe", args={}, id="c1")],
    )
    result = _with_visible_tool_call_content(raw)
    assert result.content == "连接超时了。让我尝试查看数据库的整体结构，看看有哪些表可用。"
