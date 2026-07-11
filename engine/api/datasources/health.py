from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from engine.api.datasources.common import (
    datasource_to_dict,
    datasource_to_health_config,
    persist_health_failure,
    persist_health_success,
)
from engine.app.safe_errors import (
    FixedErrorCode,
    SafeLogOperation,
    fixed_error_detail,
    log_unexpected_exception,
)
from engine.datasource import test_connection
from engine.db import get_db
from engine.errors import DBFoxError, NotFoundError
from engine.models import DataSource
from engine.schemas.datasource import _json_list_or_empty

logger = logging.getLogger("dbfox.api.datasources.health")
router = APIRouter()


@router.post("/datasources/{id}/health")
def api_check_datasource_health(id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    datasource = db.query(DataSource).filter(DataSource.id == id).first()
    if not datasource:
        raise NotFoundError("数据源不存在")

    started = time.perf_counter()
    checked_at = datetime.now(UTC)
    try:
        result = test_connection(datasource_to_health_config(datasource))
        latency_ms = int((time.perf_counter() - started) * 1000)
        persist_health_success(datasource, result, latency_ms, checked_at)
        db.commit()
        db.refresh(datasource)
        return {
            "ok": True,
            "status": "success",
            "checkedAt": datasource.last_test_at.isoformat() if datasource.last_test_at else None,
            "latencyMs": latency_ms,
            "serverVersion": datasource.last_test_server_version,
            "readonly": datasource.last_test_readonly,
            "tablesCount": datasource.last_test_tables_count,
            "warnings": _json_list_or_empty(datasource.last_test_warnings),
            "message": result.get("message", "连接健康检查通过。"),
            "datasource": datasource_to_dict(datasource),
        }
    except DBFoxError:
        latency_ms = int((time.perf_counter() - started) * 1000)
        detail = fixed_error_detail(FixedErrorCode.DATASOURCE_CONNECTION_FAILED)
        persist_health_failure(
            datasource,
            FixedErrorCode.DATASOURCE_CONNECTION_FAILED,
            latency_ms,
            checked_at,
        )
        db.commit()
        db.refresh(datasource)
        return {
            "ok": False,
            "status": "failed",
            "checkedAt": datasource.last_test_at.isoformat() if datasource.last_test_at else None,
            "latencyMs": latency_ms,
            "warnings": [],
            "code": detail["code"],
            "message": detail["message"],
            "datasource": datasource_to_dict(datasource),
        }
    except Exception as exc:
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.DATASOURCE_HEALTH_CHECK,
            exc=exc,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        detail = fixed_error_detail(FixedErrorCode.DATASOURCE_CONNECTION_FAILED)
        persist_health_failure(
            datasource,
            FixedErrorCode.DATASOURCE_CONNECTION_FAILED,
            latency_ms,
            checked_at,
        )
        db.commit()
        db.refresh(datasource)
        return {
            "ok": False,
            "status": "failed",
            "checkedAt": datasource.last_test_at.isoformat() if datasource.last_test_at else None,
            "latencyMs": latency_ms,
            "warnings": [],
            "code": detail["code"],
            "message": detail["message"],
            "datasource": datasource_to_dict(datasource),
        }
