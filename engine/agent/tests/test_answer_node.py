from __future__ import annotations

from types import SimpleNamespace

from engine.agent_core.types import AgentAnswer, AgentRunRequest


def test_answer_node_passes_a_context_created_model_without_exposing_a_key(monkeypatch) -> None:
    from engine.agent.nodes import answer_node

    captured: dict[str, object] = {}
    model = object()
    context = SimpleNamespace(
        model_name="fake-model",
        request=AgentRunRequest(datasource_id="ds-answer", question="What can you do?"),
        has_llm_credentials=True,
        create_chat_model=lambda _options: model,
    )

    def fake_synthesize_agent_answer(**kwargs):
        captured.update(kwargs)
        return AgentAnswer(answer="I can analyze databases.")

    monkeypatch.setattr(answer_node, "graph_context", lambda _config: context)
    monkeypatch.setattr(answer_node, "_answer_delta_writer", lambda: None)
    monkeypatch.setattr("engine.agent_core.answer.synthesize_agent_answer", fake_synthesize_agent_answer)

    result = answer_node.synthesize_answer(
        {
            "question": "What can you do?",
            "messages": [],
            "analysis_units": [],
            "answer": None,
            "final_answer": None,
        },
        {"configurable": {}},
    )

    assert result["answer"]["answer"] == "I can analyze databases."
    assert captured["model"] is model
    assert "api_key" not in captured


def test_answer_node_uses_evidence_mode_when_analysis_units_exist(monkeypatch) -> None:
    from engine.agent.nodes import answer_node

    captured: dict[str, object] = {}
    context = SimpleNamespace(
        model_name="fake-model",
        request=AgentRunRequest(datasource_id="ds-answer", question="How many orders?"),
        has_llm_credentials=False,
    )

    def fake_synthesize_agent_answer(**kwargs):
        captured.update(kwargs)
        return AgentAnswer(answer="There are 10 orders.")

    monkeypatch.setattr(answer_node, "graph_context", lambda _config: context)
    monkeypatch.setattr(answer_node, "_answer_delta_writer", lambda: None)
    monkeypatch.setattr("engine.agent_core.answer.synthesize_agent_answer", fake_synthesize_agent_answer)

    result = answer_node.synthesize_answer(
        {
            "question": "How many orders?",
            "analysis_units": [
                {
                    "id": "unit-orders",
                    "execution": {"success": True, "rowCount": 1, "rows": [[10]]},
                }
            ],
            "answer": None,
            "final_answer": None,
        },
        {"configurable": {}},
    )

    assert result["answer"]["answer"] == "There are 10 orders."
    assert captured["mode"] == "evidence"
    assert captured["model"] is None
