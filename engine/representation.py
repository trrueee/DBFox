"""Core-owned generic Artifact representation contracts exposed through the DLC Host.

Representations are bounded, read-only projections of a durable Artifact.  The
Core owns dispatch, authority and budgets; the contributing DLC owns the
representation-specific request and payload semantics.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.agent.artifact import Artifact


REPRESENTATION_TYPE_PATTERN = r"^[a-z][a-z0-9_.-]{2,127}$"
REPRESENTATION_OPERATION_PATTERN = r"^[a-z][a-z0-9_.-]{0,63}$"
DATAFRAME_REPRESENTATION_TYPE = "dbfox.dataframe.v1"


class ArtifactRepresentationOperation(BaseModel):
    """One operation exposed by a representation provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=REPRESENTATION_OPERATION_PATTERN)
    result_kind: Literal["json", "stream"] = "json"
    media_type: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_media_type(self) -> "ArtifactRepresentationOperation":
        if self.result_kind == "stream" and self.media_type is None:
            raise ValueError("Stream representation operations require a media_type")
        if self.result_kind == "json" and self.media_type is not None:
            raise ValueError("JSON representation operations cannot declare a media_type")
        return self


class ArtifactRepresentationDescriptor(BaseModel):
    """Wire-safe description of one representation available for an Artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    representation_type: str = Field(pattern=REPRESENTATION_TYPE_PATTERN)
    version: int = Field(ge=1)
    operations: tuple[ArtifactRepresentationOperation, ...] = Field(
        min_length=1,
        max_length=32,
    )

    @model_validator(mode="after")
    def validate_operations(self) -> "ArtifactRepresentationDescriptor":
        names = [operation.name for operation in self.operations]
        if len(names) != len(set(names)):
            raise ValueError("Representation operation names must be unique")
        return self

    def operation(self, name: str) -> ArtifactRepresentationOperation | None:
        return next((item for item in self.operations if item.name == name), None)


class ArtifactRepresentationRequest(BaseModel):
    """Generic wire request; the provider validates operation parameters."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: str = Field(pattern=REPRESENTATION_OPERATION_PATTERN)
    parameters: dict[str, Any] = Field(default_factory=dict, max_length=64)


class ArtifactRepresentationResult(BaseModel):
    """Bounded JSON result returned by a representation provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    representation_type: str = Field(pattern=REPRESENTATION_TYPE_PATTERN)
    representation_version: int = Field(ge=1)
    operation: str = Field(pattern=REPRESENTATION_OPERATION_PATTERN)
    payload: dict[str, Any]
    consistency: Literal["durable_snapshot", "live_reexecution"]
    original_observed_at: str | None = Field(default=None, max_length=64)
    read_at: str = Field(min_length=1, max_length=64)
    read_id: str = Field(min_length=1, max_length=128)
    source_version: str = Field(min_length=1, max_length=256)
    source_fingerprint: str = Field(min_length=1, max_length=256)
    warnings: tuple[str, ...] = Field(default=(), max_length=32)
    notices: tuple[str, ...] = Field(default=(), max_length=32)


@dataclass(frozen=True)
class ArtifactRepresentationStream:
    """Bounded stream result with safe response metadata."""

    chunks: Iterator[str | bytes]
    media_type: str
    file_name: str
    metadata: dict[str, str]


@dataclass(frozen=True)
class ArtifactRepresentationContext:
    """Core-authorized services available to one provider read."""

    artifact_loader: Callable[[str], Artifact | None]

    def artifact(self, artifact_id: str) -> Artifact:
        artifact = self.artifact_loader(str(artifact_id).strip())
        if artifact is None:
            raise ArtifactRepresentationError(
                "SOURCE_UNAVAILABLE",
                "The related Artifact is unavailable.",
                status_code=404,
            )
        return artifact


class ArtifactRepresentationProvider(Protocol):
    """Capability-owned reader for representations of one Artifact type."""

    def describe(self, artifact: Artifact) -> ArtifactRepresentationDescriptor: ...

    def execute(
        self,
        artifact: Artifact,
        request: ArtifactRepresentationRequest,
        context: ArtifactRepresentationContext,
    ) -> ArtifactRepresentationResult | ArtifactRepresentationStream: ...


def execute_artifact_representation(
    *,
    artifact: Artifact,
    representation_type: str,
    request: ArtifactRepresentationRequest,
    provider: ArtifactRepresentationProvider,
    context: ArtifactRepresentationContext,
    expected_kind: Literal["json", "stream"],
) -> tuple[
    ArtifactRepresentationDescriptor,
    ArtifactRepresentationResult | ArtifactRepresentationStream,
]:
    """Dispatch one provider through the canonical descriptor/result contract."""

    descriptor = provider.describe(artifact)
    if descriptor.representation_type != representation_type:
        raise RuntimeError("Representation provider descriptor does not match registration")
    operation = descriptor.operation(request.operation)
    if operation is None or operation.result_kind != expected_kind:
        raise ArtifactRepresentationError(
            "UNSUPPORTED_REPRESENTATION",
            "The representation does not provide the requested operation surface.",
            status_code=409,
        )
    untrusted_result = provider.execute(artifact, request, context)
    if expected_kind == "json":
        if not isinstance(untrusted_result, ArtifactRepresentationResult):
            raise TypeError("JSON operation returned a non-JSON representation result")
        result = ArtifactRepresentationResult.model_validate(untrusted_result)
        if (
            result.representation_type != descriptor.representation_type
            or result.representation_version != descriptor.version
            or result.operation != request.operation
        ):
            raise RuntimeError("Representation result does not match its descriptor")
        return descriptor, result
    if not isinstance(untrusted_result, ArtifactRepresentationStream):
        raise TypeError("Stream operation returned a non-stream representation result")
    if untrusted_result.media_type != operation.media_type:
        raise RuntimeError("Representation stream media type does not match descriptor")
    return descriptor, untrusted_result


class ArtifactRepresentationError(Exception):
    """Client-safe representation failure with a stable public code."""

    _ALLOWED_CODES = frozenset(
        {
            "NOT_FOUND",
            "FORBIDDEN",
            "UNSUPPORTED_REPRESENTATION",
            "SOURCE_UNAVAILABLE",
            "SOURCE_CHANGED",
            "STALE",
            "INVALID_REQUEST",
            "DEADLINE_EXCEEDED",
            "CANCELLED",
            "PROVIDER_FAILURE",
        }
    )
    _ALLOWED_STATUS_CODES = frozenset({400, 403, 404, 409, 410, 422, 429, 503})

    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        normalized_code = str(code).strip().upper()
        normalized_message = str(message).strip()
        if normalized_code not in self._ALLOWED_CODES:
            raise ValueError("Representation error code is not part of the public catalog")
        if not normalized_message or len(normalized_message) > 512:
            raise ValueError("Representation error message must contain 1 to 512 characters")
        if status_code not in self._ALLOWED_STATUS_CODES:
            raise ValueError("Representation error status is not client-safe")
        super().__init__(normalized_message)
        self.code = normalized_code
        self.message = normalized_message
        self.status_code = status_code


DataFrameScalar = Annotated[str, Field(max_length=16_384)] | int | float | bool | None
DataFrameFilterValue = DataFrameScalar | Annotated[
    list[DataFrameScalar], Field(max_length=100)
]


class DataFrameFilter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str = Field(min_length=1, max_length=256)
    operator: Literal[
        "equals",
        "not_equals",
        "contains",
        "starts_with",
        "ends_with",
        "gt",
        "gte",
        "lt",
        "lte",
        "is_null",
        "is_not_null",
        "in",
        "not_in",
    ]
    value: DataFrameFilterValue = None


class DataFrameSort(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str = Field(min_length=1, max_length=256)
    direction: Literal["asc", "desc"]


class DataFramePageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)
    sort: tuple[DataFrameSort, ...] = Field(default=(), max_length=16)
    filters: tuple[DataFrameFilter, ...] = Field(default=(), max_length=16)
    search: str | None = Field(default=None, max_length=512)
    count_mode: Literal["none", "exact", "estimate"] = "none"


class DataFrameExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sort: tuple[DataFrameSort, ...] = Field(default=(), max_length=16)
    filters: tuple[DataFrameFilter, ...] = Field(default=(), max_length=16)
    search: str | None = Field(default=None, max_length=512)


class DataFrameField(BaseModel):
    """One Arrow/Grafana-inspired field with a bounded value vector."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, max_length=256)
    name: str = Field(min_length=1, max_length=256)
    type: Literal[
        "boolean",
        "integer",
        "number",
        "string",
        "datetime",
        "date",
        "time",
        "json",
        "binary",
        "unknown",
    ] = "unknown"
    nullable: bool = True
    semantic_type: str | None = Field(default=None, max_length=128)
    unit: str | None = Field(default=None, max_length=64)
    values: list[DataFrameScalar] = Field(max_length=500)


class DataFramePage(BaseModel):
    """Canonical bounded JSON page for ``dbfox.dataframe.v1``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fields: list[DataFrameField] = Field(max_length=256)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=500)
    row_count: int | None = Field(default=None, ge=0)
    has_next_page: bool
    latency_ms: int = Field(ge=0)
    source_truncated: bool = False

    @model_validator(mode="after")
    def validate_field_vectors(self) -> "DataFramePage":
        keys = [field.key for field in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError("DataFrame field keys must be unique")
        lengths = {len(field.values) for field in self.fields}
        if len(lengths) > 1:
            raise ValueError("All DataFrame fields must contain the same number of values")
        if lengths and next(iter(lengths)) > self.page_size:
            raise ValueError("DataFrame field values exceed the requested page size")
        return self

    @property
    def returned_row_count(self) -> int:
        return len(self.fields[0].values) if self.fields else 0
