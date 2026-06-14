"""DataBox Agent Tool Registry — canonical type system for tool contracts.

This is the SINGLE source of truth for tool type definitions.
No other registry module exists.  All tool wrappers use these types.

Dependency rule: agent_core has zero agent / semantic / environment dependencies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from engine.agent_core.types import AgentRunRequest, ToolObservation

logger = logging.getLogger("databox.databox_agent.tool_registry")


# ---------------------------------------------------------------------------
# Policy (security concern only — NO execution characteristics)
# ---------------------------------------------------------------------------

RiskLevel = Literal["safe", "warning", "danger"]
SideEffect = Literal["none", "read", "write", "destructive"]
ConcurrencyMode = Literal["sequential", "parallel_safe"]


@dataclass
class ToolPolicy:
    """Security policy for a tool.  Does NOT contain execution characteristics."""

    side_effect: SideEffect = "none"
    risk_level: RiskLevel = "safe"
    requires_approval: bool = False
    requires_validated_sql: bool = False
    allowed_execution_modes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Execution characteristics (timeout / idempotency / concurrency)
# ---------------------------------------------------------------------------


@dataclass
class ToolExecutionSpec:
    """Execution behaviour — separate from security policy."""

    timeout_seconds: int = 30
    idempotent: bool = True
    retryable: bool = False
    max_retries: int = 0
    concurrency: ConcurrencyMode = "sequential"


# ---------------------------------------------------------------------------
# State binding (declarative read / write contract)
# ---------------------------------------------------------------------------


@dataclass
class ToolStateBinding:
    """Declares which state keys a tool consumes and produces.

    Used by: observe_node (databinding), eval (expectation matching),
             tool manifest (documentation), lifecycle (validation).
    """

    consumes_state_keys: list[str] = field(default_factory=list)
    produces_state_keys: list[str] = field(default_factory=list)
    artifact_types: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ToolSpec — single canonical definition
# ---------------------------------------------------------------------------


@dataclass
class ToolSpec:
    """Complete tool contract.

    Schema is derived from input_model / output_model — never stored as
    a separate dict that can drift out of sync.
    """

    name: str
    group: str = ""
    kind: Literal["code", "llm", "hybrid"] = "code"
    description: str = ""
    input_model: type[BaseModel] | None = None
    output_model: type[BaseModel] | None = None
    # Explicit schema overrides (hand-crafted descriptions).  When None,
    # the property auto-generates from input_model / output_model.
    _input_schema: dict[str, Any] | None = field(default=None, repr=False)
    _output_schema: dict[str, Any] | None = field(default=None, repr=False)
    policy: ToolPolicy = field(default_factory=ToolPolicy)
    execution: ToolExecutionSpec = field(default_factory=ToolExecutionSpec)
    binding: ToolStateBinding = field(default_factory=ToolStateBinding)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def input_schema(self) -> dict[str, Any]:
        if self._input_schema is not None:
            return self._input_schema
        if self.input_model is not None:
            return self.input_model.model_json_schema()
        return {"type": "object"}

    @property
    def output_schema(self) -> dict[str, Any]:
        if self._output_schema is not None:
            return self._output_schema
        if self.output_model is not None:
            return self.output_model.model_json_schema()
        return {"type": "object"}


# ---------------------------------------------------------------------------
# Tool runtime context — read-only, immutable
# ---------------------------------------------------------------------------


@dataclass
class ToolRuntimeContext:
    """Runtime-scoped metadata available to tool execution."""

    thread_id: str = ""
    datasource_id: str = ""
    db_dialect: str = "mysql"
    read_only: bool = True
    db_session: Session | None = None
    api_key: str | None = None
    api_base: str | None = None
    model_name: str | None = None


@dataclass(frozen=True)
class ToolContext:
    """Read-only context passed to every tool invocation.

    Tools MUST NOT mutate state_view directly.  They return ToolObservation
    and the observe_node / databinding layer is the sole state writer.
    """

    db: Session
    request: AgentRunRequest
    state_view: Mapping[str, Any] = field(default_factory=dict)
    runtime: ToolRuntimeContext = field(default_factory=ToolRuntimeContext)


# ---------------------------------------------------------------------------
# Tool handler and RegisteredTool
# ---------------------------------------------------------------------------

ToolHandler = Callable[["ToolContext", dict[str, Any]], ToolObservation]


@dataclass
class RegisteredTool:
    """A tool registered in the ToolRegistry, ready for execution."""

    spec: ToolSpec
    handler: ToolHandler
    base_tool: Any = None


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------


class ToolRegistry:
    """Central registry of all agent tools.

    Tools can come from multiple sources:
    - Builtin: engine/tools/builtin/*.yaml      (priority 0)
    - User global: ~/.databox/tools/*.yaml      (priority 10)
    - Project: .databox/tools/*.yaml             (priority 20)
    - Programmatic: registry.register(tool)       (highest priority)

    get() returns None for unknown tools (safe for guard code).
    require() raises KeyError for unknown tools (fail-fast for execution code).
    """

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}
        self._sources: list[Any] = []  # ToolSource instances
        self._loaded: bool = False

    # ── Source management ───────────────────────────────────────────────────

    def add_source(self, source: Any) -> "ToolRegistry":
        """Register a discovery source.  Call before load_all().

        Sources are loaded in priority order (low to high).  When two sources
        define the same tool name, the higher-priority one wins.
        """
        self._sources.append(source)
        self._sources.sort(key=lambda s: s.priority)
        return self

    def add_builtin_source(self, path: Any = None) -> "ToolRegistry":
        """Register the builtin tool spec directory (priority 0)."""
        from engine.agent_core.extensions.discovery import BuiltinToolSource
        return self.add_source(BuiltinToolSource(path))

    def add_user_source(self, path: str | Any, *, priority: int = 10) -> "ToolRegistry":
        """Register a user/project tool spec directory."""
        from engine.agent_core.extensions.discovery import UserToolSource
        return self.add_source(UserToolSource(path, priority=priority))

    def add_dict_source(self, tools: list[dict[str, Any]] | None = None,
                        *, priority: int = 100) -> Any:
        """Register a programmatic source and return it for further mutation."""
        from engine.agent_core.extensions.discovery import DictToolSource
        src = DictToolSource(tools, priority=priority)
        self.add_source(src)
        return src

    # ── Load ────────────────────────────────────────────────────────────────

    def load_all(self) -> list[RegisteredTool]:
        """Load tools from all registered sources + resolve handlers.

        Idempotent — subsequent calls return the cached result.
        Reset with clear() if you need to reload after adding sources.
        """
        if self._loaded:
            return list(self._tools.values())

        if not self._sources:
            # Convenience: if no sources were registered, auto-add builtins.
            self.add_builtin_source()

        from engine.agent_core.extensions.loader import load_tool_spec_from_dict
        from engine.agent_core.handler_registry import get_handler_registry

        handlers = get_handler_registry()
        total = 0

        for source in sorted(self._sources, key=lambda s: s.priority):
            for raw in source.discover():
                spec = load_tool_spec_from_dict(raw)
                if spec is None:
                    continue

                handler_name = raw.get("handler", "")
                base_tool_name = raw.get("base_tool")

                try:
                    handler_fn = handlers.resolve(handler_name)
                except KeyError:
                    logger.error(
                        "Tool '%s' references unknown handler '%s' — skipping.",
                        spec.name, handler_name,
                    )
                    continue

                base_tool = handlers.resolve_base_tool(handler_name)
                if base_tool_name:
                    resolved_bt = handlers.resolve_base_tool(base_tool_name)
                    if resolved_bt is not None:
                        base_tool = resolved_bt

                rt = RegisteredTool(spec=spec, handler=handler_fn, base_tool=base_tool)

                if spec.name in self._tools:
                    logger.info(
                        "Tool '%s' overridden by source %s (priority %d)",
                        spec.name, source, source.priority,
                    )
                self._tools[spec.name] = rt
                total += 1

        self._loaded = True
        logger.info("ToolRegistry: loaded %d tools from %d sources.",
                     len(self._tools), len(self._sources))
        return list(self._tools.values())

    # ── Manual registration ─────────────────────────────────────────────────

    def register(self, tool: RegisteredTool) -> "ToolRegistry":
        """Manually register a tool.  Overrides any source-loaded tool
        with the same name regardless of priority."""
        name = tool.spec.name
        if name in self._tools:
            logger.info("Tool '%s' overridden by manual register().", name)
        self._tools[name] = tool
        return self

    def force_register(self, tool: RegisteredTool) -> "ToolRegistry":
        """Alias for register() — always succeeds."""
        return self.register(tool)

    # ── Query ───────────────────────────────────────────────────────────────

    def get(self, name: str) -> RegisteredTool | None:
        return self._tools.get(name)

    def require(self, name: str) -> RegisteredTool:
        tool = self.get(name)
        if tool is None:
            available = ", ".join(sorted(self._tools)) or "<none>"
            raise KeyError(
                f"Unknown Agent tool `{name}`. Available tools: {available}"
            )
        return tool

    def list_specs(self) -> list[ToolSpec]:
        return [self._tools[name].spec for name in sorted(self._tools)]

    def clear(self) -> None:
        """Clear all loaded tools and reset loaded flag."""
        self._tools.clear()
        self._loaded = False

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __repr__(self) -> str:
        return f"<ToolRegistry tools={len(self._tools)} sources={len(self._sources)} loaded={self._loaded}>"


# ---------------------------------------------------------------------------
# Tool group mapping — static, no agent runtime dependency
# ---------------------------------------------------------------------------

TOOL_GROUP_MAP: dict[str, str] = {
    "environment.": "environment",
    "schema.": "schema",
    "db.": "db",
    "semantic.": "semantic",
    "memory.": "memory",
}


def tool_to_group(tool_name: str) -> str | None:
    """Map a tool name to its planner group.  Returns None if unmapped."""
    for prefix, group in TOOL_GROUP_MAP.items():
        if tool_name == prefix.rstrip("."):
            return group
    for prefix, group in TOOL_GROUP_MAP.items():
        if tool_name.startswith(prefix):
            return group
    return None
