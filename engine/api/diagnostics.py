from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from engine.agent.repositories.write_transaction import begin_agent_write
from engine.db import get_db
from engine.diagnostics.logs import (
    DEFAULT_MAX_LINES,
    clear_diagnostic_log_source,
    collect_diagnostic_logs,
    diagnostic_log_paths,
)
from engine.security.audit import (
    AUDIT_DIAGNOSTIC_MAX_RECORDS,
    AUDIT_DIAGNOSTIC_WINDOW_DAYS,
    AUDIT_RETENTION_DAYS,
    SecurityAuditService,
)
from engine.schemas.api_responses import (
    DiagnosticLogsClearedResponse,
    DiagnosticLogsResponse,
    SecurityAuditClearedResponse,
)

router = APIRouter()


@router.get("/diagnostics/logs", response_model=DiagnosticLogsResponse)
def get_diagnostic_logs(
    max_lines: int = Query(DEFAULT_MAX_LINES, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    result = collect_diagnostic_logs(
        max_lines=max_lines,
        sources=diagnostic_log_paths(),
    )
    result["security_audit"] = {
        "retention_days": AUDIT_RETENTION_DAYS,
        "export_window_days": AUDIT_DIAGNOSTIC_WINDOW_DAYS,
        "max_records": AUDIT_DIAGNOSTIC_MAX_RECORDS,
        "records": SecurityAuditService(db).diagnostic_export(),
    }
    return result


@router.post(
    "/diagnostics/logs/clear",
    response_model=DiagnosticLogsClearedResponse,
)
def clear_diagnostic_logs() -> dict[str, object]:
    cleared: list[str] = []
    for name, path in diagnostic_log_paths():
        if path.exists():
            if clear_diagnostic_log_source(path):
                cleared.append(name)
    return {"cleared": len(cleared) > 0, "sources_cleared": cleared}


@router.post(
    "/diagnostics/security-audit/clear",
    response_model=SecurityAuditClearedResponse,
)
def clear_security_audit(
    confirm_text: str = Body(embed=True),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if confirm_text != "清空安全审计":
        raise HTTPException(status_code=400, detail={"code": "AUDIT_CLEAR_CONFIRMATION_REQUIRED"})
    begin_agent_write(db)
    deleted = SecurityAuditService(db).clear()
    db.commit()
    return {"cleared": True, "records_deleted": deleted}
