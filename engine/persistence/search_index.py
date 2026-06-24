from __future__ import annotations

from typing import Any

from sqlalchemy import text as sa_text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from engine.models import QueryHistory


QUERY_HISTORY_SEARCH_DOCS_DDL = """
CREATE TABLE IF NOT EXISTS query_history_search_docs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    history_id VARCHAR NOT NULL UNIQUE,
    datasource_id VARCHAR NOT NULL,
    question TEXT,
    submitted_sql TEXT,
    generated_sql TEXT,
    safe_sql TEXT,
    executed_sql TEXT,
    error_message TEXT,
    search_text TEXT NOT NULL DEFAULT '',
    created_at DATETIME,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(history_id) REFERENCES query_history(id) ON DELETE CASCADE
)
"""

QUERY_HISTORY_SEARCH_DOCS_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS ix_query_history_search_docs_datasource
ON query_history_search_docs (datasource_id)
"""

QUERY_HISTORY_FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS query_history_fts
USING fts5(search_text, content='query_history_search_docs', content_rowid='id')
"""

QUERY_HISTORY_FTS_TRIGGERS = [
    """
    CREATE TRIGGER IF NOT EXISTS query_history_search_docs_ai
    AFTER INSERT ON query_history_search_docs BEGIN
        INSERT INTO query_history_fts(rowid, search_text)
        VALUES (new.id, new.search_text);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS query_history_search_docs_ad
    AFTER DELETE ON query_history_search_docs BEGIN
        INSERT INTO query_history_fts(query_history_fts, rowid, search_text)
        VALUES ('delete', old.id, old.search_text);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS query_history_search_docs_au
    AFTER UPDATE ON query_history_search_docs BEGIN
        INSERT INTO query_history_fts(query_history_fts, rowid, search_text)
        VALUES ('delete', old.id, old.search_text);
        INSERT INTO query_history_fts(rowid, search_text)
        VALUES (new.id, new.search_text);
    END
    """,
]


def _fts_has_expected_schema(bind: Any) -> bool:
    try:
        bind.execute(sa_text("SELECT search_text FROM query_history_fts LIMIT 0"))
        return True
    except OperationalError as exc:
        message = str(exc).lower()
        if "no such table" in message or "no such column" in message:
            return False
        raise


def ensure_query_history_search_schema(bind: Any) -> None:
    bind.execute(sa_text(QUERY_HISTORY_SEARCH_DOCS_DDL))
    bind.execute(sa_text(QUERY_HISTORY_SEARCH_DOCS_INDEX_DDL))
    if not _fts_has_expected_schema(bind):
        bind.execute(sa_text("DROP TABLE IF EXISTS query_history_fts"))
    bind.execute(sa_text(QUERY_HISTORY_FTS_DDL))
    for ddl in QUERY_HISTORY_FTS_TRIGGERS:
        bind.execute(sa_text(ddl))


class SearchIndexService:
    def __init__(self, db: Session):
        self.db = db

    def ensure_schema(self) -> None:
        ensure_query_history_search_schema(self.db)

    def rebuild_query_history_index(self) -> None:
        self.ensure_schema()
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
        self.ensure_schema()
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
                "created_at": history.created_at,
            },
        )

    def delete_query_history(self, history_id: str) -> None:
        self.ensure_schema()
        self.db.execute(
            sa_text("DELETE FROM query_history_search_docs WHERE history_id = :history_id"),
            {"history_id": history_id},
        )

    def clear_query_history(self, datasource_id: str) -> None:
        self.ensure_schema()
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
        self.ensure_schema()
        term = search.strip()
        if not term:
            return []
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
