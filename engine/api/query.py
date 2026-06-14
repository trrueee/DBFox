import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from engine.db import get_db
from engine.errors import DataBoxError
from engine.sql.executor import execute_query
from engine.sql.guardrail import guardrail_check
from engine.models import DataSource, QueryHistory
from engine.policy.engine import PolicyEngine
from engine.query_registry import QUERY_REGISTRY
from engine.schemas import SQLCancelRequest, SQLExecuteRequest, SQLExplainRequest, SQLValidateRequest

logger = logging.getLogger("databox.api.query")
router = APIRouter()


def _public_guardrail_result(result: dict[str, Any]) -> dict[str, Any]:
    """Return the JSON-safe guardrail payload exposed by public APIs.

    guardrail_check keeps internal parser artifacts such as _parsed_ast so
    TrustGate can validate schema against the SQL AST. Those objects are not
    JSON serializable and must never be returned to the browser.
    """
    return {key: value for key, value in result.items() if not key.startswith("_")}


def _query_history_to_dict(item: QueryHistory) -> dict[str, Any]:
    return {
        "id": item.id,
        "question": item.question or "",
        "submitted_sql": item.submitted_sql or "",
        "generated_sql": item.generated_sql or "",
        "safe_sql": item.safe_sql or "",
        "executed_sql": item.executed_sql or "",
        "guardrail_result": item.guardrail_result,
        "guardrail_checks": item.guardrail_checks or "",
        "execution_status": item.execution_status or "",
        "execution_time_ms": item.execution_time_ms or 0,
        "rows_returned": item.rows_returned or 0,
        "columns_returned": item.columns_returned or 0,
        "error_message": item.error_message or "",
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


@router.post("/query/validate")
def api_validate_sql(req: SQLValidateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    dialect = "mysql"
    if req.datasource_id:
        ds = db.query(DataSource).filter(DataSource.id == req.datasource_id).first()
        if not ds:
            raise HTTPException(
                status_code=404,
                detail={"code": "DATASOURCE_NOT_FOUND", "message": "Datasource not found"},
            )
        dialect = str(ds.db_type or "mysql")
    result = guardrail_check(req.sql, dialect=dialect)
    return _public_guardrail_result(dict(result))


@router.post("/query/execute")
def api_execute_sql(req: SQLExecuteRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    datasource = db.query(DataSource).filter(DataSource.id == req.datasource_id).first()
    if not datasource:
        raise HTTPException(status_code=404, detail={"code": "DATASOURCE_NOT_FOUND", "message": "Datasource not found"})

    try:
        PolicyEngine.enforce_query_policy(datasource, req.sql)
    except DataBoxError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})

    try:
        return execute_query(db, req.datasource_id, req.sql, req.question, req.execution_id)
    except DataBoxError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        logger.exception("SQL execution failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "EXECUTION_ERROR", "message": f"SQL execution failed: {str(exc)}"},
        )


@router.post("/query/explain")
def api_explain_sql(req: SQLExplainRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    datasource = db.query(DataSource).filter(DataSource.id == req.datasource_id).first()
    if not datasource:
        raise HTTPException(status_code=404, detail={"code": "DATASOURCE_NOT_FOUND", "message": "Datasource not found"})

    try:
        if str(datasource.db_type or "").lower() == "postgresql":
            from engine.sql.postgres_explain import explain_postgres_sql

            return explain_postgres_sql(db, req.datasource_id, req.sql)

        from engine.sql.executor import explain_sql

        return explain_sql(db, req.datasource_id, req.sql)
    except DataBoxError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        logger.exception("SQL explain failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "EXPLAIN_ERROR", "message": f"SQL EXPLAIN failed: {str(exc)}"},
        )


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
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_HISTORY_STATUS", "message": "Unsupported query history status filter"},
            )
        history_query = history_query.filter(QueryHistory.execution_status == status_filter)

    search_term = (search or "").strip()
    if search_term:
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
        raise HTTPException(
            status_code=404,
            detail={"code": "QUERY_HISTORY_NOT_FOUND", "message": "Query history record not found"},
        )

    db.delete(item)
    db.commit()
    return {"success": True, "deleted": 1}


@router.delete("/query/history")
def api_clear_query_history(datasource_id: str = Query(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    datasource = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not datasource:
        raise HTTPException(status_code=404, detail={"code": "DATASOURCE_NOT_FOUND", "message": "Datasource not found"})

    deleted = (
        db.query(QueryHistory)
        .filter(QueryHistory.data_source_id == datasource_id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"success": True, "deleted": deleted}
