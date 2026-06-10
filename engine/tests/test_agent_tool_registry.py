from __future__ import annotations

import pytest

from engine.agent_contracts.default_tools import DEFAULT_AGENT_TOOL_NAMES, build_default_tool_registry
from engine.agent_contracts.registry import FunctionAgentTool, ToolRegistry, ToolSpec
from engine.agent_contracts.types import ToolObservation


def _dummy_tool(name: str = "demo.safe") -> FunctionAgentTool:
    return FunctionAgentTool(
        spec=ToolSpec(name=name, description="Demo safe tool."),
        handler=lambda _input, _ctx: ToolObservation(
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
    assert [spec.name for spec in registry.list_specs()] == ["demo.safe"]


def test_tool_registry_rejects_duplicate_names() -> None:
    registry = ToolRegistry().register(_dummy_tool())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(_dummy_tool())


def test_tool_registry_unknown_name_has_clear_error() -> None:
    registry = ToolRegistry().register(_dummy_tool())

    with pytest.raises(KeyError, match="Unknown Agent tool `missing.tool`"):
        registry.get("missing.tool")


def test_default_registry_contains_current_agent_tools_only() -> None:
    registry = build_default_tool_registry()
    names = [spec.name for spec in registry.list_specs()]

    assert set(DEFAULT_AGENT_TOOL_NAMES).issubset(set(names))
    assert "sql.execute_readonly" in names
    assert not any(name.startswith("@") for name in names)
    assert not {"@limit", "@timeout", "@explain", "@export", "@chart"} & set(names)

    execute_spec = registry.get("sql.execute_readonly").spec
    assert execute_spec.risk_level == "warning"
    assert execute_spec.idempotent is False
