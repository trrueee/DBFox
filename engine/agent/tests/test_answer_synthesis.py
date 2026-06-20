from __future__ import annotations

from unittest.mock import MagicMock, patch
from engine.agent_core.answer import synthesize_agent_answer


def test_synthesize_agent_answer_no_analysis_units_no_credentials():
    """No analysis units, no credentials — should fallback to default behavior."""
    result = synthesize_agent_answer(
        question="What is the total sales?",
        analysis_units=[],
    )
    assert "total sales" in result.answer.lower()
    assert len(result.key_findings) >= 1


def test_synthesize_agent_answer_empty_result_set():
    """Empty result set — should still produce a fallback answer."""
    result = synthesize_agent_answer(
        question="How many orders?",
        analysis_units=[{
            "id": "unit1",
            "sql": "SELECT COUNT(*) FROM orders",
            "execution": {
                "success": True,
                "rowCount": 0,
                "columns": ["count"],
                "rows": [],
            },
        }],
    )
    assert result.answer is not None
    assert len(result.key_findings) >= 1


@patch("engine.llm.get_chat_model")
def test_synthesize_agent_answer_with_llm(mock_get_chat_model):
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.content = (
        "## 结论\n"
        "共 **50** 条记录，总销售额 **10,000** 元。\n\n"
        "## 关键指标\n"
        "- **总销售额：10,000**\n\n"
        "## 分析\n销售趋势稳定。\n\n"
        "## 数据口径\n覆盖全部订单。\n\n"
        "## 建议\n持续监控。"
    )
    mock_model.invoke.return_value = mock_response
    mock_get_chat_model.return_value = mock_model

    with patch.dict("os.environ", {"DBFOX_TESTING": "1"}):
        result = synthesize_agent_answer(
            question="What is the total sales?",
            analysis_units=[{
                "id": "abc",
                "sql": "SELECT SUM(amount) FROM orders",
                "execution": {
                    "success": True,
                    "rowCount": 1,
                    "columns": ["total"],
                    "rows": [[10000]],
                },
            }],
        )

    assert "10,000" in result.answer
    assert len(result.key_findings) >= 1
    mock_model.invoke.assert_called_once()
