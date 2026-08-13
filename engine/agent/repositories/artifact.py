"""Artifact identity, relationship and Evidence persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from engine.agent.artifact import (
    Artifact,
    ArtifactDraft,
    ArtifactRelation,
    ArtifactRelationType,
    ArtifactStatus,
    ArtifactType,
    ArtifactVisibility,
    default_artifact_visibility,
    validate_artifact_payload,
)
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.write_transaction import begin_agent_write
from engine.agent.session import SessionLease
from engine.json_codec import JsonCodecError, canonical_dumps as _json, loads
from engine.models import AgentArtifactRecord, AgentSession


def _loads(value: str | None, fallback: Any) -> Any:
    try:
        return loads(value or "")
    except JsonCodecError:
        return fallback


@dataclass(frozen=True, slots=True)
class ValidatedSqlArtifact:
    sql_artifact_id: str
    safety_artifact_id: str
    original_sql: str
    safe_sql: str
    safety: dict[str, Any]


class ArtifactDraftContractError(ValueError):
    """A tool emitted an Artifact batch that cannot satisfy the durable contract."""


@dataclass(frozen=True, slots=True)
class _PreparedArtifactDraft:
    draft: ArtifactDraft
    artifact_id: str
    payload: dict[str, Any]
    relations: tuple[ArtifactRelation, ...]


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
        visibility: ArtifactVisibility | None = None,
        artifact_id: str | None = None,
    ) -> Artifact:
        begin_agent_write(self.session)
        payload = validate_artifact_payload(artifact_type, payload)
        visibility = visibility or default_artifact_visibility(artifact_type)
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
        artifact_id = artifact_id or f"artifact_{uuid4().hex}"
        value = Artifact(
            id=artifact_id, session_id=lease.session_id, run_id=run_id, turn_id=turn_id,
            type=artifact_type, title=title, semantic_key=semantic_key, version=version,
            status=status, visibility=visibility, summary=summary, payload=payload, payload_ref=payload_ref,
            provenance=provenance or {}, relations=relations or [],
        )
        self.session.add(AgentArtifactRecord(
            id=artifact_id, run_id=run_id, session_id=lease.session_id, turn_id=turn_id,
            semantic_id=semantic_key, version=version, type=artifact_type.value, title=title,
            payload_json=_json(payload),
            presentation_json=_json({"visibility": visibility.value}),
            summary=summary,
            payload_ref=payload_ref,
            provenance_json=_json(provenance or {}),
            relations_json=_json([item.model_dump(mode="json") for item in relations or []]),
            status=status.value, sequence=sequence,
        ))
        self.session.flush()
        return value

    def persist_drafts(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        turn_id: str,
        invocation_id: str,
        tool_name: str,
        drafts: list[ArtifactDraft],
    ) -> list[Artifact]:
        """Persist tool-owned Artifact drafts without knowing concrete tool names."""

        if not drafts:
            return []
        prepared = self._prepare_drafts(
            lease=lease,
            drafts=drafts,
        )
        created: list[Artifact] = []
        provenance = {
            "tool_invocation_id": invocation_id,
            "tool_name": tool_name,
        }
        for item in prepared:
            draft = item.draft
            artifact = self.create(
                lease=lease,
                run_id=run_id,
                turn_id=turn_id,
                artifact_id=item.artifact_id,
                artifact_type=draft.type,
                title=draft.title,
                payload=item.payload,
                summary=draft.summary,
                semantic_key=(
                    draft.semantic_key
                    or f"{draft.type.value}:{invocation_id}:{draft.key}"
                ),
                payload_ref=draft.payload_ref,
                provenance=provenance,
                relations=list(item.relations),
                visibility=draft.visibility,
            )
            created.append(artifact)
            if draft.select_if_none:
                aggregate = self.session.get(AgentSession, lease.session_id)
                if aggregate is not None and not aggregate.selected_artifact_id:
                    self.sessions.select_artifact(
                        session_id=lease.session_id,
                        artifact_id=artifact.id,
                        selected_by="agent",
                    )
        return created

    def _prepare_drafts(
        self,
        *,
        lease: SessionLease,
        drafts: list[ArtifactDraft],
    ) -> tuple[_PreparedArtifactDraft, ...]:
        """Resolve and validate one complete draft batch before the first write."""

        keys = [draft.key for draft in drafts]
        if len(set(keys)) != len(keys):
            raise ArtifactDraftContractError(
                "Artifact draft keys must be unique within one tool outcome"
            )

        ids = {key: f"artifact_{uuid4().hex}" for key in keys}
        prepared: list[_PreparedArtifactDraft] = []
        external_relation_ids: set[str] = set()
        try:
            for draft in drafts:
                payload = dict(draft.payload)
                for field_name, draft_key in draft.payload_draft_refs.items():
                    target_id = ids.get(draft_key)
                    if target_id is None:
                        raise ArtifactDraftContractError(
                            "Artifact payload references an unknown draft key"
                        )
                    payload[field_name] = target_id

                relations: list[ArtifactRelation] = []
                for relation in draft.relations:
                    target_id = relation.artifact_id
                    if relation.draft_key:
                        target_id = ids.get(relation.draft_key)
                        if target_id is None:
                            raise ArtifactDraftContractError(
                                "Artifact relation references an unknown draft key"
                            )
                    target = str(target_id or "").strip()
                    if not target:
                        raise ArtifactDraftContractError(
                            "Artifact relation target is empty"
                        )
                    if target == ids[draft.key]:
                        raise ArtifactDraftContractError(
                            "Artifact cannot relate to itself"
                        )
                    if target not in ids.values():
                        external_relation_ids.add(target)
                    relations.append(
                        ArtifactRelation(
                            relation=relation.relation,
                            artifact_id=target,
                        )
                    )

                prepared.append(
                    _PreparedArtifactDraft(
                        draft=draft,
                        artifact_id=ids[draft.key],
                        payload=validate_artifact_payload(draft.type, payload),
                        relations=tuple(relations),
                    )
                )
        except ArtifactDraftContractError:
            raise
        except (ValidationError, ValueError) as exc:
            raise ArtifactDraftContractError(
                "Artifact draft payload or relation does not match its contract"
            ) from exc

        if external_relation_ids:
            rows = self.session.execute(
                select(AgentArtifactRecord.id, AgentArtifactRecord.session_id).where(
                    AgentArtifactRecord.id.in_(external_relation_ids)
                )
            ).all()
            visible_ids = {
                str(artifact_id)
                for artifact_id, session_id in rows
                if str(session_id) == lease.session_id
            }
            if visible_ids != external_relation_ids:
                raise ArtifactDraftContractError(
                    "Artifact relation target is unavailable in this Session"
                )

        # Run ownership is enforced by the lease on writes. Relation targets may
        # intentionally refer to earlier Artifacts in the same Session.
        return tuple(prepared)

    def require_validated_sql(
        self,
        *,
        session_id: str,
        run_id: str,
        sql_artifact_id: str,
    ) -> ValidatedSqlArtifact:
        """Resolve one exact SQL→Safety relation as the execution source of truth."""

        sql_row = self.session.get(AgentArtifactRecord, sql_artifact_id)
        if (
            sql_row is None
            or str(sql_row.session_id) != str(session_id)
            or str(sql_row.run_id) != str(run_id)
            or str(sql_row.type) != ArtifactType.SQL.value
        ):
            raise ValueError("The SQL validation Artifact is unavailable in this Run")
        sql_payload = validate_artifact_payload(
            ArtifactType.SQL,
            _loads(str(sql_row.payload_json or "{}"), {}),
        )
        relation_items = _loads(str(sql_row.relations_json or "[]"), [])
        safety_id = next(
            (
                str(item.get("artifact_id") or "")
                for item in relation_items
                if isinstance(item, dict)
                and item.get("relation") == ArtifactRelationType.VALIDATED_BY.value
            ),
            "",
        )
        safety_row = (
            self.session.get(AgentArtifactRecord, safety_id)
            if safety_id
            else None
        )
        if (
            safety_row is None
            or str(safety_row.session_id) != str(session_id)
            or str(safety_row.run_id) != str(run_id)
            or str(safety_row.type) != ArtifactType.SAFETY.value
        ):
            raise ValueError("The SQL Artifact has no valid Safety Artifact")
        safety_payload = validate_artifact_payload(
            ArtifactType.SAFETY,
            _loads(str(safety_row.payload_json or "{}"), {}),
        )
        safe_sql = str(safety_payload.get("safeSql") or "").strip()
        if safe_sql != str(sql_payload.get("safeSql") or "").strip():
            raise ValueError("The SQL and Safety Artifacts do not bind the same statement")
        return ValidatedSqlArtifact(
            sql_artifact_id=str(sql_row.id),
            safety_artifact_id=str(safety_row.id),
            original_sql=str(safety_payload.get("originalSql") or ""),
            safe_sql=safe_sql,
            safety={
                "datasource_id": safety_payload["datasourceId"],
                "policy": safety_payload["policy"],
                "original_sql": safety_payload["originalSql"],
                "safe_sql": safety_payload["safeSql"],
                "passed": safety_payload["passed"],
                "can_execute": safety_payload["canExecute"],
                "requires_confirmation": safety_payload["requiresApproval"],
                "risk_level": safety_payload["riskLevel"],
                "guardrail": safety_payload["guardrail"],
                "schema_warnings": safety_payload["schemaWarnings"],
                "scope_state": safety_payload["scopeState"],
                "blocked_reasons": safety_payload["blockedReasons"],
                "messages": safety_payload["messages"],
            },
        )

    def result_for_sql_artifact(
        self,
        *,
        session_id: str,
        run_id: str,
        sql_artifact_id: str,
    ) -> Artifact | None:
        rows = self.session.execute(
            select(AgentArtifactRecord).where(
                AgentArtifactRecord.session_id == session_id,
                AgentArtifactRecord.run_id == run_id,
                AgentArtifactRecord.type == ArtifactType.RESULT_VIEW.value,
            )
        ).scalars()
        for row in rows:
            payload = _loads(str(row.payload_json or "{}"), {})
            if str(payload.get("sourceSqlArtifactId") or "") == sql_artifact_id:
                return self._domain(row)
        return None

    def list_for_run(self, run_id: str) -> list[Artifact]:
        rows = self.session.execute(
            select(AgentArtifactRecord).where(AgentArtifactRecord.run_id == run_id)
            .order_by(AgentArtifactRecord.sequence, AgentArtifactRecord.created_at)
        ).scalars()
        return [self._domain(row) for row in rows]

    @staticmethod
    def _domain(row: AgentArtifactRecord) -> Artifact:
        artifact_type = ArtifactType(str(row.type))
        presentation = _loads(str(row.presentation_json or "{}"), {})
        try:
            visibility = ArtifactVisibility(str(
                presentation.get("visibility") if isinstance(presentation, dict) else None
            ))
        except (TypeError, ValueError):
            visibility = default_artifact_visibility(artifact_type)
        return Artifact(
            id=str(row.id), session_id=str(row.session_id), run_id=str(row.run_id),
            turn_id=str(row.turn_id) if row.turn_id else None,
            type=artifact_type, title=str(row.title),
            semantic_key=str(row.semantic_id) if row.semantic_id else None,
            version=int(row.version or 1), status=ArtifactStatus(str(row.status)),
            visibility=visibility,
            summary=str(row.summary) if row.summary else None,
            payload=_loads(str(row.payload_json or "{}"), {}),
            payload_ref=str(row.payload_ref) if row.payload_ref else None,
            provenance=_loads(str(row.provenance_json or "{}"), {}),
            relations=[ArtifactRelation.model_validate(item) for item in _loads(str(row.relations_json or "[]"), [])],
        )
