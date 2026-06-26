from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from engine.crypto import encrypt_password
from engine.datasource import build_mysql_ssl_params, build_postgres_ssl_params, test_connection
from engine.db import get_db
from engine.errors import DBFoxError, DataSourceConnectionError, NotFoundError
from engine.models import DataSource
from engine.schemas.datasource import (
    DataSourceCreateRequest,
    DataSourceResponse,
    DataSourceTestRequest,
    DataSourceUpdateRequest,
)
from engine.api.datasources.common import (
    datasource_to_dict,
    replace_secret_if_present,
    set_model_attr,
)

logger = logging.getLogger("dbfox.api.datasources.crud")
router = APIRouter()


class DatasourceDeleteConfirmRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    confirm_token: str | None = Field(default=None, min_length=1, max_length=256)
    confirm_text: str | None = Field(default=None, min_length=1, max_length=256)


@router.post("/datasources/test")
def api_test_connection(req: DataSourceTestRequest) -> dict[str, Any]:
    try:
        return test_connection(req.model_dump())
    except DBFoxError:
        raise
    except Exception as exc:
        logger.exception("Connection test failed")
        raise DataSourceConnectionError(f"数据库连接测试失败: {str(exc)}") from exc


@router.post("/datasources", response_model=DataSourceResponse)
def api_create_datasource(
    req: DataSourceCreateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        from engine.projects.service import resolve_project_id

        config = req.model_dump()
        if req.db_type == "mysql":
            build_mysql_ssl_params(config)
        elif req.db_type == "postgresql":
            build_postgres_ssl_params(config)
        project_id = resolve_project_id(db, req.project_id)
        cipher, nonce = encrypt_password(req.password or "")

        ssh_password_ciphertext = ""
        ssh_password_nonce = ""
        if req.ssh_password:
            ssh_password_ciphertext, ssh_password_nonce = encrypt_password(req.ssh_password)

        ssh_pkey_passphrase_ciphertext = ""
        ssh_pkey_passphrase_nonce = ""
        if req.ssh_pkey_passphrase:
            ssh_pkey_passphrase_ciphertext, ssh_pkey_passphrase_nonce = encrypt_password(
                req.ssh_pkey_passphrase
            )

        datasource = DataSource(
            id=str(uuid.uuid4()),
            project_id=project_id,
            name=req.name,
            db_type=req.db_type,
            host=req.host,
            port=req.port,
            database_name=req.database_name,
            username=req.username,
            password_ciphertext=cipher,
            password_nonce=nonce,
            ssh_enabled=req.ssh_enabled,
            ssh_host=req.ssh_host,
            ssh_port=req.ssh_port,
            ssh_username=req.ssh_username,
            ssh_password_ciphertext=ssh_password_ciphertext,
            ssh_password_nonce=ssh_password_nonce,
            ssh_pkey_path=req.ssh_pkey_path,
            ssh_pkey_passphrase_ciphertext=ssh_pkey_passphrase_ciphertext,
            ssh_pkey_passphrase_nonce=ssh_pkey_passphrase_nonce,
            ssl_enabled=req.ssl_enabled,
            ssl_ca_path=req.ssl_ca_path,
            ssl_cert_path=req.ssl_cert_path,
            ssl_key_path=req.ssl_key_path,
            ssl_verify_identity=req.ssl_verify_identity,
            connection_mode=req.connection_mode,
            is_read_only=req.is_read_only,
            env=req.env,
            status="active",
        )
        db.add(datasource)
        db.commit()
        db.refresh(datasource)
        return datasource_to_dict(datasource)
    except Exception:
        db.rollback()
        raise


@router.get("/datasources", response_model=list[DataSourceResponse])
def api_list_datasources(
    project_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    from engine.projects.service import get_or_create_default_project

    _project, created = get_or_create_default_project(db)
    if created:
        db.commit()

    query = db.query(DataSource)
    if project_id:
        query = query.filter(DataSource.project_id == project_id)
    return [datasource_to_dict(ds) for ds in query.all()]


@router.put("/datasources/{id}", response_model=DataSourceResponse)
def api_update_datasource(
    id: str,
    req: DataSourceUpdateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    datasource = db.query(DataSource).filter(DataSource.id == id).first()
    if not datasource:
        raise NotFoundError("数据源不存在")

    try:
        config = req.model_dump()
        if req.db_type == "mysql":
            build_mysql_ssl_params(config)
        elif req.db_type == "postgresql":
            build_postgres_ssl_params(config)

        set_model_attr(datasource, "name", req.name)
        set_model_attr(datasource, "db_type", req.db_type)
        set_model_attr(datasource, "host", req.host)
        set_model_attr(datasource, "port", req.port)
        set_model_attr(datasource, "database_name", req.database_name)
        set_model_attr(datasource, "username", req.username)
        set_model_attr(datasource, "connection_mode", req.connection_mode)
        set_model_attr(datasource, "is_read_only", req.is_read_only)
        set_model_attr(datasource, "env", req.env)
        set_model_attr(datasource, "ssh_enabled", req.ssh_enabled)
        set_model_attr(datasource, "ssh_host", req.ssh_host)
        set_model_attr(datasource, "ssh_port", req.ssh_port)
        set_model_attr(datasource, "ssh_username", req.ssh_username)
        set_model_attr(datasource, "ssh_pkey_path", req.ssh_pkey_path)
        set_model_attr(datasource, "ssl_enabled", req.ssl_enabled)
        set_model_attr(datasource, "ssl_ca_path", req.ssl_ca_path)
        set_model_attr(datasource, "ssl_cert_path", req.ssl_cert_path)
        set_model_attr(datasource, "ssl_key_path", req.ssl_key_path)
        set_model_attr(datasource, "ssl_verify_identity", req.ssl_verify_identity)

        replace_secret_if_present(datasource, req.password, "password_ciphertext", "password_nonce")
        replace_secret_if_present(datasource, req.ssh_password, "ssh_password_ciphertext", "ssh_password_nonce")
        replace_secret_if_present(
            datasource,
            req.ssh_pkey_passphrase,
            "ssh_pkey_passphrase_ciphertext",
            "ssh_pkey_passphrase_nonce",
        )

        db.commit()
        db.refresh(datasource)
        return datasource_to_dict(datasource)
    except Exception:
        db.rollback()
        raise


@router.delete("/datasources/{id}")
def api_delete_datasource(
    id: str,
    confirm: DatasourceDeleteConfirmRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    datasource = db.query(DataSource).filter(DataSource.id == id).first()
    if not datasource:
        raise NotFoundError("数据源不存在")

    from engine.policy import confirmation_bypass_enabled, confirmation_manager

    if not confirmation_bypass_enabled():
        expected_details = {"datasource_id": id}
        confirm_token = confirm.confirm_token if confirm else None
        confirm_text = confirm.confirm_text if confirm else None
        if not confirm_token:
            token = confirmation_manager.create_confirmation(
                datasource_id=id,
                action="delete_datasource",
                details=expected_details,
                expected_confirm_text=str(datasource.name),
            )
            return {
                "success": False,
                "requires_confirmation": True,
                "confirm_token": token,
                "impact_summary": (
                    f"⚠️ 警告：您即将在系统中删除数据源 '{datasource.name}'！\n\n"
                    "该操作会清空本地保存的所有相关 Schema 结构和元数据历史缓存！请输入数据源名称以确认执行。"
                ),
                "expected_confirm_text": str(datasource.name),
            }

        is_valid, err_msg = confirmation_manager.validate_and_consume(
            confirm_token,
            confirm_text or "",
            expected_action="delete_datasource",
            expected_datasource_id=id,
            expected_details=expected_details,
        )
        if not is_valid:
            raise DBFoxError(message=err_msg, code="CONFIRMATION_FAILED")

    try:
        from engine.datasource import close_active_tunnel
        from engine.sql.pool_registry import get_pool_registry

        close_active_tunnel(id)
        get_pool_registry().dispose_datasource(id)
        db.delete(datasource)
        db.commit()
        return {"success": True, "message": "数据源已删除"}
    except Exception:
        db.rollback()
        raise


@router.post("/datasources/{id}/release")
def api_release_datasource(id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        from engine.sql.pool_registry import get_pool_registry

        get_pool_registry().dispose_datasource(id)
        return {"success": True, "message": "数据源连接池已成功释放"}
    except Exception:
        logger.exception("Failed to release datasource connection pool")
        raise
