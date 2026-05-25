import logging
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from engine.db import get_db
from engine.crypto import decrypt_password, encrypt_password
from engine.datasource import build_mysql_ssl_params, is_demo_db, test_connection
from engine.errors import DataBoxError
from engine.models import (
    DEFAULT_PROJECT_ID,
    DataSource,
    SchemaTable,
)
from engine.schemas import DataSourceTestRequest, DataSourceCreateRequest
from engine.schema_sync import _guess_module_tag, build_er_diagram_data, sync_schema

logger = logging.getLogger("databox.api.datasources")
router = APIRouter()


def _json_list_or_empty(value: Any) -> list[str]:
    if not value:
        return []
    try:
        decoded = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    return [str(item) for item in decoded]


def _datasource_to_dict(ds: DataSource) -> dict[str, Any]:
    return {
        "id": ds.id,
        "project_id": ds.project_id or DEFAULT_PROJECT_ID,
        "environment_id": ds.environment_id,
        "name": ds.name,
        "db_type": ds.db_type or "mysql",
        "host": ds.host,
        "port": ds.port,
        "database_name": ds.database_name,
        "username": ds.username,
        "connection_mode": ds.connection_mode,
        "is_read_only": bool(ds.is_read_only),
        "env": ds.env or "dev",
        "status": ds.status,
        "ssh_enabled": bool(ds.ssh_enabled),
        "ssh_host": ds.ssh_host or "",
        "ssh_port": ds.ssh_port or 22,
        "ssh_username": ds.ssh_username or "",
        "ssh_pkey_path": ds.ssh_pkey_path or "",
        "ssl_enabled": bool(ds.ssl_enabled),
        "ssl_ca_path": ds.ssl_ca_path or "",
        "ssl_cert_path": ds.ssl_cert_path or "",
        "ssl_key_path": ds.ssl_key_path or "",
        "ssl_verify_identity": bool(ds.ssl_verify_identity),
        "last_test_at": ds.last_test_at.isoformat() if ds.last_test_at else None,
        "last_test_status": ds.last_test_status,
        "last_test_error": ds.last_test_error,
        "last_test_latency_ms": ds.last_test_latency_ms,
        "last_test_readonly": ds.last_test_readonly,
        "last_test_server_version": ds.last_test_server_version,
        "last_test_tables_count": ds.last_test_tables_count,
        "last_test_warnings": _json_list_or_empty(ds.last_test_warnings),
        "last_sync_at": ds.last_sync_at.isoformat() if ds.last_sync_at else None,
        "last_sync_status": ds.last_sync_status,
        "last_sync_error": ds.last_sync_error,
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
    }


def _decrypt_optional(ciphertext: str | None, nonce: str | None) -> str | None:
    if not ciphertext or not nonce:
        return None
    return decrypt_password(ciphertext, nonce)


def _datasource_to_health_config(ds: DataSource) -> dict[str, Any]:
    host = str(ds.host or "")
    database_name = str(ds.database_name or "")
    db_type = str(ds.db_type or "mysql")
    password = ""

    if db_type != "sqlite" and not is_demo_db(host, database_name):
        password = decrypt_password(str(ds.password_ciphertext), str(ds.password_nonce))

    return {
        "db_type": db_type,
        "host": host,
        "port": int(ds.port or 0),
        "database_name": database_name,
        "username": str(ds.username or ""),
        "password": password,
        "ssh_enabled": bool(ds.ssh_enabled),
        "ssh_host": ds.ssh_host,
        "ssh_port": int(ds.ssh_port or 22),
        "ssh_username": ds.ssh_username,
        "ssh_password": _decrypt_optional(
            cast(str | None, ds.ssh_password_ciphertext),
            cast(str | None, ds.ssh_password_nonce),
        ),
        "ssh_pkey_path": ds.ssh_pkey_path,
        "ssh_pkey_passphrase": _decrypt_optional(
            cast(str | None, ds.ssh_pkey_passphrase_ciphertext),
            cast(str | None, ds.ssh_pkey_passphrase_nonce),
        ),
        "ssl_enabled": bool(ds.ssl_enabled),
        "ssl_ca_path": ds.ssl_ca_path,
        "ssl_cert_path": ds.ssl_cert_path,
        "ssl_key_path": ds.ssl_key_path,
        "ssl_verify_identity": bool(ds.ssl_verify_identity),
    }


def _persist_health_success(ds: DataSource, result: dict[str, Any], latency_ms: int, checked_at: datetime) -> None:
    warnings = [str(item) for item in result.get("warnings", [])]
    setattr(ds, "last_test_at", checked_at)
    setattr(ds, "last_test_status", "success")
    setattr(ds, "last_test_error", None)
    setattr(ds, "last_test_latency_ms", latency_ms)
    setattr(ds, "last_test_readonly", bool(result.get("readonly", False)))
    setattr(ds, "last_test_server_version", str(result.get("serverVersion") or ""))
    setattr(ds, "last_test_tables_count", int(result.get("tablesCount") or 0))
    setattr(ds, "last_test_warnings", json.dumps(warnings, ensure_ascii=False))


def _persist_health_failure(ds: DataSource, message: str, latency_ms: int, checked_at: datetime) -> None:
    setattr(ds, "last_test_at", checked_at)
    setattr(ds, "last_test_status", "failed")
    setattr(ds, "last_test_error", message)
    setattr(ds, "last_test_latency_ms", latency_ms)
    setattr(ds, "last_test_readonly", None)
    setattr(ds, "last_test_server_version", None)
    setattr(ds, "last_test_tables_count", None)
    setattr(ds, "last_test_warnings", json.dumps([], ensure_ascii=False))


def _resolve_project_id(db: Session, project_id: str | None) -> str:
    from engine.api.projects import _resolve_project_id as resolve
    return resolve(db, project_id)


@router.post("/datasources/test")
def api_test_connection(req: DataSourceTestRequest) -> dict[str, Any]:
    try:
        return test_connection(req.model_dump())
    except DataBoxError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        logger.exception("Connection test failed")
        raise HTTPException(status_code=400, detail={"code": "CONNECTION_FAILED", "message": "数据库连接测试失败，请检查连接配置。"})


@router.post("/datasources")
def api_create_datasource(req: DataSourceCreateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        if req.db_type == "mysql":
            build_mysql_ssl_params(req.model_dump())
        project_id = _resolve_project_id(db, req.project_id)
        cipher, nonce = encrypt_password(req.password or "")

        ssh_password_ciphertext = ""
        ssh_password_nonce = ""
        if req.ssh_password:
            ssh_password_ciphertext, ssh_password_nonce = encrypt_password(req.ssh_password)

        ssh_pkey_passphrase_ciphertext = ""
        ssh_pkey_passphrase_nonce = ""
        if req.ssh_pkey_passphrase:
            ssh_pkey_passphrase_ciphertext, ssh_pkey_passphrase_nonce = encrypt_password(req.ssh_pkey_passphrase)

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
        return _datasource_to_dict(datasource)
    except HTTPException:
        db.rollback()
        raise
    except DataBoxError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to create datasource")
        raise HTTPException(
            status_code=500,
            detail={"code": "DATASOURCE_CREATE_FAILED", "message": "创建数据源失败，请稍后重试。"},
        )


@router.get("/datasources")
def api_list_datasources(
    project_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    from engine.api.projects import _get_or_create_default_project
    _get_or_create_default_project(db)
    db.commit()

    query = db.query(DataSource)
    if project_id:
        query = query.filter(DataSource.project_id == project_id)
    return [_datasource_to_dict(ds) for ds in query.all()]


@router.post("/datasources/{id}/health")
def api_check_datasource_health(id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    datasource = db.query(DataSource).filter(DataSource.id == id).first()
    if not datasource:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "数据源不存在"})

    started = time.perf_counter()
    checked_at = datetime.now(UTC)
    try:
        result = test_connection(_datasource_to_health_config(datasource))
        latency_ms = int((time.perf_counter() - started) * 1000)
        _persist_health_success(datasource, result, latency_ms, checked_at)
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
            "datasource": _datasource_to_dict(datasource),
        }
    except DataBoxError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        _persist_health_failure(datasource, str(exc), latency_ms, checked_at)
        db.commit()
        db.refresh(datasource)
        return {
            "ok": False,
            "status": "failed",
            "checkedAt": datasource.last_test_at.isoformat() if datasource.last_test_at else None,
            "latencyMs": latency_ms,
            "warnings": [],
            "message": str(exc),
            "datasource": _datasource_to_dict(datasource),
        }
    except Exception as exc:
        logger.exception("Datasource health check failed")
        latency_ms = int((time.perf_counter() - started) * 1000)
        message = "数据库连接健康检查失败，请检查连接配置。"
        _persist_health_failure(datasource, message, latency_ms, checked_at)
        db.commit()
        db.refresh(datasource)
        return {
            "ok": False,
            "status": "failed",
            "checkedAt": datasource.last_test_at.isoformat() if datasource.last_test_at else None,
            "latencyMs": latency_ms,
            "warnings": [],
            "message": message,
            "datasource": _datasource_to_dict(datasource),
        }


@router.delete("/datasources/{id}")
def api_delete_datasource(
    id: str,
    confirm_token: str | None = Query(default=None),
    confirm_text: str | None = Query(default=None),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    datasource = db.query(DataSource).filter(DataSource.id == id).first()
    if not datasource:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "数据源不存在"})

    # 🔒 Two-Phase confirmation check for deleting datasources
    from engine.policy import confirmation_bypass_enabled, confirmation_manager
    if not confirmation_bypass_enabled():
        expected_details = {"datasource_id": id}
        if not confirm_token:
            token = confirmation_manager.create_confirmation(
                datasource_id=id,
                action="delete_datasource",
                details=expected_details,
                expected_confirm_text=str(datasource.name)
            )
            return {
                "success": False,
                "requires_confirmation": True,
                "confirm_token": token,
                "impact_summary": f"⚠️ 警告：您即将在系统中删除数据源 '{datasource.name}'！\n\n该操作会清空本地保存的所有相关 Schema 结构和元数据历史缓存！请输入数据源名称以确认执行。",
                "expected_confirm_text": str(datasource.name)
            }
        else:
            is_valid, err_msg = confirmation_manager.validate_and_consume(
                confirm_token,
                confirm_text or "",
                expected_action="delete_datasource",
                expected_datasource_id=id,
                expected_details=expected_details
            )
            if not is_valid:
                raise HTTPException(status_code=400, detail={"code": "CONFIRMATION_FAILED", "message": err_msg})

    try:
        from engine.datasource import close_active_tunnel
        close_active_tunnel(id)

        db.delete(datasource)
        db.commit()
        return {"success": True, "message": "数据源已删除"}
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to delete datasource")
        raise HTTPException(
            status_code=500,
            detail={"code": "DATASOURCE_DELETE_FAILED", "message": "删除数据源失败，请稍后重试。"},
        )


@router.post("/datasources/{id}/sync")
def api_sync_schema(id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return sync_schema(db, id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "SYNC_FAILED", "message": str(exc)})
    except Exception as exc:
        logger.exception("Schema sync failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "SYNC_FAILED", "message": "元数据结构同步失败，请检查数据库连接后重试。"},
        )


@router.get("/schema/tables")
def api_list_tables(datasource_id: str = Query(...), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    tables = db.query(SchemaTable).filter(SchemaTable.data_source_id == datasource_id).all()
    return [
        {
            "id": table.id,
            "table_name": table.table_name,
            "table_comment": table.table_comment or "",
            "table_type": table.table_type,
            "row_count_estimate": table.row_count_estimate,
            "columns_count": len(table.columns),
            "module_tag": _guess_module_tag(str(table.table_name)),
        }
        for table in tables
    ]


@router.get("/schema/tables/{table_id}/columns")
def api_list_columns(table_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    table = db.query(SchemaTable).filter(SchemaTable.id == table_id).first()
    if not table:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "表结构记录不存在"})

    return [
        {
            "id": column.id,
            "column_name": column.column_name,
            "data_type": column.data_type,
            "column_type": column.column_type,
            "is_nullable": bool(column.is_nullable),
            "column_default": column.column_default or "",
            "column_comment": column.column_comment or "",
            "is_primary_key": bool(column.is_primary_key),
            "is_foreign_key": bool(column.is_foreign_key),
            "foreign_table_id": column.foreign_table_id,
            "foreign_column_id": column.foreign_column_id,
        }
        for column in table.columns
    ]


@router.get("/schema/er-diagram")
def api_get_er_diagram(datasource_id: str = Query(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return build_er_diagram_data(db, datasource_id)
    except Exception as exc:
        logger.exception("ER diagram build failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "DIAGRAM_FAILED", "message": "生成 ER 图失败，请确认已完成 Schema 同步。"},
        )
