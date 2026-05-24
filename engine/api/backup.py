import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from engine.backup import create_backup, execute_restore, precheck_restore
from engine.db import get_db
from engine.errors import DataBoxError
from engine.models import BackupRecord, DataSource
from engine.schemas import BackupCreateRequest
from engine.schema_sync import sync_schema
from engine.policy.engine import PolicyEngine

logger = logging.getLogger("databox.api.backup")
router = APIRouter()


def _backup_to_dict(record: BackupRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "project_id": record.project_id,
        "datasource_id": record.datasource_id,
        "environment_id": record.environment_id,
        "label": record.label or "",
        "backup_type": record.backup_type,
        "status": record.status,
        "file_path": record.file_path,
        "file_size_bytes": record.file_size_bytes,
        "checksum_sha256": record.checksum_sha256,
        "started_at": record.started_at.isoformat() if record.started_at else None,
        "completed_at": record.completed_at.isoformat() if record.completed_at else None,
        "duration_ms": record.duration_ms,
        "error_message": record.error_message,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


def _resolve_project_id(db: Session, project_id: str | None) -> str:
    from engine.api.projects import _resolve_project_id as resolve
    return resolve(db, project_id)


@router.get("/projects/{project_id}/backups")
def api_list_project_backups(
    project_id: str,
    datasource_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    _resolve_project_id(db, project_id)
    query = db.query(BackupRecord).filter(BackupRecord.project_id == project_id)
    if datasource_id:
        query = query.filter(BackupRecord.datasource_id == datasource_id)
    records = query.order_by(BackupRecord.created_at.desc()).all()
    return [_backup_to_dict(record) for record in records]


@router.post("/backups")
def api_create_backup(req: BackupCreateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        record = create_backup(db, req.datasource_id, req.label, allow_fallback=req.allow_fallback)
        db.commit()
        db.refresh(record)
        return _backup_to_dict(record)
    except DataBoxError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        db.rollback()
        logger.exception("Backup failed")
        raise HTTPException(status_code=500, detail={"code": "BACKUP_FAILED", "message": f"Backup failed: {exc}"})


@router.get("/backups/{backup_id}")
def api_get_backup(backup_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    record = db.query(BackupRecord).filter(BackupRecord.id == backup_id).first()
    if not record:
        raise HTTPException(status_code=404, detail={"code": "BACKUP_NOT_FOUND", "message": "Backup not found"})
    return _backup_to_dict(record)


@router.post("/backups/{backup_id}/restore-precheck")
def api_restore_precheck(backup_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    record = db.query(BackupRecord).filter(BackupRecord.id == backup_id).first()
    if not record:
        raise HTTPException(status_code=404, detail={"code": "BACKUP_NOT_FOUND", "message": "Backup not found"})
    return precheck_restore(record)


@router.post("/backups/{backup_id}/restore")
def api_restore_backup(
    backup_id: str,
    allow_fallback: bool = Query(default=True),
    confirm_token: str | None = Query(default=None),
    confirm_text: str | None = Query(default=None),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    record = db.query(BackupRecord).filter(BackupRecord.id == backup_id).first()
    if not record:
        raise HTTPException(status_code=404, detail={"code": "BACKUP_NOT_FOUND", "message": "备份记录不存在"})

    datasource = db.query(DataSource).filter(DataSource.id == record.datasource_id).first()
    if not datasource:
        raise HTTPException(status_code=404, detail={"code": "DATASOURCE_NOT_FOUND", "message": "关联的数据源不存在"})

    # 🔒 Policy Engine Enforcement for database restore
    try:
        PolicyEngine.enforce_restore_policy(datasource)
    except DataBoxError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})

    # 🔒 Two-Phase confirmation check for dangerous database restores
    from engine.policy import confirmation_bypass_enabled, confirmation_manager
    if not confirmation_bypass_enabled():
        expected_details = {"backup_id": backup_id}
        if not confirm_token:
            token = confirmation_manager.create_confirmation(
                datasource_id=str(record.datasource_id),
                action="restore_backup",
                details=expected_details,
                expected_confirm_text=datasource.name
            )
            return {
                "success": False,
                "requires_confirmation": True,
                "confirm_token": token,
                "impact_summary": f"⚠️ 警告：您即将对数据源 '{datasource.name}' 执行备份恢复（覆盖还原）！\n\n该操作会覆盖目标数据库的所有当前数据，并可能导致现有修改被覆盖丢失！请输入数据源名称以确认执行。",
                "expected_confirm_text": datasource.name
            }
        else:
            is_valid, err_msg = confirmation_manager.validate_and_consume(
                confirm_token,
                confirm_text or "",
                expected_action="restore_backup",
                expected_datasource_id=str(record.datasource_id),
                expected_details=expected_details
            )
            if not is_valid:
                raise HTTPException(status_code=400, detail={"code": "CONFIRMATION_FAILED", "message": err_msg})

    try:
        res = execute_restore(db, backup_id, allow_fallback=allow_fallback)
        db.commit()
        
        # Trigger schema sync in background so our metadata is fresh
        try:
            sync_schema(db, res["datasource_id"])
            db.commit()
        except Exception:
            logger.exception("Failed to sync schema after database restore")
            
        return res
    except DataBoxError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        db.rollback()
        logger.exception("Restore failed")
        raise HTTPException(status_code=500, detail={"code": "RESTORE_FAILED", "message": f"Database restore failed: {exc}"})
