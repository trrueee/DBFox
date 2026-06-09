from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from engine.databox_agent.graph.state import DataBoxAgentState
from engine.databox_agent.nodes.finalize_node import finalize_answer


class TestFinalizeNode:
    def test_finalize_with_answer_content(self):
        state: DataBoxAgentState = {
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
        state: DataBoxAgentState = {
            "messages": [],
            "status": "running",
            "error": "Something went wrong",
            "pending_approval": None,
        }
        result = finalize_answer(state, {})
        assert result["status"] == "failed"
        assert result["error"] == "Something went wrong"

    def test_finalize_with_pending_approval(self):
        state: DataBoxAgentState = {
            "messages": [AIMessage(content="Approval needed.")],
            "status": "running",
            "error": None,
            "pending_approval": {"id": "approval-1", "tool_name": "sql.execute_readonly"},
        }
        result = finalize_answer(state, {})
        assert result["status"] == "waiting_approval"

    def test_finalize_empty_no_error_marks_failed(self):
        state: DataBoxAgentState = {
            "messages": [],
            "status": "running",
            "error": None,
            "pending_approval": None,
        }
        result = finalize_answer(state, {})
        assert result["status"] == "failed"
        assert result["error"]

    def test_finalize_output_has_answer_payload(self):
        state: DataBoxAgentState = {
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
