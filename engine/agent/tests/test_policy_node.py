from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage

from engine.agent.nodes.policy_node import apply_policy
from engine.agent_core.types import AgentApprovalRecord, AgentRunRequest
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


class FakeEventStore:
    def __init__(self) -> None:
        self.created_approvals: list[dict] = []

    def create_approval(self, **kwargs):
        self.created_approvals.append(kwargs)
        return AgentApprovalRecord(
            id="approval-event-store",
            run_id=kwargs["run_id"],
            session_id=kwargs["session_id"],
            step_name=kwargs["step_name"],
            tool_name=kwargs["tool_name"],
            status="pending",
            risk_level=kwargs["risk_level"],
            reason=kwargs["reason"],
            policy_decision=kwargs["policy_decision"],
            requested_action=kwargs["requested_action"],
            created_at=datetime.now(UTC),
        )


def _config(registry: ToolRegistry, *, event_store=None, db=None) -> dict:
    return {
        "configurable": {
            "thread_id": "thread-1",
            "registry": registry,
            "db": db,
            "event_store": event_store,
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


def test_apply_policy_creates_approval_through_event_store(monkeypatch):
    from engine.agent_core import persistence as agent_persistence

    def fail_create_approval(*_args, **_kwargs):
        raise AssertionError("policy node must not write approvals directly")

    monkeypatch.setattr(agent_persistence, "create_approval", fail_create_approval)

    registry = ToolRegistry().register(
        PolicyNodeTestTool(
            "sql.execute_readonly",
            ToolPolicy(side_effect="read", risk_level="warning", requires_validated_sql=True),
        )
    )
    store = FakeEventStore()
    message = AIMessage(
        content="",
        tool_calls=[
            {"name": "sql.execute_readonly", "args": {"sql": "SELECT 1"}, "id": "call_approval"},
        ],
    )

    result = apply_policy(
        {
            "run_id": "run-policy-approval",
            "thread_id": "session-policy-approval",
            "messages": [message],
            "allowed_tool_groups": ["sql"],
            "execution_mode": "agent_autonomous_read",
            "execute": True,
            "environment_profile": {"env": "prod"},
            "safety": {
                "can_execute": True,
                "safe_sql": "SELECT 1",
                "blocked_reasons": [],
            },
        },
        _config(registry, event_store=store, db=object()),
    )

    assert result["status"] == "waiting_approval"
    assert result["pending_approval"]["id"] == "approval-event-store"
    assert result["pending_approval"]["tool_call_id"] == "call_approval"
    assert store.created_approvals[0]["run_id"] == "run-policy-approval"
