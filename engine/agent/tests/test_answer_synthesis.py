from __future__ import annotations

from unittest.mock import MagicMock, patch
from engine.agent_core.answer import synthesize_agent_answer


@patch("engine.llm.get_chat_model")
def test_synthesize_agent_answer_streams_delta_chunks(mock_get_chat_model):
    class Chunk:
        def __init__(self, content: str) -> None:
            self.content = content

    mock_model = MagicMock()
    mock_model.stream.return_value = [Chunk("结论："), Chunk("共 10 条记录。")]
    mock_get_chat_model.return_value = mock_model
    deltas: list[str] = []

    with patch.dict("os.environ", {"DBFOX_TESTING": "1"}):
        result = synthesize_agent_answer(
            question="How many orders?",
            analysis_units=[{
                "id": "unit-stream",
                "sql": "SELECT COUNT(*) AS count FROM orders",
                "execution": {
                    "success": True,
                    "rowCount": 1,
                    "columns": ["count"],
                    "rows": [[10]],
                },
            }],
            emit_answer_delta=deltas.append,
        )

    assert deltas == ["结论：", "共 10 条记录。"]
    assert result.answer == "结论：共 10 条记录。"
    mock_model.stream.assert_called_once()
    mock_model.invoke.assert_not_called()


def test_synthesize_agent_answer_no_analysis_units_no_credentials():
    """No analysis units, no credentials — should fallback to default behavior."""
    with patch.dict("os.environ", {
        "OPENAI_API_KEY": "",
        "QWEN_API_KEY": "",
        "DBFOX_LLM_API_KEY": "",
        "DBFOX_TESTING": "",
    }):
        result = synthesize_agent_answer(
            question="What is the total sales?",
            analysis_units=[],
        )
    assert "total sales" in result.answer.lower()
    assert result.key_findings == []
    assert result.evidence[0].value == 0


def test_synthesize_agent_answer_empty_result_set():
    """Empty result set — should still produce a fallback answer."""
    with patch.dict("os.environ", {
        "OPENAI_API_KEY": "",
        "QWEN_API_KEY": "",
        "DBFOX_LLM_API_KEY": "",
        "DBFOX_TESTING": "",
    }):
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
    assert result.key_findings == []
    assert result.evidence[0].value == 0


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
    messages = mock_model.invoke.call_args.args[0]
    system_content = messages[0].content
    assert "自适应 Markdown" in system_content
    assert "不要强制使用固定章节" in system_content
    assert "## 结论" not in system_content
    assert "## 建议" not in system_content
