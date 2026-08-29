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
    ArtifactPayloadContractResolver,
    ArtifactRelation,
    ArtifactRelationType,
    ArtifactStatus,
    ArtifactVisibility,
    default_artifact_visibility,
    validate_artifact_payload,
)
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.write_transaction import begin_agent_write
from engine.agent.resource_refs import (
    dump_resource_refs,
    load_resource_refs,
    resource_refs_for_run,
)
from engine.agent.session import SessionLease
from engine.json_codec import JsonCodecError, canonical_dumps as _json, loads
from engine.models import (
    AgentArtifactRecord,
    AgentObservationRecord,
    AgentRun,
    AgentSession,
)
from engine.tools.runtime.attempt import ResourceScopeRef


def _loads(value: str | None, fallback: Any) -> Any:
    try:
        return loads(value or "")
    except JsonCodecError:
        return fallback


class ArtifactDraftContractError(ValueError):
    """A tool emitted an Artifact batch that cannot satisfy the durable contract."""


@dataclass(frozen=True, slots=True)
class _PreparedArtifactDraft:
    draft: ArtifactDraft
    artifact_id: str
    payload: dict[str, Any]
    relations: tuple[ArtifactRelation, ...]


class ArtifactRepository:
    def __init__(
        self,
        session: Session,
        *,
        payload_contract_resolver: ArtifactPayloadContractResolver | None = None,
    ) -> None:
        self.session = session
        self.sessions = SessionRepository(session)
        self.payload_contract_resolver = payload_contract_resolver

    def get_for_run(
        self,
        *,
        session_id: str,
        run_id: str,
        artifact_id: str,
    ) -> Artifact | None:
        """Return one Artifact only inside the exact invoking Run boundary."""

        row = self.session.get(AgentArtifactRecord, artifact_id)
        if (
            row is None
            or str(row.session_id) != str(session_id)
            or str(row.run_id) != str(run_id)
        ):
            return None
        return self._domain(row)

    def get(self, artifact_id: str) -> Artifact | None:
        """Return one durable Artifact envelope by its opaque identity."""

        row = self.session.get(AgentArtifactRecord, artifact_id)
        return self._domain(row) if row is not None else None

    def artifacts_relating_to_for_run(
        self,
        *,
        session_id: str,
        run_id: str,
        artifact_id: str,
        relation: ArtifactRelationType,
    ) -> tuple[Artifact, ...]:
        """Return current-Run Artifacts with an outbound relation to ``artifact_id``."""

        if self.get_for_run(
            session_id=session_id,
            run_id=run_id,
            artifact_id=artifact_id,
        ) is None:
            return ()
        rows = self.session.execute(
            select(AgentArtifactRecord)
            .where(
                AgentArtifactRecord.session_id == session_id,
                AgentArtifactRecord.run_id == run_id,
            )
            .order_by(
                AgentArtifactRecord.sequence,
                AgentArtifactRecord.created_at,
            )
        ).scalars()
        matches: list[Artifact] = []
        for row in rows:
            relations = _loads(str(row.relations_json or "[]"), [])
            if any(
                isinstance(item, dict)
                and item.get("relation") == relation.value
                and str(item.get("artifact_id") or "") == artifact_id
                for item in relations
            ):
                matches.append(self._domain(row))
        return tuple(matches)

    def create(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        turn_id: str,
        artifact_type: str,
        schema_version: int = 1,
        title: str,
        payload: dict[str, Any],
        summary: str | None = None,
        semantic_key: str | None = None,
        payload_ref: str | None = None,
        resource_refs: tuple[ResourceScopeRef, ...] = (),
        provenance: dict[str, Any] | None = None,
        relations: list[ArtifactRelation] | None = None,
        status: ArtifactStatus = ArtifactStatus.COMPLETED,
        visibility: ArtifactVisibility | None = None,
        artifact_id: str | None = None,
    ) -> Artifact:
        begin_agent_write(self.session)
        artifact_type = str(artifact_type)
        payload = validate_artifact_payload(
            artifact_type,
            payload,
            schema_version=schema_version,
            contract_resolver=self.payload_contract_resolver,
        )
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
            type=artifact_type, schema_version=schema_version, title=title,
            semantic_key=semantic_key, version=version,
            status=status, visibility=visibility, summary=summary, payload=payload, payload_ref=payload_ref,
            resource_refs=resource_refs,
            provenance=provenance or {}, relations=relations or [],
        )
        self.session.add(AgentArtifactRecord(
            id=artifact_id, run_id=run_id, session_id=lease.session_id, turn_id=turn_id,
            semantic_id=semantic_key, version=version, type=artifact_type,
            schema_version=schema_version, title=title,
            payload_json=_json(payload),
            presentation_json=_json({"visibility": visibility.value}),
            summary=summary,
            payload_ref=payload_ref,
            resource_refs_json=dump_resource_refs(resource_refs),
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
            run_id=run_id,
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
                schema_version=draft.schema_version,
                title=draft.title,
                payload=item.payload,
                summary=draft.summary,
                semantic_key=(
                    draft.semantic_key
                    or f"{draft.type}:{invocation_id}:{draft.key}"
                ),
                payload_ref=draft.payload_ref,
                resource_refs=draft.resource_refs,
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
        run_id: str,
        drafts: list[ArtifactDraft],
    ) -> tuple[_PreparedArtifactDraft, ...]:
        """Resolve and validate one complete draft batch before the first write."""

        keys = [draft.key for draft in drafts]
        if len(set(keys)) != len(keys):
            raise ArtifactDraftContractError(
                "Artifact draft keys must be unique within one tool outcome"
            )

        authorized_refs = resource_refs_for_run(
            self.session,
            self.session.get(AgentRun, run_id),
        )
        authorized = {
            (ref.kind, ref.id, ref.version)
            for ref in authorized_refs
        }
        for draft in drafts:
            declared = [
                (ref.kind, ref.id, ref.version)
                for ref in draft.resource_refs
            ]
            if len(set(declared)) != len(declared):
                raise ArtifactDraftContractError(
                    "Artifact resource_refs must be unique by exact resource identity"
                )
            if any(identity not in authorized for identity in declared):
                raise ArtifactDraftContractError(
                    "Artifact resource_refs must be a subset of the Run authority"
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
                    _set_payload_draft_ref(payload, field_name, target_id)

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
                        payload=validate_artifact_payload(
                            draft.type,
                            payload,
                            schema_version=draft.schema_version,
                            contract_resolver=self.payload_contract_resolver,
                        ),
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
    def list_for_run(self, run_id: str) -> list[Artifact]:
        rows = self.session.execute(
            select(AgentArtifactRecord).where(AgentArtifactRecord.run_id == run_id)
            .order_by(AgentArtifactRecord.sequence, AgentArtifactRecord.created_at)
        ).scalars()
        return [self._domain(row) for row in rows]

    def available_artifact(
        self,
        *,
        current_run_id: str,
        artifact_id: str,
        session_id: str,
    ) -> Artifact | None:
        """Resolve one prior Artifact within its durable resource fence."""

        current_run = self.session.get(AgentRun, current_run_id)
        row = self.session.get(AgentArtifactRecord, artifact_id)
        owner_run = (
            self.session.get(AgentRun, str(row.run_id)) if row is not None else None
        )
        current_refs = (
            resource_refs_for_run(self.session, current_run)
            if current_run is not None
            else ()
        )
        owner_refs = (
            resource_refs_for_run(self.session, owner_run)
            if owner_run is not None
            else ()
        )
        artifact_refs = (
            load_resource_refs(str(row.resource_refs_json))
            if row is not None and row.resource_refs_json
            else ()
        )
        if (
            current_run is None
            or row is None
            or owner_run is None
            or str(row.status) != ArtifactStatus.COMPLETED.value
            or str(row.session_id) != session_id
            or str(current_run.session_id) != session_id
            or str(owner_run.session_id) != session_id
            or any(ref not in current_refs for ref in artifact_refs)
            or any(ref not in owner_refs for ref in artifact_refs)
        ):
            return None
        artifact = self._domain(row)
        if str(owner_run.id) == str(current_run.id):
            return artifact
        # Internal Artifacts are execution details of their owning Run. They may
        # be consumed by later tools in that same Run, but must never become
        # cross-Run context merely because the resource fence still matches.
        if artifact.visibility == ArtifactVisibility.INTERNAL:
            return None
        if (
            int(owner_run.session_sequence or 0)
            >= int(current_run.session_sequence or 0)
            or str(owner_run.status) not in {"completed", "failed", "cancelled"}
        ):
            return None
        return artifact

    def referenced_artifacts_for_run(self, run_id: str) -> list[Artifact]:
        """Return prior Artifacts explicitly observed by this Run."""

        current_run = self.session.get(AgentRun, run_id)
        if current_run is None:
            return []
        referenced_ids: list[str] = []
        rows = self.session.execute(
            select(AgentObservationRecord.artifact_ids_json)
            .where(AgentObservationRecord.run_id == run_id)
            .order_by(AgentObservationRecord.sequence)
        ).scalars()
        for encoded in rows:
            values = _loads(str(encoded or "[]"), [])
            if not isinstance(values, list):
                continue
            for value in values:
                artifact_id = str(value).strip()
                if artifact_id and artifact_id not in referenced_ids:
                    referenced_ids.append(artifact_id)
        artifacts: list[Artifact] = []
        for artifact_id in referenced_ids:
            artifact = self.available_artifact(
                current_run_id=run_id,
                artifact_id=artifact_id,
                session_id=str(current_run.session_id),
            )
            if artifact is not None and artifact.run_id != run_id:
                artifacts.append(artifact)
        return artifacts

    @staticmethod
    def _domain(row: AgentArtifactRecord) -> Artifact:
        artifact_type = str(row.type)
        schema_version = int(row.schema_version or 1)
        presentation = _loads(str(row.presentation_json or "{}"), {})
        try:
            visibility = ArtifactVisibility(str(
                presentation.get("visibility") if isinstance(presentation, dict) else None
            ))
        except (TypeError, ValueError):
            visibility = default_artifact_visibility(artifact_type)
        payload = _loads(str(row.payload_json or "{}"), {})
        # Unknown historical type/version keeps its envelope without guessing.
        validate_artifact_payload(
            artifact_type,
            payload,
            schema_version=schema_version,
            allow_unknown=True,
        )
        return Artifact(
            id=str(row.id), session_id=str(row.session_id), run_id=str(row.run_id),
            turn_id=str(row.turn_id) if row.turn_id else None,
            type=artifact_type, schema_version=schema_version, title=str(row.title),
            semantic_key=str(row.semantic_id) if row.semantic_id else None,
            version=int(row.version or 1), status=ArtifactStatus(str(row.status)),
            visibility=visibility,
            summary=str(row.summary) if row.summary else None,
            payload=payload,
            payload_ref=str(row.payload_ref) if row.payload_ref else None,
            resource_refs=(
                load_resource_refs(str(row.resource_refs_json))
                if getattr(row, "resource_refs_json", None)
                else ()
            ),
            provenance=_loads(str(row.provenance_json or "{}"), {}),
            relations=[ArtifactRelation.model_validate(item) for item in _loads(str(row.relations_json or "[]"), [])],
        )


def _set_payload_draft_ref(
    payload: dict[str, Any],
    field_or_pointer: str,
    artifact_id: str,
) -> None:
    """Resolve a same-outcome Artifact ID at a top-level key or JSON Pointer.

    Existing top-level field names remain valid. A leading slash opts into the
    RFC 6901 path syntax so a DLC can atomically relate nested, typed payloads
    without copying a generated Artifact ID through a second write.
    """

    if not field_or_pointer.startswith("/"):
        payload[field_or_pointer] = artifact_id
        return

    tokens = [
        token.replace("~1", "/").replace("~0", "~")
        for token in field_or_pointer[1:].split("/")
    ]
    if not tokens:
        raise ArtifactDraftContractError("Artifact payload reference path is empty")

    current: Any = payload
    for token in tokens[:-1]:
        if isinstance(current, dict):
            if token not in current:
                raise ArtifactDraftContractError(
                    "Artifact payload reference path does not exist"
                )
            current = current[token]
            continue
        if isinstance(current, list):
            try:
                index = int(token)
            except ValueError as exc:
                raise ArtifactDraftContractError(
                    "Artifact payload reference array index is invalid"
                ) from exc
            if index < 0 or index >= len(current):
                raise ArtifactDraftContractError(
                    "Artifact payload reference array index is out of range"
                )
            current = current[index]
            continue
        raise ArtifactDraftContractError(
            "Artifact payload reference path crosses a scalar value"
        )

    leaf = tokens[-1]
    if isinstance(current, dict):
        current[leaf] = artifact_id
        return
    if isinstance(current, list):
        try:
            index = int(leaf)
        except ValueError as exc:
            raise ArtifactDraftContractError(
                "Artifact payload reference array index is invalid"
            ) from exc
        if index < 0 or index >= len(current):
            raise ArtifactDraftContractError(
                "Artifact payload reference array index is out of range"
            )
        current[index] = artifact_id
        return
    raise ArtifactDraftContractError(
        "Artifact payload reference path targets a scalar value"
    )
