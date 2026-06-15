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

    def __repr__(self) -> str:
        return f"<Project id={self.id!r} name={self.name!r} status={self.status!r}>"


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

    def __repr__(self) -> str:
        return f"<DataSource id={self.id!r} name={self.name!r} db_type={self.db_type!r} env={self.env!r}>"


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

    def __repr__(self) -> str:
        return f"<SchemaTable id={self.id!r} table_name={self.table_name!r} data_source_id={self.data_source_id!r}>"


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

    def __repr__(self) -> str:
        return f"<SchemaColumn id={self.id!r} column_name={self.column_name!r} data_type={self.data_type!r}>"


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

    def __repr__(self) -> str:
        return f"<QueryHistory id={self.id!r} status={self.execution_status!r} latency_ms={self.execution_time_ms!r}>"


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


class AgentSession(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_sessions"
    __table_args__ = (
        Index("ix_agent_sessions_datasource", "datasource_id"),
        Index("ix_agent_sessions_created", "created_at"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    datasource_id = Column(String, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    runs = relationship("AgentRun", back_populates="session", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<AgentSession id={self.id!r} title={self.title!r} datasource_id={self.datasource_id!r}>"


class AgentRun(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_session", "session_id"),
        Index("ix_agent_runs_datasource", "datasource_id"),
        Index("ix_agent_runs_created", "created_at"),
    )

    id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False)
    parent_run_id = Column(String, nullable=True)
    datasource_id = Column(String, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False)
    question = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="running")
    current_step_name = Column(String, nullable=True)
    waiting_approval_id = Column(String, nullable=True)
    response_json = Column(Text, nullable=True)
    context_summary = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    completed_at = Column(DateTime, nullable=True)

    session = relationship("AgentSession", back_populates="runs")
    artifacts = relationship("AgentArtifactRecord", back_populates="run", cascade="all, delete-orphan")
    runtime_events = relationship("AgentRuntimeEventRecord", back_populates="run", cascade="all, delete-orphan")
    trace_events = relationship("AgentTraceEventRecord", back_populates="run", cascade="all, delete-orphan")
    approvals = relationship("AgentApproval", back_populates="run", cascade="all, delete-orphan")
    checkpoints = relationship("AgentCheckpoint", back_populates="run", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<AgentRun id={self.id!r} status={self.status!r} datasource_id={self.datasource_id!r}>"


class AgentApproval(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_approvals"
    __table_args__ = (
        Index("ix_agent_approvals_run", "run_id"),
        Index("ix_agent_approvals_session", "session_id"),
        Index("ix_agent_approvals_status", "status"),
    )

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(String, nullable=False)
    step_name = Column(String, nullable=False)
    tool_name = Column(String, nullable=True)

    status = Column(String, nullable=False, default="pending")
    risk_level = Column(String, nullable=False, default="warning")
    reason = Column(Text, nullable=True)

    policy_decision_json = Column(Text, nullable=False)
    requested_action_json = Column(Text, nullable=True)

    decided_by = Column(String, nullable=True)
    decision_note = Column(Text, nullable=True)
    decided_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=utcnow)
    expires_at = Column(DateTime, nullable=True)

    run = relationship("AgentRun", back_populates="approvals")

    def __repr__(self) -> str:
        return f"<AgentApproval id={self.id!r} status={self.status!r} risk_level={self.risk_level!r}>"


class AgentCheckpoint(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_checkpoints"
    __table_args__ = (
        Index("ix_agent_checkpoints_run", "run_id"),
        Index("ix_agent_checkpoints_session", "session_id"),
    )

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(String, nullable=False)

    checkpoint_index = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    current_step_name = Column(String, nullable=True)
    next_step_name = Column(String, nullable=True)

    plan_json = Column(Text, nullable=True)
    state_json = Column(Text, nullable=False)
    completed_steps_json = Column(Text, nullable=False)
    pending_steps_json = Column(Text, nullable=False)
    artifacts_json = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=utcnow)

    run = relationship("AgentRun", back_populates="checkpoints")


class AgentArtifactRecord(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_artifacts"
    __table_args__ = (
        Index("ix_agent_artifacts_run", "run_id"),
        Index("ix_agent_artifacts_session", "session_id"),
    )

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(String, nullable=False)
    semantic_id = Column(String, nullable=True)
    type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    produced_by_step = Column(String, nullable=True)
    depends_on_json = Column(Text, nullable=True)
    payload_json = Column(Text, nullable=False)
    presentation_json = Column(Text, nullable=False)
    refs_json = Column(Text, nullable=True)
    sequence = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    run = relationship("AgentRun", back_populates="artifacts")


class AgentRuntimeEventRecord(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_runtime_events"
    __table_args__ = (
        Index("ix_agent_runtime_events_run", "run_id"),
        Index("ix_agent_runtime_events_session", "session_id"),
    )

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(String, nullable=False)
    sequence = Column(Integer, nullable=False)
    type = Column(String, nullable=False)
    event_json = Column(Text, nullable=False)
    created_at_ms = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    run = relationship("AgentRun", back_populates="runtime_events")


class AgentTraceEventRecord(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_trace_events"
    __table_args__ = (
        Index("ix_agent_trace_events_run", "run_id"),
        Index("ix_agent_trace_events_session", "session_id"),
    )

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(String, nullable=False)
    sequence = Column(Integer, nullable=False)
    type = Column(String, nullable=False)
    event_json = Column(Text, nullable=False)
    created_at_ms = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    run = relationship("AgentRun", back_populates="trace_events")


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


class SemanticAlias(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "semantic_aliases"
    __table_args__ = (
        Index("ix_semantic_aliases_datasource", "data_source_id"),
        Index("ix_semantic_aliases_alias", "alias"),
        UniqueConstraint("data_source_id", "alias", "target_type", "target", name="uq_semantic_aliases_ds_alias_target"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    data_source_id = Column(String, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False)
    alias = Column(String, nullable=False)
    target_type = Column(String, nullable=False)
    target = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class SemanticMetric(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "semantic_metrics"
    __table_args__ = (
        Index("ix_semantic_metrics_datasource", "data_source_id"),
        UniqueConstraint("data_source_id", "name", name="uq_semantic_metrics_ds_name"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    data_source_id = Column(String, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    expression = Column(String, nullable=False)
    source_columns_json = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class SemanticDimension(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "semantic_dimensions"
    __table_args__ = (
        Index("ix_semantic_dimensions_datasource", "data_source_id"),
        UniqueConstraint("data_source_id", "name", name="uq_semantic_dimensions_ds_name"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    data_source_id = Column(String, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    column_ref = Column(String, nullable=False)
    transform = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class WorkspaceTableScope(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "workspace_table_scopes"
    __table_args__ = (
        Index("ix_workspace_table_scopes_project_ds", "project_id", "data_source_id"),
        UniqueConstraint("project_id", "data_source_id", "table_id", name="uq_workspace_scopes_project_ds_table"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    data_source_id = Column(String, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False)
    table_id = Column(String, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


# ─────────────────────────────────────────────
# Agent Eval models
# ─────────────────────────────────────────────

class AgentGoldenTask(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_golden_tasks"
    __table_args__ = (
        Index("ix_agent_golden_tasks_datasource", "datasource_id"),
        Index("ix_agent_golden_tasks_project", "project_id"),
        Index("ix_agent_golden_tasks_intent", "expected_intent"),
        Index("ix_agent_golden_tasks_source", "source"),
        Index("ix_agent_golden_tasks_source_case", "source_case_id"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    datasource_id = Column(String, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(String, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    question = Column(String, nullable=False)
    workspace_context_json = Column(Text, nullable=False, default="{}")
    expected_intent = Column(String, nullable=True)
    expected_tools_json = Column(Text, nullable=False, default="[]")
    forbidden_tools_json = Column(Text, nullable=False, default="[]")
    expected_artifact_types_json = Column(Text, nullable=False, default="[]")
    expected_final_contains_json = Column(Text, nullable=False, default="[]")
    expected_approval_state = Column(String, nullable=True)
    expected_sql_required = Column(Boolean, nullable=False, default=False)
    tags_json = Column(Text, nullable=False, default="[]")
    source = Column(String, nullable=False, default="internal")
    source_case_id = Column(String, nullable=True)
    difficulty = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class AgentEvalRun(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_eval_runs"
    __table_args__ = (
        Index("ix_agent_eval_runs_datasource", "datasource_id"),
        Index("ix_agent_eval_runs_project", "project_id"),
        Index("ix_agent_eval_runs_status", "status"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    datasource_id = Column(String, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(String, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    source_filter_json = Column(Text, nullable=False, default="{}")
    status = Column(String, nullable=False, default="running")
    total_cases = Column(Integer, nullable=False, default=0)
    passed_cases = Column(Integer, nullable=False, default=0)
    failed_cases = Column(Integer, nullable=False, default=0)
    pass_rate = Column(Float, nullable=True)
    avg_latency_ms = Column(Float, nullable=True)
    summary_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    completed_at = Column(DateTime, nullable=True)

    case_results = relationship("AgentEvalCaseResult", back_populates="eval_run", cascade="all, delete-orphan")


class AgentEvalCaseResult(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_eval_case_results"
    __table_args__ = (
        Index("ix_agent_eval_case_results_run", "eval_run_id"),
        Index("ix_agent_eval_case_results_task", "task_id"),
        Index("ix_agent_eval_case_results_status", "status"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    eval_run_id = Column(String, ForeignKey("agent_eval_runs.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(String, ForeignKey("agent_golden_tasks.id", ondelete="CASCADE"), nullable=False)
    run_id = Column(String, nullable=True)
    status = Column(String, nullable=False, default="pending")
    score = Column(Float, nullable=False, default=0.0)
    latency_ms = Column(Integer, nullable=True)
    actual_intent = Column(String, nullable=True)
    actual_tools_json = Column(Text, nullable=False, default="[]")
    actual_artifact_types_json = Column(Text, nullable=False, default="[]")
    actual_approval_state = Column(String, nullable=True)
    actual_sql_json = Column(Text, nullable=False, default="[]")
    failure_reasons_json = Column(Text, nullable=False, default="[]")
    response_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)

    eval_run = relationship("AgentEvalRun", back_populates="case_results")


class ChatConversation(Base):  # type: ignore[misc,valid-type]
    """Local chat session history mirrored from the desktop UI."""

    __tablename__ = "chat_conversations"
    __table_args__ = (Index("ix_chat_conversations_updated_at", "updated_at"),)

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    created_at = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=False)
    context_tables_json = Column(Text, nullable=False, default="[]")
    messages_json = Column(Text, nullable=False, default="[]")
    artifacts_json = Column(Text, nullable=False, default="[]")

    def __repr__(self) -> str:
        return f"<ChatConversation id={self.id!r} title={self.title!r}>"
