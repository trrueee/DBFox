from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

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
    set_model_attr,
)
from engine.api.credentials import (
    get_credential_lease_registry,
)
from engine.security.credential_vault import (
    CredentialKind,
    CredentialVault,
    get_credential_vault,
)

logger = logging.getLogger("dbfox.api.datasources.crud")
router = APIRouter()
_CONNECTION_TEST_FAILED_MESSAGE = "数据库连接测试失败，请检查连接配置。"


class DatasourceDeleteConfirmRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    confirm_token: str | None = Field(default=None, min_length=1, max_length=256)
    confirm_text: str | None = Field(default=None, min_length=1, max_length=256)


def _require_credential_reference(
    vault: CredentialVault,
    credential_id: str | None,
    kind: CredentialKind,
) -> str | None:
    if credential_id is None:
        return None
    if vault.get(credential_id, expected_kind=kind) is None:
        raise DBFoxError(
            "Credential reference was not found or has the wrong kind.",
            code="CREDENTIAL_REFERENCE_INVALID",
        )
    return credential_id


def _connection_test_config(req: DataSourceTestRequest) -> dict[str, Any]:
    """Resolve transient test credentials without persisting a secret field."""
    vault = get_credential_vault()
    config = req.model_dump()
    config.pop("credential_lease_id", None)
    if req.db_type in {"mysql", "postgresql"} and not req.password_credential_id:
        raise DataSourceConnectionError(
            "A password credential is required for network datasource connections."
        )
    password_id = _require_credential_reference(
        vault,
        req.password_credential_id,
        CredentialKind.DATASOURCE_PASSWORD,
    )
    ssh_password_id = _require_credential_reference(
        vault,
        req.ssh_password_credential_id,
        CredentialKind.SSH_PASSWORD,
    )
    ssh_passphrase_id = _require_credential_reference(
        vault,
        req.ssh_key_passphrase_credential_id,
        CredentialKind.SSH_KEY_PASSPHRASE,
    )
    config["password"] = vault.get(password_id) if password_id else ""
    config["ssh_password"] = vault.get(ssh_password_id) if ssh_password_id else ""
    config["ssh_pkey_passphrase"] = vault.get(ssh_passphrase_id) if ssh_passphrase_id else ""
    return config


def _request_credential_ids(
    req: DataSourceTestRequest | DataSourceCreateRequest | DataSourceUpdateRequest,
) -> set[str]:
    return {
        credential_id
        for credential_id in (
            req.password_credential_id,
            req.ssh_password_credential_id,
            req.ssh_key_passphrase_credential_id,
        )
        if credential_id
    }


def _claim_credential_lease(
    req: DataSourceTestRequest | DataSourceCreateRequest | DataSourceUpdateRequest,
    credential_ids: set[str],
) -> str | None:
    if not credential_ids:
        if req.credential_lease_id:
            raise DBFoxError(
                "Credential lease has no matching request references.",
                code="CREDENTIAL_LEASE_INVALID",
            )
        return None
    if not req.credential_lease_id:
        raise DBFoxError(
            "New datasource credentials require a server-issued credential lease.",
            code="CREDENTIAL_LEASE_REQUIRED",
        )
    get_credential_lease_registry().claim(req.credential_lease_id, credential_ids)
    return req.credential_lease_id


def _release_credential_lease(vault: CredentialVault, lease_id: str | None) -> None:
    if not lease_id:
        return
    try:
        for credential_id in get_credential_lease_registry().abort_claimed(lease_id):
            vault.delete(credential_id)
    except Exception as exc:
        logger.warning("Could not release datasource credential lease (%s)", type(exc).__name__)


def _public_connection_test_failure(exc: Exception) -> DataSourceConnectionError:
    """Log only safe diagnostics and return a fixed client-facing failure."""
    logger.warning("Connection test failed (%s)", type(exc).__name__)
    return DataSourceConnectionError(_CONNECTION_TEST_FAILED_MESSAGE)


def _commit_credential_lease(lease_id: str | None) -> None:
    if lease_id:
        get_credential_lease_registry().commit(lease_id)


def _delete_replaced_credentials(vault: CredentialVault, credential_ids: set[str]) -> None:
    for credential_id in credential_ids:
        try:
            vault.delete(credential_id)
        except Exception:
            logger.warning("Could not remove replaced credential reference %s", credential_id)


@router.post("/datasources/test")
def api_test_connection(req: DataSourceTestRequest) -> dict[str, Any]:
    vault = get_credential_vault()
    lease_id = _claim_credential_lease(req, _request_credential_ids(req))
    try:
        try:
            config = _connection_test_config(req)
        except DBFoxError:
            # Credential/vault contract errors are already typed and safe.
            raise
        except Exception as exc:
            raise _public_connection_test_failure(exc) from None

        try:
            return test_connection(config)
        except Exception as exc:
            raise _public_connection_test_failure(exc) from None
    finally:
        _release_credential_lease(vault, lease_id)


@router.post("/datasources", response_model=DataSourceResponse)
def api_create_datasource(
    req: DataSourceCreateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    vault = get_credential_vault()
    lease_id: str | None = None
    metadata_committed = False
    try:
        lease_id = _claim_credential_lease(req, _request_credential_ids(req))
        from engine.projects.service import resolve_project_id

        config = req.model_dump()
        if req.db_type == "mysql":
            build_mysql_ssl_params(config)
        elif req.db_type == "postgresql":
            build_postgres_ssl_params(config)
        project_id = resolve_project_id(db, req.project_id)
        password_credential_id = _require_credential_reference(
            vault, req.password_credential_id, CredentialKind.DATASOURCE_PASSWORD
        )
        ssh_password_credential_id = _require_credential_reference(
            vault, req.ssh_password_credential_id, CredentialKind.SSH_PASSWORD
        )
        ssh_key_passphrase_credential_id = _require_credential_reference(
            vault,
            req.ssh_key_passphrase_credential_id,
            CredentialKind.SSH_KEY_PASSPHRASE,
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
            password_credential_id=password_credential_id,
            ssh_enabled=req.ssh_enabled,
            ssh_host=req.ssh_host,
            ssh_port=req.ssh_port,
            ssh_username=req.ssh_username,
            ssh_password_credential_id=ssh_password_credential_id,
            ssh_pkey_path=req.ssh_pkey_path,
            ssh_key_passphrase_credential_id=ssh_key_passphrase_credential_id,
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
        metadata_committed = True
        _commit_credential_lease(lease_id)
        db.refresh(datasource)
        return datasource_to_dict(datasource)
    except Exception:
        db.rollback()
        if not metadata_committed:
            _release_credential_lease(vault, lease_id)
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

    vault = get_credential_vault()
    lease_id: str | None = None
    metadata_committed = False
    try:
        existing_credential_ids = {
            field: getattr(datasource, field)
            for field in (
                "password_credential_id",
                "ssh_password_credential_id",
                "ssh_key_passphrase_credential_id",
            )
        }
        changed_credential_ids = {
            credential_id
            for field, credential_id in (
                ("password_credential_id", req.password_credential_id),
                ("ssh_password_credential_id", req.ssh_password_credential_id),
                ("ssh_key_passphrase_credential_id", req.ssh_key_passphrase_credential_id),
            )
            if credential_id and credential_id != existing_credential_ids[field]
        }
        lease_id = _claim_credential_lease(req, changed_credential_ids)
        old_credential_ids = {
            credential_id
            for credential_id in (
                datasource.password_credential_id,
                datasource.ssh_password_credential_id,
                datasource.ssh_key_passphrase_credential_id,
            )
            if credential_id
        }
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
        if req.password_credential_id is not None:
            set_model_attr(
                datasource,
                "password_credential_id",
                _require_credential_reference(
                    vault,
                    req.password_credential_id,
                    CredentialKind.DATASOURCE_PASSWORD,
                ),
            )
        if req.ssh_password_credential_id is not None:
            set_model_attr(
                datasource,
                "ssh_password_credential_id",
                _require_credential_reference(
                    vault,
                    req.ssh_password_credential_id,
                    CredentialKind.SSH_PASSWORD,
                ),
            )
        if req.ssh_key_passphrase_credential_id is not None:
            set_model_attr(
                datasource,
                "ssh_key_passphrase_credential_id",
                _require_credential_reference(
                    vault,
                    req.ssh_key_passphrase_credential_id,
                    CredentialKind.SSH_KEY_PASSPHRASE,
                ),
            )

        db.commit()
        metadata_committed = True
        _commit_credential_lease(lease_id)
        db.refresh(datasource)
        current_credential_ids = {
            credential_id
            for credential_id in (
                datasource.password_credential_id,
                datasource.ssh_password_credential_id,
                datasource.ssh_key_passphrase_credential_id,
            )
            if credential_id
        }
        _delete_replaced_credentials(vault, old_credential_ids - current_credential_ids)
        return datasource_to_dict(datasource)
    except Exception:
        db.rollback()
        if not metadata_committed:
            _release_credential_lease(vault, lease_id)
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

        credential_ids = {
            credential_id
            for credential_id in (
                datasource.password_credential_id,
                datasource.ssh_password_credential_id,
                datasource.ssh_key_passphrase_credential_id,
            )
            if credential_id
        }
        close_active_tunnel(id)
        get_pool_registry().dispose_datasource(id)
        db.delete(datasource)
        db.commit()
        _delete_replaced_credentials(get_credential_vault(), credential_ids)
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
