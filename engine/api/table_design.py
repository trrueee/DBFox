import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from engine.app.safe_errors import (
    FixedErrorCode,
    SafeLogOperation,
    fixed_error_detail,
    log_unexpected_exception,
)
from engine.db import get_db
from engine.errors import DBFoxError
from engine.models import DataSource
from engine.schemas.table_design import TestDataGenerateRequest
from engine.policy.engine import PolicyEngine

logger = logging.getLogger("dbfox.api.table_design")
router = APIRouter()


@router.post("/schema/generate-test-data")
def api_generate_test_data(req: TestDataGenerateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    datasource = db.query(DataSource).filter(DataSource.id == req.datasource_id).first()
    if not datasource:
        raise HTTPException(status_code=404, detail={"code": "DATASOURCE_NOT_FOUND", "message": "数据源不存在"})

    try:
        PolicyEngine.enforce_test_data_policy(datasource)
    except DBFoxError:
        raise HTTPException(
            status_code=400,
            detail=fixed_error_detail(FixedErrorCode.TABLE_DESIGN_ERROR),
        ) from None

    from engine.policy import confirmation_bypass_enabled, confirmation_manager
    if not confirmation_bypass_enabled():
        expected_details = {"table_name": req.table_name, "row_count": req.row_count, "language": req.language}
        if not req.confirm_token:
            token = confirmation_manager.create_confirmation(
                datasource_id=req.datasource_id,
                action="generate_test_data",
                details=expected_details,
                expected_confirm_text=str(datasource.name)
            )
            return {
                "success": False,
                "requires_confirmation": True,
                "confirm_token": token,
                "impact_summary": f"⚠️ 警告：您即将在数据源 '{datasource.name}' 的表 '{req.table_name}' 上批量生成 {req.row_count} 条测试数据。\n\n这会向该表插入大量模拟行！请输入数据源名称以确认执行。",
                "expected_confirm_text": datasource.name
            }

        is_valid, err_msg = confirmation_manager.validate_and_consume(
            req.confirm_token,
            req.confirm_text or "",
            expected_action="generate_test_data",
            expected_datasource_id=req.datasource_id,
            expected_details=expected_details
        )
        if not is_valid:
            raise HTTPException(status_code=400, detail={"code": "CONFIRMATION_FAILED", "message": err_msg})

    try:
        from engine.test_data import generate_smart_test_data
        return generate_smart_test_data(
            db=db,
            datasource_id=req.datasource_id,
            table_name=req.table_name,
            row_count=req.row_count,
            language=req.language
        )
    except DBFoxError:
        raise HTTPException(
            status_code=400,
            detail=fixed_error_detail(FixedErrorCode.TABLE_DESIGN_ERROR),
        ) from None
    except Exception as exc:
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.TABLE_DESIGN_TEST_DATA,
            exc=exc,
        )
        raise HTTPException(
            status_code=500,
            detail=fixed_error_detail(FixedErrorCode.TEST_DATA_FAILED),
        )
