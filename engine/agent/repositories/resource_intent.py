"""Durable Conversation resource intent repository.

Intent contains identity only. It is never an execution grant and never stores
the canonical resource version; input admission re-authorizes every identity.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from engine.agent.repositories.write_transaction import begin_agent_write
from engine.agent.resource_refs import MAX_INPUT_RESOURCE_REFS, RequestedResourceRef
from engine.models import AgentSession, ConversationResourceIntent


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ConversationResourceIntentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, conversation_id: str) -> tuple[RequestedResourceRef, ...]:
        rows = self.session.execute(
            select(ConversationResourceIntent)
            .where(ConversationResourceIntent.conversation_id == conversation_id)
            .order_by(ConversationResourceIntent.position)
        ).scalars().all()
        return tuple(
            RequestedResourceRef(kind=str(row.kind), id=str(row.resource_id))
            for row in rows
        )

    def replace(
        self,
        conversation_id: str,
        refs: tuple[RequestedResourceRef, ...],
    ) -> tuple[RequestedResourceRef, ...]:
        if len(refs) > MAX_INPUT_RESOURCE_REFS:
            raise ValueError(
                f"resource intent count exceeds maximum {MAX_INPUT_RESOURCE_REFS}"
            )
        keys = [(ref.kind, ref.id) for ref in refs]
        if len(set(keys)) != len(keys):
            raise ValueError("resource intents must be unique by (kind, id)")

        begin_agent_write(self.session)
        aggregate = self.session.execute(
            select(AgentSession)
            .where(AgentSession.id == conversation_id)
            .with_for_update()
        ).scalar_one_or_none()
        if aggregate is None or aggregate.deleted_at is not None:
            raise ValueError("Conversation not found")

        self.session.execute(
            delete(ConversationResourceIntent).where(
                ConversationResourceIntent.conversation_id == conversation_id
            )
        )
        now = _utcnow()
        self.session.add_all([
            ConversationResourceIntent(
                conversation_id=conversation_id,
                kind=ref.kind,
                resource_id=ref.id,
                position=position,
                created_at=now,
            )
            for position, ref in enumerate(refs)
        ])
        aggregate.context_epoch = int(aggregate.context_epoch or 0) + 1
        aggregate.updated_at = now
        self.session.flush()
        return refs
