"""Conversation memory and datasource-scoped reusable SQL persistence."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from engine.agent_core.memory import sql_fingerprint
from engine.agent_core.persistence._common import (
    _model_datetime,
    _model_int,
    _model_optional_str,
    _model_str,
    _model_value,
)
from engine.models import AgentSessionMemory, ReusableSQL


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _json_load(raw: str | None, fallback: Any) -> Any:
    if raw is None:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def load_session_memory(db: Session, session_id: str) -> dict[str, Any] | None:
    record = (
        db.query(AgentSessionMemory)
        .filter(AgentSessionMemory.session_id == session_id)
        .first()
    )
    if record is None:
        return None

    payload = _json_load(_model_optional_str(record, "memory_json"), {})
    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("conversation_summary", _model_optional_str(record, "conversation_summary"))
    payload.setdefault("summary_cursor_message_id", _model_optional_str(record, "summary_cursor_message_id"))
    payload.setdefault("session_id", _model_str(record, "session_id"))
    payload.setdefault("datasource_id", _model_str(record, "datasource_id"))
    return payload


def save_session_memory(
    db: Session,
    *,
    session_id: str,
    datasource_id: str,
    payload: dict[str, Any],
) -> AgentSessionMemory:
    now = datetime.now(UTC)
    record = (
        db.query(AgentSessionMemory)
        .filter(AgentSessionMemory.session_id == session_id)
        .first()
    )
    if record is None:
        record = AgentSessionMemory(
            session_id=session_id,
            datasource_id=datasource_id,
            created_at=now,
        )
        db.add(record)

    record.datasource_id = datasource_id  # type: ignore[assignment]
    record.conversation_summary = payload.get("conversation_summary")  # type: ignore[assignment]
    record.summary_cursor_message_id = payload.get("summary_cursor_message_id")  # type: ignore[assignment]
    record.memory_json = _json_dump(payload)  # type: ignore[assignment]
    record.updated_at = now  # type: ignore[assignment]
    db.flush()
    return record


def upsert_reusable_sql(
    db: Session,
    *,
    datasource_id: str,
    question: str,
    safe_sql: str,
    purpose: str | None = None,
    involved_tables: list[str] | None = None,
    result_columns: list[str] | None = None,
    source_artifact_id: str | None = None,
    source_sql_artifact_id: str | None = None,
    verified: bool = False,
) -> ReusableSQL:
    now = datetime.now(UTC)
    fingerprint = sql_fingerprint(safe_sql)
    record = (
        db.query(ReusableSQL)
        .filter(
            ReusableSQL.data_source_id == datasource_id,
            ReusableSQL.sql_fingerprint == fingerprint,
        )
        .first()
    )
    if record is None:
        record = ReusableSQL(
            data_source_id=datasource_id,
            sql_fingerprint=fingerprint,
            usage_count=0,
            created_at=now,
        )
        db.add(record)

    record.question = question  # type: ignore[assignment]
    record.safe_sql = safe_sql  # type: ignore[assignment]
    record.purpose = purpose  # type: ignore[assignment]
    record.involved_tables_json = _json_dump(involved_tables or [])  # type: ignore[assignment]
    record.result_columns_json = _json_dump(result_columns or [])  # type: ignore[assignment]
    record.source_artifact_id = source_artifact_id  # type: ignore[assignment]
    record.source_sql_artifact_id = source_sql_artifact_id  # type: ignore[assignment]
    record.verified = bool(_model_value(record, "verified") or verified)  # type: ignore[assignment]
    record.usage_count = _model_int(record, "usage_count") + 1  # type: ignore[assignment]
    record.last_used_at = now  # type: ignore[assignment]
    record.updated_at = now  # type: ignore[assignment]
    db.flush()
    return record


def list_reusable_sqls(
    db: Session,
    *,
    datasource_id: str,
    limit: int = 5,
    verified_only: bool = True,
) -> list[dict[str, Any]]:
    query = db.query(ReusableSQL).filter(ReusableSQL.data_source_id == datasource_id)
    if verified_only:
        query = query.filter(ReusableSQL.verified.is_(True))
    rows = (
        query.order_by(
            ReusableSQL.usage_count.desc(),
            ReusableSQL.last_used_at.desc(),
            ReusableSQL.updated_at.desc(),
        )
        .limit(max(0, limit))
        .all()
    )

    candidates: list[dict[str, Any]] = []
    for row in rows:
        tables = _json_load(_model_optional_str(row, "involved_tables_json"), [])
        columns = _json_load(_model_optional_str(row, "result_columns_json"), [])
        last_used_at = _model_datetime(row, "last_used_at")
        candidates.append(
            {
                "id": _model_str(row, "id"),
                "kind": "reusable_sql",
                "datasource_id": _model_str(row, "data_source_id"),
                "question": _model_str(row, "question"),
                "safe_sql": _model_str(row, "safe_sql"),
                "sql_fingerprint": _model_str(row, "sql_fingerprint"),
                "purpose": _model_optional_str(row, "purpose"),
                "tables": tables if isinstance(tables, list) else [],
                "columns": columns if isinstance(columns, list) else [],
                "source_artifact_id": _model_optional_str(row, "source_artifact_id"),
                "source_sql_artifact_id": _model_optional_str(row, "source_sql_artifact_id"),
                "usage_count": _model_int(row, "usage_count"),
                "verified": bool(_model_value(row, "verified")),
                "last_used_at": last_used_at.isoformat() if last_used_at else None,
            }
        )
    return candidates
