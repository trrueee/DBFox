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
    visible_to_model: bool = True


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
    """Base class for all DBFox agent tools.

    Subclasses MUST define these class-level attributes::

        class MyTool(BaseTool[MyInput, MyOutput]):
            name = "my.tool"
            group = "my_group"
            description = "What this tool does."
            input_model = MyInput
            output_model = MyOutput
            policy = ToolPolicy(...)      # optional
            execution = ToolExecutionSpec()  # optional
            state = ToolStateSpec(...)    # optional
            artifacts = ArtifactSpec(...) # optional
            kind = "code"                 # optional

    ``name``, ``group``, ``description``, ``input_model``, and
    ``output_model`` are enforced at subclass definition time via
    ``__init_subclass__``.
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Only enforce on concrete tool classes, skip intermediate bases.
        required = ["name", "group", "description", "input_model", "output_model"]
        missing = [attr for attr in required if not hasattr(cls, attr) or getattr(cls, attr, None) is None]
        if missing:
            raise TypeError(
                f"{cls.__name__} is missing required tool attributes: {', '.join(missing)}. "
                f"Define them as class-level attributes on your tool class."
            )

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,  # type: ignore[attr-defined]
            group=self.group,  # type: ignore[attr-defined]
            description=self.description,  # type: ignore[attr-defined]
            input_model=self.input_model,  # type: ignore[attr-defined]
            output_model=self.output_model,  # type: ignore[attr-defined]
            policy=self.policy,
            execution=self.execution,
            state=self.state,
            artifacts=self.artifacts,
            kind=self.kind,
            metadata=dict(self.metadata),
        )

    def run(self, tool_input: I, context: Any) -> O:
        raise NotImplementedError(f"{self.__class__.__name__}.run() must be implemented")
