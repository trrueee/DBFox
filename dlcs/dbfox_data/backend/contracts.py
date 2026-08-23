from __future__ import annotations

from typing import Literal

from dbfox_dlc_api import BaseModel, ConfigDict, Field
from pydantic import JsonValue

DatabaseProvider = Literal["mysql", "postgresql", "sqlite"]
Environment = Literal["dev", "test", "staging", "prod"]


class ConnectionProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    project_id: str
    name: str
    provider: DatabaseProvider
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password_credential_ref: str | None = None
    connection_mode: Literal["direct"] = "direct"
    is_read_only: bool = False
    environment: Environment = "dev"
    ssh_enabled: bool = False
    ssh_host: str | None = None
    ssh_port: int | None = None
    ssh_username: str | None = None
    ssh_password_credential_ref: str | None = None
    ssh_pkey_path: str | None = None
    ssh_key_passphrase_credential_ref: str | None = None
    ssl_enabled: bool = False
    ssl_ca_path: str | None = None
    ssl_cert_path: str | None = None
    ssl_key_path: str | None = None
    ssl_verify_identity: bool = True
    connection_generation: int = Field(ge=1)
    status: str = "active"
    created_at: str
    updated_at: str


class DatabaseResource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    connection_profile_id: str
    database_name: str
    display_name: str
    resource_generation: int = Field(ge=1)
    catalog_revision: int = Field(ge=0)
    catalog_refreshed_at: str | None = None
    status: str = "active"
    created_at: str
    updated_at: str


class DatabaseHandle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: ConnectionProfile
    database: DatabaseResource
    scope_version: str


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileIdInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(min_length=1, max_length=128)


class DatabaseIdInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database_id: str = Field(min_length=1, max_length=128)


class ConsoleExecuteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database_id: str = Field(min_length=1, max_length=128)
    sql: str = Field(min_length=1, max_length=50_000)
    question: str | None = Field(default=None, max_length=20_000)
    session_id: str | None = Field(default=None, min_length=1, max_length=128)
    execution_id: str | None = Field(default=None, min_length=1, max_length=128)


class ConsoleExecuteOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["success", "blocked"]
    run_id: str
    session_id: str
    sql_artifact_id: str
    safety_artifact_id: str
    result_artifact_id: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, JsonValue]] = Field(default_factory=list)
    row_count: int = Field(default=0, ge=0)
    returned_rows: int = Field(default=0, ge=0)
    truncated: bool = False
    warnings: list[str] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)


class TablePreviewOperationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    session_id: str
    result_artifact_id: str
    table: str
    columns: list[str]
    rows: list[dict[str, JsonValue]] = Field(default_factory=list)
    returned_rows: int = Field(ge=0)
    truncated: bool
    warnings: list[str] = Field(default_factory=list)


class CreateProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    provider: DatabaseProvider
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65_535)
    username: str | None = Field(default=None, max_length=255)
    password_credential_ref: str | None = Field(default=None, min_length=1, max_length=256)
    is_read_only: bool = False
    environment: Environment = "dev"
    ssh_enabled: bool = False
    ssh_host: str | None = Field(default=None, max_length=255)
    ssh_port: int | None = Field(default=None, ge=1, le=65_535)
    ssh_username: str | None = Field(default=None, max_length=255)
    ssh_password_credential_ref: str | None = Field(default=None, min_length=1, max_length=256)
    ssh_pkey_path: str | None = Field(default=None, max_length=1024)
    ssh_key_passphrase_credential_ref: str | None = Field(default=None, min_length=1, max_length=256)
    ssl_enabled: bool = False
    ssl_ca_path: str | None = Field(default=None, max_length=1024)
    ssl_cert_path: str | None = Field(default=None, max_length=1024)
    ssl_key_path: str | None = Field(default=None, max_length=1024)
    ssl_verify_identity: bool = True
    initial_database_name: str | None = Field(default=None, min_length=1, max_length=1024)
    initial_database_display_name: str | None = Field(default=None, min_length=1, max_length=128)


class UpdateProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(min_length=1, max_length=128)
    expected_generation: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=128)
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65_535)
    username: str | None = Field(default=None, max_length=255)
    password_credential_ref: str | None = Field(default=None, min_length=1, max_length=256)
    is_read_only: bool = False
    environment: Environment = "dev"
    ssh_enabled: bool = False
    ssh_host: str | None = Field(default=None, max_length=255)
    ssh_port: int | None = Field(default=None, ge=1, le=65_535)
    ssh_username: str | None = Field(default=None, max_length=255)
    ssh_password_credential_ref: str | None = Field(default=None, min_length=1, max_length=256)
    ssh_pkey_path: str | None = Field(default=None, max_length=1024)
    ssh_key_passphrase_credential_ref: str | None = Field(default=None, min_length=1, max_length=256)
    ssl_enabled: bool = False
    ssl_ca_path: str | None = Field(default=None, max_length=1024)
    ssl_cert_path: str | None = Field(default=None, max_length=1024)
    ssl_key_path: str | None = Field(default=None, max_length=1024)
    ssl_verify_identity: bool = True


class AddDatabaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(min_length=1, max_length=128)
    database_name: str = Field(min_length=1, max_length=1024)
    display_name: str | None = Field(default=None, min_length=1, max_length=128)


class UpdateDatabaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database_id: str = Field(min_length=1, max_length=128)
    expected_generation: int = Field(ge=1)
    database_name: str = Field(min_length=1, max_length=1024)
    display_name: str = Field(min_length=1, max_length=128)


class ProfileWithDatabases(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: ConnectionProfile
    databases: tuple[DatabaseResource, ...] = ()


class ProfileListOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profiles: tuple[ProfileWithDatabases, ...] = ()


class DeleteOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    deleted: bool


class BackupCreateInput(DatabaseIdInput):
    label: str | None = Field(default=None, max_length=128)


class BackupListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database_id: str | None = Field(default=None, min_length=1, max_length=128)


class BackupRestoreInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backup_id: str = Field(min_length=1, max_length=128)
    expected_resource_version: str = Field(min_length=1, max_length=128)
    confirmation: Literal["restore-to-isolated-database"]


class BackupRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    project_id: str
    database_resource_id: str
    resource_version: str
    label: str | None = None
    backup_type: str
    status: str
    file_size_bytes: int | None = Field(default=None, ge=0)
    checksum_sha256: str | None = None
    source_database_name: str
    started_at: str
    completed_at: str | None = None


class BackupListOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    backups: tuple[BackupRecord, ...] = ()


class RestoreResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    backup_id: str
    database_resource_id: str
    status: Literal["success"]
    source_database_name: str
    target_database_name: str
    previous_resource_version: str
    committed_resource_version: str
    validated_table_count: int = Field(ge=0)
    completed_at: str
