"""User-visible Agent work products and their immutable relationships."""

from __future__ import annotations

from enum import StrEnum
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator


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


def default_artifact_visibility(artifact_type: str) -> ArtifactVisibility:
    try:
        return _DEFAULT_VISIBILITY_BY_TYPE[ArtifactType(str(artifact_type))]
    except ValueError:
        return ArtifactVisibility.PRIMARY


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


_ARTIFACT_TYPE_PATTERN = r"^[a-z][a-z0-9_.-]*(?:[.:][a-z][a-z0-9_.-]*)+$"
_KNOWN_ARTIFACT_TYPES = frozenset(
    item.value for item in ArtifactType
)


def validate_artifact_type(value: str) -> str:
    """Allow existing flat IDs and future namespaced Extension IDs only."""

    candidate = str(value).strip()
    if not candidate:
        raise ValueError("Artifact type must not be empty")
    if candidate in _KNOWN_ARTIFACT_TYPES:
        return candidate
    if re.fullmatch(_ARTIFACT_TYPE_PATTERN, candidate) is None:
        raise ValueError(
            "New Artifact type must use a namespaced ID like "
            "dbfox.workspace.code_patch"
        )
    return candidate


class ArtifactDraft(BaseModel):
    """Provider-neutral Artifact description emitted by a data tool."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    type: str = Field(min_length=1, max_length=128)
    schema_version: int = Field(default=1, ge=1)
    title: str = Field(min_length=1, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_draft_refs: dict[str, str] = Field(default_factory=dict)
    summary: str | None = Field(default=None, max_length=2_000)
    semantic_key: str | None = Field(default=None, max_length=1_000)
    payload_ref: str | None = Field(default=None, max_length=1_000)
    relations: tuple[ArtifactRelationDraft, ...] = ()
    visibility: ArtifactVisibility | None = None
    select_if_none: bool = False

    @field_validator("type")
    @classmethod
    def validate_type_namespace(cls, value: str) -> str:
        return validate_artifact_type(value)

class SqlArtifactPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    sql: str
    safe_sql: str = Field(alias="safeSql")
    dialect: str
    query_fingerprint: str = Field(alias="queryFingerprint")
    parameters: dict[str, JsonValue] = Field(default_factory=dict)


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


class ArtifactPayloadContractRegistry:
    """Direct registrar for concrete Artifact payload contracts.

    New write types register one ``(type, schema_version)`` key without any
    Manager/Factory indirection. ``freeze()`` makes the registry immutable for
    the rest of the process.
    """

    def __init__(self) -> None:
        self._contracts: dict[tuple[str, int], type[BaseModel]] = {}
        self._frozen = False

    @property
    def frozen(self) -> bool:
        return self._frozen

    def register(
        self,
        artifact_type: str,
        schema_version: int,
        validator: type[BaseModel],
    ) -> "ArtifactPayloadContractRegistry":
        if self._frozen:
            raise RuntimeError("Artifact payload contracts are frozen.")
        normalized_type = validate_artifact_type(artifact_type)
        if int(schema_version) < 1:
            raise ValueError("Artifact schema_version must be >= 1")
        if not isinstance(validator, type) or not issubclass(validator, BaseModel):
            raise TypeError("Artifact payload validator must be a BaseModel subclass")
        key = (normalized_type, int(schema_version))
        if key in self._contracts:
            raise ValueError(
                f"Artifact payload contract is already registered: "
                f"{normalized_type} v{schema_version}"
            )
        self._contracts[key] = validator
        return self

    def get(
        self,
        artifact_type: str,
        schema_version: int,
    ) -> type[BaseModel] | None:
        return self._contracts.get((str(artifact_type), int(schema_version)))

    def snapshot(self) -> dict[tuple[str, int], type[BaseModel]]:
        return dict(self._contracts)

    def freeze(self) -> "ArtifactPayloadContractRegistry":
        self._frozen = True
        return self


artifact_payload_contracts = ArtifactPayloadContractRegistry()


def register_artifact_payload_contract(
    artifact_type: str,
    schema_version: int,
    validator: type[BaseModel],
) -> ArtifactPayloadContractRegistry:
    """Register a concrete Artifact payload write contract before startup freeze."""

    return artifact_payload_contracts.register(
        artifact_type,
        schema_version,
        validator,
    )


def freeze_artifact_payload_contracts() -> ArtifactPayloadContractRegistry:
    return artifact_payload_contracts.freeze()


register_artifact_payload_contract(ArtifactType.SQL.value, 1, SqlArtifactPayload)
register_artifact_payload_contract(ArtifactType.SAFETY.value, 1, SafetyArtifactPayload)
register_artifact_payload_contract(ArtifactType.RESULT_VIEW.value, 1, ResultViewArtifactPayload)
register_artifact_payload_contract(ArtifactType.CHART.value, 1, ChartArtifactPayload)

_RESULT_VALUE_KEYS = frozenset({"rows", "previewRows", "preview_rows", "series"})


def validate_artifact_payload(
    artifact_type: str,
    payload: dict[str, Any],
    *,
    schema_version: int = 1,
    allow_unknown: bool = False,
) -> dict[str, Any]:
    """Validate the durable Artifact boundary.

    New writes reject unknown type/version combinations. Historical reads use
    ``allow_unknown=True`` so an unknown historical type keeps its envelope and
    fails soft instead of being guessed.
    """

    _reject_result_values(payload)
    candidate = str(artifact_type)
    model = artifact_payload_contracts.get(candidate, int(schema_version))
    if model is not None:
        return model.model_validate(payload).model_dump(
            mode="json",
            by_alias=True,
            exclude_none=False,
        )
    if candidate in _KNOWN_ARTIFACT_TYPES:
        if allow_unknown:
            # Historical reads may meet a future schema_version of a known
            # type. Keep the envelope instead of guessing a newer contract.
            return dict(payload)
        raise ValueError(
            f"Artifact type {candidate!r} has no payload contract at "
            f"schema_version={schema_version}"
        )
    if allow_unknown:
        return dict(payload)
    raise ValueError(
        f"Unknown new Artifact type {candidate!r} cannot be written"
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
    type: str = Field(min_length=1, max_length=128)
    schema_version: int = Field(default=1, ge=1)
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

    @field_validator("type")
    @classmethod
    def validate_type_contract(cls, value: str) -> str:
        return validate_artifact_type(value)

    @model_validator(mode="after")
    def validate_relations(self) -> "Artifact":
        if any(relation.artifact_id == self.id for relation in self.relations):
            raise ValueError("Artifact cannot relate to itself")
        validate_artifact_payload(
            self.type,
            self.payload,
            schema_version=self.schema_version,
            allow_unknown=True,
        )
        return self


class ArtifactSelectionSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    reason: str
    replace_automatic_selection: bool = True
