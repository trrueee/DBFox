"""Pydantic response schemas — replace manual _*_to_dict() serialization."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer

from engine.projects.service import DEFAULT_PROJECT_ID


# ── helpers ──

def _json_list_or_empty(raw: Any) -> list[Any]:
    """Parse a JSON list string or return empty list."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def _isoformat_or_none(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


# ── DataSource ──

class DataSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None = None
    environment_id: str | None = None
    name: str
    db_type: str | None = None
    host: str | None = None
    port: int | None = None
    database_name: str | None = None
    username: str | None = None
    connection_mode: str | None = None
    is_read_only: bool = False
    env: str | None = None
    status: str | None = None
    enable_embedding_recall: bool = False
    ssh_enabled: bool = False
    ssh_host: str | None = None
    ssh_port: int | None = None
    ssh_username: str | None = None
    ssh_pkey_path: str | None = None
    ssl_enabled: bool = False
    ssl_ca_path: str | None = None
    ssl_cert_path: str | None = None
    ssl_key_path: str | None = None
    ssl_verify_identity: bool = False
    last_test_at: str | None = None
    last_test_status: str | None = None
    last_test_error: str | None = None
    last_test_latency_ms: int | None = None
    last_test_readonly: bool | None = None
    last_test_server_version: str | None = None
    last_test_tables_count: int | None = None
    last_test_warnings: list[Any] = []
    last_sync_at: str | None = None
    last_sync_status: str | None = None
    last_sync_error: str | None = None
    created_at: str | None = None

    # Normalize booleans from ORM (may be int 0/1)
    @staticmethod
    def _normalize_bool(v: Any) -> bool:
        return bool(v)

    @field_serializer("db_type")
    def default_db_type(self, v: str | None) -> str:
        return v or "mysql"

    @field_serializer("env")
    def default_env(self, v: str | None) -> str:
        return v or "dev"

    @field_serializer("project_id")
    def default_project_id(self, v: str | None) -> str | None:
        return v or DEFAULT_PROJECT_ID

    @field_serializer("ssh_host")
    def default_ssh_host(self, v: str | None) -> str:
        return v or ""

    @field_serializer("ssh_port")
    def default_ssh_port(self, v: int | None) -> int:
        return v or 22

    @field_serializer("ssh_username")
    def default_ssh_username(self, v: str | None) -> str:
        return v or ""

    @field_serializer("ssh_pkey_path")
    def default_ssh_pkey_path(self, v: str | None) -> str:
        return v or ""

    @field_serializer("ssl_ca_path")
    def default_ssl_ca_path(self, v: str | None) -> str:
        return v or ""

    @field_serializer("ssl_cert_path")
    def default_ssl_cert_path(self, v: str | None) -> str:
        return v or ""

    @field_serializer("ssl_key_path")
    def default_ssl_key_path(self, v: str | None) -> str:
        return v or ""

    @field_serializer("last_test_warnings")
    def parse_test_warnings(self, v: Any) -> list[Any]:
        return _json_list_or_empty(v)
