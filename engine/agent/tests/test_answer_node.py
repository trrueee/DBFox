from __future__ import annotations

from unittest.mock import MagicMock

from engine.agent_core.types import AgentAnswer, AgentRunRequest
from engine.tools.dbfox_tools import register_dbfox_tools


def _config() -> dict:
    return {
        "configurable": {
            "thread_id": "session-answer-node",
            "registry": register_dbfox_tools(),
            "db": MagicMock(),
            "request": AgentRunRequest(datasource_id="ds-answer", question="你能做什么？"),
            "model_name": "fake-model",
            "api_key": "test-key",
            "api_base": None,
        }
    }


def test_answer_node_streams_direct_answer_without_persisted_context_mutation(monkeypatch):
    from engine.agent.nodes.answer_node import synthesize_answer

    captured: dict = {}
    deltas: list[str] = []

    def fake_writer():
        return deltas.append

    def fake_synthesize_agent_answer(**kwargs):
        captured.update(kwargs)
        kwargs["emit_answer_delta"]("我")
        kwargs["emit_answer_delta"]("可以")
        return AgentAnswer(answer="我可以分析数据库。")

    monkeypatch.setattr("engine.agent.nodes.answer_node._answer_delta_writer", fake_writer)
    monkeypatch.setattr(
        "engine.agent_core.answer.synthesize_agent_answer",
        fake_synthesize_agent_answer,
    )

    result = synthesize_answer(
        {
            "question": "你能做什么？",
            "messages": [{"role": "assistant", "content": "我可以直接回答这个产品问题。"}],
            "progress_decision": {"status": "ready_for_answer"},
            "workspace_context": {"datasource_id": "ds-answer"},
            "follow_up_context": {"previous_question": "之前问了什么"},
            "recent_turns": [{"question": "上轮", "answer": "上轮答案"}],
            "conversation_summary": "用户正在了解 DBFox 能力。",
            "analysis_units": [{"__clear__": True}],
            "answer": None,
            "final_answer": None,
        },
        _config(),
    )

    assert deltas == ["我", "可以"]
    assert result["answer"]["answer"] == "我可以分析数据库。"
    assert result["final_answer"]["answer"] == "我可以分析数据库。"
    assert "messages" not in result
    assert "recent_turns" not in result
    assert "conversation_summary" not in result
    assert captured["mode"] == "direct"
    assert captured["context"]["workspace_context"] == {"datasource_id": "ds-answer"}
    assert captured["context"]["recent_turns"] == [{"question": "上轮", "answer": "上轮答案"}]
    assert captured["context"]["direct_context"] == "我可以直接回答这个产品问题。"


def test_answer_node_uses_evidence_mode_when_analysis_units_exist(monkeypatch):
    from engine.agent.nodes.answer_node import synthesize_answer

    captured: dict = {}

    def fake_synthesize_agent_answer(**kwargs):
        captured.update(kwargs)
        return AgentAnswer(answer="订单共有 10 条。")

    monkeypatch.setattr("engine.agent.nodes.answer_node._answer_delta_writer", lambda: None)
    monkeypatch.setattr(
        "engine.agent_core.answer.synthesize_agent_answer",
        fake_synthesize_agent_answer,
    )

    result = synthesize_answer(
        {
            "question": "订单数是多少？",
            "progress_decision": {"status": "ready_for_answer"},
            "analysis_units": [{
                "id": "unit-orders",
                "sql": "SELECT COUNT(*) AS count FROM orders",
                "execution": {"success": True, "rowCount": 1, "columns": ["count"], "rows": [[10]]},
            }],
            "sql": "SELECT COUNT(*) AS count FROM orders",
            "execution": {"success": True, "rowCount": 1},
            "answer": None,
            "final_answer": None,
        },
        _config(),
    )

    assert result["answer"]["answer"] == "订单共有 10 条。"
    assert captured["mode"] == "evidence"
    assert captured["analysis_units"][0]["id"] == "unit-orders"
    assert captured["context"]["execution"] == {"success": True, "rowCount": 1}
