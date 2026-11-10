"""Private Host metadata. Core Run and Tool records remain independent."""

from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, Index, Integer, LargeBinary, String, Text

from engine.db import Base


class LocalExecutionJob(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "local_execution_jobs"
    __table_args__ = (
        Index("ix_local_execution_jobs_session_created", "session_id", "created_at"),
        Index("ix_local_execution_jobs_finished", "finished_at"),
    )

    id = Column(String, primary_key=True)
    invocation_id = Column(String, nullable=False, unique=True)
    approval_id = Column(String, nullable=False)
    run_id = Column(String, nullable=False)
    session_id = Column(String, ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False)
    workspace_id = Column(String, nullable=False)
    workspace_generation = Column(String, nullable=False)
    engine_generation = Column(String, nullable=False)
    command_json = Column(Text, nullable=False)
    state = Column(String, nullable=False)
    reason = Column(String)
    root_exit_code = Column(BigInteger)
    active_processes = Column(Integer)
    stdin_open = Column(Boolean, nullable=False)
    output_finalized = Column(Boolean, nullable=False)
    first_cursor = Column(BigInteger, nullable=False)
    last_cursor = Column(BigInteger, nullable=False)
    total_bytes = Column(BigInteger, nullable=False)
    retained_bytes = Column(Integer, nullable=False)
    created_at = Column(BigInteger, nullable=False)
    finished_at = Column(BigInteger)


class LocalExecutionLog(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "local_execution_logs"

    job_id = Column(String, ForeignKey("local_execution_jobs.id", ondelete="CASCADE"), primary_key=True)
    cursor = Column(BigInteger, primary_key=True)
    stream = Column(String, nullable=False)
    byte_end = Column(BigInteger, nullable=False)
    data = Column(LargeBinary, nullable=False)
