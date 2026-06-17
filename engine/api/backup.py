# -*- coding: utf-8 -*-
"""
DBFox 备份与恢复 API 路由模块 (Backup & Restore Router)
------------------------------------------------------
这个模块定义了所有与数据库备份、覆盖恢复相关的 RESTful Web API 接口。
它演示了如何与 SQLAlchemy 数据库会话 (Session) 交互，利用 Pydantic 模型进行请求体校验，
以及通过双重因子确认保护（Two-Phase Confirmation）机制执行高风险操作（数据库覆盖恢复）。
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from engine.backup import create_backup, execute_restore, precheck_restore
from engine.db import get_db
from engine.errors import DBFoxError
from engine.models import BackupRecord, DataSource
from engine.schemas import BackupCreateRequest
from engine.schema_sync import sync_schema
from engine.policy.engine import PolicyEngine

# 获取当前模块的日志记录器
logger = logging.getLogger("dbfox.api.backup")

# 创建一个 API 路由组 (APIRouter)
# 在 FastAPI 中，我们将不同业务模块的接口拆分到各个路由文件中，然后使用 APIRouter 独立配置，最后统一挂载到主应用上。
router = APIRouter()


def _backup_to_dict(record: BackupRecord) -> dict[str, Any]:
    """
    辅助函数：将 SQLAlchemy 数据库模型对象 (BackupRecord) 转换为标准的字典格式，以便 FastAPI 序列化为 JSON 返回给前端。
    
    Python & Pydantic 知识点:
      - `record.started_at.isoformat()`：在 Python 中，`datetime` 对象需要被转换为符合 ISO-8601 标准的字符串（如 "2026-05-26T21:30:00"），才能通过 JSON 传输。
      - `dict[str, Any]`：表示这是一个字典，其键是字符串，值可以是任意类型。
    """
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
        # 调用核心备份方法
        record = create_backup(db, req.datasource_id, req.label, allow_fallback=req.allow_fallback)
        db.commit()      # 提交事务
        db.refresh(record)  # 刷新模型
        return _backup_to_dict(record)
    except DBFoxError as exc:
        db.rollback()    # 发生业务错误，回滚事务
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        db.rollback()    # 发生未知错误，回滚事务
        logger.exception("创建备份失败")
        raise HTTPException(status_code=500, detail={"code": "BACKUP_FAILED", "message": f"创建备份失败: {exc}"})


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
        raise HTTPException(status_code=404, detail={"code": "BACKUP_NOT_FOUND", "message": "未找到指定的备份记录"})
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
        raise HTTPException(status_code=404, detail={"code": "BACKUP_NOT_FOUND", "message": "备份不存在"})
    return precheck_restore(record)


# =========================================================================
# 接口 5: 执行备份恢复（覆盖目标数据库的高风险操作） (POST)
# =========================================================================
@router.post("/backups/{backup_id}/restore")
def api_restore_backup(
    backup_id: str,
    allow_fallback: bool = Query(default=True),
    confirm_token: str | None = Query(default=None),
    confirm_text: str | None = Query(default=None),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    执行备份恢复 (高风险覆写操作)
    
    为了绝对防范误操作，该接口实现了双因子令牌验证 (Two-Phase Confirmation)：
    1. 第一次调用：不带 `confirm_token`。接口拦截并自动生成一个一次性确认令牌 `confirm_token` 返回给前端，
       并提示警告语，要求用户必须手动输入“数据源名称”以表确认。
    2. 第二次调用：带上 `confirm_token` 和用户输入的 `confirm_text`。后端验证比对通过后才真正执行物理恢复。
    """
    # 1. 查找备份记录
    record = db.query(BackupRecord).filter(BackupRecord.id == backup_id).first()
    if not record:
        raise HTTPException(status_code=404, detail={"code": "BACKUP_NOT_FOUND", "message": "备份记录不存在"})

    # 2. 查找关联的数据源信息
    datasource = db.query(DataSource).filter(DataSource.id == record.datasource_id).first()
    if not datasource:
        raise HTTPException(status_code=404, detail={"code": "DATASOURCE_NOT_FOUND", "message": "关联的数据源不存在"})

    # 3. 🔒 强制安全合规校验：例如禁止在生产环境中执行数据库恢复还原
    try:
        PolicyEngine.enforce_restore_policy(datasource)
    except DBFoxError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})

    # 4. 🔒 检查是否跳过二次确认（通常开发测试环境或自动化集成中可以配置绕过）
    from engine.policy import confirmation_bypass_enabled, confirmation_manager
    if not confirmation_bypass_enabled():
        expected_details = {"backup_id": backup_id}
        
        # 4.1 阶段一：尚未发起确认令牌。生成令牌并拦截返回
        if not confirm_token:
            token = confirmation_manager.create_confirmation(
                datasource_id=str(record.datasource_id),
                action="restore_backup",
                details=expected_details,
                expected_confirm_text=str(datasource.name)  # 期望用户输入的文本是该数据源的真实名称
            )
            return {
                "success": False,
                "requires_confirmation": True,
                "confirm_token": token,
                "impact_summary": f"⚠️ 警告：您即将对数据源 '{datasource.name}' 执行备份恢复（覆盖还原）！\n\n该操作会覆盖目标数据库的所有当前数据，并可能导致现有修改被覆盖丢失！请输入数据源名称以确认执行。",
                "expected_confirm_text": datasource.name
            }
        # 4.2 阶段二：用户带上了确认令牌与输入文本。进行一致性及有效性核对
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

    # 5. 二次确认通过，执行底层真实的恢复逻辑
    try:
        res = execute_restore(db, backup_id, allow_fallback=allow_fallback)
        db.commit()  # 物理恢复完成，更新本地备份记录的状态为已成功，并提交本地事务
        
        # 恢复完成后，在后台异步触发一次表结构元数据同步，使 DBFox 里的元数据与实际数据库保持一致
        try:
            sync_schema(db, res["datasource_id"])
            db.commit()
        except Exception:
            logger.exception("还原数据库后尝试刷新同步元数据时失败")
            
        return res
    except DBFoxError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        db.rollback()
        logger.exception("数据库覆盖还原失败")
        raise HTTPException(status_code=500, detail={"code": "RESTORE_FAILED", "message": f"数据库覆写恢复失败: {exc}"})

