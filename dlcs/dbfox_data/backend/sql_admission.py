"""Artifact-bound admission for Data read execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from dbfox_dlc_api import (
    Artifact,
    ArtifactRelationType,
    ResourceScopeRef,
    ToolAdmissionContext,
    ToolAdmissionDecision,
    ToolInputError,
)

from .resource_kind import DATABASE_RESOURCE_KIND
from .tool_contracts import SqlExecuteReadonlyInput


class SqlArtifactContext(Protocol):
    def scopes(self, kind: str) -> tuple[ResourceScopeRef, ...]: ...
    def artifact(self, artifact_id: str) -> Artifact: ...
    def artifacts_relating_to(
        self,
        artifact_id: str,
        relation: ArtifactRelationType,
    ) -> tuple[Artifact, ...]: ...


@dataclass(frozen=True, slots=True)
class ValidatedSqlExecution:
    resource_ref: ResourceScopeRef
    sql_artifact: Artifact
    safety_artifact: Artifact
    safe_sql: str
    original_sql: str
    approval_subject: dict[str, object]


def _selected_database_ref(
    context: SqlArtifactContext,
    database_id: str | None,
) -> ResourceScopeRef:
    refs = context.scopes(DATABASE_RESOURCE_KIND)
    if database_id is None:
        if len(refs) != 1:
            raise ToolInputError(
                "database_id is required when the Run authorizes multiple databases."
            )
        return refs[0]
    selected = next((ref for ref in refs if ref.id == database_id), None)
    if selected is None:
        raise ToolInputError("The selected database is not authorized for this Run.")
    return selected


def resolve_validated_sql_execution(
    tool_input: SqlExecuteReadonlyInput,
    context: SqlArtifactContext,
    *,
    sql_artifact_type: str,
    safety_artifact_type: str,
    result_artifact_type: str,
) -> ValidatedSqlExecution:
    resource_ref = _selected_database_ref(context, tool_input.database_id)
    try:
        sql_artifact = context.artifact(tool_input.validation_artifact_id)
    except RuntimeError as exc:
        raise ToolInputError(
            "The SQL validation Artifact is unavailable in this Run."
        ) from exc
    if (
        sql_artifact.type != sql_artifact_type
        or sql_artifact.resource_refs != (resource_ref,)
    ):
        raise ToolInputError(
            "The SQL validation Artifact does not belong to the selected database."
        )

    safety_ids = tuple(
        relation.artifact_id
        for relation in sql_artifact.relations
        if relation.relation is ArtifactRelationType.VALIDATED_BY
    )
    if len(safety_ids) != 1:
        raise ToolInputError("The SQL Artifact has no unique Safety Artifact.")
    try:
        safety_artifact = context.artifact(safety_ids[0])
    except RuntimeError as exc:
        raise ToolInputError("The SQL Artifact Safety decision is unavailable.") from exc
    if (
        safety_artifact.type != safety_artifact_type
        or safety_artifact.resource_refs != (resource_ref,)
    ):
        raise ToolInputError(
            "The SQL Safety Artifact does not belong to the selected database."
        )

    sql_payload = sql_artifact.payload
    safety = safety_artifact.payload
    safe_sql = str(safety.get("safeSql") or "").strip()
    if safe_sql != str(sql_payload.get("safeSql") or "").strip():
        raise ToolInputError("The SQL and Safety Artifacts bind different statements.")
    if str(safety.get("datasourceId") or "") != resource_ref.id:
        raise ToolInputError("The Safety Artifact binds another database resource.")
    hard_blockers = [
        str(reason)
        for reason in list(safety.get("blockedReasons") or [])
        if str(reason) != "requires_confirmation"
    ]
    if (
        not bool(safety.get("passed"))
        or not bool(safety.get("canExecute"))
        or not safe_sql
        or hard_blockers
    ):
        raise ToolInputError(
            "The selected SQL validation cannot execute; validate a corrected query."
        )

    existing = tuple(
        artifact
        for artifact in context.artifacts_relating_to(
            sql_artifact.id,
            ArtifactRelationType.DERIVED_FROM,
        )
        if artifact.type == result_artifact_type
    )
    if existing:
        raise ToolInputError(
            "This validated SQL was already executed; reuse its Result Artifact."
        )

    subject: dict[str, object] = {
        "validationArtifactId": sql_artifact.id,
        "safetyArtifactId": safety_artifact.id,
        "resourceRef": resource_ref.model_dump(mode="json"),
        "safety": safety,
    }
    return ValidatedSqlExecution(
        resource_ref=resource_ref,
        sql_artifact=sql_artifact,
        safety_artifact=safety_artifact,
        safe_sql=safe_sql,
        original_sql=str(safety.get("originalSql") or ""),
        approval_subject=subject,
    )


def admit_sql_execution(
    tool_input: SqlExecuteReadonlyInput,
    context: ToolAdmissionContext,
    *,
    sql_artifact_type: str,
    safety_artifact_type: str,
    result_artifact_type: str,
) -> ToolAdmissionDecision:
    try:
        execution = resolve_validated_sql_execution(
            tool_input,
            context,
            sql_artifact_type=sql_artifact_type,
            safety_artifact_type=safety_artifact_type,
            result_artifact_type=result_artifact_type,
        )
    except ToolInputError as exc:
        return ToolAdmissionDecision(
            status="blocked",
            reason=str(exc),
            risk_level="danger",
        )
    if bool(execution.safety_artifact.payload.get("requiresApproval")):
        return ToolAdmissionDecision(
            status="approval_required",
            reason="This validated database read requires human approval.",
            risk_level="warning",
            approval_subject=execution.approval_subject,
            resource_ref=execution.resource_ref,
        )
    return ToolAdmissionDecision(
        status="allowed",
        reason="The immutable SQL and Safety Artifacts authorize this read.",
        risk_level="safe",
        resource_ref=execution.resource_ref,
    )
