import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from engine.app.safe_errors import (
    FixedErrorCode,
    SafeLogOperation,
    fixed_error_message,
    log_unexpected_exception,
)
from engine.db import get_db
from engine.errors import DBFoxError, NotFoundError
from engine.sql.dialect_context import DialectContext
from engine.sql.safety.service import SqlSafetyService
from engine.models import DataSource, QueryHistory
from engine.persistence.search_index import SearchIndexService
from engine.policy.redactor import DataRedactor
from engine.query_registry import QUERY_REGISTRY
from engine.schemas import SQLCancelRequest, SQLExplainRequest, SQLValidateRequest

logger = logging.getLogger("dbfox.api.query")
router = APIRouter()


def _public_guardrail_result(result: dict[str, Any]) -> dict[str, Any]:
    """Return the JSON-safe guardrail payload exposed by public APIs.

    Defensive filtering keeps internal-only fields out of browser responses if
    future guardrail helpers add private artifacts.
    """
    return {key: value for key, value in result.items() if not key.startswith("_")}


from engine.schemas.query import QueryHistoryResponse


_QUERY_HISTORY_PUBLIC_TEXT_FIELDS = (
    "question",
    "submitted_sql",
    "generated_sql",
    "safe_sql",
    "executed_sql",
    "guardrail_checks",
    "error_message",
)


def _public_query_history_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return DataRedactor.redact_sql(value)


def _query_history_to_dict(item: QueryHistory) -> dict[str, Any]:
    payload = QueryHistoryResponse.model_validate(item).model_dump(mode="json")
    for field in _QUERY_HISTORY_PUBLIC_TEXT_FIELDS:
        payload[field] = _public_query_history_text(payload.get(field))
    return payload


@router.post("/query/validate")
def api_validate_sql(req: SQLValidateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    ctx = DialectContext(datasource_id=req.datasource_id or "", dialect="mysql")
    if req.datasource_id:
        ds = db.query(DataSource).filter(DataSource.id == req.datasource_id).first()
        if not ds:
            raise NotFoundError("Datasource not found", "DATASOURCE_NOT_FOUND")
        ctx = DialectContext.from_datasource(ds)
    result = SqlSafetyService(db).public_validate_sql(req.sql, ctx)
    return _public_guardrail_result(dict(result))


@router.post("/query/explain")
def api_explain_sql(req: SQLExplainRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    datasource = db.query(DataSource).filter(DataSource.id == req.datasource_id).first()
    if not datasource:
        raise NotFoundError("Datasource not found", "DATASOURCE_NOT_FOUND")

    try:
        if str(datasource.db_type or "").lower() == "postgresql":
            from engine.sql.postgres_explain import explain_postgres_sql

            return explain_postgres_sql(db, req.datasource_id, req.sql)

        from engine.sql.executor import explain_sql

        return explain_sql(db, req.datasource_id, req.sql)
    except DBFoxError:
        raise
    except Exception as exc:
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.QUERY_EXPLAIN,
            exc=exc,
        )
        raise DBFoxError(
            fixed_error_message(FixedErrorCode.QUERY_EXECUTION_FAILED),
            FixedErrorCode.QUERY_EXECUTION_FAILED.value,
        ) from None


@router.post("/query/cancel")
def api_cancel_sql(req: SQLCancelRequest) -> dict[str, Any]:
    return QUERY_REGISTRY.cancel(req.execution_id)


@router.get("/query/history")
def api_query_history(
    datasource_id: str | None = Query(None),
    search: str | None = Query(None, max_length=200),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    history_query = db.query(QueryHistory)

    if datasource_id:
        history_query = history_query.filter(QueryHistory.data_source_id == datasource_id)

    status_filter = (status or "").strip().lower()
    if status_filter and status_filter != "all":
        allowed_statuses = {"success", "failed", "timeout", "cancelled"}
        if status_filter not in allowed_statuses:
            raise DBFoxError("Unsupported query history status filter", "INVALID_HISTORY_STATUS")
        history_query = history_query.filter(QueryHistory.execution_status == status_filter)

    search_term = (search or "").strip()
    if search_term:
        try:
            fts_ids = SearchIndexService(db).search_query_history(
                search_term,
                datasource_id=datasource_id,
                limit=limit * 2,
            )
            if fts_ids:
                history_query = history_query.filter(QueryHistory.id.in_(fts_ids))
            else:
                return []
        except Exception:
            # FTS5 unavailable — fall back to LIKE
            pattern = f"%{search_term}%"
            history_query = history_query.filter(
                or_(
                    QueryHistory.question.ilike(pattern),
                    QueryHistory.submitted_sql.ilike(pattern),
                    QueryHistory.generated_sql.ilike(pattern),
                    QueryHistory.safe_sql.ilike(pattern),
                    QueryHistory.executed_sql.ilike(pattern),
                    QueryHistory.error_message.ilike(pattern),
                )
            )

    history = history_query.order_by(QueryHistory.created_at.desc()).limit(limit).all()
    return [_query_history_to_dict(item) for item in history]


@router.delete("/query/history/{history_id}")
def api_delete_query_history(history_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = db.query(QueryHistory).filter(QueryHistory.id == history_id).first()
    if not item:
        raise NotFoundError("Query history record not found", "QUERY_HISTORY_NOT_FOUND")

    try:
        try:
            SearchIndexService(db).delete_query_history(history_id)
        except Exception as exc:
            db.rollback()
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.QUERY_HISTORY_INDEX_DELETE,
                exc=exc,
                level="warning",
            )
        db.delete(item)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"success": True, "deleted": 1}


@router.delete("/query/history")
def api_clear_query_history(datasource_id: str = Query(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    datasource = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not datasource:
        raise NotFoundError("Datasource not found", "DATASOURCE_NOT_FOUND")

    try:
        try:
            SearchIndexService(db).clear_query_history(datasource_id)
        except Exception as exc:
            db.rollback()
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.QUERY_HISTORY_INDEX_CLEAR,
                exc=exc,
                level="warning",
            )
        deleted = (
            db.query(QueryHistory)
            .filter(QueryHistory.data_source_id == datasource_id)
            .delete(synchronize_session=False)
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"success": True, "deleted": deleted}
