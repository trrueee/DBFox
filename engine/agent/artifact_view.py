"""Generic read-only presentation contract for durable tabular Artifact payloads."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from engine.agent.artifact import Artifact


ArtifactViewScalar = Annotated[str, Field(max_length=4_096)] | int | float | bool | None
ArtifactViewFilterValue = ArtifactViewScalar | Annotated[
    list[ArtifactViewScalar], Field(max_length=100)
]


class ArtifactViewFilter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    column: str = Field(min_length=1, max_length=256)
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
    value: ArtifactViewFilterValue = None


class ArtifactViewSort(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    column: str = Field(min_length=1, max_length=256)
    direction: Literal["asc", "desc"]


class ArtifactTablePageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=500)
    sort: tuple[ArtifactViewSort, ...] = Field(default=(), max_length=16)
    filters: tuple[ArtifactViewFilter, ...] = Field(default=(), max_length=16)
    search: str | None = Field(default=None, max_length=512)
    count_mode: Literal["none", "exact", "estimate"] = "none"


class ArtifactTableExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sort: tuple[ArtifactViewSort, ...] = Field(default=(), max_length=16)
    filters: tuple[ArtifactViewFilter, ...] = Field(default=(), max_length=16)
    search: str | None = Field(default=None, max_length=512)


class ArtifactTablePage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    columns: list[str]
    rows: list[dict[str, Any]]
    page: int
    page_size: int
    row_count: int
    has_next_page: bool
    latency_ms: int
    consistency: Literal["durable_snapshot"] = "durable_snapshot"
    original_executed_at: str | None = None
    read_at: str
    read_id: str
    resource_version: str
    source_fingerprint: str
    warnings: list[str] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class ArtifactCsvStream:
    chunks: Iterator[str]
    row_count: int
    source_truncated: bool


class ArtifactChartData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    series: list[dict[str, Any]]
    sample_size: int = Field(ge=0)
    truncated: bool = False
    consistency: Literal["durable_snapshot"] = "durable_snapshot"
    original_executed_at: str | None = None
    read_at: str
    read_id: str
    resource_version: str
    source_fingerprint: str


class ArtifactViewError(Exception):
    """Client-safe failure raised while resolving a durable Artifact view."""

    _ALLOWED_STATUS_CODES = frozenset({400, 404, 409})

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        normalized = str(message).strip()
        if not normalized or len(normalized) > 512:
            raise ValueError("Artifact view error must contain 1 to 512 characters")
        if status_code not in self._ALLOWED_STATUS_CODES:
            raise ValueError("Artifact view error status is not client-safe")
        super().__init__(normalized)
        self.message = normalized
        self.status_code = status_code


class ArtifactTableViewProvider(Protocol):
    """Capability-owned reader for one durable tabular Artifact type."""

    def page(
        self,
        artifact: Artifact,
        request: ArtifactTablePageRequest,
    ) -> ArtifactTablePage: ...

    def export_csv(
        self,
        artifact: Artifact,
        request: ArtifactTableExportRequest,
    ) -> ArtifactCsvStream: ...


class ArtifactChartViewProvider(Protocol):
    """Capability-owned reader for one durable chart Artifact type."""

    def data(
        self,
        artifact: Artifact,
        source_artifact: Artifact,
    ) -> ArtifactChartData: ...
