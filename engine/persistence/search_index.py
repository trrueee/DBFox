from __future__ import annotations

from typing import Any

from sqlalchemy import text as sa_text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from engine.models import QueryHistory


def assert_query_history_search_schema(bind: Any) -> None:
    """Fail closed when Alembic's query-history search contract is absent.

    FTS tables and triggers are schema, not a runtime repair mechanism.  The
    application startup verifier and migrations own their creation; this
    service only checks the contract before manipulating indexed content.
    """
    try:
        bind.execute(sa_text("SELECT search_text FROM query_history_fts LIMIT 0"))
        bind.execute(sa_text("SELECT 1 FROM query_history_search_docs LIMIT 0"))
        definition = bind.execute(
            sa_text(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'table' AND name = 'query_history_fts'"
            )
        ).scalar_one_or_none()
        triggers = set(
            bind.execute(
                sa_text(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                    "AND name IN ('query_history_search_docs_ai', "
                    "'query_history_search_docs_ad', 'query_history_search_docs_au')"
                )
            ).scalars()
        )
    except OperationalError as exc:
        raise RuntimeError("DBFOX_METADATA_FTS_CONTRACT_MISSING") from exc
    normalized_definition = str(definition or "").replace(" ", "").lower()
    expected_triggers = {
        "query_history_search_docs_ai",
        "query_history_search_docs_ad",
        "query_history_search_docs_au",
    }
    if "tokenize='trigram'" not in normalized_definition or triggers != expected_triggers:
        raise RuntimeError("DBFOX_METADATA_FTS_CONTRACT_MISSING")


class SearchIndexService:
    def __init__(self, db: Session):
        self.db = db

    def assert_schema(self) -> None:
        assert_query_history_search_schema(self.db)

    def rebuild_query_history_index(self) -> None:
        self.assert_schema()
        self.db.execute(sa_text("DELETE FROM query_history_search_docs"))
        self.db.execute(
            sa_text(
                """
                INSERT INTO query_history_search_docs (
                    history_id, datasource_id, question, submitted_sql, generated_sql,
                    safe_sql, executed_sql, error_message, search_text, created_at, updated_at
                )
                SELECT
                    id,
                    data_source_id,
                    question,
                    submitted_sql,
                    generated_sql,
                    safe_sql,
                    executed_sql,
                    error_message,
                    trim(
                        coalesce(question, '') || ' ' ||
                        coalesce(submitted_sql, '') || ' ' ||
                        coalesce(generated_sql, '') || ' ' ||
                        coalesce(safe_sql, '') || ' ' ||
                        coalesce(executed_sql, '') || ' ' ||
                        coalesce(error_message, '')
                    ),
                    created_at,
                    CURRENT_TIMESTAMP
                FROM query_history
                """
            )
        )
        self.db.execute(sa_text("INSERT INTO query_history_fts(query_history_fts) VALUES ('rebuild')"))

    def index_query_history(self, history: QueryHistory) -> None:
        self.assert_schema()
        self.db.execute(
            sa_text(
                """
                INSERT INTO query_history_search_docs (
                    history_id, datasource_id, question, submitted_sql, generated_sql,
                    safe_sql, executed_sql, error_message, search_text, created_at, updated_at
                )
                VALUES (
                    :history_id, :datasource_id, :question, :submitted_sql, :generated_sql,
                    :safe_sql, :executed_sql, :error_message, :search_text, :created_at, CURRENT_TIMESTAMP
                )
                ON CONFLICT(history_id) DO UPDATE SET
                    datasource_id = excluded.datasource_id,
                    question = excluded.question,
                    submitted_sql = excluded.submitted_sql,
                    generated_sql = excluded.generated_sql,
                    safe_sql = excluded.safe_sql,
                    executed_sql = excluded.executed_sql,
                    error_message = excluded.error_message,
                    search_text = excluded.search_text,
                    created_at = excluded.created_at,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {
                "history_id": history.id,
                "datasource_id": history.data_source_id,
                "question": history.question or "",
                "submitted_sql": history.submitted_sql or "",
                "generated_sql": history.generated_sql or "",
                "safe_sql": history.safe_sql or "",
                "executed_sql": history.executed_sql or "",
                "error_message": history.error_message or "",
                "search_text": self._history_search_text(history),
                # Raw SQLite text statements must not rely on Python 3.12's
                # deprecated default datetime adapter.
                "created_at": history.created_at.isoformat(),
            },
        )

    def delete_query_history(self, history_id: str) -> None:
        self.assert_schema()
        self.db.execute(
            sa_text("DELETE FROM query_history_search_docs WHERE history_id = :history_id"),
            {"history_id": history_id},
        )

    def clear_query_history(self, datasource_id: str) -> None:
        self.assert_schema()
        self.db.execute(
            sa_text("DELETE FROM query_history_search_docs WHERE datasource_id = :datasource_id"),
            {"datasource_id": datasource_id},
        )

    def search_query_history(
        self,
        search: str,
        *,
        datasource_id: str | None = None,
        limit: int = 50,
    ) -> list[str]:
        self.assert_schema()
        term = search.strip()
        if not term:
            return []
        if len(term) < 3:
            if not datasource_id:
                # Trigram cannot match fewer than three Unicode characters.
                # A short literal scan is allowed only inside one indexed
                # datasource partition and remains bounded by the caller limit.
                return []
            rows = self.db.execute(
                sa_text(
                    """
                    SELECT history_id
                    FROM query_history_search_docs
                    WHERE datasource_id = :datasource_id
                      AND instr(lower(search_text), lower(:literal_query)) > 0
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit
                    """
                ),
                {
                    "datasource_id": datasource_id,
                    "literal_query": term,
                    "limit": limit,
                },
            ).fetchall()
            return [str(row[0]) for row in rows]
        fts_query = f'"{term.replace(chr(34), chr(34) + chr(34))}"'
        sql = """
            SELECT d.history_id
            FROM query_history_fts
            JOIN query_history_search_docs d ON d.id = query_history_fts.rowid
            WHERE query_history_fts MATCH :query
        """
        params: dict[str, Any] = {"query": fts_query, "limit": limit}
        if datasource_id:
            sql += " AND d.datasource_id = :datasource_id"
            params["datasource_id"] = datasource_id
        sql += " ORDER BY rank LIMIT :limit"
        rows = self.db.execute(sa_text(sql), params).fetchall()
        return [str(row[0]) for row in rows]

    @staticmethod
    def _history_search_text(history: QueryHistory) -> str:
        parts = [
            history.question,
            history.submitted_sql,
            history.generated_sql,
            history.safe_sql,
            history.executed_sql,
            history.error_message,
        ]
        return " ".join(str(part) for part in parts if part).strip()
