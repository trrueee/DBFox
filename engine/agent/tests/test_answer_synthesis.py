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


@patch("engine.llm.get_chat_model")
def test_synthesize_agent_answer_emits_each_chunk_before_stream_finishes(mock_get_chat_model):
    class Chunk:
        def __init__(self, content: str) -> None:
            self.content = content

    deltas: list[str] = []

    def stream(_messages):
        yield Chunk("第一段")
        assert deltas == ["第一段"]
        yield Chunk("第二段")
        assert deltas == ["第一段", "第二段"]

    mock_model = MagicMock()
    mock_model.stream.side_effect = stream
    mock_get_chat_model.return_value = mock_model

    with patch.dict("os.environ", {"DBFOX_TESTING": "1"}):
        result = synthesize_agent_answer(
            question="How many orders?",
            analysis_units=[{
                "id": "unit-stream-timing",
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

    assert result.answer == "第一段第二段"
    mock_model.invoke.assert_not_called()


@patch("engine.llm.get_chat_model")
def test_synthesize_direct_answer_streams_without_query_fallback(mock_get_chat_model):
    class Chunk:
        def __init__(self, content: str) -> None:
            self.content = content

    mock_model = MagicMock()
    mock_model.stream.return_value = [Chunk("我可以"), Chunk("帮你分析数据库。")]
    mock_get_chat_model.return_value = mock_model
    deltas: list[str] = []

    with patch.dict("os.environ", {"DBFOX_TESTING": "1"}):
        result = synthesize_agent_answer(
            question="你可以帮我做什么？",
            analysis_units=[],
            mode="direct",
            context={
                "direct_context": "Model said it can answer without database tools.",
                "workspace_context": {"datasource_id": "ds-1"},
                "recent_turns": [{"question": "之前的问题", "answer": "之前的回答"}],
            },
            emit_answer_delta=deltas.append,
        )

    assert deltas == ["我可以", "帮你分析数据库。"]
    assert result.answer == "我可以帮你分析数据库。"
    assert "已完成查询" not in result.answer
    messages = mock_model.stream.call_args.args[0]
    assert "DBFox" in messages[0].content
    assert "数据库查询" in messages[0].content
    assert "SQL" in messages[0].content
    assert "图表" in messages[0].content
    assert "示例" in messages[0].content
    assert "基于大语言模型" in messages[0].content
    assert "不要编造具体模型厂商" in messages[0].content
    assert "不要只用一两句话带过" in messages[0].content
    assert "分组说明能力" in messages[0].content
    assert "主动给出可直接复制的示例问题" in messages[0].content
    assert "上一轮过程文本只是上下文" in messages[0].content
    assert "不要声称已经查询数据库" in messages[0].content
    assert "最终回答阶段" not in messages[0].content
    assert "内部节点" not in messages[0].content


@patch("engine.llm.get_chat_model")
def test_synthesize_agent_answer_falls_back_to_invoke_when_stream_fails(mock_get_chat_model):
    class Chunk:
        def __init__(self, content: str) -> None:
            self.content = content

    def broken_stream(_messages):
        yield Chunk("半句")
        raise RuntimeError("stream failed")

    mock_model = MagicMock()
    mock_model.stream.side_effect = broken_stream
    mock_response = MagicMock()
    mock_response.content = "完整答案"
    mock_model.invoke.return_value = mock_response
    mock_get_chat_model.return_value = mock_model
    deltas: list[str] = []

    with patch.dict("os.environ", {"DBFOX_TESTING": "1"}):
        result = synthesize_agent_answer(
            question="How many orders?",
            analysis_units=[{
                "id": "unit-stream-fallback",
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

    assert deltas == ["半句"]
    assert result.answer == "完整答案"
    mock_model.invoke.assert_called_once()


def test_synthesize_agent_answer_no_analysis_units_no_credentials():
    """No analysis units, no credentials — should use direct-answer fallback."""
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
    assert result.evidence == []


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
    assert "比较、评估、口径说明或设计判断" in system_content
    assert "Markdown 表格" in system_content
    assert "分层观察" in system_content
    assert "优质回答的共性" in system_content
    assert "不要照搬固定模板" in system_content
    assert "不要为了凑格式而使用表格" in system_content
    assert "表格写作规则" in system_content
    assert "不要在表格单元格里堆叠粗体标记" in system_content
    assert "不要使用 HTML <br>" in system_content
    assert "多个示例更适合放在表格外的短列表" in system_content
    assert "数据库结构或分表设计" in system_content
    assert "## 结论" not in system_content
    assert "## 建议" not in system_content
