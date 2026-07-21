# -*- coding: utf-8 -*-
"""
DBFox 备份 API 路由模块 (Backup Router)
-----------------------------------------
这个模块定义受控的备份创建、查询和恢复预检 API。逻辑备份不能原子覆盖现有
数据库，因此恢复端点在具备隔离目标与可审计切换流程前一律拒绝执行。
"""

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

# 创建一个 API 路由组 (APIRouter)
# 在 FastAPI 中，我们将不同业务模块的接口拆分到各个路由文件中，然后使用 APIRouter 独立配置，最后统一挂载到主应用上。
router = APIRouter()


def _backup_to_dict(record: BackupRecord) -> dict[str, Any]:
    payload = BackupResponse.model_validate(record).model_dump(mode="json")
    payload["file_path"] = safe_backup_record_path(record.file_path)
    if payload.get("error_message"):
        payload["error_message"] = fixed_error_message(FixedErrorCode.BACKUP_OPERATION_FAILED)
    return payload


# =========================================================================
# 接口 1: 获取某个项目下的所有备份记录列表 (GET)
# =========================================================================
@router.get("/projects/{project_id}/backups")
def api_list_project_backups(
    project_id: str,
    datasource_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """
    获取备份记录列表
    
    FastAPI 知识点:
      - `@router.get("/...")`：声明这是一个 HTTP GET 请求路由，路径中的 `{project_id}` 是路径参数，会被自动映射到函数的 `project_id: str` 参数中。
      - `datasource_id: str | None = Query(default=None)`：声明这是一个 URL 查询参数（如 ?datasource_id=xxxx）。
        如果前端没有传这个参数，其值默认为 None。
      - `db: Session = Depends(get_db)`：【依赖注入】系统。这是 FastAPI 的核心看家本领！
        FastAPI 会在接收到请求时，自动执行 `Depends` 里的 `get_db` 函数，获取一个 SQLite 数据库连接会话，注入给本函数的参数 `db`。
        当请求结束时，FastAPI 还会自动清理并关闭该连接会话（我们在 db.py 中写的 `yield db` 和 `finally` 保证了这一行为）。
      - `db.query(BackupRecord)`：使用 SQLAlchemy 的 ORM 查询语法，表示从备份记录表开始检索。
      - `.filter(...)`：SQL SQLAlchemy 的 WHERE 条件子句。
      - `.order_by(BackupRecord.created_at.desc())`：按创建时间倒序排列。
      - `.all()`：立即执行 SQL 查询并返回一个 Python 列表。
    """
    # 验证项目 ID 是否合法存在
    from engine.projects.service import resolve_project_id
    resolve_project_id(db, project_id)
    
    # 构造查询语句并追加过滤条件
    query = db.query(BackupRecord).filter(BackupRecord.project_id == project_id)
    if datasource_id:
        query = query.filter(BackupRecord.datasource_id == datasource_id)
        
    # 执行查询
    records = query.order_by(BackupRecord.created_at.desc()).all()
    
    # 列表推导式：快速将所有数据库记录对象转换成用于 JSON 返回的字典列表
    return [_backup_to_dict(record) for record in records]


# =========================================================================
# 接口 2: 创建新的数据库备份 (POST)
# =========================================================================
@router.post("/backups")
def api_create_backup(req: BackupCreateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    创建数据库备份
    
    FastAPI 知识点:
      - `req: BackupCreateRequest`：前端传过来的请求体（JSON 格式）。
        FastAPI 发现它是一个 Pydantic 模型 (BackupCreateRequest)，就会自动将 JSON 解析、校验并绑定到 `req` 对象中！
        如果数据格式不合法，FastAPI 会自动拦截并返回 422 格式错误响应。
      - `db.commit()`：提交当前的数据库事务，使备份记录的写入真正落盘。
      - `db.refresh(record)`：重新加载该模型对象，从而拿到由 SQLite 自动生成的 ID 和默认的时间值等。
      - `db.rollback()`：如果操作中发生异常，立刻回滚未提交的事务，确保数据库的一致性。
      - `raise HTTPException(...)`：抛出 FastAPI 的 HTTP 错误异常，以返回指定的 HTTP 状态码（如 400 或 500）和错误详情。
    """
    try:
        record = create_backup(db, req.datasource_id, req.label)
        db.commit()
        db.refresh(record)
        return _backup_to_dict(record)
    except Exception:
        # create_backup already committed the failed status — no rollback.
        raise


# =========================================================================
# 接口 3: 根据备份 ID 获取单条备份记录详情 (GET)
# =========================================================================
@router.get("/backups/{backup_id}")
def api_get_backup(backup_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    查询单条备份详情
    
    SQLAlchemy 知识点:
      - `.filter(BackupRecord.id == backup_id).first()`：查找符合条件的第一条记录。如果没找到，返回 None。
    """
    record = db.query(BackupRecord).filter(BackupRecord.id == backup_id).first()
    if not record:
        raise NotFoundError("未找到指定的备份记录", "BACKUP_NOT_FOUND")
    return _backup_to_dict(record)


# =========================================================================
# 接口 4: 执行备份恢复前的安全预检 (POST)
# =========================================================================
@router.post("/backups/{backup_id}/restore-precheck")
def api_restore_precheck(backup_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    数据库恢复预检
    
    检查备份文件是否存在、大小是否正常、数据库版本是否兼容等。
    """
    record = db.query(BackupRecord).filter(BackupRecord.id == backup_id).first()
    if not record:
        raise NotFoundError("备份不存在", "BACKUP_NOT_FOUND")
    return precheck_restore(record)


# =========================================================================
# 接口 5: 隔离恢复与原子切换 (POST)
# =========================================================================
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

