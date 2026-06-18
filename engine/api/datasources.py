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
from engine.datasource import build_mysql_ssl_params, build_postgres_ssl_params, test_connection
from engine.errors import DBFoxError, DataSourceConnectionError, NotFoundError
from engine.models import (
    DEFAULT_PROJECT_ID,
    DataSource,
    SchemaTable,
)
from engine.schemas.datasource import DataSourceTestRequest, DataSourceCreateRequest, DataSourceUpdateRequest, DataSourceResponse, _json_list_or_empty
from engine.schema_sync import build_er_diagram_data
from engine.schema_sync_safe import sync_schema

logger = logging.getLogger("dbfox.api.datasources")
router = APIRouter()


def _datasource_to_dict(ds: DataSource) -> dict[str, Any]:
    result = DataSourceResponse.model_validate(ds).model_dump(mode="json")
    # Apply defaults matching the old manual serialization contract
    result.setdefault("db_type", "mysql")
    result.setdefault("env", "dev")
    for field in ("ssh_host", "ssh_username", "ssh_pkey_path", "ssl_ca_path", "ssl_cert_path", "ssl_key_path"):
        if result.get(field) is None:
            result[field] = ""
    result.setdefault("ssh_port", 22)
    result.setdefault("is_read_only", False)
    result.setdefault("ssl_verify_identity", False)
    result.setdefault("connection_mode", "direct")
    result.setdefault("status", "active")
    result.setdefault("enable_embedding_recall", False)
    result.setdefault("ssh_enabled", False)
    result.setdefault("ssl_enabled", False)
    result.setdefault("project_id", DEFAULT_PROJECT_ID)
    return result


def _load_schema_tables(db: Session, datasource_id: str) -> list[SchemaTable]:
    return db.query(SchemaTable).filter(SchemaTable.data_source_id == datasource_id).all()


def _schema_table_to_dict(table: SchemaTable) -> dict[str, Any]:
    return {
        "id": table.id,
        "table_name": table.table_name,
        "table_comment": table.table_comment or "",
        "table_type": table.table_type,
        "row_count_estimate": table.row_count_estimate,
        "columns_count": len(table.columns),
        "module_tag": table.table_schema or None,
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

    if db_type != "sqlite":
        password = decrypt_password(str(ds.password_ciphertext), str(ds.password_nonce))

    return {
        "id": ds.id,
        "is_managed": True,
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
        "ssh_password_ciphertext": ds.ssh_password_ciphertext,
        "ssh_password_nonce": ds.ssh_password_nonce,
        "ssh_pkey_path": ds.ssh_pkey_path,
        "ssh_pkey_passphrase_ciphertext": ds.ssh_pkey_passphrase_ciphertext,
        "ssh_pkey_passphrase_nonce": ds.ssh_pkey_passphrase_nonce,
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
    from engine.policy.error_sanitizer import sanitize_error_message
    setattr(ds, "last_test_at", checked_at)
    setattr(ds, "last_test_status", "failed")
    setattr(ds, "last_test_error", sanitize_error_message(message))
    setattr(ds, "last_test_latency_ms", latency_ms)
    setattr(ds, "last_test_readonly", None)
    setattr(ds, "last_test_server_version", None)
    setattr(ds, "last_test_tables_count", None)
    setattr(ds, "last_test_warnings", json.dumps([], ensure_ascii=False))


@router.post("/datasources/test")
def api_test_connection(req: DataSourceTestRequest) -> dict[str, Any]:
    """测试连接 — 任何失败都转为 DataSourceConnectionError，确保返回 400。"""
    try:
        return test_connection(req.model_dump())
    except DBFoxError:
        raise
    except Exception as exc:
        logger.exception("Connection test failed")
        raise DataSourceConnectionError(f"数据库连接测试失败: {str(exc)}") from exc


@router.post("/datasources", response_model=DataSourceResponse)
def api_create_datasource(req: DataSourceCreateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
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
            enable_embedding_recall=req.enable_embedding_recall,
        )
        db.add(datasource)
        db.commit()
        db.refresh(datasource)
        return _datasource_to_dict(datasource)
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
    return [_datasource_to_dict(ds) for ds in query.all()]


def _replace_secret_if_present(obj: DataSource, value: str | None, cipher_attr: str, nonce_attr: str) -> None:
    if value is None or value == "":
        return
    cipher, nonce = encrypt_password(value)
    setattr(obj, cipher_attr, cipher)
    setattr(obj, nonce_attr, nonce)


@router.put("/datasources/{id}", response_model=DataSourceResponse)
def api_update_datasource(id: str, req: DataSourceUpdateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    datasource = db.query(DataSource).filter(DataSource.id == id).first()
    if not datasource:
        raise NotFoundError("数据源不存在")

    try:
        config = req.model_dump()
        if req.db_type == "mysql":
            build_mysql_ssl_params(config)
        elif req.db_type == "postgresql":
            build_postgres_ssl_params(config)

        datasource.name = req.name
        datasource.db_type = req.db_type
        datasource.host = req.host
        datasource.port = req.port
        datasource.database_name = req.database_name
        datasource.username = req.username
        datasource.connection_mode = req.connection_mode
        datasource.is_read_only = req.is_read_only
        datasource.env = req.env
        datasource.enable_embedding_recall = req.enable_embedding_recall
        datasource.ssh_enabled = req.ssh_enabled
        datasource.ssh_host = req.ssh_host
        datasource.ssh_port = req.ssh_port
        datasource.ssh_username = req.ssh_username
        datasource.ssh_pkey_path = req.ssh_pkey_path
        datasource.ssl_enabled = req.ssl_enabled
        datasource.ssl_ca_path = req.ssl_ca_path
        datasource.ssl_cert_path = req.ssl_cert_path
        datasource.ssl_key_path = req.ssl_key_path
        datasource.ssl_verify_identity = req.ssl_verify_identity

        _replace_secret_if_present(datasource, req.password, "password_ciphertext", "password_nonce")
        _replace_secret_if_present(datasource, req.ssh_password, "ssh_password_ciphertext", "ssh_password_nonce")
        _replace_secret_if_present(
            datasource,
            req.ssh_pkey_passphrase,
            "ssh_pkey_passphrase_ciphertext",
            "ssh_pkey_passphrase_nonce",
        )

        db.commit()
        db.refresh(datasource)
        return _datasource_to_dict(datasource)
    except Exception:
        db.rollback()
        raise


@router.post("/datasources/{id}/health")
def api_check_datasource_health(id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    datasource = db.query(DataSource).filter(DataSource.id == id).first()
    if not datasource:
        raise NotFoundError("数据源不存在")

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
    except DBFoxError as exc:
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
    except Exception:
        logger.exception("Datasource health check failed")
        latency_ms = int((time.perf_counter() - started) * 1000)
        _persist_health_failure(datasource, "数据库连接健康检查失败，请检查连接配置。", latency_ms, checked_at)
        db.commit()
        db.refresh(datasource)
        return {
            "ok": False,
            "status": "failed",
            "checkedAt": datasource.last_test_at.isoformat() if datasource.last_test_at else None,
            "latencyMs": latency_ms,
            "warnings": [],
            "message": "数据库连接健康检查失败，请检查连接配置。",
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
        raise NotFoundError("数据源不存在")

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
                raise DBFoxError(err_msg, "CONFIRMATION_FAILED")

    try:
        from engine.datasource import close_active_tunnel
        close_active_tunnel(id)
        from engine.sql.pool_registry import get_pool_registry
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


@router.post("/datasources/{id}/sync")
def api_sync_schema(id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return sync_schema(db, id)
    except ValueError as exc:
        raise DBFoxError(code="SYNC_FAILED", message=str(exc))


@router.get("/schema/tables")
def api_list_tables(datasource_id: str = Query(...), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    tables = _load_schema_tables(db, datasource_id)
    if not tables:
        try:
            sync_schema(db, datasource_id)
        except Exception:
            db.rollback()
            logger.warning("Auto schema sync before listing tables failed for %s", datasource_id)
        else:
            tables = _load_schema_tables(db, datasource_id)
    return [_schema_table_to_dict(table) for table in tables]


@router.get("/schema/tables/{table_id}/columns")
def api_list_columns(table_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    table = db.query(SchemaTable).filter(SchemaTable.id == table_id).first()
    if not table:
        raise NotFoundError("表结构记录不存在")

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
    except Exception:
        logger.exception("ER diagram build failed")
        raise


from pydantic import BaseModel

class DomainTagRuleSchema(BaseModel):
    pattern: str
    tag: str
    priority: int

@router.get("/datasources/{id}/domain-tags")
def api_get_domain_tags(id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    from engine.models import DomainTagRule
    rules = db.query(DomainTagRule).filter(DomainTagRule.data_source_id == id).order_by(DomainTagRule.priority.desc()).all()
    if not rules:
        default_patterns = [
            ("user", ["user", "member", "customer", "account"]),
            ("order", ["order", "cart", "coupon"]),
            ("product", ["product", "category", "sku", "inventory", "item"]),
            ("payment", ["payment", "pay", "refund", "transaction"]),
            ("shipping", ["shipping", "address", "carrier", "logistics"]),
            ("analytics", ["analytics", "click", "recommendation", "event", "log"]),
            ("system", ["system", "admin", "setting", "config"]),
            ("content", ["article", "post", "comment", "review", "tag"]),
        ]
        for tag, needles in default_patterns:
            for needle in needles:
                db.add(
                    DomainTagRule(
                        data_source_id=id,
                        pattern=needle,
                        tag=tag,
                        priority=10,
                    )
                )
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.warning("Failed to persist default domain tags for datasource %s", id)
        rules = db.query(DomainTagRule).filter(DomainTagRule.data_source_id == id).order_by(DomainTagRule.priority.desc()).all()
        
    return [{"id": r.id, "pattern": r.pattern, "tag": r.tag, "priority": r.priority} for r in rules]

@router.post("/datasources/{id}/domain-tags")
def api_save_domain_tags(id: str, rules: list[DomainTagRuleSchema], db: Session = Depends(get_db)) -> dict[str, Any]:
    from engine.models import DomainTagRule
    try:
        db.query(DomainTagRule).filter(DomainTagRule.data_source_id == id).delete()
        for r in rules:
            db.add(
                DomainTagRule(
                    data_source_id=id,
                    pattern=r.pattern,
                    tag=r.tag,
                    priority=r.priority
                )
            )
        db.commit()
        return {"success": True, "message": "Domain tag rules saved successfully"}
    except Exception as exc:
        db.rollback()
        from engine.policy.error_sanitizer import sanitize_error_message
        raise HTTPException(status_code=400, detail=sanitize_error_message(str(exc)))
