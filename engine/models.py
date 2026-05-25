import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from engine.db import Base

DEFAULT_PROJECT_ID = "default-project"
DEFAULT_PROJECT_NAME = "Default Workspace"


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class Project(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_status", "status"),
        UniqueConstraint("name", name="uq_projects_name"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="active")

    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    data_sources = relationship("DataSource", back_populates="project")
    environments = relationship("DatabaseEnvironment", back_populates="project", cascade="all, delete-orphan")
    backups = relationship("BackupRecord", back_populates="project", cascade="all, delete-orphan")
    drafts = relationship("TableDesignDraft", back_populates="project", cascade="all, delete-orphan")


class DatabaseEnvironment(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "database_environments"
    __table_args__ = (
        Index("ix_database_environments_project", "project_id"),
        Index("ix_database_environments_status", "status"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    name = Column(String, nullable=False)
    runtime = Column(String, nullable=False, default="docker")
    engine_type = Column(String, nullable=False, default="mysql")
    engine_version = Column(String, nullable=False, default="8.0")
    image = Column(String, nullable=False, default="mysql:8.0")
    container_name = Column(String, nullable=False)

    host = Column(String, nullable=False, default="127.0.0.1")
    port = Column(Integer, nullable=False)
    database_name = Column(String, nullable=False)
    username = Column(String, nullable=False)
    password_ciphertext = Column(String, nullable=False)
    password_nonce = Column(String, nullable=False)

    datasource_id = Column(String, ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True)
    status = Column(String, nullable=False, default="created")
    last_health_status = Column(String, nullable=True)
    last_health_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    project = relationship("Project", back_populates="environments")
    datasource = relationship("DataSource", foreign_keys=[datasource_id])


class DataSource(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "data_sources"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_datasources_project_name"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    environment_id = Column(String, ForeignKey("database_environments.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String, nullable=False)
    db_type = Column(String, nullable=False, default="mysql")

    host = Column(String, nullable=False)
    port = Column(Integer, nullable=False, default=3306)
    database_name = Column(String, nullable=False)
    username = Column(String, nullable=False)

    password_ciphertext = Column(String, nullable=False)
    password_nonce = Column(String, nullable=False)
    password_key_version = Column(String, nullable=False, default="v1")

    # SSH Tunnel configurations
    ssh_enabled = Column(Boolean, nullable=False, default=False)
    ssh_host = Column(String, nullable=True)
    ssh_port = Column(Integer, nullable=False, default=22)
    ssh_username = Column(String, nullable=True)
    ssh_password_ciphertext = Column(String, nullable=True)
    ssh_password_nonce = Column(String, nullable=True)
    ssh_pkey_path = Column(String, nullable=True)
    ssh_pkey_passphrase_ciphertext = Column(String, nullable=True)
    ssh_pkey_passphrase_nonce = Column(String, nullable=True)

    ssl_enabled = Column(Boolean, nullable=False, default=False)
    ssl_ca_path = Column(String, nullable=True)
    ssl_cert_path = Column(String, nullable=True)
    ssl_key_path = Column(String, nullable=True)
    ssl_verify_identity = Column(Boolean, nullable=False, default=True)

    connection_mode = Column(String, nullable=False, default="direct")
    is_read_only = Column(Boolean, nullable=False, default=False)
    env = Column(String, nullable=False, default="dev")
    status = Column(String, nullable=False, default="active")

    last_test_at = Column(DateTime, nullable=True)
    last_test_status = Column(String, nullable=True)
    last_test_error = Column(String, nullable=True)
    last_test_latency_ms = Column(Integer, nullable=True)
    last_test_readonly = Column(Boolean, nullable=True)
    last_test_server_version = Column(String, nullable=True)
    last_test_tables_count = Column(Integer, nullable=True)
    last_test_warnings = Column(Text, nullable=True)

    last_sync_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String, nullable=True)
    last_sync_error = Column(String, nullable=True)

    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    project = relationship("Project", back_populates="data_sources")
    tables = relationship("SchemaTable", back_populates="datasource", cascade="all, delete-orphan")
    queries = relationship("QueryHistory", back_populates="datasource", cascade="all, delete-orphan")
    golden_sqls = relationship("GoldenSQL", back_populates="datasource", cascade="all, delete-orphan")
    backups = relationship("BackupRecord", back_populates="datasource", cascade="all, delete-orphan")


class BackupRecord(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "backup_records"
    __table_args__ = (
        Index("ix_backup_records_project", "project_id"),
        Index("ix_backup_records_datasource", "datasource_id"),
        Index("ix_backup_records_created", "created_at"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    datasource_id = Column(String, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False)
    environment_id = Column(String, ForeignKey("database_environments.id", ondelete="SET NULL"), nullable=True)

    label = Column(String, nullable=True)
    backup_type = Column(String, nullable=False, default="mysqldump")
    status = Column(String, nullable=False, default="running")
    file_path = Column(Text, nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    checksum_sha256 = Column(String, nullable=True)

    started_at = Column(DateTime, nullable=False, default=utcnow)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    project = relationship("Project", back_populates="backups")
    datasource = relationship("DataSource", back_populates="backups")


class SchemaTable(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "schema_tables"
    __table_args__ = (
        Index("ix_schema_tables_datasource", "data_source_id"),
        UniqueConstraint("data_source_id", "table_schema", "table_name", name="uq_schema_tables_ds_schema_table"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    data_source_id = Column(String, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False)

    table_schema = Column(String, nullable=False)
    table_name = Column(String, nullable=False)
    table_comment = Column(String, nullable=True)
    table_type = Column(String, nullable=True)
    row_count_estimate = Column(Integer, nullable=True, default=0)
    engine_name = Column(String, nullable=True)

    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    datasource = relationship("DataSource", back_populates="tables")
    columns = relationship("SchemaColumn", back_populates="table", cascade="all, delete-orphan")


class SchemaColumn(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "schema_columns"
    __table_args__ = (
        Index("ix_schema_columns_table", "table_id"),
        UniqueConstraint("table_id", "column_name", name="uq_schema_columns_table_column"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    table_id = Column(String, ForeignKey("schema_tables.id", ondelete="CASCADE"), nullable=False)

    column_name = Column(String, nullable=False)
    data_type = Column(String, nullable=True)
    column_type = Column(String, nullable=True)
    is_nullable = Column(Boolean, nullable=False, default=True)
    column_default = Column(String, nullable=True)
    column_comment = Column(String, nullable=True)

    is_primary_key = Column(Boolean, nullable=False, default=False)
    is_foreign_key = Column(Boolean, nullable=False, default=False)

    foreign_table_id = Column(String, nullable=True)
    foreign_column_id = Column(String, nullable=True)

    ordinal_position = Column(Integer, nullable=True)

    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    table = relationship("SchemaTable", back_populates="columns")


class QueryHistory(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "query_history"
    __table_args__ = (
        Index("ix_query_history_datasource", "data_source_id"),
        Index("ix_query_history_created", "created_at"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    data_source_id = Column(String, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False)

    question = Column(String, nullable=True)
    submitted_sql = Column(Text, nullable=True)
    generated_sql = Column(Text, nullable=True)
    safe_sql = Column(Text, nullable=True)
    executed_sql = Column(Text, nullable=True)

    guardrail_result = Column(String, nullable=False)
    guardrail_checks = Column(Text, nullable=True)

    execution_status = Column(String, nullable=True)
    execution_time_ms = Column(Integer, nullable=True)
    connect_ms = Column(Integer, nullable=True)
    guardrail_ms = Column(Integer, nullable=True)
    execute_ms = Column(Integer, nullable=True)
    fetch_ms = Column(Integer, nullable=True)
    serialize_ms = Column(Integer, nullable=True)
    rows_returned = Column(Integer, nullable=True)
    columns_returned = Column(Integer, nullable=True)

    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    datasource = relationship("DataSource", back_populates="queries")


class LLMLog(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "llm_logs"

    id = Column(String, primary_key=True, default=generate_uuid)
    data_source_id = Column(String, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=True)
    request_type = Column(String, nullable=False)

    prompt_hash = Column(String, nullable=True)
    prompt_text = Column(Text, nullable=True)
    response_text = Column(Text, nullable=True)

    model_name = Column(String, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    status = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)

    # Prompt versioning & RAG audit fields
    prompt_version = Column(String, nullable=True)
    prompt_template_hash = Column(String, nullable=True)
    model_temperature = Column(Float, nullable=True)
    max_tokens = Column(Integer, nullable=True)
    schema_validation_warnings = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=utcnow)

    datasource = relationship("DataSource")



class GoldenSQL(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "golden_sqls"
    __table_args__ = (
        Index("ix_golden_sqls_datasource", "data_source_id"),
        UniqueConstraint("data_source_id", "question", name="uq_golden_sqls_ds_question"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    data_source_id = Column(String, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False)

    question = Column(String, nullable=False)
    golden_sql = Column(Text, nullable=False)

    created_at = Column(DateTime, nullable=False, default=utcnow)

    datasource = relationship("DataSource", back_populates="golden_sqls")


class TableDesignDraft(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "table_design_drafts"
    __table_args__ = (
        Index("ix_table_design_drafts_project", "project_id"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    table_name = Column(String, nullable=False)
    table_comment = Column(String, nullable=True)
    columns_json = Column(Text, nullable=False)
    indexes_json = Column(Text, nullable=False)

    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    project = relationship("Project", back_populates="drafts")
