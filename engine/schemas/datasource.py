import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from engine.schemas import _to_iso


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


DbType = Literal["mysql", "postgresql", "sqlite"]
DatasourceEnv = Literal["dev", "test", "prod"]
ConnectionMode = Literal["direct"]


class _DatasourceRequestStringNormalizer(BaseModel):
    @field_validator(
        "project_id",
        "name",
        "db_type",
        "host",
        "database_name",
        "username",
        "connection_mode",
        "env",
        "ssh_host",
        "ssh_username",
        "ssh_pkey_path",
        "ssl_ca_path",
        "ssl_cert_path",
        "ssl_key_path",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def _strip_non_secret_strings(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class DataSourceTestRequest(_DatasourceRequestStringNormalizer):

    db_type: DbType = "mysql"
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=0, le=65_535)
    database_name: str = Field(min_length=1, max_length=1024)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=4096)

    ssh_enabled: bool = False
    ssh_host: str | None = Field(default=None, max_length=255)
    ssh_port: int = Field(default=22, ge=1, le=65_535)
    ssh_username: str | None = Field(default=None, max_length=255)
    ssh_password: str | None = Field(default=None, max_length=4096)
    ssh_pkey_path: str | None = Field(default=None, max_length=1024)
    ssh_pkey_passphrase: str | None = Field(default=None, max_length=4096)

    ssl_enabled: bool = False
    ssl_ca_path: str | None = Field(default=None, max_length=1024)
    ssl_cert_path: str | None = Field(default=None, max_length=1024)
    ssl_key_path: str | None = Field(default=None, max_length=1024)
    ssl_verify_identity: bool = True


class DataSourceCreateRequest(_DatasourceRequestStringNormalizer):

    project_id: str | None = Field(default=None, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    db_type: DbType = "mysql"
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=0, le=65_535)
    database_name: str = Field(min_length=1, max_length=1024)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=4096)
    connection_mode: ConnectionMode = "direct"
    is_read_only: bool = False
    env: DatasourceEnv = "dev"

    ssh_enabled: bool = False
    ssh_host: str | None = Field(default=None, max_length=255)
    ssh_port: int = Field(default=22, ge=1, le=65_535)
    ssh_username: str | None = Field(default=None, max_length=255)
    ssh_password: str | None = Field(default=None, max_length=4096)
    ssh_pkey_path: str | None = Field(default=None, max_length=1024)
    ssh_pkey_passphrase: str | None = Field(default=None, max_length=4096)

    ssl_enabled: bool = False
    ssl_ca_path: str | None = Field(default=None, max_length=1024)
    ssl_cert_path: str | None = Field(default=None, max_length=1024)
    ssl_key_path: str | None = Field(default=None, max_length=1024)
    ssl_verify_identity: bool = True


class DataSourceUpdateRequest(_DatasourceRequestStringNormalizer):

    name: str = Field(min_length=1, max_length=128)
    db_type: DbType = "mysql"
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=0, le=65_535)
    database_name: str = Field(min_length=1, max_length=1024)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=4096)
    connection_mode: ConnectionMode = "direct"
    is_read_only: bool = False
    env: DatasourceEnv = "dev"

    ssh_enabled: bool = False
    ssh_host: str | None = Field(default=None, max_length=255)
    ssh_port: int = Field(default=22, ge=1, le=65_535)
    ssh_username: str | None = Field(default=None, max_length=255)
    ssh_password: str | None = Field(default=None, max_length=4096)
    ssh_pkey_path: str | None = Field(default=None, max_length=1024)
    ssh_pkey_passphrase: str | None = Field(default=None, max_length=4096)

    ssl_enabled: bool = False
    ssl_ca_path: str | None = Field(default=None, max_length=1024)
    ssl_cert_path: str | None = Field(default=None, max_length=1024)
    ssl_key_path: str | None = Field(default=None, max_length=1024)
    ssl_verify_identity: bool = True
