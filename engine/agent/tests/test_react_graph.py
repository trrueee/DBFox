from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from engine.agent.graph.state import DBFoxAgentState
from engine.agent.graph.react_graph import build_dbfox_react_graph
from engine.agent.graph.routes import (
    route_model_output,
    route_policy_output,
    route_approval_output,
    route_progress_output,
)


class TestGraphCompilation:
    def test_graph_compiles_with_all_nodes(self):
        graph = build_dbfox_react_graph()
        nodes = list(graph.nodes.keys())
        assert "__start__" in nodes
        assert "start_turn" in nodes
        assert "model" in nodes
        assert "policy" in nodes
        assert "tools" in nodes
        assert "observe" in nodes
        assert "progress" in nodes
        assert "repair" in nodes
        assert "approval" in nodes
        assert "finalize" in nodes
        assert "finalize_turn" in nodes


class TestModelRoute:
    def test_no_tool_calls_routes_to_progress(self):
        from langchain_core.messages import AIMessage, HumanMessage

        state: DBFoxAgentState = {
            "messages": [HumanMessage(content="hello"), AIMessage(content="Hi!")],
            "status": "running",
        }
        assert route_model_output(state) == "progress"

    def test_with_tool_calls_routes_to_policy(self):
        from langchain_core.messages import AIMessage, HumanMessage

        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "sql.generate", "args": {}, "id": "call_1"}],
        )
        state: DBFoxAgentState = {
            "messages": [HumanMessage(content="query"), ai_msg],
            "status": "running",
        }
        assert route_model_output(state) == "policy"

    def test_empty_messages_routes_to_progress(self):
        state: DBFoxAgentState = {"messages": [], "status": "running"}
        assert route_model_output(state) == "progress"


class TestPolicyRoute:
    def test_allowed_calls_routes_to_tools(self):
        state: DBFoxAgentState = {
            "allowed_tool_calls": [{"name": "sql.generate"}],
            "status": "running",
        }
        assert route_policy_output(state) == "tools"

    def test_no_calls_routes_to_model(self):
        state: DBFoxAgentState = {"allowed_tool_calls": [], "status": "running", "consecutive_blocks": 0}
        assert route_policy_output(state) == "model"

    def test_waiting_approval_routes_to_approval(self):
        state: DBFoxAgentState = {
            "status": "waiting_approval",
            "pending_approval": {"id": "test"},
            "allowed_tool_calls": [],
        }
        assert route_policy_output(state) == "approval"

    def test_pending_approval_field_routes_to_approval(self):
        state: DBFoxAgentState = {
            "status": "running",
            "pending_approval": {"id": "test"},
            "allowed_tool_calls": [],
        }
        assert route_policy_output(state) == "approval"

    def test_consecutive_blocks_exceeded_routes_to_progress(self):
        state: DBFoxAgentState = {
            "status": "running",
            "allowed_tool_calls": [],
            "consecutive_blocks": 3,
        }
        assert route_policy_output(state) == "progress"


class TestApprovalRoute:
    def test_approved_with_calls_routes_to_tools(self):
        state: DBFoxAgentState = {
            "approval_result": {"status": "approved"},
            "allowed_tool_calls": [{"name": "sql.execute_readonly"}],
        }
        assert route_approval_output(state) == "tools"

    def test_rejected_routes_to_model(self):
        state: DBFoxAgentState = {
            "approval_result": {"status": "rejected"},
            "allowed_tool_calls": [],
        }
        assert route_approval_output(state) == "model"

    def test_approved_no_calls_routes_to_progress(self):
        state: DBFoxAgentState = {
            "approval_result": {"status": "approved"},
            "allowed_tool_calls": [],
        }
        assert route_approval_output(state) == "progress"

    def test_no_approval_result_routes_to_progress(self):
        state: DBFoxAgentState = {"approval_result": None, "allowed_tool_calls": []}
        assert route_approval_output(state) == "progress"


class TestProgressRoute:
    def test_complete_routes_to_finalize(self):
        state: DBFoxAgentState = {
            "progress_decision": {"status": "complete"},
        }
        assert route_progress_output(state) == "finalize"

    def test_continue_routes_to_model(self):
        state: DBFoxAgentState = {
            "progress_decision": {"status": "continue"},
        }
        assert route_progress_output(state) == "model"

    def test_continue_with_recovery_routes_to_repair(self):
        state: DBFoxAgentState = {
            "progress_decision": {
                "status": "continue",
                "recovery_strategy": "lookup_schema_then_revise_sql",
            },
            "repair_mode": True,
        }
        assert route_progress_output(state) == "repair"

    def test_replan_routes_to_model(self):
        """Replan now routes to model — the model adapts autonomously with progress guidance."""
        state: DBFoxAgentState = {
            "progress_decision": {"status": "replan", "retry_budget": 1},
            "replan_count": 0,
        }
        assert route_progress_output(state) == "model"

    def test_replan_exceeded_routes_to_finalize(self):
        """Replan with exhausted budget (no retry_budget set) → finalize."""
        state: DBFoxAgentState = {
            "progress_decision": {"status": "replan", "retry_budget": 0},
            "replan_count": 3,
        }
        assert route_progress_output(state) == "finalize"

    def test_clarify_routes_to_finalize(self):
        state: DBFoxAgentState = {
            "progress_decision": {"status": "clarify"},
        }
        assert route_progress_output(state) == "finalize"

    def test_blocked_routes_to_finalize(self):
        state: DBFoxAgentState = {
            "progress_decision": {"status": "blocked"},
        }
        assert route_progress_output(state) == "finalize"

    def test_failed_routes_to_finalize(self):
        state: DBFoxAgentState = {
            "progress_decision": {"status": "failed"},
        }
        assert route_progress_output(state) == "finalize"

    def test_no_decision_routes_to_finalize(self):
        state: DBFoxAgentState = {}
        assert route_progress_output(state) == "finalize"
