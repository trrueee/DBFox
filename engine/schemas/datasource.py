from pydantic import BaseModel


class DataSourceResponse(BaseModel):
    id: str
    project_id: str | None = None
    environment_id: str | None = None
    name: str
    db_type: str = "mysql"
    host: str
    port: int
    database_name: str
    username: str
    connection_mode: str = "direct"
    is_read_only: bool = False
    env: str = "dev"
    status: str = "active"

    ssh_enabled: bool = False
    ssh_host: str = ""
    ssh_port: int = 22
    ssh_username: str = ""
    ssh_pkey_path: str = ""

    ssl_enabled: bool = False
    ssl_ca_path: str = ""
    ssl_cert_path: str = ""
    ssl_key_path: str = ""
    ssl_verify_identity: bool = True

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
