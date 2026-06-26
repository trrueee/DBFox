from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from engine.crypto import decrypt_password, encrypt_password
from engine.models import DEFAULT_PROJECT_ID, DataSource, SchemaColumn, SchemaTable
from engine.schemas.datasource import DataSourceResponse


def datasource_to_dict(ds: DataSource) -> dict[str, Any]:
    result = DataSourceResponse.model_validate(ds).model_dump(mode="json")
    result.setdefault("db_type", "mysql")
    result.setdefault("env", "dev")
    for field in (
        "host",
        "database_name",
        "username",
        "ssh_host",
        "ssh_username",
        "ssh_pkey_path",
        "ssl_ca_path",
        "ssl_cert_path",
        "ssl_key_path",
    ):
        if result.get(field) is None:
            result[field] = ""
    result.setdefault("ssh_port", 22)
    result.setdefault("is_read_only", False)
    result.setdefault("ssl_verify_identity", False)
    result.setdefault("connection_mode", "direct")
    result.setdefault("status", "active")
    result.setdefault("ssh_enabled", False)
    result.setdefault("ssl_enabled", False)
    result.setdefault("project_id", DEFAULT_PROJECT_ID)
    return result


def schema_table_to_dict(table: SchemaTable) -> dict[str, Any]:
    return {
        "id": table.id,
        "table_name": table.table_name,
        "table_comment": table.table_comment or "",
        "table_type": table.table_type,
        "row_count_estimate": table.row_count_estimate,
        "columns_count": len(table.columns),
        "module_tag": table.table_schema or None,
        "ai_description": table.ai_description or "",
        "semantic_tags": table.semantic_tags or "",
        "business_terms": table.business_terms or "",
        "ai_confidence": table.ai_confidence,
        "subject_area": table.subject_area or "",
    }


def schema_column_to_dict(column: SchemaColumn) -> dict[str, Any]:
    return {
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
        "ai_description": column.ai_description or "",
        "semantic_tags": column.semantic_tags or "",
        "business_terms": column.business_terms or "",
        "ai_confidence": column.ai_confidence,
    }


def datasource_to_health_config(ds: DataSource) -> dict[str, Any]:
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


def persist_health_success(
    ds: DataSource,
    result: dict[str, Any],
    latency_ms: int,
    checked_at: datetime,
) -> None:
    warnings = [str(item) for item in result.get("warnings", [])]
    setattr(ds, "last_test_at", checked_at)
    setattr(ds, "last_test_status", "success")
    setattr(ds, "last_test_error", None)
    setattr(ds, "last_test_latency_ms", latency_ms)
    setattr(ds, "last_test_readonly", bool(result.get("readonly", False)))
    setattr(ds, "last_test_server_version", str(result.get("serverVersion") or ""))
    setattr(ds, "last_test_tables_count", int(result.get("tablesCount") or 0))
    setattr(ds, "last_test_warnings", json.dumps(warnings, ensure_ascii=False))


def persist_health_failure(
    ds: DataSource,
    message: str,
    latency_ms: int,
    checked_at: datetime,
) -> None:
    setattr(ds, "last_test_at", checked_at)
    setattr(ds, "last_test_status", "failed")
    setattr(ds, "last_test_error", message)
    setattr(ds, "last_test_latency_ms", latency_ms)
    setattr(ds, "last_test_readonly", None)
    setattr(ds, "last_test_server_version", None)
    setattr(ds, "last_test_tables_count", None)
    setattr(ds, "last_test_warnings", json.dumps([], ensure_ascii=False))


def replace_secret_if_present(
    obj: DataSource,
    value: str | None,
    cipher_attr: str,
    nonce_attr: str,
) -> None:
    if value is None or value == "":
        return
    cipher, nonce = encrypt_password(value)
    setattr(obj, cipher_attr, cipher)
    setattr(obj, nonce_attr, nonce)


def set_model_attr(obj: object, attr: str, value: Any) -> None:
    setattr(obj, attr, value)
