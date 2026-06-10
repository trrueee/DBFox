from __future__ import annotations

import pytest

from engine.agent_core.tool_registry import (
    RegisteredTool,
    ToolRegistry,
    ToolSpec,
)
from engine.agent_core.types import ToolObservation


def _dummy_tool(name: str = "demo.safe") -> RegisteredTool:
    return RegisteredTool(
        spec=ToolSpec(name=name, group="test", description="Demo safe tool."),
        handler=lambda _ctx, _args: ToolObservation(
            name="demo_step",
            status="success",
            input={},
            output={"ok": True},
            latency_ms=0,
        ),
    )


def test_tool_registry_register_get_and_list_specs() -> None:
    registry = ToolRegistry()
    tool = _dummy_tool()

    registry.register(tool)

    assert registry.get("demo.safe") is tool
    assert registry.require("demo.safe") is tool
    assert [spec.name for spec in registry.list_specs()] == ["demo.safe"]


def test_tool_registry_get_returns_none_for_unknown() -> None:
    registry = ToolRegistry().register(_dummy_tool())
    assert registry.get("missing.tool") is None


def test_tool_registry_require_raises_for_unknown() -> None:
    registry = ToolRegistry().register(_dummy_tool())
    with pytest.raises(KeyError, match="Unknown Agent tool `missing.tool`"):
        registry.require("missing.tool")


def test_tool_registry_rejects_duplicate_names() -> None:
    registry = ToolRegistry().register(_dummy_tool())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(_dummy_tool())


def test_default_registry_contains_current_agent_tools_only() -> None:
    from engine.tests.fixtures.agent_tools import DEFAULT_AGENT_TOOL_NAMES, build_default_tool_registry

    registry = build_default_tool_registry()
    names = [spec.name for spec in registry.list_specs()]

    assert set(DEFAULT_AGENT_TOOL_NAMES).issubset(set(names))
    assert "sql.execute_readonly" in names
    assert not any(name.startswith("@") for name in names)
    assert not {"@limit", "@timeout", "@explain", "@export", "@chart"} & set(names)

    execute_spec = registry.get("sql.execute_readonly").spec
    assert execute_spec.policy.risk_level == "warning"
    assert execute_spec.execution.idempotent is False


def test_registered_tools_have_group_and_kind() -> None:
    from engine.tests.fixtures.agent_tools import build_default_tool_registry

    registry = build_default_tool_registry()
    for spec in registry.list_specs():
        assert spec.kind in ("code", "llm", "hybrid"), (
            f"Tool {spec.name} has no kind"
        )
        assert isinstance(spec.policy.risk_level, str), (
            f"Tool {spec.name} has no risk_level"
        )
        assert isinstance(spec.execution.idempotent, bool), (
            f"Tool {spec.name} has no idempotent"
        )
