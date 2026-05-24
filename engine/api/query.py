import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from engine.db import get_db
from engine.errors import DataBoxError
from engine.executor import execute_query
from engine.guardrail import guardrail_check
from engine.models import DataSource, QueryHistory
from engine.query_registry import QUERY_REGISTRY
from engine.schemas import SQLValidateRequest, SQLExecuteRequest, SQLCancelRequest, SQLExplainRequest
from engine.policy.engine import PolicyEngine

logger = logging.getLogger("databox.api.query")
router = APIRouter()


@router.post("/query/validate")
def api_validate_sql(req: SQLValidateRequest) -> dict[str, Any]:
    result = guardrail_check(req.sql)
    return dict(result)


@router.post("/query/execute")
def api_execute_sql(req: SQLExecuteRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    datasource = db.query(DataSource).filter(DataSource.id == req.datasource_id).first()
    if not datasource:
        raise HTTPException(status_code=404, detail={"code": "DATASOURCE_NOT_FOUND", "message": "数据源不存在"})

    # 🔒 Policy Engine Enforcement
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
            detail={"code": "EXECUTION_ERROR", "message": f"SQL 执行失败: {str(exc)}"},
        )


@router.post("/query/explain")
def api_explain_sql(req: SQLExplainRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        from engine.executor import explain_sql
        return explain_sql(db, req.datasource_id, req.sql)
    except DataBoxError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        logger.exception("SQL explain failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "EXPLAIN_ERROR", "message": f"SQL EXPLAIN 诊断失败: {str(exc)}"},
        )


@router.post("/query/cancel")
def api_cancel_sql(req: SQLCancelRequest) -> dict[str, Any]:
    return QUERY_REGISTRY.cancel(req.execution_id)


@router.get("/query/history")
def api_query_history(datasource_id: str = Query(...), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    history = (
        db.query(QueryHistory)
        .filter(QueryHistory.data_source_id == datasource_id)
        .order_by(QueryHistory.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": item.id,
            "question": item.question or "",
            "submitted_sql": item.submitted_sql,
            "generated_sql": item.generated_sql or "",
            "safe_sql": item.safe_sql or "",
            "executed_sql": item.executed_sql or "",
            "guardrail_result": item.guardrail_result,
            "guardrail_checks": item.guardrail_checks or "",
            "execution_status": item.execution_status,
            "execution_time_ms": item.execution_time_ms or 0,
            "rows_returned": item.rows_returned or 0,
            "columns_returned": item.columns_returned or 0,
            "error_message": item.error_message or "",
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        for item in history
    ]
