from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel

RiskLevel = Literal["safe", "warning", "danger"]
SideEffect = Literal["none", "read", "write", "destructive"]
ConcurrencyMode = Literal["sequential", "parallel_safe"]
MergeStrategy = Literal["reuse", "new", "always_new"]


class ToolPolicy(BaseModel):
    side_effect: SideEffect = "none"
    risk_level: RiskLevel = "safe"
    requires_approval: bool = False
    requires_validated_sql: bool = False
    allowed_execution_modes: tuple[str, ...] = ()


class ToolExecutionSpec(BaseModel):
    timeout_seconds: int = 30
    idempotent: bool = True
    retryable: bool = False
    max_retries: int = 0
    concurrency: ConcurrencyMode = "sequential"


class ToolStateSpec(BaseModel):
    consumes: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    clear_on_success: tuple[str, ...] = ()
    merge_strategy: MergeStrategy = "reuse"


class ArtifactSpec(BaseModel):
    emit: bool = False
    artifact_types: tuple[str, ...] = ()


I = TypeVar("I", bound=BaseModel)
O = TypeVar("O", bound=BaseModel)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    group: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    policy: ToolPolicy
    execution: ToolExecutionSpec
    state: ToolStateSpec
    artifacts: ArtifactSpec
    kind: Literal["code", "llm", "hybrid"] = "code"
    metadata: dict[str, Any] | None = None

    @property
    def input_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()

    @property
    def output_schema(self) -> dict[str, Any]:
        return self.output_model.model_json_schema()


class BaseTool(Generic[I, O]):
    name: str
    group: str
    description: str
    input_model: type[I]
    output_model: type[O]
    policy: ToolPolicy = ToolPolicy()
    execution: ToolExecutionSpec = ToolExecutionSpec()
    state: ToolStateSpec = ToolStateSpec()
    artifacts: ArtifactSpec = ArtifactSpec()
    kind: Literal["code", "llm", "hybrid"] = "code"
    metadata: dict[str, Any] = {}

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            group=self.group,
            description=self.description,
            input_model=self.input_model,
            output_model=self.output_model,
            policy=self.policy,
            execution=self.execution,
            state=self.state,
            artifacts=self.artifacts,
            kind=self.kind,
            metadata=dict(self.metadata),
        )

    def run(self, tool_input: I, context: Any) -> O:
        raise NotImplementedError
