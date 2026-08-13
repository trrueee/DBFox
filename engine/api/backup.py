"""Controlled backup creation, inspection, and isolated restore routes."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from engine.app.safe_errors import (
    FixedErrorCode,
    fixed_error_message,
)
from engine.backup import create_backup, execute_restore, precheck_restore, safe_backup_record_path
from engine.db import get_db
from engine.errors import NotFoundError
from engine.models import BackupRecord
from engine.schemas import BackupCreateRequest
from engine.schemas.backup import (
    BackupResponse,
    BackupRestoreRequest,
    RestoreOperationResponse,
)
from engine.schemas.api_responses import BackupPrecheckResponse

router = APIRouter()


def _backup_to_dict(record: BackupRecord) -> dict[str, Any]:
    payload = BackupResponse.model_validate(record).model_dump(mode="json")
    payload["file_path"] = safe_backup_record_path(record.file_path)
    if payload.get("error_message"):
        payload["error_message"] = fixed_error_message(FixedErrorCode.BACKUP_OPERATION_FAILED)
    return payload


@router.get("/projects/{project_id}/backups", response_model=list[BackupResponse])
def api_list_project_backups(
    project_id: str,
    datasource_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List backups owned by one project, optionally narrowed to a datasource."""
    from engine.projects.service import resolve_project_id
    resolve_project_id(db, project_id)

    query = db.query(BackupRecord).filter(BackupRecord.project_id == project_id)
    if datasource_id:
        query = query.filter(BackupRecord.datasource_id == datasource_id)
    records = query.order_by(BackupRecord.created_at.desc()).all()
    return [_backup_to_dict(record) for record in records]


@router.post("/backups", response_model=BackupResponse)
def api_create_backup(req: BackupCreateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Create and persist a logical backup."""
    try:
        record = create_backup(db, req.datasource_id, req.label)
        return _backup_to_dict(record)
    except Exception:
        # create_backup already committed the failed status — no rollback.
        raise


@router.get("/backups/{backup_id}", response_model=BackupResponse)
def api_get_backup(backup_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Return one backup record."""
    record = db.query(BackupRecord).filter(BackupRecord.id == backup_id).first()
    if not record:
        raise NotFoundError("未找到指定的备份记录", "BACKUP_NOT_FOUND")
    return _backup_to_dict(record)


@router.post(
    "/backups/{backup_id}/restore-precheck",
    response_model=BackupPrecheckResponse,
)
def api_restore_precheck(backup_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Validate a backup before isolated restore."""
    record = db.query(BackupRecord).filter(BackupRecord.id == backup_id).first()
    if not record:
        raise NotFoundError("备份不存在", "BACKUP_NOT_FOUND")
    return precheck_restore(record)


@router.post("/backups/{backup_id}/restore", response_model=RestoreOperationResponse)
def api_restore_backup(
    backup_id: str,
    req: BackupRestoreRequest,
    db: Session = Depends(get_db),
) -> RestoreOperationResponse:
    """Restore to a new database and switch only after validation and generation CAS."""

    operation = execute_restore(
        db,
        backup_id,
        expected_datasource_generation=req.expected_datasource_generation,
    )
    return RestoreOperationResponse.model_validate(operation)

