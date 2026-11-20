"""Host resource authorization metadata, not a second Run or Job store."""
from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from engine.db import Base


class ComputerGrantRecord(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "computer_grants"
    __table_args__ = (
        Index("ix_computer_grants_session_created", "session_id", "created_at"),
        CheckConstraint("permission IN ('observe', 'control')", name="ck_computer_grant_permission"),
        CheckConstraint("status IN ('active', 'paused', 'revoked', 'interrupted')", name="ck_computer_grant_status"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("agent_sessions.id", ondelete="CASCADE"))
    version: Mapped[str] = mapped_column(String)
    engine_generation: Mapped[str] = mapped_column(String)
    target_kind: Mapped[str] = mapped_column(String)
    target_json: Mapped[str] = mapped_column(Text)
    permission: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[int] = mapped_column(BigInteger)
    expires_at: Mapped[int] = mapped_column(BigInteger)
