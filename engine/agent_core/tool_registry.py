"""DataBox Agent Tool Registry — canonical type system for tool contracts.

This is the SINGLE source of truth for tool type definitions.
No other registry module exists.  All tool wrappers use these types.

Dependency rule: agent_core has zero agent / semantic / environment dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from engine.agent_core.types import AgentRunRequest, ToolObservation


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
    max_retries: int = 0


# ---------------------------------------------------------------------------
# Execution characteristics (timeout / idempotency / concurrency)
# ---------------------------------------------------------------------------


@dataclass
class ToolExecutionSpec:
    """Execution behaviour — separate from security policy."""

    timeout_seconds: int = 30
    idempotent: bool = True
    retryable: bool = False
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

    get() returns None for unknown tools (safe for guard code).
    require() raises KeyError for unknown tools (fail-fast for execution code).
    """

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, tool: RegisteredTool) -> "ToolRegistry":
        name = tool.spec.name
        if name in self._tools:
            raise ValueError(f"Agent tool `{name}` is already registered.")
        self._tools[name] = tool
        return self

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
