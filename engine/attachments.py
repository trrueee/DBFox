"""Generic Host input snapshots, outside the capability-neutral Agent Kernel."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path
import re
from uuid import uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.agent.references import ConversationInputReference
from engine.agent.resource_refs import ProjectResourceDescriptor
from engine.models import AgentRun, AgentSession, AgentSessionInput, ConversationAttachment
from engine.resource import ResourceScopeRef
from engine.runtime_paths import private_runtime_dir

ATTACHMENT_RESOURCE_KIND = "dbfox.core.attachment"
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_SESSION_ATTACHMENTS = 10
MAX_SESSION_ATTACHMENT_BYTES = 100 * 1024 * 1024


class AttachmentError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.status = code, status


class AttachmentSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    session_id: str
    display_name: str
    media_type: str
    byte_count: int
    content_sha256: str
    created_at: datetime
    first_input_id: str | None
    first_input_sequence: int | None
    available: bool


@dataclass(frozen=True)
class AttachmentResourceHandle:
    """Trusted read-only snapshot location. Never serialize the path to a model."""
    id: str
    session_id: str
    project_id: str
    display_name: str
    media_type: str
    byte_count: int
    content_sha256: str
    path: Path


def require_session(db: Session, session_id: str) -> AgentSession:
    row = db.get(AgentSession, session_id)
    if row is None or row.deleted_at is not None:
        raise AttachmentError("CONVERSATION_NOT_FOUND", "会话不存在或已删除。", 404)
    return row


class AttachmentService:
    def __init__(self, db: Session, root: Path | None = None):
        self.db = db
        self.root = root if root is not None else private_runtime_dir("attachments")
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, attachment_id: str) -> Path:
        if re.fullmatch(r"att_[0-9a-f]{32}", attachment_id) is None:
            raise AttachmentError("ATTACHMENT_NOT_FOUND", "附件不可用。", 404)
        return self.root / (attachment_id + ".blob")

    def owned(self, session_id: str, attachment_id: str) -> ConversationAttachment:
        require_session(self.db, session_id)
        row = self.db.get(ConversationAttachment, attachment_id)
        if row is None or row.session_id != session_id:
            raise AttachmentError("ATTACHMENT_NOT_FOUND", "附件不属于当前会话或已不可用。", 404)
        return row

    def summary(self, row: ConversationAttachment) -> AttachmentSummary:
        return AttachmentSummary(
            id=str(row.id), session_id=str(row.session_id), display_name=str(row.display_name),
            media_type=str(row.media_type), byte_count=int(row.byte_count), content_sha256=str(row.content_sha256),
            # SQLite stores the UTC timestamp without an offset. Restore it at
            # the HTTP boundary so generated ISO datetime clients accept it.
            created_at=row.created_at.replace(tzinfo=UTC), first_input_id=row.first_input_id,
            first_input_sequence=row.first_input_sequence, available=self.path(str(row.id)).is_file(),
        )

    def listing(self, session_id: str, boundary: int | None = None, *, staged: bool = False) -> tuple[ConversationAttachment, ...]:
        require_session(self.db, session_id)
        rows = self.db.scalars(select(ConversationAttachment).where(
            ConversationAttachment.session_id == session_id,
        ).order_by(ConversationAttachment.first_input_sequence, ConversationAttachment.created_at, ConversationAttachment.id))
        return tuple(row for row in rows if (
            row.first_input_sequence is not None and (boundary is None or row.first_input_sequence <= boundary)
        ) or (staged and row.first_input_id is None))

    def publish(self, session_id: str, *, temporary: Path, name: str, media_type: str, size: int, digest: str, key: str) -> ConversationAttachment:
        """Caller holds the existing Host write transaction; stream first, lock last."""
        require_session(self.db, session_id)
        prior = self.db.scalar(select(ConversationAttachment).where(
            ConversationAttachment.session_id == session_id, ConversationAttachment.upload_key == key,
        ))
        if prior is not None:
            if (prior.display_name, prior.media_type, prior.byte_count, prior.content_sha256) != (name, media_type, size, digest):
                raise AttachmentError("UPLOAD_KEY_CONFLICT", "上传标识已经用于不同文件。", 409)
            self.resolve(ResourceScopeRef(kind=ATTACHMENT_RESOURCE_KIND, id=str(prior.id), version=str(prior.content_sha256)))
            return prior
        rows = self.listing(session_id, staged=True)
        if len(rows) >= MAX_SESSION_ATTACHMENTS or sum(int(r.byte_count) for r in rows) + size > MAX_SESSION_ATTACHMENT_BYTES:
            raise AttachmentError("ATTACHMENT_QUOTA_EXCEEDED", "当前会话附件容量已满。", 409)
        row = ConversationAttachment(
            id="att_" + uuid4().hex, session_id=session_id, display_name=name, media_type=media_type,
            byte_count=size, content_sha256=digest, upload_key=key,
        )
        temporary.replace(self.path(str(row.id)))
        self.db.add(row)
        self.db.flush()
        return row

    def admit(self, session_id: str, input_id: str, references: tuple[ConversationInputReference, ...]) -> None:
        """Atomically link a snapshot to its first immutable SessionInput."""
        admitted = self.db.get(AgentSessionInput, input_id)
        if admitted is None or admitted.session_id != session_id:
            raise AttachmentError("ATTACHMENT_ADMISSION_INVALID", "附件输入关联无效。")
        selected = [r for r in references if r.object is not None and r.object.kind == ATTACHMENT_RESOURCE_KIND]
        fresh = []
        for reference in selected:
            assert reference.object is not None
            row = self.owned(session_id, reference.object.id)
            if reference.object.version != row.content_sha256:
                raise AttachmentError("ATTACHMENT_VERSION_CHANGED", "附件版本无效。", 409)
            self.resolve(ResourceScopeRef(kind=ATTACHMENT_RESOURCE_KIND, id=str(row.id), version=str(row.content_sha256)))
            if row.first_input_id is None:
                fresh.append(row)
        if len(fresh) > 1:
            raise AttachmentError("ONE_NEW_ATTACHMENT_PER_INPUT", "每条消息只能添加一份新文件。")
        for row in fresh:
            row.first_input_id, row.first_input_sequence = input_id, int(admitted.sequence)
        self.db.flush()

    def descriptors(self, session_id: str, boundary: int | None = None, *, staged: bool = False) -> tuple[ProjectResourceDescriptor, ...]:
        return tuple(ProjectResourceDescriptor(
            kind=ATTACHMENT_RESOURCE_KIND, id=str(row.id), version=str(row.content_sha256),
            name=f"文件{index} · {row.display_name} · 第{row.first_input_sequence}次输入" if row.first_input_sequence is not None else f"{row.display_name} · 待发送",
        ) for index, row in enumerate(self.listing(session_id, boundary, staged=staged), 1))

    def resolve(self, ref: ResourceScopeRef) -> AttachmentResourceHandle:
        row = self.db.get(ConversationAttachment, ref.id)
        if row is None or ref.kind != ATTACHMENT_RESOURCE_KIND or ref.version != row.content_sha256:
            raise AttachmentError("ATTACHMENT_UNAVAILABLE", "原始附件不可用或版本已变化。", 409)
        aggregate = require_session(self.db, str(row.session_id))
        path = self.path(ref.id)
        if not path.is_file() or path.stat().st_size != row.byte_count or hashlib.sha256(path.read_bytes()).hexdigest() != row.content_sha256:
            raise AttachmentError("ATTACHMENT_UNAVAILABLE", "原始附件缺失或完整性检查失败，请重新添加。", 409)
        return AttachmentResourceHandle(
            id=str(row.id), session_id=str(row.session_id), project_id=str(aggregate.project_id or ""), display_name=str(row.display_name),
            media_type=str(row.media_type), byte_count=int(row.byte_count), content_sha256=str(row.content_sha256), path=path,
        )

    def remove_staged(self, session_id: str, attachment_id: str) -> None:
        row = self.owned(session_id, attachment_id)
        if row.first_input_id is not None:
            raise AttachmentError("ATTACHMENT_ALREADY_SENT", "已发送附件随会话保留。", 409)
        self.db.delete(row)
        self.db.flush()
        self.path(attachment_id).unlink(missing_ok=True)

    def collect(self) -> int:
        """Reclaim abandoned stages/orphans; never delete bytes of an admitted input."""
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24)
        expired = tuple(self.db.scalars(select(ConversationAttachment).where(
            ConversationAttachment.first_input_id.is_(None), ConversationAttachment.created_at < cutoff,
        )))
        for row in expired:
            self.db.delete(row)
        self.db.flush()
        active = {str(row.id) for row in self.db.scalars(select(ConversationAttachment))}
        removed = 0
        for path in self.root.iterdir():
            abandoned = (re.fullmatch(r"att_[0-9a-f]{32}\.blob", path.name) and path.stem not in active) or re.fullmatch(r"upload_[0-9a-f]{32}\.tmp", path.name)
            if path.is_file() and abandoned and datetime.fromtimestamp(path.stat().st_mtime, UTC).replace(tzinfo=None) < cutoff:
                path.unlink()
                removed += 1
        return removed


def run_input_boundary(db: Session, run: AgentRun) -> int:
    """Only consumed steering input may move a Run's visibility frontier."""
    rows = db.scalars(select(AgentSessionInput).where(
        AgentSessionInput.run_id == run.id,
        AgentSessionInput.session_id == run.session_id,
    ))
    return max((int(r.sequence) for r in rows if r.id == run.input_id or r.status == "consumed"), default=0)
