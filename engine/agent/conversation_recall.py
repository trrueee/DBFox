"""Read-only access to the canonical current-session conversation archive.

The FTS table is a derived locator.  Every returned message is read from
``agent_messages`` and is scoped by the caller-supplied session identifier.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Sequence

from sqlalchemy import text as sa_text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session


ConversationRole = Literal["user", "assistant"]


def assert_agent_message_search_schema(bind: Any) -> None:
    """Fail closed when Alembic's conversation-recall contract is absent."""

    try:
        bind.execute(sa_text("SELECT search_text FROM agent_message_fts LIMIT 0"))
        bind.execute(sa_text("SELECT 1 FROM agent_message_search_docs LIMIT 0"))
    except OperationalError as exc:
        raise RuntimeError("DBFOX_AGENT_MESSAGE_FTS_CONTRACT_MISSING") from exc


@dataclass(frozen=True)
class RecalledMessage:
    message_id: str
    sequence: int
    role: ConversationRole
    content: str
    created_at: str


@dataclass(frozen=True)
class ConversationArchiveStats:
    message_count: int
    oldest_sequence: int | None
    newest_sequence: int | None


class ConversationRecallService:
    """Search and page one session without creating another transcript store."""

    def __init__(self, db: Session):
        self.db = db

    def assert_schema(self) -> None:
        assert_agent_message_search_schema(self.db)

    def archive_stats(self, session_id: str) -> ConversationArchiveStats:
        row = self.db.execute(
            sa_text(
                """
                SELECT count(m.id), min(m.sequence), max(m.sequence)
                FROM agent_messages AS m
                JOIN agent_sessions AS s ON s.id = m.session_id
                WHERE m.session_id = :session_id
                  AND s.deleted_at IS NULL
                  AND (
                    m.role = 'user'
                    OR (m.role = 'assistant' AND m.status = 'completed')
                  )
                """
            ),
            {"session_id": session_id},
        ).one()
        return ConversationArchiveStats(
            message_count=int(row[0] or 0),
            oldest_sequence=int(row[1]) if row[1] is not None else None,
            newest_sequence=int(row[2]) if row[2] is not None else None,
        )

    def search(
        self,
        *,
        session_id: str,
        query: str,
        roles: Sequence[ConversationRole],
        limit: int,
    ) -> tuple[list[RecalledMessage], Literal["fts5_trigram", "literal_scan"]]:
        self.assert_schema()
        term = query.strip()
        if not term:
            return [], "fts5_trigram"
        include_user = 1 if "user" in roles else 0
        include_assistant = 1 if "assistant" in roles else 0
        common_params: dict[str, Any] = {
            "session_id": session_id,
            "include_user": include_user,
            "include_assistant": include_assistant,
            "limit": limit,
        }

        if len(term) >= 3:
            # This is FTS query syntax, not SQL interpolation.  The complete FTS
            # expression remains a bound SQL value; quotes make it a literal phrase.
            fts_query = f'"{term.replace(chr(34), chr(34) + chr(34))}"'
            rows = self.db.execute(
                sa_text(
                    """
                    SELECT m.id, m.sequence, m.role, m.content, m.created_at
                    FROM agent_message_fts
                    JOIN agent_message_search_docs AS d
                      ON d.id = agent_message_fts.rowid
                    JOIN agent_messages AS m ON m.id = d.message_id
                    JOIN agent_sessions AS s ON s.id = m.session_id
                    WHERE agent_message_fts MATCH :fts_query
                      AND m.session_id = :session_id
                      AND s.deleted_at IS NULL
                      AND (
                        (:include_user = 1 AND m.role = 'user')
                        OR (
                          :include_assistant = 1
                          AND m.role = 'assistant'
                          AND m.status = 'completed'
                        )
                      )
                    ORDER BY bm25(agent_message_fts), m.sequence DESC
                    LIMIT :limit
                    """
                ),
                {**common_params, "fts_query": fts_query},
            ).all()
            mode: Literal["fts5_trigram", "literal_scan"] = "fts5_trigram"
        else:
            # FTS5's trigram tokenizer cannot match fewer than three Unicode
            # characters.  The explicit short-query contract uses one bound,
            # current-session canonical scan and still returns a bounded page.
            rows = self.db.execute(
                sa_text(
                    """
                    SELECT m.id, m.sequence, m.role, m.content, m.created_at
                    FROM agent_messages AS m
                    JOIN agent_sessions AS s ON s.id = m.session_id
                    WHERE m.session_id = :session_id
                      AND s.deleted_at IS NULL
                      AND instr(lower(m.content), lower(:literal_query)) > 0
                      AND (
                        (:include_user = 1 AND m.role = 'user')
                        OR (
                          :include_assistant = 1
                          AND m.role = 'assistant'
                          AND m.status = 'completed'
                        )
                      )
                    ORDER BY m.sequence DESC
                    LIMIT :limit
                    """
                ),
                {**common_params, "literal_query": term},
            ).all()
            mode = "literal_scan"
        return [self._message(row) for row in rows], mode

    def read(
        self,
        *,
        session_id: str,
        after_sequence: int,
        limit: int,
    ) -> tuple[list[RecalledMessage], bool]:
        rows = self.db.execute(
            sa_text(
                """
                SELECT m.id, m.sequence, m.role, m.content, m.created_at
                FROM agent_messages AS m
                JOIN agent_sessions AS s ON s.id = m.session_id
                WHERE m.session_id = :session_id
                  AND s.deleted_at IS NULL
                  AND m.sequence > :after_sequence
                  AND (
                    m.role = 'user'
                    OR (m.role = 'assistant' AND m.status = 'completed')
                  )
                ORDER BY m.sequence ASC
                LIMIT :fetch_limit
                """
            ),
            {
                "session_id": session_id,
                "after_sequence": after_sequence,
                "fetch_limit": limit + 1,
            },
        ).all()
        has_more = len(rows) > limit
        return [self._message(row) for row in rows[:limit]], has_more

    @staticmethod
    def _message(row: Any) -> RecalledMessage:
        timestamp = row[4]
        created_at = (
            timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp)
        )
        return RecalledMessage(
            message_id=str(row[0]),
            sequence=int(row[1]),
            role=str(row[2]),  # type: ignore[arg-type]
            content=str(row[3] or ""),
            created_at=created_at,
        )
