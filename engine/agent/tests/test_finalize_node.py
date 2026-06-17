from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from engine.agent.graph.state import DBFoxAgentState
from engine.agent.nodes.finalize_node import finalize_answer


class TestFinalizeNode:
    def test_finalize_with_answer_content(self):
        state: DBFoxAgentState = {
            "messages": [
                HumanMessage(content="What is 1+1?"),
                AIMessage(content="1+1 equals 2."),
            ],
            "status": "running",
            "error": None,
            "pending_approval": None,
        }
        result = finalize_answer(state, {})
        assert result["status"] == "completed"
        assert result["answer"]["answer"] == "1+1 equals 2."
        assert result["error"] is None

    def test_finalize_with_error(self):
        state: DBFoxAgentState = {
            "messages": [],
            "status": "running",
            "error": "Something went wrong",
            "pending_approval": None,
        }
        result = finalize_answer(state, {})
        assert result["status"] == "failed"
        assert result["error"] == "Something went wrong"

    def test_finalize_with_answer_and_stale_error_completes_with_caveat(self):
        state: DBFoxAgentState = {
            "messages": [
                HumanMessage(content="Inspect users"),
                AIMessage(content="Found the users table and sample rows."),
            ],
            "status": "running",
            "error": "Inspect error: 'int' object has no attribute 'fetchone'",
            "pending_approval": None,
        }

        result = finalize_answer(state, {})

        assert result["status"] == "completed"
        assert result["error"] is None
        assert result["trace_events"][0]["has_answer"] is True
        assert result["trace_events"][0]["has_error"] is True
        assert "artifacts" not in result
        assert any("部分后续检查未完成" in item for item in result["answer"]["caveats"])

    def test_finalize_with_pending_approval(self):
        state: DBFoxAgentState = {
            "messages": [AIMessage(content="Approval needed.")],
            "status": "running",
            "error": None,
            "pending_approval": {"id": "approval-1", "tool_name": "sql.execute_readonly"},
        }
        result = finalize_answer(state, {})
        assert result["status"] == "waiting_approval"

    def test_finalize_empty_no_error_marks_failed(self):
        state: DBFoxAgentState = {
            "messages": [],
            "status": "running",
            "error": None,
            "pending_approval": None,
        }
        result = finalize_answer(state, {})
        assert result["status"] == "failed"
        assert result["error"]

    def test_finalize_output_has_answer_payload(self):
        state: DBFoxAgentState = {
            "messages": [AIMessage(content="Analysis complete.")],
            "status": "running",
            "error": None,
            "pending_approval": None,
        }
        result = finalize_answer(state, {})
        assert "answer" in result["answer"]
        assert "key_findings" in result["answer"]
        assert "caveats" in result["answer"]
        assert "recommendations" in result["answer"]
        assert "follow_up_questions" in result["answer"]
        assert "final_answer" in result
