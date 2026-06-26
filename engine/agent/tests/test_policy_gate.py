from __future__ import annotations

from pydantic import BaseModel

from engine.policy.gate import PolicyGate
from engine.tools.runtime import BaseTool, ToolPolicy, ToolRegistry


class EmptyInput(BaseModel):
    pass


class EmptyOutput(BaseModel):
    ok: bool = True


class PolicyTestTool(BaseTool[EmptyInput, EmptyOutput]):
    name = "dummy.tool"
    group = "dummy"
    description = "dummy description"
    input_model = EmptyInput
    output_model = EmptyOutput

    def __init__(self, name: str, policy: ToolPolicy) -> None:
        self.name = name
        self.group = name.split(".", 1)[0]
        self.description = f"Test tool: {name}"
        self.policy = policy

    def run(self, tool_input, context):
        return EmptyOutput()


def _make_tool(
    name: str,
    risk_level: str = "safe",
    side_effect: str = "none",
    requires_approval: bool = False,
    requires_validated_sql: bool = False,
):
    return PolicyTestTool(
        name,
        ToolPolicy(
            risk_level=risk_level,
            side_effect=side_effect,
            requires_approval=requires_approval,
            requires_validated_sql=requires_validated_sql,
        ),
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
        registry.register(_make_tool("schema.describe_table"))
        gate = PolicyGate(registry)
        decision = gate.check({}, "schema.describe_table", {})
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

    def test_escalate_tool_group_bypasses_group_check(self):
        from engine.tools.dbfox_tools import register_dbfox_tools

        registry = register_dbfox_tools()
        gate = PolicyGate(registry)
        state = {
            "allowed_tool_groups": [
                "environment",
                "schema",
                "db",
                "semantic",
                "result",
                "chart",
                "answer",
            ]
        }

        decision = gate.check(
            state,
            "escalate.tool_group",
            {"group": "execution", "reason": "Need to execute validated SQL."},
        )

        assert decision.status == "allowed"


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
        assert "not allowed" in decision.reason.lower()

    def test_execute_without_validation_blocked(self):
        gate = PolicyGate(self._registry_with_execute_tool())
        state = {"execute": True}
        decision = gate.check(state, "sql.execute_readonly", {})
        assert decision.status == "blocked"

    def test_execute_with_can_execute_false_blocked(self):
        gate = PolicyGate(self._registry_with_execute_tool())
        state = {
            "execute": True,
            "safety": {
                "can_execute": False,
                "safe_sql": "SELECT 1",
                "original_sql": "SELECT 1",
                "blocked_reasons": [],
            },
        }
        decision = gate.check(state, "sql.execute_readonly", {})
        assert decision.status == "blocked"

    def test_execute_with_missing_safe_sql_blocked(self):
        gate = PolicyGate(self._registry_with_execute_tool())
        state = {
            "execute": True,
            "safety": {
                "can_execute": True,
                "original_sql": "SELECT 1",
                "blocked_reasons": [],
            },
        }
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

    def test_model_supplied_sql_is_ignored_not_blocked(self):
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
        assert decision.status == "allowed"
        assert decision.safe_args == {"ignored_model_sql": "DROP TABLE users"}
