from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest
from engine.agent_core.types import ResultProfile
from engine.agent_core.answer import synthesize_agent_answer


def test_synthesize_agent_answer_fallback():
    # No credentials, should fallback to default behavior
    result = synthesize_agent_answer(
        question="What is the total sales?",
        query_plan=None,
        sql="SELECT SUM(sales) FROM orders",
        safety={"can_execute": True},
        execution={
            "success": True,
            "rowCount": 50,
            "columns": ["total_sales"],
            "rows": [[10000]],
        },
        result_profile=ResultProfile(
            row_count=50,
            notable_facts=["Total sales is 10000."],
            anomalies=[],
            limitations=[],
        ),
    )
    assert result.answer.startswith("Total sales is 10000.")
    assert "result_table" in [ev.artifact_id for ev in result.evidence]


@patch("engine.llm.get_chat_model")
def test_synthesize_agent_answer_with_llm(mock_get_chat_model):
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "This is a detailed AI generated business analysis."
    mock_model.invoke.return_value = mock_response
    mock_get_chat_model.return_value = mock_model

    # With credentials (or DBFOX_TESTING)
    with patch.dict("os.environ", {"DBFOX_TESTING": "1"}):
        result = synthesize_agent_answer(
            question="What is the total sales?",
            query_plan=None,
            sql="SELECT SUM(sales) FROM orders",
            safety={"can_execute": True},
            execution={
                "success": True,
                "rowCount": 50,
                "columns": ["total_sales"],
                "rows": [[10000]],
            },
            result_profile=ResultProfile(
                row_count=50,
                notable_facts=["Total sales is 10000."],
                anomalies=[],
                limitations=[],
            ),
        )

    assert result.answer == "This is a detailed AI generated business analysis."
    # Since we mocked the model, it should be invoked with HumanMessage and SystemMessage
    mock_model.invoke.assert_called_once()
