from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from engine.agent.tool_registry import (
    RegisteredTool,
    ToolContext,
    ToolPolicy,
    ToolRegistry,
    ToolSpec,
)
from engine.databox_agent.guardrails.policy_gate import PolicyGate, PolicyDecision


def _make_tool(
    name: str,
    risk_level: str = "safe",
    side_effect: str = "none",
    requires_approval: bool = False,
    requires_validated_sql: bool = False,
):
    return RegisteredTool(
        spec=ToolSpec(
            name=name,
            description=f"Test tool: {name}",
            policy=ToolPolicy(
                risk_level=risk_level,
                side_effect=side_effect,
                requires_approval=requires_approval,
                requires_validated_sql=requires_validated_sql,
            ),
        ),
        handler=lambda ctx, args: MagicMock(),
    )


class TestPolicyGateBasics:
    def test_unknown_tool_blocked(self):
        registry = ToolRegistry()
        gate = PolicyGate(registry)
        decision = gate.check({}, "nonexistent.tool", {})
        assert decision.status == "blocked"
        assert "Unknown tool" in decision.reason

    def test_safe_tool_allowed(self):
        registry = ToolRegistry()
        registry.register(_make_tool("schema.build_context"))
        gate = PolicyGate(registry)
        decision = gate.check({}, "schema.build_context", {})
        assert decision.status == "allowed"

    def test_write_tool_blocked(self):
        registry = ToolRegistry()
        registry.register(_make_tool("dangerous.write", side_effect="write"))
        gate = PolicyGate(registry)
        decision = gate.check({}, "dangerous.write", {})
        assert decision.status == "blocked"

    def test_destructive_tool_blocked(self):
        registry = ToolRegistry()
        registry.register(_make_tool("dangerous.drop", side_effect="destructive"))
        gate = PolicyGate(registry)
        decision = gate.check({}, "dangerous.drop", {})
        assert decision.status == "blocked"

    def test_approval_required_tool(self):
        registry = ToolRegistry()
        registry.register(_make_tool("risky.tool", requires_approval=True, risk_level="warning"))
        gate = PolicyGate(registry)
        decision = gate.check({}, "risky.tool", {"arg": 1})
        assert decision.status == "approval_required"
        assert decision.risk_level == "warning"


class TestSqlExecutionPolicy:
    def _registry_with_execute_tool(self):
        registry = ToolRegistry()
        registry.register(
            _make_tool(
                "sql.execute_readonly",
                side_effect="read",
                requires_validated_sql=True,
                risk_level="warning",
            )
        )
        return registry

    def test_execute_disabled_in_state(self):
        gate = PolicyGate(self._registry_with_execute_tool())
        state = {"execute": False}
        decision = gate.check(state, "sql.execute_readonly", {})
        assert decision.status == "blocked"
        assert "disabled" in decision.reason.lower()

    def test_execute_without_validation_blocked(self):
        gate = PolicyGate(self._registry_with_execute_tool())
        state = {"execute": True}
        decision = gate.check(state, "sql.execute_readonly", {})
        assert decision.status == "blocked"

    def test_execute_with_validated_sql_allowed(self):
        gate = PolicyGate(self._registry_with_execute_tool())
        state = {
            "execute": True,
            "safety": {
                "can_execute": True,
                "safe_sql": "SELECT 1",
                "original_sql": "SELECT 1",
            },
        }
        decision = gate.check(state, "sql.execute_readonly", {})
        assert decision.status == "allowed"

    def test_execute_with_requires_confirmation(self):
        gate = PolicyGate(self._registry_with_execute_tool())
        state = {
            "execute": True,
            "safety": {
                "can_execute": True,
                "safe_sql": "SELECT * FROM users",
                "original_sql": "SELECT * FROM users",
                "requires_confirmation": True,
            },
            "sql": "SELECT * FROM users",
        }
        decision = gate.check(state, "sql.execute_readonly", {})
        assert decision.status == "approval_required"

    def test_sql_mismatch_blocked(self):
        gate = PolicyGate(self._registry_with_execute_tool())
        state = {
            "execute": True,
            "safety": {
                "can_execute": True,
                "safe_sql": "SELECT 1",
                "original_sql": "SELECT 1",
            },
        }
        decision = gate.check(state, "sql.execute_readonly", {"sql": "DROP TABLE users"})
        assert decision.status == "blocked"
        assert "does not match" in decision.reason.lower()
