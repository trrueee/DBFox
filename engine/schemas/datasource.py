from pydantic import BaseModel

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
