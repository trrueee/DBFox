from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from engine.databox_agent.graph.state import DataBoxAgentState
from engine.databox_agent.graph.react_graph import build_databox_react_graph
from engine.databox_agent.graph.routes import (
    route_model_output,
    route_policy_output,
    route_approval_output,
    route_observe_output,
)


class TestGraphCompilation:
    def test_graph_compiles_with_all_nodes(self):
        graph = build_databox_react_graph()
        nodes = list(graph.nodes.keys())
        assert "__start__" in nodes
        assert "model" in nodes
        assert "policy" in nodes
        assert "tools" in nodes
        assert "observe" in nodes
        assert "approval" in nodes
        assert "finalize" in nodes


class TestModelRoute:
    def test_no_tool_calls_routes_to_finalize(self):
        from langchain_core.messages import AIMessage, HumanMessage

        state: DataBoxAgentState = {
            "messages": [HumanMessage(content="hello"), AIMessage(content="Hi!")],
            "status": "running",
        }
        assert route_model_output(state) == "finalize"

    def test_with_tool_calls_routes_to_policy(self):
        from langchain_core.messages import AIMessage, HumanMessage

        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "sql.generate", "args": {}, "id": "call_1"}],
        )
        state: DataBoxAgentState = {
            "messages": [HumanMessage(content="query"), ai_msg],
            "status": "running",
        }
        assert route_model_output(state) == "policy"

    def test_empty_messages_routes_to_finalize(self):
        state: DataBoxAgentState = {"messages": [], "status": "running"}
        assert route_model_output(state) == "finalize"


class TestPolicyRoute:
    def test_allowed_calls_routes_to_tools(self):
        state: DataBoxAgentState = {
            "allowed_tool_calls": [{"name": "sql.generate"}],
            "status": "running",
        }
        assert route_policy_output(state) == "tools"

    def test_no_calls_routes_to_model(self):
        state: DataBoxAgentState = {"allowed_tool_calls": [], "status": "running"}
        assert route_policy_output(state) == "model"

    def test_waiting_approval_routes_to_approval(self):
        state: DataBoxAgentState = {
            "status": "waiting_approval",
            "pending_approval": {"id": "test"},
            "allowed_tool_calls": [],
        }
        assert route_policy_output(state) == "approval"

    def test_pending_approval_field_routes_to_approval(self):
        state: DataBoxAgentState = {
            "status": "running",
            "pending_approval": {"id": "test"},
            "allowed_tool_calls": [],
        }
        assert route_policy_output(state) == "approval"


class TestApprovalRoute:
    def test_approved_with_calls_routes_to_tools(self):
        state: DataBoxAgentState = {
            "approval_result": {"status": "approved"},
            "allowed_tool_calls": [{"name": "sql.execute_readonly"}],
        }
        assert route_approval_output(state) == "tools"

    def test_rejected_routes_to_model(self):
        state: DataBoxAgentState = {
            "approval_result": {"status": "rejected"},
            "allowed_tool_calls": [],
        }
        assert route_approval_output(state) == "model"

    def test_approved_no_calls_routes_to_finalize(self):
        state: DataBoxAgentState = {
            "approval_result": {"status": "approved"},
            "allowed_tool_calls": [],
        }
        assert route_approval_output(state) == "finalize"

    def test_no_approval_result_routes_to_finalize(self):
        state: DataBoxAgentState = {"approval_result": None, "allowed_tool_calls": []}
        assert route_approval_output(state) == "finalize"


class TestObserveRoute:
    def test_running_routes_to_model(self):
        state: DataBoxAgentState = {"status": "running", "step_count": 1, "max_steps": 20}
        assert route_observe_output(state) == "model"

    def test_completed_routes_to_finalize(self):
        state: DataBoxAgentState = {"status": "completed", "step_count": 3, "max_steps": 20}
        assert route_observe_output(state) == "finalize"

    def test_failed_routes_to_finalize(self):
        state: DataBoxAgentState = {"status": "failed", "step_count": 3, "max_steps": 20}
        assert route_observe_output(state) == "finalize"

    def test_step_limit_routes_to_finalize(self):
        state: DataBoxAgentState = {"status": "running", "step_count": 25, "max_steps": 20}
        assert route_observe_output(state) == "finalize"
