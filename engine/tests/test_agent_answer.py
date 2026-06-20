from __future__ import annotations

from engine.agent_core.answer import synthesize_agent_answer


def test_synthesize_agent_answer_uses_chinese_summary_for_small_results():
    answer = synthesize_agent_answer(
        question="分析小红书工具使用情况",
        analysis_units=[{
            "id": "unit1",
            "sql": "SELECT tool_name, usage_count FROM ai_tool_invocations",
            "execution": {
                "success": True,
                "rowCount": 2,
                "columns": ["tool_name", "usage_count"],
                "rows": [
                    {"tool_name": "publish_note", "usage_count": 18},
                    {"tool_name": "reply_comment", "usage_count": 13},
                ],
            },
        }],
    )

    assert answer.answer.startswith("已完成查询")
    assert "Query returned" not in answer.answer
    assert "tool_name | usage_count" not in answer.answer
    assert "publish_note 使用次数最高。" in answer.key_findings
