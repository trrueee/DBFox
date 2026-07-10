from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from engine.agent_core.answer import synthesize_agent_answer


def _analysis_units() -> list[dict[str, object]]:
    return [
        {
            "id": "unit-orders",
            "sql": "SELECT COUNT(*) AS count FROM orders",
            "execution": {
                "success": True,
                "rowCount": 1,
                "columns": ["count"],
                "rows": [[10]],
            },
        }
    ]


def test_synthesize_agent_answer_streams_delta_chunks_from_injected_model() -> None:
    model = MagicMock()
    model.stream.return_value = [
        SimpleNamespace(content="There are "),
        SimpleNamespace(content="10 orders."),
    ]
    deltas: list[str] = []

    result = synthesize_agent_answer(
        "How many orders?",
        analysis_units=_analysis_units(),
        model=model,
        emit_answer_delta=deltas.append,
    )

    assert deltas == ["There are ", "10 orders."]
    assert result.answer == "There are 10 orders."
    model.stream.assert_called_once()
    model.invoke.assert_not_called()


def test_synthesize_agent_answer_falls_back_to_invoke_when_stream_fails() -> None:
    model = MagicMock()

    def broken_stream(_messages):
        yield SimpleNamespace(content="partial")
        raise RuntimeError("stream failure")

    model.stream.side_effect = broken_stream
    model.invoke.return_value = SimpleNamespace(content="complete answer")
    deltas: list[str] = []

    result = synthesize_agent_answer(
        "How many orders?",
        analysis_units=_analysis_units(),
        model=model,
        emit_answer_delta=deltas.append,
    )

    assert deltas == ["partial"]
    assert result.answer == "complete answer"
    model.invoke.assert_called_once()


def test_synthesize_agent_answer_uses_a_safe_fallback_without_a_model() -> None:
    result = synthesize_agent_answer("How many orders?", analysis_units=_analysis_units())

    assert "1" in result.answer
    assert result.evidence[0].value == 1


def test_synthesize_direct_answer_uses_injected_model() -> None:
    model = MagicMock()
    model.invoke.return_value = SimpleNamespace(content="I can analyze databases.")

    result = synthesize_agent_answer(
        "What can you do?",
        analysis_units=[],
        mode="direct",
        model=model,
    )

    assert result.answer == "I can analyze databases."
    model.invoke.assert_called_once()
