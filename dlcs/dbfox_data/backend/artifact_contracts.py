"""Durable Artifact payload contracts owned by the Data capability."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

SQL_ARTIFACT_TYPE = "dbfox.data.sql"
SAFETY_ARTIFACT_TYPE = "dbfox.data.safety"
RESULT_VIEW_ARTIFACT_TYPE = "dbfox.data.result_view"
CHART_ARTIFACT_TYPE = "dbfox.data.chart"


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
    datasource_generation: str | int | None = Field(alias="datasourceGeneration")
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
