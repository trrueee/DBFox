from __future__ import annotations

from sqlalchemy.orm import Session

from engine.agent.artifact import (
    ArtifactDraft,
    ArtifactRelationDraft,
    ArtifactRelationType,
    ArtifactType,
    ArtifactVisibility,
)
from engine.sql.dialect_context import DialectContext
from engine.sql.result_view.fingerprint import result_source_fingerprint
from engine.tools.builtin.contracts import (
    DataPreviewOutput,
    QueryResultOutput,
    SqlValidateOutput,
)


def sql_validation_drafts(
    db: Session,
    datasource_id: str,
    output: SqlValidateOutput,
) -> tuple[ArtifactDraft, ...]:
    decision = output.execution_safety_decision
    dialect, fingerprint = _query_identity(db, datasource_id, output.safe_sql or output.original_sql)
    safety = ArtifactDraft(
        key="safety",
        type=ArtifactType.SAFETY,
        title="SQL 安全检查",
        summary="可执行" if output.can_execute else "查询被安全规则阻止",
        visibility=ArtifactVisibility.INTERNAL,
        payload={
            "canExecute": output.can_execute,
            "requiresApproval": output.requires_confirmation,
            "riskLevel": output.risk_level,
            "blockedReasons": output.blocked_reasons,
            "messages": output.messages,
            "datasourceId": str(decision.get("datasource_id") or datasource_id),
            "policy": str(decision.get("policy") or "agent_readonly"),
            "originalSql": str(decision.get("original_sql") or output.original_sql),
            "safeSql": str(decision.get("safe_sql") or output.safe_sql),
            "passed": bool(decision.get("passed", output.can_execute)),
            "guardrail": decision.get("guardrail") or {},
            "schemaWarnings": decision.get("schema_warnings") or [],
            "scopeState": decision.get("scope_state") or {},
        },
    )
    query = ArtifactDraft(
        key="sql",
        type=ArtifactType.SQL,
        title="分析 SQL",
        summary="已通过安全检查" if output.can_execute else "未通过安全检查",
        visibility=ArtifactVisibility.SUPPORTING,
        payload={
            "sql": output.original_sql,
            "safeSql": output.safe_sql,
            "dialect": dialect,
            "queryFingerprint": fingerprint,
        },
        relations=(
            ArtifactRelationDraft(
                relation=ArtifactRelationType.VALIDATED_BY,
                draft_key="safety",
            ),
        ),
    )
    return safety, query


def preview_drafts(
    db: Session,
    datasource_id: str,
    datasource_generation: int | None,
    output: DataPreviewOutput,
) -> tuple[ArtifactDraft, ...]:
    dialect, fingerprint = _query_identity(
        db, datasource_id, output.safe_sql, output.parameters
    )
    source = ArtifactDraft(
        key="preview_sql",
        type=ArtifactType.SQL,
        title="数据预览 SQL",
        summary="受限抽样查询来源",
        visibility=ArtifactVisibility.SUPPORTING,
        payload={
            "sql": output.safe_sql,
            "safeSql": output.safe_sql,
            "dialect": dialect,
            "queryFingerprint": fingerprint,
            "parameters": output.parameters,
        },
    )
    result = ArtifactDraft(
        key="sample",
        type=ArtifactType.RESULT_VIEW,
        title="数据样例",
        summary=f"抽样返回 {output.returned_rows} 行、{len(output.columns)} 列",
        payload={
            "sourceSqlArtifactId": "",
            "queryFingerprint": fingerprint,
            "datasourceGeneration": datasource_generation,
            "columns": output.columns,
            "rowCount": output.returned_rows,
            "returnedRows": output.returned_rows,
            "latencyMs": output.latency_ms,
            "executedAt": _now_iso(),
            "truncated": output.truncated,
            "evidenceKind": "sample_rows",
        },
        payload_draft_refs={"sourceSqlArtifactId": "preview_sql"},
        payload_ref=str(output.audit.get("history_id") or "") or None,
        relations=(
            ArtifactRelationDraft(
                relation=ArtifactRelationType.DERIVED_FROM,
                draft_key="preview_sql",
            ),
        ),
        select_if_none=True,
    )
    return source, result


def query_result_draft(
    db: Session,
    datasource_id: str,
    validation_artifact_id: str,
    datasource_generation: int | None,
    output: QueryResultOutput,
) -> ArtifactDraft:
    _, fingerprint = _query_identity(db, datasource_id, output.safe_sql)
    return ArtifactDraft(
        key="result",
        type=ArtifactType.RESULT_VIEW,
        title="查询结果",
        summary=f"返回 {output.returned_rows} 行、{len(output.columns)} 列",
        payload={
            "sourceSqlArtifactId": validation_artifact_id,
            "queryFingerprint": fingerprint,
            "datasourceGeneration": datasource_generation,
            "columns": output.columns,
            "rowCount": output.row_count,
            "returnedRows": output.returned_rows,
            "latencyMs": output.latency_ms,
            "executedAt": _now_iso(),
            "truncated": output.truncated,
            "evidenceKind": "query_result",
        },
        payload_ref=str(output.audit.get("history_id") or "") or None,
        relations=(
            ArtifactRelationDraft(
                relation=ArtifactRelationType.DERIVED_FROM,
                artifact_id=validation_artifact_id,
            ),
        ),
        select_if_none=True,
    )


def _query_identity(
    db: Session,
    datasource_id: str,
    sql: str,
    parameters: dict[str, object] | None = None,
) -> tuple[str, str]:
    if not sql.strip():
        return "", ""
    context = DialectContext.from_datasource_id(db, datasource_id)
    return (
        context.sqlglot_dialect,
        result_source_fingerprint(sql, context.sqlglot_dialect, parameters),
    )


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
