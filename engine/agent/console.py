"""Application service for artifact-backed SQL Console runs."""

from __future__ import annotations
from dlcs.dbfox_data.backend.resource_kind import DATABASE_RESOURCE_KIND

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from engine.agent.artifact import (
    Artifact,
    ArtifactRelation,
    ArtifactRelationType,
    ArtifactSelectionSuggestion,
    ArtifactType,
)
from engine.agent.response import AnswerCandidate, CompletionDisposition, ResponseComposer
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.write_transaction import begin_agent_write
from engine.agent.session import SessionLease
from engine.agent.terminalizer import Terminalizer
from engine.errors import DBFoxError
from engine.models import AgentSession, DataSource
from engine.policy.engine import PolicyEngine
from dlcs.dbfox_data.backend.sql.dialect_context import DatabaseDialectContext
from engine.sql.dialect_context import dialect_context_from_datasource
from engine.sql.executor import execute_query
from engine.sql.result_view.fingerprint import result_source_fingerprint
from engine.sql.safety.service import SqlSafetyService


@dataclass(frozen=True)
class ConsoleExecutionRequest:
    datasource_id: str
    sql: str
    question: str
    session_id: str | None = None
    execution_id: str | None = None


@dataclass(frozen=True)
class ConsoleExecutionResult:
    run_id: str
    session_id: str
    sql_artifact_id: str
    safety_artifact_id: str | None
    result_artifact_id: str | None
    artifacts: tuple[Artifact, ...]
    warnings: tuple[str, ...]
    notices: tuple[str, ...]


class ConsoleRunService:
    """Execute one user-authored read-only query and project a durable Run."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def execute(self, request: ConsoleExecutionRequest) -> ConsoleExecutionResult:
        datasource = self.session.get(DataSource, request.datasource_id)
        if datasource is None:
            raise DBFoxError("Datasource does not exist.", code="DATASOURCE_NOT_FOUND")

        sql = request.sql.strip()
        if not sql:
            raise DBFoxError("SQL is required.", code="SQL_EMPTY")
        question = request.question.strip() or "SQL Console"

        PolicyEngine.enforce_query_policy(datasource, sql)
        dialect = dialect_context_from_datasource(datasource)
        decision = SqlSafetyService(self.session).build_execution_decision(
            sql,
            dialect,
            policy="user_readonly",
        )
        execution = execute_query(
            self.session,
            request.datasource_id,
            sql,
            question,
            request.execution_id,
            safety_decision=decision,
            safety_policy="user_readonly",
        )

        safe_sql = str(decision.safe_sql or "").strip()
        safety = _safety_payload(decision)
        session_id = (request.session_id or f"console_session_{uuid4().hex}").strip()
        project_id = str(datasource.project_id) if datasource.project_id else None
        begin_agent_write(self.session)
        aggregate = self.session.get(AgentSession, session_id)
        if aggregate is None:
            self.session.add(
                AgentSession(
                    id=session_id,
                    project_id=project_id,
                    title="SQL Console",
                )
            )
            self.session.flush()

        from engine.tools.runtime.attempt import ResourceScopeRef
        resource_refs = (
            ResourceScopeRef(
                kind=DATABASE_RESOURCE_KIND,
                id=request.datasource_id,
                version=int(datasource.connection_generation),
            ),
        )
        sessions = SessionRepository(self.session)
        admission = sessions.admit(
            session_id=session_id,
            resource_refs=resource_refs,
            content=question,
            idempotency_key=f"console:{request.execution_id or uuid4().hex}",
            llm_credential_id="sql-console",
            api_base=None,
            model_name=None,
            request_payload={"source": "sql_console"},
        )
        lease = sessions.claim(session_id=session_id, owner=f"console:{uuid4().hex}")
        if lease is None:
            raise DBFoxError(
                "Console Session could not be claimed.",
                code="CONSOLE_SESSION_BUSY",
            )
        sessions.promote_next_input(lease=lease)
        turn = sessions.start_turn(
            lease=lease,
            run_id=admission.run_id,
            agent_definition_version="sql-console@1",
            prompt_version="sql-console@1",
            prompt_hash="sql-console",
            context_snapshot={"source": "sql_console"},
            context_hash="sql-console",
            tool_materialization={"tools": []},
            tool_materialization_hash="sql-console",
            provider="none",
            model_name="none",
        )
        artifacts = self._create_artifacts(
            lease=lease,
            run_id=admission.run_id,
            turn_id=str(turn.id),
            datasource=datasource,
            dialect=dialect,
            safe_sql=safe_sql,
            safety=safety,
            execution=execution,
        )
        sql_artifact_id = _artifact_id_by_type(artifacts, "sql")
        if not sql_artifact_id:
            raise DBFoxError(
                "Console execution did not produce a SQL artifact.",
                code="CONSOLE_SQL_ARTIFACT_MISSING",
            )

        result_artifact_id = _artifact_id_by_type(artifacts, "result_view")
        response = ResponseComposer().compose(
            session_id=session_id,
            run_id=admission.run_id,
            completion_disposition=CompletionDisposition.COMPLETE,
            limitation_codes=[],
            answer=AnswerCandidate(text="SQL Console execution completed."),
            artifacts=artifacts,
            selection_suggestion=(
                ArtifactSelectionSuggestion(
                    artifact_id=result_artifact_id,
                    reason="SQL Console 查询结果",
                )
                if result_artifact_id
                else None
            ),
        )
        Terminalizer.complete_in_session(self.session, lease, response)
        sessions.release(lease=lease)
        self.session.commit()
        return ConsoleExecutionResult(
            run_id=admission.run_id,
            session_id=session_id,
            sql_artifact_id=sql_artifact_id,
            safety_artifact_id=_artifact_id_by_type(artifacts, "safety"),
            result_artifact_id=result_artifact_id,
            artifacts=tuple(artifacts),
            warnings=tuple(str(item) for item in execution.get("warnings") or []),
            notices=tuple(str(item) for item in execution.get("notices") or []),
        )

    def _create_artifacts(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        turn_id: str,
        datasource: DataSource,
        dialect: DatabaseDialectContext,
        safe_sql: str,
        safety: dict[str, Any],
        execution: dict[str, Any],
    ) -> list[Artifact]:
        repository = ArtifactRepository(self.session)
        safety_artifact = repository.create(
            lease=lease,
            run_id=run_id,
            turn_id=turn_id,
            artifact_type=ArtifactType.SAFETY,
            title="SQL 安全检查",
            payload=safety,
            summary="可执行" if safety["canExecute"] else "未通过安全检查",
            semantic_key=f"console-safety:{run_id}",
            provenance={"source": "sql_console"},
        )
        fingerprint = result_source_fingerprint(safe_sql, dialect.sqlglot_dialect)
        sql_artifact = repository.create(
            lease=lease,
            run_id=run_id,
            turn_id=turn_id,
            artifact_type=ArtifactType.SQL,
            title="SQL",
            payload={
                "sql": safe_sql,
                "safeSql": safe_sql,
                "dialect": dialect.sqlglot_dialect,
                "queryFingerprint": fingerprint,
            },
            semantic_key=f"console-sql:{run_id}",
            provenance={
                "source": "sql_console",
                "datasource_id": str(datasource.id),
            },
            relations=[
                ArtifactRelation(
                    relation=ArtifactRelationType.VALIDATED_BY,
                    artifact_id=safety_artifact.id,
                )
            ],
        )
        result_artifact = repository.create(
            lease=lease,
            run_id=run_id,
            turn_id=turn_id,
            artifact_type=ArtifactType.RESULT_VIEW,
            title="查询结果",
            payload={
                "sourceSqlArtifactId": sql_artifact.id,
                "queryFingerprint": fingerprint,
                "datasourceGeneration": int(datasource.connection_generation),
                "columns": list(execution.get("columns") or []),
                "rowCount": int(execution.get("rowCount") or 0),
                "returnedRows": len(execution.get("rows") or []),
                "latencyMs": int(execution.get("latencyMs") or 0),
                "executedAt": datetime.now(UTC).isoformat(),
                "truncated": bool(execution.get("truncated")),
            },
            semantic_key=f"console-result:{run_id}",
            provenance={
                "source": "sql_console",
                "datasource_id": str(datasource.id),
            },
            relations=[
                ArtifactRelation(
                    relation=ArtifactRelationType.DERIVED_FROM,
                    artifact_id=sql_artifact.id,
                )
            ],
        )
        return [sql_artifact, safety_artifact, result_artifact]


def _safety_payload(decision: Any) -> dict[str, Any]:
    return {
        "passed": bool(decision.passed),
        "canExecute": bool(decision.can_execute),
        "requiresApproval": bool(decision.requires_confirmation),
        "riskLevel": str(decision.risk_level),
        "blockedReasons": list(decision.blocked_reasons or []),
        "datasourceId": str(decision.datasource_id),
        "guardrail": dict(decision.guardrail),
        "schemaWarnings": list(decision.schema_warnings or []),
        "scopeState": dict(decision.scope_state or {}),
        "messages": list(decision.messages or []),
        "policy": decision.policy,
        "safeSql": decision.safe_sql,
        "originalSql": decision.original_sql,
    }


def _artifact_id_by_type(artifacts: list[Artifact], artifact_type: str) -> str | None:
    return next(
        (artifact.id for artifact in artifacts if artifact.type == artifact_type),
        None,
    )
