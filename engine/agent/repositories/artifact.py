"""Artifact identity, relationship and Evidence persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from engine.agent.artifact import Artifact, ArtifactRelation, ArtifactRelationType, ArtifactStatus, ArtifactType
from engine.agent.events import RuntimeEventProjector, RuntimeEventType
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.write_transaction import begin_agent_write
from engine.agent.session import SessionLease
from engine.models import AgentArtifactRecord, AgentRun, AgentSession
from engine.sql.dialect_context import DialectContext
from engine.sql.result_view.fingerprint import result_source_fingerprint


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _loads(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


class ArtifactRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.sessions = SessionRepository(session)

    def create(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        turn_id: str,
        artifact_type: ArtifactType,
        title: str,
        payload: dict[str, Any],
        summary: str | None = None,
        semantic_key: str | None = None,
        payload_ref: str | None = None,
        provenance: dict[str, Any] | None = None,
        relations: list[ArtifactRelation] | None = None,
        status: ArtifactStatus = ArtifactStatus.COMPLETED,
    ) -> Artifact:
        begin_agent_write(self.session)
        version = 1
        if semantic_key:
            version = int(self.session.execute(
                select(func.coalesce(func.max(AgentArtifactRecord.version), 0)).where(
                    AgentArtifactRecord.session_id == lease.session_id,
                    AgentArtifactRecord.semantic_id == semantic_key,
                )
            ).scalar_one()) + 1
        sequence = int(self.session.execute(
            select(func.coalesce(func.max(AgentArtifactRecord.sequence), 0)).where(
                AgentArtifactRecord.run_id == run_id
            )
        ).scalar_one()) + 1
        artifact_id = f"artifact_{uuid4().hex}"
        value = Artifact(
            id=artifact_id, session_id=lease.session_id, run_id=run_id, turn_id=turn_id,
            type=artifact_type, title=title, semantic_key=semantic_key, version=version,
            status=status, summary=summary, payload=payload, payload_ref=payload_ref,
            provenance=provenance or {}, relations=relations or [],
        )
        self.session.add(AgentArtifactRecord(
            id=artifact_id, run_id=run_id, session_id=lease.session_id, turn_id=turn_id,
            semantic_id=semantic_key, version=version, type=artifact_type.value, title=title,
            payload_json=_json(payload), presentation_json="{}", summary=summary,
            payload_ref=payload_ref,
            provenance_json=_json(provenance or {}),
            relations_json=_json([item.model_dump(mode="json") for item in relations or []]),
            status=status.value, sequence=sequence,
        ))
        self.session.flush()
        self.sessions.append_event(
            lease=lease, event_type=RuntimeEventType.ARTIFACT_CREATED, run_id=run_id,
            turn_id=turn_id, payload=RuntimeEventProjector.entity("artifact", value),
        )
        return value

    def project_tool_result(
        self, *, lease: SessionLease, run_id: str, turn_id: str,
        invocation_id: str, tool_name: str, tool_input: dict[str, Any], output: dict[str, Any],
    ) -> list[Artifact]:
        begin_agent_write(self.session)
        provenance = {"tool_invocation_id": invocation_id, "tool_name": tool_name}
        if tool_name == "sql.validate":
            sql = str(output.get("original_sql") or tool_input.get("sql") or "")
            safe_sql = str(output.get("safe_sql") or "")
            dialect, query_fingerprint = self._query_identity(run_id, safe_sql or sql)
            safety = self.create(
                lease=lease, run_id=run_id, turn_id=turn_id,
                artifact_type=ArtifactType.SAFETY, title="SQL 安全检查",
                summary="可执行" if output.get("can_execute") else "查询被安全规则阻止",
                payload={
                    "canExecute": bool(output.get("can_execute")),
                    "requiresApproval": bool(output.get("requires_confirmation")),
                    "riskLevel": output.get("risk_level"),
                    "blockedReasons": output.get("blocked_reasons") or [],
                    "messages": output.get("messages") or [],
                }, semantic_key=f"safety:{sql}", provenance=provenance,
            )
            query = self.create(
                lease=lease, run_id=run_id, turn_id=turn_id,
                artifact_type=ArtifactType.SQL, title="分析 SQL",
                summary="已通过安全检查" if output.get("can_execute") else "未通过安全检查",
                payload={
                    "sql": sql,
                    "safeSql": safe_sql,
                    "dialect": dialect,
                    "queryFingerprint": query_fingerprint,
                },
                semantic_key=f"sql:{sql}", provenance=provenance,
                relations=[ArtifactRelation(
                    relation=ArtifactRelationType.VALIDATED_BY, artifact_id=safety.id
                )],
            )
            return [query, safety]

        if tool_name in {"sql.execute_readonly", "db.preview"}:
            rows = output.get("rows") or []
            columns = output.get("columns") or []
            query = self._latest(run_id, ArtifactType.SQL)
            run = self.session.get(AgentRun, run_id)
            safe_sql = str(output.get("safe_sql") or (query.payload.get("safeSql") if query else "") or "")
            dialect, query_fingerprint = self._query_identity(run_id, safe_sql)
            query_safe_sql = str(query.payload.get("safeSql") or "") if query else ""
            if safe_sql and (query is None or query_safe_sql.strip() != safe_sql.strip()):
                query = self.create(
                    lease=lease,
                    run_id=run_id,
                    turn_id=turn_id,
                    artifact_type=ArtifactType.SQL,
                    title="数据预览 SQL" if tool_name == "db.preview" else "执行 SQL",
                    summary="只读查询来源",
                    payload={
                        "sql": safe_sql,
                        "safeSql": safe_sql,
                        "dialect": dialect,
                        "queryFingerprint": query_fingerprint,
                    },
                    semantic_key=f"sql-source:{invocation_id}",
                    provenance=provenance,
                )
            if query is None:
                raise RuntimeError("Successful query output is missing its SQL source artifact")
            relations = [ArtifactRelation(
                relation=ArtifactRelationType.DERIVED_FROM, artifact_id=query.id
            )]
            result = self.create(
                lease=lease, run_id=run_id, turn_id=turn_id,
                artifact_type=ArtifactType.RESULT_VIEW,
                title="查询结果" if tool_name == "sql.execute_readonly" else "数据预览",
                summary=f"返回 {len(rows)} 行、{len(columns)} 列",
                payload={
                    "sourceSqlArtifactId": query.id,
                    "queryFingerprint": query_fingerprint,
                    "datasourceGeneration": int(run.datasource_generation) if run is not None else None,
                    "columns": columns,
                    "rowCount": output.get("rowCount", len(rows)),
                    "returnedRows": len(rows),
                    "latencyMs": output.get("latencyMs"),
                    "executedAt": datetime.now(UTC).isoformat(),
                    "truncated": bool(output.get("truncated")),
                },
                semantic_key=f"result:{invocation_id}",
                payload_ref=(output.get("audit") or {}).get("history_id"),
                provenance=provenance, relations=relations,
            )
            self._append_relation(query.id, ArtifactRelationType.EXECUTED_AS, result.id)
            aggregate = self.session.get(AgentSession, lease.session_id)
            if aggregate is not None and not aggregate.selected_artifact_id:
                self.sessions.select_artifact(
                    session_id=lease.session_id,
                    artifact_id=result.id,
                    selected_by="agent",
                )
            return [result]

        if tool_name == "chart.suggest" and output.get("chartable"):
            result = self._latest(run_id, ArtifactType.RESULT_VIEW)
            relations = ([ArtifactRelation(
                relation=ArtifactRelationType.DERIVED_FROM, artifact_id=result.id
            )] if result else [])
            chart = self.create(
                lease=lease, run_id=run_id, turn_id=turn_id,
                artifact_type=ArtifactType.CHART,
                title=str(output.get("title") or "数据图表"),
                summary=str(output.get("reason") or "查询结果可视化"),
                payload={
                    "sourceResultArtifactId": result.id if result else None,
                    "chartType": output.get("type"),
                    "x": output.get("x"),
                    "y": [output.get("y")] if output.get("y") else [],
                    "aggregation": output.get("aggregation"),
                    "title": output.get("title"),
                },
                semantic_key=f"chart:{invocation_id}", provenance=provenance, relations=relations,
            )
            if result:
                self._append_relation(result.id, ArtifactRelationType.VISUALIZED_AS, chart.id)
            return [chart]
        return []

    def _query_identity(self, run_id: str, safe_sql: str) -> tuple[str, str]:
        run = self.session.get(AgentRun, run_id)
        if run is None or not safe_sql.strip():
            return "", ""
        ctx = DialectContext.from_datasource_id(self.session, str(run.datasource_id))
        return ctx.sqlglot_dialect, result_source_fingerprint(safe_sql, ctx.sqlglot_dialect)

    def list_for_run(self, run_id: str) -> list[Artifact]:
        rows = self.session.execute(
            select(AgentArtifactRecord).where(AgentArtifactRecord.run_id == run_id)
            .order_by(AgentArtifactRecord.sequence, AgentArtifactRecord.created_at)
        ).scalars()
        return [self._domain(row) for row in rows]

    def _latest(self, run_id: str, artifact_type: ArtifactType) -> Artifact | None:
        row = self.session.execute(
            select(AgentArtifactRecord).where(
                AgentArtifactRecord.run_id == run_id,
                AgentArtifactRecord.type == artifact_type.value,
            ).order_by(AgentArtifactRecord.sequence.desc(), AgentArtifactRecord.created_at.desc())
        ).scalars().first()
        return self._domain(row) if row is not None else None

    def _append_relation(self, artifact_id: str, relation_type: ArtifactRelationType, target_id: str) -> None:
        row = self.session.get(AgentArtifactRecord, artifact_id)
        if row is None:
            return
        relations = _loads(str(row.relations_json or "[]"), [])
        value = {"relation": relation_type.value, "artifact_id": target_id}
        if value not in relations:
            relations.append(value)
            row.relations_json = _json(relations)
            self.session.flush()

    @staticmethod
    def _domain(row: AgentArtifactRecord) -> Artifact:
        return Artifact(
            id=str(row.id), session_id=str(row.session_id), run_id=str(row.run_id),
            turn_id=str(row.turn_id) if row.turn_id else None,
            type=ArtifactType(str(row.type)), title=str(row.title),
            semantic_key=str(row.semantic_id) if row.semantic_id else None,
            version=int(row.version or 1), status=ArtifactStatus(str(row.status)),
            summary=str(row.summary) if row.summary else None,
            payload=_loads(str(row.payload_json or "{}"), {}),
            payload_ref=str(row.payload_ref) if row.payload_ref else None,
            provenance=_loads(str(row.provenance_json or "{}"), {}),
            relations=[ArtifactRelation.model_validate(item) for item in _loads(str(row.relations_json or "[]"), [])],
        )
