"""User-visible Agent work products and their immutable relationships."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class ArtifactType(StrEnum):
    ANALYSIS_PLAN = "analysis_plan"
    SQL = "sql"
    SAFETY = "safety"
    RESULT_VIEW = "result_view"
    CHART = "chart"
    MARKDOWN = "markdown"
    ERROR = "error"


class ArtifactStatus(StrEnum):
    CREATING = "creating"
    COMPLETED = "completed"
    FAILED = "failed"
    STALE = "stale"


class ArtifactVisibility(StrEnum):
    """Product presentation tier, independent from durable audit retention."""

    PRIMARY = "primary"
    SUPPORTING = "supporting"
    INTERNAL = "internal"


_DEFAULT_VISIBILITY_BY_TYPE: dict[ArtifactType, ArtifactVisibility] = {
    ArtifactType.ANALYSIS_PLAN: ArtifactVisibility.INTERNAL,
    ArtifactType.SQL: ArtifactVisibility.SUPPORTING,
    ArtifactType.SAFETY: ArtifactVisibility.INTERNAL,
    ArtifactType.RESULT_VIEW: ArtifactVisibility.PRIMARY,
    ArtifactType.CHART: ArtifactVisibility.PRIMARY,
    ArtifactType.MARKDOWN: ArtifactVisibility.PRIMARY,
    ArtifactType.ERROR: ArtifactVisibility.INTERNAL,
}


def default_artifact_visibility(artifact_type: ArtifactType) -> ArtifactVisibility:
    return _DEFAULT_VISIBILITY_BY_TYPE[artifact_type]


class ArtifactRelationType(StrEnum):
    VALIDATED_BY = "validated_by"
    EXECUTED_AS = "executed_as"
    VISUALIZED_AS = "visualized_as"
    DERIVED_FROM = "derived_from"
    SUPPORTS = "supports"


class ArtifactRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relation: ArtifactRelationType
    artifact_id: str


class ArtifactRelationDraft(BaseModel):
    """Relation to an existing Artifact or an earlier draft in the same outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    relation: ArtifactRelationType
    artifact_id: str | None = None
    draft_key: str | None = None

    @model_validator(mode="after")
    def validate_target(self) -> "ArtifactRelationDraft":
        if bool(self.artifact_id) == bool(self.draft_key):
            raise ValueError(
                "Artifact relation draft requires exactly one target"
            )
        return self


class ArtifactDraft(BaseModel):
    """Provider-neutral Artifact description emitted by a data tool."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    type: ArtifactType
    title: str = Field(min_length=1, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_draft_refs: dict[str, str] = Field(default_factory=dict)
    summary: str | None = Field(default=None, max_length=2_000)
    semantic_key: str | None = Field(default=None, max_length=1_000)
    payload_ref: str | None = Field(default=None, max_length=1_000)
    relations: tuple[ArtifactRelationDraft, ...] = ()
    visibility: ArtifactVisibility | None = None
    select_if_none: bool = False

class SqlArtifactPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    sql: str
    safe_sql: str = Field(alias="safeSql")
    dialect: str
    query_fingerprint: str = Field(alias="queryFingerprint")


class SafetyArtifactPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    can_execute: bool = Field(alias="canExecute")
    requires_approval: bool = Field(alias="requiresApproval")
    risk_level: str = Field(alias="riskLevel")
    blocked_reasons: list[str] = Field(alias="blockedReasons")
    messages: list[str]
    datasource_id: str = Field(alias="datasourceId")
    policy: str
    original_sql: str = Field(alias="originalSql")
    safe_sql: str = Field(alias="safeSql")
    passed: bool
    guardrail: dict[str, JsonValue]
    schema_warnings: list[str] = Field(alias="schemaWarnings")
    scope_state: dict[str, JsonValue] = Field(alias="scopeState")


class ResultViewArtifactPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source_sql_artifact_id: str = Field(alias="sourceSqlArtifactId", min_length=1)
    query_fingerprint: str = Field(alias="queryFingerprint")
    datasource_generation: int | None = Field(alias="datasourceGeneration")
    columns: list[Any] = Field(default_factory=list)
    row_count: int = Field(alias="rowCount", ge=0)
    returned_rows: int = Field(alias="returnedRows", ge=0)
    latency_ms: int | float | None = Field(alias="latencyMs", default=None, ge=0)
    executed_at: str = Field(alias="executedAt", min_length=1)
    truncated: bool = False
    evidence_kind: Literal["sample_rows", "query_result"] = Field(
        alias="evidenceKind",
        default="query_result",
    )


class ChartArtifactPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source_result_artifact_id: str = Field(alias="sourceResultArtifactId", min_length=1)
    chart_type: str = Field(alias="chartType", min_length=1)
    x: str | None = None
    y: list[str] = Field(default_factory=list)
    aggregation: str | None = None
    title: str | None = None


_PAYLOAD_MODELS: dict[ArtifactType, type[BaseModel]] = {
    ArtifactType.SQL: SqlArtifactPayload,
    ArtifactType.SAFETY: SafetyArtifactPayload,
    ArtifactType.RESULT_VIEW: ResultViewArtifactPayload,
    ArtifactType.CHART: ChartArtifactPayload,
}
_RESULT_VALUE_KEYS = frozenset({"rows", "previewRows", "preview_rows", "series"})


def validate_artifact_payload(
    artifact_type: ArtifactType,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Validate the durable Artifact boundary before any database write."""
    _reject_result_values(payload)
    model = _PAYLOAD_MODELS.get(artifact_type)
    if model is None:
        return dict(payload)
    return model.model_validate(payload).model_dump(
        mode="json",
        by_alias=True,
        exclude_none=False,
    )


def _reject_result_values(value: Any, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) in _RESULT_VALUE_KEYS:
                raise ValueError(
                    f"Artifact payload cannot persist result values at {path}.{key}"
                )
            _reject_result_values(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_result_values(item, f"{path}[{index}]")


class Artifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    session_id: str
    run_id: str
    turn_id: str | None = None
    type: ArtifactType
    title: str
    semantic_key: str | None = None
    version: int = Field(default=1, ge=1)
    status: ArtifactStatus = ArtifactStatus.COMPLETED
    visibility: ArtifactVisibility = ArtifactVisibility.PRIMARY
    summary: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_ref: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    relations: list[ArtifactRelation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_relations(self) -> "Artifact":
        if any(relation.artifact_id == self.id for relation in self.relations):
            raise ValueError("Artifact cannot relate to itself")
        validate_artifact_payload(self.type, self.payload)
        return self


class ArtifactSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    artifact_id: str
    selected_by: str
    reason: str | None = None


class ArtifactSelectionSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    reason: str
    replace_automatic_selection: bool = True
