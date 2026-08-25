import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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
    def __repr__(self) -> str:
        return f"<Project id={self.id!r} name={self.name!r} status={self.status!r}>"


class FoundationRuntimeState(Base):  # type: ignore[misc,valid-type]
    """Singleton marker written by the one-time foundation runtime reset."""

    __tablename__ = "foundation_runtime_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_foundation_runtime_state_singleton"),
    )

    id = Column(Integer, primary_key=True, default=1)
    runtime_version = Column(String, nullable=False)
    reset_completed_at = Column(DateTime, nullable=True)




class CredentialLeaseRecord(Base):  # type: ignore[misc,valid-type]
    """Durable saga state for credential-vault references awaiting ownership."""

    __tablename__ = "credential_leases"
    __table_args__ = (
        Index("ix_credential_leases_status_expires", "status", "expires_at"),
    )

    id = Column(String, primary_key=True)
    credential_ids_json = Column(Text, nullable=False)
    status = Column(String, nullable=False)
    owner_id = Column(String, nullable=True)
    owner_operation = Column(String, nullable=True)
    owner_project_id = Column(String, nullable=True)
    version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    expires_at = Column(DateTime, nullable=False)
    claimed_at = Column(DateTime, nullable=True)
    committed_at = Column(DateTime, nullable=True)
    cleanup_started_at = Column(DateTime, nullable=True)
    released_at = Column(DateTime, nullable=True)


















class AgentSession(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_sessions"
    __table_args__ = (
        Index("ix_agent_sessions_project", "project_id"),
        Index("ix_agent_sessions_created", "created_at"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    title = Column(String, nullable=True)
    input_sequence = Column(Integer, nullable=False, default=0)
    event_sequence = Column(Integer, nullable=False, default=0)
    event_floor_sequence = Column(Integer, nullable=False, default=0)
    lease_owner = Column(String, nullable=True)
    lease_token = Column(Integer, nullable=False, default=0)
    lease_expires_at = Column(DateTime, nullable=True)
    selected_artifact_id = Column(String, nullable=True)
    context_epoch = Column(Integer, nullable=False, default=0)
    message_sequence = Column(Integer, nullable=False, default=0)
    archived_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    messages = relationship(
        "AgentMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AgentMessage.sequence",
    )
    runs = relationship("AgentRun", back_populates="session", cascade="all, delete-orphan")
    resource_intents = relationship(
        "ConversationResourceIntent",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ConversationResourceIntent.position",
    )
    memory = relationship("AgentSessionMemory", back_populates="session", cascade="all, delete-orphan", uselist=False)

    def __repr__(self) -> str:
        return f"<AgentSession id={self.id!r} title={self.title!r} project_id={self.project_id!r}>"


class ConversationResourceIntent(Base):  # type: ignore[misc,valid-type]
    """Durable UX intent; execution authority is still frozen per SessionInput."""

    __tablename__ = "conversation_resource_intents"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "kind",
            "resource_id",
            name="uq_conversation_resource_intent_identity",
        ),
        UniqueConstraint(
            "conversation_id",
            "position",
            name="uq_conversation_resource_intent_position",
        ),
        Index("ix_conversation_resource_intents_conversation", "conversation_id"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    conversation_id = Column(
        String,
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind = Column(String(64), nullable=False)
    resource_id = Column(String(256), nullable=False)
    position = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    session = relationship("AgentSession", back_populates="resource_intents")


class AgentMessage(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_messages"
    __table_args__ = (
        Index("ix_agent_messages_session", "session_id"),
        Index("ix_agent_messages_role", "role"),
        UniqueConstraint("session_id", "sequence", name="uq_agent_messages_session_sequence"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False, default="")
    status = Column(String, nullable=False, default="created")
    sequence = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    session = relationship("AgentSession", back_populates="messages")


class AgentMessageSearchDoc(Base):  # type: ignore[misc,valid-type]
    """Derived, rebuildable projection used by SQLite FTS5 conversation recall."""

    __tablename__ = "agent_message_search_docs"
    __table_args__ = (
        Index("ix_agent_message_search_docs_session_sequence", "session_id", "sequence"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(
        String,
        ForeignKey("agent_messages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    session_id = Column(
        String,
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence = Column(Integer, nullable=False)
    role = Column(String, nullable=False)
    status = Column(String, nullable=False)
    search_text = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class AgentSessionMemory(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_session_memories"
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_agent_session_memories_session"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False)
    memory_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    session = relationship("AgentSession", back_populates="memory")


class AgentRun(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_session", "session_id"),
        Index("ix_agent_runs_created", "created_at"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False)
    input_id = Column(String, ForeignKey("agent_session_inputs.id", ondelete="RESTRICT"), nullable=True)
    session_sequence = Column(Integer, nullable=False, default=0)
    parent_run_id = Column(String, nullable=True)
    llm_credential_id = Column(String, nullable=True)
    api_base = Column(String, nullable=True)
    model_name = Column(String, nullable=True)
    user_message_id = Column(String, ForeignKey("agent_messages.id", ondelete="SET NULL"), nullable=True)
    assistant_message_id = Column(String, ForeignKey("agent_messages.id", ondelete="SET NULL"), nullable=True)
    question = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="running")
    version = Column(Integer, nullable=False, default=0)
    lease_token = Column(Integer, nullable=False, default=0)
    current_turn_id = Column(String, nullable=True)
    request_json = Column(Text, nullable=False, default="{}")
    result_json = Column(Text, nullable=True)
    cancel_requested = Column(Boolean, nullable=False, default=False)
    consumed_input_tokens = Column(Integer, nullable=False, default=0, server_default="0")
    consumed_output_tokens = Column(Integer, nullable=False, default=0, server_default="0")
    consumed_tokens = Column(Integer, nullable=False, default=0, server_default="0")
    consumed_cost_usd = Column(Float, nullable=False, default=0.0, server_default="0")
    provider_retry_count = Column(Integer, nullable=False, default=0, server_default="0")
    repair_attempt_count = Column(Integer, nullable=False, default=0, server_default="0")
    current_step_name = Column(String, nullable=True)
    waiting_approval_id = Column(String, nullable=True)
    response_json = Column(Text, nullable=True)
    context_summary = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    completed_at = Column(DateTime, nullable=True)

    session = relationship("AgentSession", back_populates="runs")
    artifacts = relationship("AgentArtifactRecord", back_populates="run", cascade="all, delete-orphan")
    approvals = relationship("AgentApproval", back_populates="run", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<AgentRun id={self.id!r} status={self.status!r}>"


class AgentApproval(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_approvals"
    __table_args__ = (
        Index("ix_agent_approvals_run", "run_id"),
        Index("ix_agent_approvals_session", "session_id"),
        Index("ix_agent_approvals_status", "status"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    run_id = Column(String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(String, ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False)
    step_name = Column(String, nullable=False)
    tool_name = Column(String, nullable=True)
    turn_id = Column(String, nullable=True)
    tool_invocation_id = Column(String, nullable=True)

    status = Column(String, nullable=False, default="pending")
    version = Column(Integer, nullable=False, default=0)
    risk_level = Column(String, nullable=False, default="warning")
    reason = Column(Text, nullable=True)

    policy_decision_json = Column(Text, nullable=False)
    requested_action_json = Column(Text, nullable=True)

    decided_by = Column(String, nullable=True)
    decision_note = Column(Text, nullable=True)
    decided_at = Column(DateTime, nullable=True)
    consumed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=utcnow)
    expires_at = Column(DateTime, nullable=True)

    run = relationship("AgentRun", back_populates="approvals")

    def __repr__(self) -> str:
        return f"<AgentApproval id={self.id!r} status={self.status!r} risk_level={self.risk_level!r}>"


class AgentArtifactRecord(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_artifacts"
    __table_args__ = (
        Index("ix_agent_artifacts_run", "run_id"),
        Index("ix_agent_artifacts_session", "session_id"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    run_id = Column(String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(String, nullable=False)
    message_id = Column(String, ForeignKey("agent_messages.id", ondelete="SET NULL"), nullable=True)
    turn_id = Column(String, nullable=True)
    semantic_id = Column(String, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    type = Column(String, nullable=False)
    # Payload contract version. ``version`` remains the semantic-key
    # work-product version; the two are never interchangeable.
    schema_version = Column(Integer, nullable=False, default=1, server_default="1")
    title = Column(String, nullable=False)
    produced_by_step = Column(String, nullable=True)
    depends_on_json = Column(Text, nullable=True)
    payload_json = Column(Text, nullable=False)
    presentation_json = Column(Text, nullable=False)
    refs_json = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    payload_ref = Column(String, nullable=True)
    # Exact Runtime resources that produced this Artifact. Domain payloads must
    # not carry a second, capability-specific copy of execution authority.
    resource_refs_json = Column(Text, nullable=False, default="[]", server_default="[]")
    provenance_json = Column(Text, nullable=False, default="{}")
    relations_json = Column(Text, nullable=False, default="[]")
    status = Column(String, nullable=False, default="completed")
    sequence = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    run = relationship("AgentRun", back_populates="artifacts")


class AgentSessionInput(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_session_inputs"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_agent_session_inputs_sequence"),
        UniqueConstraint("session_id", "idempotency_key", name="uq_agent_session_inputs_idempotency"),
        Index("ix_agent_session_inputs_status", "session_id", "status", "sequence"),
        Index("ix_agent_session_inputs_run", "run_id"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False)
    run_id = Column(String, nullable=True)
    message_id = Column(String, ForeignKey("agent_messages.id", ondelete="SET NULL"), nullable=True)
    sequence = Column(Integer, nullable=False)
    idempotency_key = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    delivery_mode = Column(String, nullable=False, default="queue")
    selected_artifact_ids_json = Column(Text, nullable=False, default="[]")
    workspace_context_json = Column(Text, nullable=False, default="{}")
    resource_refs_json = Column(Text, nullable=False, default="[]")
    references_json = Column(Text, nullable=False, default="[]")
    reply_to_request_id = Column(String, nullable=True)
    status = Column(String, nullable=False, default="admitted")
    admitted_at = Column(DateTime, nullable=False, default=utcnow)
    consumed_at = Column(DateTime, nullable=True)


class AgentTurn(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_turns"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_agent_turns_run_sequence"),
        Index("ix_agent_turns_session", "session_id", "created_at"),
        Index("ix_agent_turns_status", "status"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False)
    run_id = Column(String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    sequence = Column(Integer, nullable=False)
    attempt = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="running")
    agent_definition_version = Column(String, nullable=False)
    prompt_version = Column(String, nullable=False)
    prompt_hash = Column(String, nullable=False)
    context_snapshot_json = Column(Text, nullable=False, default="{}")
    context_hash = Column(String, nullable=False)
    tool_materialization_json = Column(Text, nullable=False, default="{}")
    tool_materialization_hash = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    model_name = Column(String, nullable=False)
    reasoning_summary = Column(Text, nullable=False, default="")
    tool_calls_json = Column(Text, nullable=False, default="[]")
    response_items_json = Column(Text, nullable=False, default="[]")
    usage_json = Column(Text, nullable=False, default="{}")
    termination = Column(String, nullable=True)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    completed_at = Column(DateTime, nullable=True)


class AgentToolInvocation(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_tool_invocations"
    __table_args__ = (
        UniqueConstraint("turn_id", "provider_call_id", name="uq_agent_tool_invocations_provider_call"),
        UniqueConstraint("idempotency_key", name="uq_agent_tool_invocations_idempotency"),
        Index("ix_agent_tool_invocations_run", "run_id", "created_at"),
        Index("ix_agent_tool_invocations_status", "status"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False)
    run_id = Column(String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    turn_id = Column(String, ForeignKey("agent_turns.id", ondelete="CASCADE"), nullable=False)
    provider_call_id = Column(String, nullable=False)
    tool_name = Column(String, nullable=False)
    declared_version = Column(String, nullable=False)
    contract_hash = Column(String, nullable=False)
    owner_id = Column(String, nullable=True)
    package_digest = Column(String, nullable=True)
    input_json = Column(Text, nullable=False)
    resource_refs_json = Column(Text, nullable=False, default="[]")

    input_hash = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=False)
    status = Column(String, nullable=False, default="requested")
    policy_json = Column(Text, nullable=False, default="{}")
    presentation_json = Column(Text, nullable=False)
    approval_id = Column(String, ForeignKey("agent_approvals.id", ondelete="SET NULL"), nullable=True)
    recovery_policy = Column(String, nullable=False)
    attempt_count = Column(Integer, nullable=False, default=0)
    result_ref = Column(String, nullable=True)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class AgentObservationRecord(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_observations"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_agent_observations_run_sequence"),
        UniqueConstraint("tool_invocation_id", name="uq_agent_observations_invocation"),
        Index("ix_agent_observations_session", "session_id", "created_at"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False)
    run_id = Column(String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    turn_id = Column(String, ForeignKey("agent_turns.id", ondelete="CASCADE"), nullable=False)
    tool_invocation_id = Column(String, ForeignKey("agent_tool_invocations.id", ondelete="CASCADE"), nullable=False)
    sequence = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    model_visible_summary = Column(Text, nullable=False)
    model_output_json = Column(Text, nullable=False)
    structured_result_ref = Column(String, nullable=True)
    artifact_ids_json = Column(Text, nullable=False, default="[]")
    facts_json = Column(Text, nullable=False, default="{}")
    semantic_capabilities_json = Column(Text, nullable=False, default="[]")
    contributes_progress = Column(Boolean, nullable=False, default=True)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    retryable = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class AgentEvidenceRecord(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_evidence"
    __table_args__ = (
        Index("ix_agent_evidence_run", "run_id"),
        Index("ix_agent_evidence_artifact", "artifact_id"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False)
    run_id = Column(String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    claim_id = Column(String, nullable=False)
    artifact_id = Column(String, ForeignKey("agent_artifacts.id", ondelete="RESTRICT"), nullable=False)
    label = Column(String, nullable=False)
    observed_at = Column(DateTime, nullable=False)
    locator_json = Column(Text, nullable=False, default="{}")
    value_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class AgentQuestionRequest(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_question_requests"
    __table_args__ = (
        Index("ix_agent_question_requests_run", "run_id"),
        Index("ix_agent_question_requests_status", "status"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False)
    run_id = Column(String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    turn_id = Column(String, ForeignKey("agent_turns.id", ondelete="CASCADE"), nullable=False)
    tool_invocation_id = Column(
        String,
        ForeignKey("agent_tool_invocations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status = Column(String, nullable=False, default="pending")
    version = Column(Integer, nullable=False, default=0)
    question = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)
    options_json = Column(Text, nullable=False, default="[]")
    allow_free_text = Column(Boolean, nullable=False, default=True)
    response_message_id = Column(String, ForeignKey("agent_messages.id", ondelete="SET NULL"), nullable=True)
    response_json = Column(Text, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    answered_at = Column(DateTime, nullable=True)


class AgentEventRecord(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_events"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_agent_events_session_sequence"),
        Index("ix_agent_events_run", "run_id", "sequence"),
        Index("ix_agent_events_session", "session_id", "sequence"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False)
    run_id = Column(String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True)
    turn_id = Column(String, ForeignKey("agent_turns.id", ondelete="SET NULL"), nullable=True)
    sequence = Column(Integer, nullable=False)
    type = Column(String, nullable=False)
    event_version = Column(Integer, nullable=False, default=1)
    payload_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)


class AgentRunItemRecord(Base):  # type: ignore[misc,valid-type]
    """Canonical persisted read model shared by snapshots and RuntimeEvents."""

    __tablename__ = "agent_run_items"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_agent_run_items_session_sequence"),
        Index("ix_agent_run_items_session", "session_id", "sequence"),
        Index("ix_agent_run_items_run", "run_id", "sequence"),
    )

    id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False)
    run_id = Column(String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    turn_id = Column(String, ForeignKey("agent_turns.id", ondelete="SET NULL"), nullable=True)
    sequence = Column(Integer, nullable=False)
    item_type = Column(String, nullable=False)
    revision = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    item_json = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    completed_at = Column(DateTime, nullable=True)


class AgentTaskPlanRecord(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_task_plans"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_agent_task_plans_run"),
        Index("ix_agent_task_plans_session", "session_id", "updated_at"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False)
    run_id = Column(String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    turn_id = Column(String, ForeignKey("agent_turns.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    objective = Column(Text, nullable=False)
    steps_json = Column(Text, nullable=False, default="[]")
    status = Column(String, nullable=False, default="active")
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class SecurityAuditRecord(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "security_audit_records"
    __table_args__ = (
        Index("ix_security_audit_created", "created_at"),
        Index("ix_security_audit_action", "action", "created_at"),
        Index("ix_security_audit_session", "session_id", "created_at"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    action = Column(String, nullable=False)
    outcome = Column(String, nullable=False)
    actor_type = Column(String, nullable=False, default="local_user")
    actor_id = Column(String, nullable=True)
    resource_type = Column(String, nullable=False)
    resource_id = Column(String, nullable=True)
    session_id = Column(String, nullable=True)
    run_id = Column(String, nullable=True)
    correlation_id = Column(String, nullable=False)
    details_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
