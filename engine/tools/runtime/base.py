from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import re
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.resource import is_namespaced_resource_kind
from engine.tools.runtime.semantics import ToolSemanticSpec
from engine.tools.runtime.observation import (
    ToolObservationProjection,
    safe_observation_facts,
)
from engine.tools.runtime.result import ToolOutcome, ToolReconciliation

if TYPE_CHECKING:
    from engine.tools.runtime.admission import (
        ToolAdmissionContext,
        ToolAdmissionDecision,
    )
    from engine.tools.runtime.context import ToolRunContext

RiskLevel = Literal["safe", "warning", "danger"]
ConcurrencyMode = Literal["sequential", "parallel_safe"]
ToolExecutionBackend = Literal["in_process", "isolated_process"]
ToolPresentationCategory = Literal["explore", "query", "visualize", "manage"]
ToolPresentationVisibility = Literal["summary", "details", "developer"]
ToolProgressStyle = Literal["indeterminate", "determinate", "none"]
ToolCapability = Literal[
    "metadata_read",
    "metadata_write",
    "filesystem_read",
    "filesystem_write",
    "network",
    "subprocess",
]

TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class ToolRecoveryPolicy(StrEnum):
    """How an interrupted tool leaf is made safe after worker loss.

    ``RETRY_SAFE`` is valid only when repeating the same authorized input with
    ``ToolRunContext.idempotency_key`` cannot duplicate the effect.
    ``RECONCILE`` requires a read-only lookup by that key before any replay.
    """

    RETRY_SAFE = "retry_safe"
    RECONCILE = "reconcile"
    NEVER_RETRY = "never_retry"


class ToolPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    risk_level: RiskLevel = "safe"
    requires_approval: bool = False
    requires_admission: bool = False
    allowed_execution_modes: tuple[str, ...] = ()
    visible_to_model: bool = True


class ToolResourceRequirement(BaseModel):
    """Declarative binding from one Tool input to one exact Project Resource."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    selector_field: str | None = Field(default=None, min_length=1, max_length=64)
    artifact_selector_field: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
    )

    @model_validator(mode="after")
    def validate_kind(self) -> "ToolResourceRequirement":
        if not is_namespaced_resource_kind(self.kind) or len(self.kind) > 64:
            raise ValueError(
                "Resource kind must be a namespaced identifier such as "
                "'dbfox.data.database'"
            )
        if (
            self.selector_field is not None
            and self.artifact_selector_field is not None
        ):
            raise ValueError(
                "A resource requirement cannot use both an identity selector "
                "and an artifact selector"
            )
        return self


class ToolExecutionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    timeout_seconds: int = Field(default=30, ge=1, le=3_600)
    recovery: ToolRecoveryPolicy = ToolRecoveryPolicy.NEVER_RETRY
    retryable: bool = False
    max_retries: int = Field(default=0, ge=0, le=5)
    concurrency: ConcurrencyMode = "sequential"
    max_output_bytes: int = Field(default=1_000_000, ge=1_024, le=16_000_000)
    backend: ToolExecutionBackend = "in_process"
    capabilities: tuple[ToolCapability, ...] = ()
    required_resources: tuple[ToolResourceRequirement, ...] = ()

    @model_validator(mode="after")
    def validate_execution_spec(self) -> "ToolExecutionSpec":
        if (
            self.retryable
            and self.recovery is not ToolRecoveryPolicy.RETRY_SAFE
        ):
            raise ValueError(
                "retryable=True requires recovery='retry_safe'"
            )
        if self.max_retries and not self.retryable:
            raise ValueError(
                "max_retries requires retryable=True"
            )
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("Tool capabilities must not contain duplicates")
        if len(self.required_resources) > 8:
            raise ValueError("Tool required_resources cannot exceed 8 items")
        kinds = [requirement.kind for requirement in self.required_resources]
        if len(set(kinds)) != len(kinds):
            raise ValueError("Tool required_resources cannot contain duplicate kinds")
        return self


class ToolPresentation(BaseModel):
    """Stable user-facing metadata owned by the tool definition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1, max_length=80)
    category: ToolPresentationCategory
    visibility: ToolPresentationVisibility = "summary"
    progress: ToolProgressStyle = "indeterminate"


I = TypeVar("I", bound=BaseModel)
O = TypeVar("O", bound=BaseModel)


class ToolInputModel(BaseModel):
    """Strict base contract for all model-authored function arguments."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ToolOutputModel(BaseModel):
    """Strict base contract for data returned by one executable tool."""

    model_config = ConfigDict(extra="forbid", frozen=True)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    group: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    policy: ToolPolicy
    execution: ToolExecutionSpec
    semantics: ToolSemanticSpec
    presentation: ToolPresentation
    kind: Literal["code", "llm", "hybrid", "control"] = "code"

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
            name = "my_tool"
            group = "my_group"
            description = "What this tool does."
            input_model = MyInput
            output_model = MyOutput
            policy = ToolPolicy(...)      # optional
            execution = ToolExecutionSpec()  # optional
            kind = "code"                 # optional

    ``name``, ``group``, ``description``, ``input_model``, ``output_model``, and
    ``presentation`` are enforced at subclass definition time via
    ``__init_subclass__``.
    """

    # Defaults — subclasses override as needed
    name: str
    group: str
    description: str
    input_model: type[I]
    output_model: type[O]
    presentation: ToolPresentation
    version: str = "1"
    policy: ToolPolicy = ToolPolicy()
    execution: ToolExecutionSpec = ToolExecutionSpec()
    semantics: ToolSemanticSpec = ToolSemanticSpec()
    kind: Literal["code", "llm", "hybrid"] = "code"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Only enforce on concrete tool classes, skip intermediate bases.
        required = [
            "name",
            "group",
            "description",
            "input_model",
            "output_model",
            "presentation",
        ]
        missing = [attr for attr in required if not hasattr(cls, attr) or getattr(cls, attr, None) is None]
        if missing:
            raise TypeError(
                f"{cls.__name__} is missing required tool attributes: {', '.join(missing)}. "
                f"Define them as class-level attributes on your tool class."
            )
        input_model = getattr(cls, "input_model")
        if input_model.model_config.get("extra") != "forbid":
            raise TypeError(
                f"{cls.__name__}.input_model must reject unknown fields. "
                "Inherit from ToolInputModel or set ConfigDict(extra='forbid')."
            )
        output_model = getattr(cls, "output_model")
        if output_model.model_config.get("extra") != "forbid":
            raise TypeError(
                f"{cls.__name__}.output_model must reject unknown fields. "
                "Inherit from ToolOutputModel or set ConfigDict(extra='forbid')."
            )
        name = str(getattr(cls, "name"))
        if TOOL_NAME_PATTERN.fullmatch(name) is None:
            raise TypeError(
                f"{cls.__name__}.name must match {TOOL_NAME_PATTERN.pattern} so the "
                "same canonical Tool ID is valid for every supported model provider."
            )
        group = str(getattr(cls, "group")).strip()
        if not group or len(group) > 64:
            raise TypeError(f"{cls.__name__}.group must contain 1 to 64 characters")
        description = str(getattr(cls, "description")).strip()
        if not description or len(description) > 1_024:
            raise TypeError(
                f"{cls.__name__}.description must contain 1 to 1024 characters"
            )
        version = str(getattr(cls, "version", "")).strip()
        if not version or len(version) > 32:
            raise TypeError(f"{cls.__name__}.version must contain 1 to 32 characters")
        execution = cast(
            ToolExecutionSpec,
            getattr(cls, "execution", ToolExecutionSpec()),
        )
        input_fields = set(input_model.model_fields)
        for requirement in execution.required_resources:
            for selector_field in (
                requirement.selector_field,
                requirement.artifact_selector_field,
            ):
                if selector_field is not None and selector_field not in input_fields:
                    raise TypeError(
                        f"{cls.__name__} resource selector field "
                        f"{selector_field!r} is not present in its input model"
                    )
        if (
            execution.recovery is ToolRecoveryPolicy.RECONCILE
            and "reconcile" not in cls.__dict__
        ):
            raise TypeError(
                f"{cls.__name__} declares recovery='reconcile' and must implement reconcile()"
            )
        policy = cast(ToolPolicy, getattr(cls, "policy", ToolPolicy()))
        if (
            policy.requires_admission
            and getattr(cls, "admit", None) is BaseTool.admit
        ):
            raise TypeError(
                f"{cls.__name__} declares requires_admission=True and must implement admit()"
            )

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,  # type: ignore[attr-defined]
            version=self.version,
            group=self.group,  # type: ignore[attr-defined]
            description=self.description,  # type: ignore[attr-defined]
            input_model=self.input_model,  # type: ignore[attr-defined]
            output_model=self.output_model,  # type: ignore[attr-defined]
            policy=self.policy,
            execution=self.execution,
            semantics=self.semantics,
            presentation=self.presentation,  # type: ignore[attr-defined]
            kind=self.kind,
        )

    def run(
        self,
        tool_input: I,
        context: ToolRunContext,
    ) -> O | ToolOutcome[O]:
        raise NotImplementedError(f"{self.__class__.__name__}.run() must be implemented")

    def cancel(self, invocation_id: str) -> None:
        """Best-effort interruption hook for the currently running invocation."""

        del invocation_id

    def admit(
        self,
        tool_input: I,
        context: "ToolAdmissionContext",
    ) -> "ToolAdmissionDecision":
        """Validate domain facts before policy grants an execution attempt."""

        raise NotImplementedError(
            f"{self.__class__.__name__}.admit() must be implemented"
        )

    def reconcile(
        self,
        tool_input: I,
        context: ToolRunContext,
    ) -> ToolReconciliation:
        """Look up a previously interrupted external action without repeating it."""

        raise NotImplementedError(
            f"{self.__class__.__name__}.reconcile() must be implemented"
        )

    def project_observation(
        self,
        *,
        status: str,
        output: dict[str, Any],
        artifacts: list[Any],
    ) -> ToolObservationProjection:
        if status != "success":
            return ToolObservationProjection(summary=f"{self.name} 未能完成。")
        facts = {
            key: output[key]
            for key in ("count", "tableCount", "matchCount", "hasMore", "refreshed")
            if key in output
        }
        return ToolObservationProjection(
            summary=f"{self.name} 已完成。",
            facts=safe_observation_facts(facts),
        )

class ControlDisposition(StrEnum):
    SETTLED = "settled"
    WAITING_INPUT = "waiting_input"


@dataclass(frozen=True, slots=True)
class ControlCommandResult(Generic[O]):
    disposition: ControlDisposition
    output: O | None = None
    summary: str = ""
    facts: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ControlCommandContext:
    db: Any
    lease: Any
    run_id: str
    turn_id: str
    invocation_id: str


class ControlCommand(Generic[I, O]):
    """Model-visible control signal handled by the Agent Runtime, not ToolRuntime."""

    name: str
    group: str = "control"
    description: str
    input_model: type[I]
    output_model: type[O]
    presentation: ToolPresentation
    version: str = "1"
    policy: ToolPolicy = ToolPolicy()
    execution: ToolExecutionSpec = ToolExecutionSpec()
    semantics: ToolSemanticSpec = ToolSemanticSpec(contributes_progress=False)
    kind: Literal["control"] = "control"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        required = [
            "name",
            "description",
            "input_model",
            "output_model",
            "presentation",
        ]
        missing = [
            attr
            for attr in required
            if not hasattr(cls, attr) or getattr(cls, attr, None) is None
        ]
        if missing:
            raise TypeError(
                f"{cls.__name__} is missing required control attributes: "
                f"{', '.join(missing)}"
            )
        for attribute, base_model in (
            ("input_model", ToolInputModel),
            ("output_model", ToolOutputModel),
        ):
            model = getattr(cls, attribute)
            if not issubclass(model, base_model):
                raise TypeError(
                    f"{cls.__name__}.{attribute} must inherit from "
                    f"{base_model.__name__}"
                )
        if TOOL_NAME_PATTERN.fullmatch(str(getattr(cls, "name"))) is None:
            raise TypeError(
                f"{cls.__name__}.name must match {TOOL_NAME_PATTERN.pattern}"
            )

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            version=self.version,
            group=self.group,
            description=self.description,
            input_model=self.input_model,
            output_model=self.output_model,
            policy=self.policy,
            execution=self.execution,
            semantics=self.semantics,
            presentation=self.presentation,
            kind=self.kind,
        )

    def handle(
        self,
        command_input: I,
        context: ControlCommandContext,
    ) -> ControlCommandResult[O]:
        raise NotImplementedError
