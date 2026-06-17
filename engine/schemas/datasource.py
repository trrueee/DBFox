import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


def _to_iso(v: Any) -> str | None:
    if v is None: return None
    if isinstance(v, datetime): return v.isoformat()
    return str(v)


def _json_list_or_empty(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return [str(item) for item in parsed] if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []


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
    last_test_warnings: list[str] = []

    last_sync_at: str | None = None
    last_sync_status: str | None = None
    last_sync_error: str | None = None

    created_at: str | None = None

    @field_validator("last_test_warnings", mode="before")
    @classmethod
    def parse_test_warnings(cls, v: Any) -> list[str]:
        return _json_list_or_empty(v)

    @field_validator("last_test_at", "last_sync_at", "created_at", mode="before")
    @classmethod
    def _iso_dates(cls, v: Any) -> str | None:
        return _to_iso(v)


class DataSourceTestRequest(BaseModel):
    db_type: str = "mysql"
    host: str | None = None
    port: int | None = None
    database_name: str
    username: str | None = None
    password: str | None = None

    ssh_enabled: bool = False
    ssh_host: str | None = None
    ssh_port: int = 22
    ssh_username: str | None = None
    ssh_password: str | None = None
    ssh_pkey_path: str | None = None
    ssh_pkey_passphrase: str | None = None

    ssl_enabled: bool = False
    ssl_ca_path: str | None = None
    ssl_cert_path: str | None = None
    ssl_key_path: str | None = None
    ssl_verify_identity: bool = True


class DataSourceCreateRequest(BaseModel):
    project_id: str | None = None
    name: str
    db_type: str = "mysql"
    host: str | None = None
    port: int | None = None
    database_name: str
    username: str | None = None
    password: str | None = None
    connection_mode: str = "direct"
    is_read_only: bool = False
    env: str = "dev"
    enable_embedding_recall: bool = False

    ssh_enabled: bool = False
    ssh_host: str | None = None
    ssh_port: int = 22
    ssh_username: str | None = None
    ssh_password: str | None = None
    ssh_pkey_path: str | None = None
    ssh_pkey_passphrase: str | None = None

    ssl_enabled: bool = False
    ssl_ca_path: str | None = None
    ssl_cert_path: str | None = None
    ssl_key_path: str | None = None
    ssl_verify_identity: bool = True


class DataSourceUpdateRequest(BaseModel):
    name: str
    db_type: str = "mysql"
    host: str | None = None
    port: int | None = None
    database_name: str
    username: str | None = None
    password: str | None = None
    connection_mode: str = "direct"
    is_read_only: bool = False
    env: str = "dev"
    enable_embedding_recall: bool = False

    ssh_enabled: bool = False
    ssh_host: str | None = None
    ssh_port: int = 22
    ssh_username: str | None = None
    ssh_password: str | None = None
    ssh_pkey_path: str | None = None
    ssh_pkey_passphrase: str | None = None

    ssl_enabled: bool = False
    ssl_ca_path: str | None = None
    ssl_cert_path: str | None = None
    ssl_key_path: str | None = None
    ssl_verify_identity: bool = True
