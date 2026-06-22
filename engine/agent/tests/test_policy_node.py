from __future__ import annotations

from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage

from engine.agent.nodes.policy_node import apply_policy
from engine.agent_core.types import AgentRunRequest
from engine.tools.runtime import BaseTool, ToolPolicy, ToolRegistry


class SearchInput(BaseModel):
    query: str
    limit: int = Field(default=5)


class LooseOutput(BaseModel):
    ok: bool = True


class PolicyNodeTestTool(BaseTool[SearchInput, LooseOutput]):
    name = "db.search"
    group = "db"
    description = "Search schema metadata."
    input_model = SearchInput
    output_model = LooseOutput
    policy = ToolPolicy()

    def __init__(self, name: str | None = None, policy: ToolPolicy | None = None) -> None:
        if name is not None:
            self.name = name
            self.group = name.split(".", 1)[0]
            self.description = f"Test tool: {name}"
        if policy is not None:
            self.policy = policy

    def run(self, tool_input, context):
        return LooseOutput()


def _config(registry: ToolRegistry) -> dict:
    return {
        "configurable": {
            "thread_id": "thread-1",
            "registry": registry,
            "db": None,
            "request": AgentRunRequest(datasource_id="ds-1", question="find orders"),
        }
    }


def test_apply_policy_allows_same_discovery_tool_batch():
    registry = ToolRegistry().register(PolicyNodeTestTool())
    message = AIMessage(
        content="",
        tool_calls=[
            {"name": "db.search", "args": {"query": "orders", "limit": 5}, "id": "call_1"},
            {"name": "db.search", "args": {"query": "customers", "limit": 5}, "id": "call_2"},
        ],
    )

    result = apply_policy(
        {
            "messages": [message],
            "allowed_tool_groups": ["db"],
            "execution_mode": "user_requested_read",
        },
        _config(registry),
    )

    assert result["allowed_tool_calls"] == [
        {"name": "db.search", "args": {"query": "orders", "limit": 5}, "id": "call_1"},
        {"name": "db.search", "args": {"query": "customers", "limit": 5}, "id": "call_2"},
    ]
    assert result.get("messages", []) == []
    assert result["trace_events"][0]["tool_names"] == ["db.search", "db.search"]


def test_apply_policy_defers_stateful_sql_lifecycle_batch():
    registry = ToolRegistry()
    registry.register(PolicyNodeTestTool("sql.validate", ToolPolicy()))
    registry.register(
        PolicyNodeTestTool(
            "sql.execute_readonly",
            ToolPolicy(side_effect="read", risk_level="warning", requires_validated_sql=True),
        )
    )
    message = AIMessage(
        content="",
        tool_calls=[
            {"name": "sql.validate", "args": {"sql": "SELECT 1"}, "id": "call_1"},
            {"name": "sql.execute_readonly", "args": {"sql": "SELECT 1"}, "id": "call_2"},
        ],
    )

    result = apply_policy(
        {
            "messages": [message],
            "allowed_tool_groups": ["sql"],
            "execution_mode": "user_requested_read",
            "execute": True,
        },
        _config(registry),
    )

    assert result["allowed_tool_calls"] == [
        {"name": "sql.validate", "args": {"sql": "SELECT 1"}, "id": "call_1"},
    ]
    assert len(result["messages"]) == 1
    assert "Please wait for the result of 'sql.validate'" in result["messages"][0].content
