from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from engine.agent_core.types import AgentRunRequest, ToolObservation


RiskLevel = Literal["safe", "warning", "danger"]
SideEffect = Literal["none", "read", "write", "destructive"]


class ToolPolicy(BaseModel):
    risk_level: RiskLevel = "safe"
    side_effect: SideEffect = "none"
    requires_approval: bool = False
    requires_validated_sql: bool = False
    max_retries: int = 0


class ToolSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    input_model: type[BaseModel] | None = Field(default=None, exclude=True)
    output_model: type[BaseModel] | None = Field(default=None, exclude=True)
    policy: ToolPolicy = Field(default_factory=ToolPolicy)
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass
class ToolContext:
    db: Session
    request: AgentRunRequest
    state: dict[str, Any]


ToolHandler = Callable[[ToolContext, dict[str, Any]], ToolObservation]


@dataclass
class RegisteredTool:
    spec: ToolSpec
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, tool: RegisteredTool) -> ToolRegistry:
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
            raise KeyError(f"Unknown Agent tool `{name}`. Available tools: {available}")
        return tool

    def list_specs(self) -> list[ToolSpec]:
        return [self._tools[name].spec for name in sorted(self._tools)]
