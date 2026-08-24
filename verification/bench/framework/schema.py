"""Small, domain-neutral contracts for benchmark ownership and measurement."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BenchSubjectKind(StrEnum):
    CORE = "core"
    CAPABILITY = "capability"
    COMPOSITION = "composition"


class MetricDirection(StrEnum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"
    ZERO_IS_BEST = "zero_is_best"
    INFORMATIONAL = "informational"


class SubjectUnderTest(BaseModel):
    """Declares what owns a benchmark result and what is only fixture support."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: BenchSubjectKind
    components: tuple[str, ...] = Field(min_length=1)
    supporting_fixtures: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_subject_shape(self) -> "SubjectUnderTest":
        if self.kind is BenchSubjectKind.CORE and any(
            component.startswith("dbfox.") for component in self.components
        ):
            raise ValueError("CoreBench cannot name a capability DLC as its subject")
        if self.kind is BenchSubjectKind.CAPABILITY and len(self.components) != 1:
            raise ValueError("CapabilityBench must have exactly one subject capability")
        if self.kind is BenchSubjectKind.COMPOSITION and len(self.components) < 2:
            raise ValueError("CompositionBench must name at least two components")
        return self


class MetricSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,79}$")
    direction: MetricDirection
    unit: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=240)


class ExecutionMatrix(BaseModel):
    """Declares provider and repetition dimensions without owning execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_modes: tuple[str, ...] = Field(min_length=1)
    default_repetitions: int = Field(default=1, ge=1, le=100)
    max_repetitions: int = Field(ge=1, le=100)

    @model_validator(mode="after")
    def validate_repetitions(self) -> "ExecutionMatrix":
        if self.default_repetitions > self.max_repetitions:
            raise ValueError("default_repetitions cannot exceed max_repetitions")
        if len(self.provider_modes) != len(set(self.provider_modes)):
            raise ValueError("provider_modes must be unique")
        return self


class SuiteManifest(BaseModel):
    """Versioned suite identity; domain case schemas remain suite-owned."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    suite_id: str = Field(pattern=r"^(core|capability|composition)\.[a-z0-9_.-]+$")
    suite_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    description: str = Field(min_length=1, max_length=500)
    subject: SubjectUnderTest
    execution: ExecutionMatrix
    dataset: str = Field(min_length=1, max_length=240)
    metrics: tuple[MetricSpec, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity(self) -> "SuiteManifest":
        if not self.suite_id.startswith(f"{self.subject.kind.value}."):
            raise ValueError("suite_id prefix must match the subject kind")
        names = [metric.name for metric in self.metrics]
        if len(names) != len(set(names)):
            raise ValueError("suite metric names must be unique")
        return self

    def public_summary(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "suite_id": self.suite_id,
            "suite_version": self.suite_version,
            "subject": self.subject.model_dump(mode="json"),
            "execution": self.execution.model_dump(mode="json"),
            "dataset": self.dataset,
            "metrics": [metric.model_dump(mode="json") for metric in self.metrics],
        }


def load_suite_manifest(path: Path) -> SuiteManifest:
    return SuiteManifest.model_validate_json(path.read_text(encoding="utf-8"))
