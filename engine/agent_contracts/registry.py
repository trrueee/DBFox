from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from engine.agent_contracts.tool_runtime_gateway import ToolRuntimeGateway
from engine.agent_contracts.types import AgentRunRequest, ToolObservation


ToolRiskLevel = Literal["safe", "warning", "danger"]


class ToolSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    input_model: type[BaseModel] | None = Field(default=None, exclude=True)
    output_model: type[BaseModel] | None = Field(default=None, exclude=True)
    risk_level: ToolRiskLevel = "safe"
    requires_approval: bool = False
    timeout_seconds: int = 30
    idempotent: bool = True


@dataclass
class AgentToolContext:
    db: Session
    request: AgentRunRequest
    state: Any | None = None


class AgentTool(Protocol):
    spec: ToolSpec

    def execute(self, input: dict[str, Any], ctx: AgentToolContext) -> ToolObservation:
        ...


ToolHandler = Callable[[dict[str, Any], AgentToolContext], ToolObservation]


@dataclass
class FunctionAgentTool:
    spec: ToolSpec
    handler: ToolHandler

    def execute(self, input: dict[str, Any], ctx: AgentToolContext) -> ToolObservation:
        validated_input = ToolRuntimeGateway.validate_input(self.spec.name, self.spec.input_model, input)
        observation = self.handler(validated_input, ctx)
        return ToolRuntimeGateway.validate_observation_output(self.spec.name, self.spec.output_model, observation)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> ToolRegistry:
        name = tool.spec.name
        if name in self._tools:
            raise ValueError(f"Agent tool `{name}` is already registered.")
        self._tools[name] = tool
        return self

    def get(self, name: str) -> AgentTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            available = ", ".join(sorted(self._tools)) or "<none>"
            raise KeyError(f"Unknown Agent tool `{name}`. Available tools: {available}") from exc

    def list_specs(self) -> list[ToolSpec]:
        return [self._tools[name].spec for name in sorted(self._tools)]
