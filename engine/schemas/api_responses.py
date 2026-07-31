from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from engine.agent.run_item import RunItem, RunProjection


class DeleteCountResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: Literal[True] = True
    deleted: int


class QueryCancelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool
    cancelled: bool
    executionId: str
    message: str


class GuardrailCheckResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule: str
    level: Literal["warn", "reject"]
    message: str


class GuardrailResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    result: Literal["pass", "warn", "reject"]
    originalSql: str
    safeSql: str
    checks: list[GuardrailCheckResponse] = Field(default_factory=list)
    message: str


class QueryExplainResponse(BaseModel):
    """Dialect-neutral public EXPLAIN envelope.

    Plans are intentionally JSON values because MySQL, PostgreSQL and SQLite
    return different native plan structures.  The HTTP envelope itself remains
    stable and generated into the frontend contract.
    """

    model_config = ConfigDict(extra="allow")

    success: bool | None = None
    plan: Any | None = None
    rows: list[dict[str, Any]] | None = None
    warnings: list[str] = Field(default_factory=list)


class BackupPrecheckResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    filePath: str | None = None
    fileSizeBytes: int
    checksumSha256: str | None = None
    restoreAvailable: bool


class TableScopeUpdateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: Literal[True] = True
    message: str


class TestDataGeneratedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: Literal[True] = True
    tableName: str
    insertedRows: int
    latencyMs: int
    message: str


class DiagnosticLogSourceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    path: str
    exists: bool
    size_bytes: int
    modified_at: str | None = None
    content: str


class DiagnosticPolicyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    redacted: bool
    max_lines_per_source: int
    omitted: list[str]


class DiagnosticEnvironmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app: str
    pid: int
    python: str
    platform: str
    frozen: bool


class SecurityAuditRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    action: str
    outcome: str
    actorType: str
    resourceType: str
    resourceId: str | None = None
    sessionId: str | None = None
    runId: str | None = None
    correlationId: str
    details: dict[str, Any]
    createdAt: str


class SecurityAuditDiagnosticsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retention_days: int
    export_window_days: int
    max_records: int
    records: list[SecurityAuditRecordResponse]


class DiagnosticLogsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: str
    policy: DiagnosticPolicyResponse
    environment: DiagnosticEnvironmentResponse
    sources: list[DiagnosticLogSourceResponse]
    security_audit: SecurityAuditDiagnosticsResponse


class DiagnosticLogsClearedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cleared: bool
    sources_cleared: list[str]


class SecurityAuditClearedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cleared: Literal[True] = True
    records_deleted: int


class ConversationSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    datasource_id: str
    title: str
    selected_artifact_id: str | None = None
    updated_at: str


class ConversationSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    datasource_id: str
    title: str
    context_epoch: int
    selected_artifact_id: str | None = None
    context_tables: list[str]


class PaginationCursorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    has_more: bool
    next_before_sequence: int | None = None


class ConversationPaginationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: PaginationCursorResponse
    runs: PaginationCursorResponse


class ConversationSnapshotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[2]
    session: ConversationSessionResponse
    runs: list[RunProjection]
    items: list[RunItem]
    pagination: ConversationPaginationResponse
    cursor: int


class ConversationProjectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[2]
    cursor: int
    items: list[RunItem]
    runs: list[RunProjection]


class ConversationInputAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    input_id: str
    run_id: str
    user_message_id: str
    input_sequence: int
    event_cursor: int
    projection: ConversationProjectionResponse
    stream_path: str


class ConversationDeleteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "deleting"]


class ArtifactSelectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    artifact_id: str


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str
    run_id: str
    claim_id: str
    artifact_id: str
    label: str
    query_fingerprint: str
    observed_at: str
    locator: dict[str, Any]
    value: Any | None = None


class TraceSpanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    parent_id: str | None = None
    kind: Literal["run", "turn", "model", "tool", "policy", "approval"]
    name: str
    status: str
    started_at: str | None = None
    ended_at: str | None = None
    attributes: dict[str, Any]


class RunTraceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    session_id: str
    run_id: str
    spans: list[TraceSpanResponse]


class RunCancelledResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: str
    version: int
