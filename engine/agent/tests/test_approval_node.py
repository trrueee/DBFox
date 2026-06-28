from __future__ import annotations

from unittest.mock import patch, MagicMock

from engine.agent.graph.state import DBFoxAgentState
from engine.agent.nodes.approval_node import approval_interrupt


class TestApprovalNode:
    def test_approval_interrupt_approved(self):
        """When interrupt returns approved, allowed_tool_calls should be populated."""
        state: DBFoxAgentState = {
            "pending_approval": {
                "id": "approval-1",
                "tool_name": "sql.execute_readonly",
                "requested_action": {
                    "tool_name": "sql.execute_readonly",
                    "args": {"safe_sql": "SELECT 1"},
                },
            },
            "status": "waiting_approval",
            "allowed_tool_calls": [],
        }

        with patch(
            "engine.agent.nodes.approval_node.interrupt",
            return_value={"decision": "approved", "note": "looks safe"},
        ):
            result = approval_interrupt(state, {})

        assert result["status"] == "running"
        assert result["pending_approval"] is None
        assert result["approval_result"]["status"] == "approved"
        assert len(result["allowed_tool_calls"]) == 1
        assert result["allowed_tool_calls"][0]["name"] == "sql.execute_readonly"

    def test_approval_interrupt_rejected(self):
        """When interrupt returns rejected, allowed_tool_calls should be empty."""
        state: DBFoxAgentState = {
            "pending_approval": {
                "id": "approval-2",
                "tool_name": "sql.execute_readonly",
                "requested_action": {
                    "tool_name": "sql.execute_readonly",
                    "args": {"safe_sql": "SELECT 1"},
                },
            },
            "status": "waiting_approval",
            "allowed_tool_calls": [],
        }

        with patch(
            "engine.agent.nodes.approval_node.interrupt",
            return_value={"decision": "rejected", "note": "too risky"},
        ):
            result = approval_interrupt(state, {})

        assert result["status"] == "running"
        assert result["pending_approval"] is None
        assert result["approval_result"]["status"] == "rejected"
        assert result["allowed_tool_calls"] == []

    def test_approval_interrupt_unknown_decision(self):
        """Unknown decision is treated as rejected."""
        state: DBFoxAgentState = {
            "pending_approval": {
                "id": "approval-3",
                "tool_name": "sql.execute_readonly",
                "requested_action": {
                    "tool_name": "sql.execute_readonly",
                    "args": {},
                },
            },
            "status": "waiting_approval",
            "allowed_tool_calls": [],
        }

        with patch(
            "engine.agent.nodes.approval_node.interrupt",
            return_value={"decision": "unknown_action"},
        ):
            result = approval_interrupt(state, {})

        assert result["status"] == "running"
        assert result["allowed_tool_calls"] == []

    def test_approval_interrupt_string_decision(self):
        """If interrupt returns a string instead of dict, treat as rejected."""
        state: DBFoxAgentState = {
            "pending_approval": {
                "id": "approval-4",
                "tool_name": "sql.execute_readonly",
                "requested_action": {"tool_name": "sql.execute_readonly", "args": {}},
            },
            "status": "waiting_approval",
            "allowed_tool_calls": [],
        }

        with patch(
            "engine.agent.nodes.approval_node.interrupt",
            return_value="approved",
        ):
            result = approval_interrupt(state, {})

        assert result["status"] == "running"
        assert result["allowed_tool_calls"] == []
