"""Durable, conversation-scoped sharing and the side-effect authorization fence."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
import time
from uuid import uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from engine.agent.repositories.write_transaction import begin_agent_write
from engine.agent.resource_refs import ProjectResourceDescriptor
from engine.attachments import require_session
from engine.computer.contracts import ComputerError, ComputerGrant, GrantStatus, Permission, TARGET_KIND, TargetIdentity
from engine.computer.records import ComputerGrantRecord
from engine.resource import ResourceScopeRef


def now_ms() -> int:
    return int(time.time() * 1000)


class ComputerGrantStore:
    def __init__(self, sessions: Callable[[], Session], *, clock: Callable[[], int] = now_ms) -> None:
        self.sessions, self.clock = sessions, clock
        self.generation = uuid4().hex
        with self.sessions() as db:
            begin_agent_write(db)
            db.execute(update(ComputerGrantRecord).where(
                ComputerGrantRecord.status.in_(("active", "paused")),
            ).values(status="interrupted"))
            db.commit()

    def _view(self, row: ComputerGrantRecord) -> ComputerGrant:
        state = GrantStatus(row.status)
        if state in (GrantStatus.ACTIVE, GrantStatus.PAUSED) and row.expires_at <= self.clock():
            state = GrantStatus.EXPIRED
        return ComputerGrant(
            id=row.id, session_id=row.session_id, version=row.version,
            target=TargetIdentity.model_validate_json(row.target_json), permission=Permission(row.permission),
            status=state, created_at=row.created_at, expires_at=row.expires_at,
        )

    def list(self, session_id: str) -> tuple[ComputerGrant, ...]:
        with self.sessions() as db:
            require_session(db, session_id)
            return self._list(db, session_id)

    def _list(self, db: Session, session_id: str) -> tuple[ComputerGrant, ...]:
        live = and_(
            ComputerGrantRecord.engine_generation == self.generation,
            ComputerGrantRecord.status.in_(("active", "paused")),
            ComputerGrantRecord.expires_at > self.clock(),
        )
        history = select(ComputerGrantRecord.id).where(
            ComputerGrantRecord.session_id == session_id, ~live,
        ).order_by(ComputerGrantRecord.created_at.desc(), ComputerGrantRecord.id.desc()).limit(16)
        rows = db.scalars(select(ComputerGrantRecord).where(
            ComputerGrantRecord.session_id == session_id,
            or_(live, ComputerGrantRecord.id.in_(history)),
        ).order_by(ComputerGrantRecord.created_at.desc(), ComputerGrantRecord.id.desc()))
        return tuple(self._view(row) for row in rows)

    def create(self, session_id: str, target: TargetIdentity, *, permission: str,
               duration_minutes: int, replace_existing: bool = False) -> ComputerGrant:
        if permission not in ("observe", "control") or duration_minutes not in (5, 15, 30):
            raise ComputerError("COMPUTER_SHARE_INVALID", "请选择明确的权限和共享期限。", 400)
        with self.sessions() as db:
            begin_agent_write(db)
            require_session(db, session_id)
            existing = tuple(db.scalars(select(ComputerGrantRecord).where(
                ComputerGrantRecord.session_id == session_id,
                ComputerGrantRecord.target_kind == target.kind,
                ComputerGrantRecord.status.in_(("active", "paused")),
                ComputerGrantRecord.expires_at > self.clock(),
            )))
            if existing and not replace_existing:
                raise ComputerError("COMPUTER_ALREADY_SHARED", "此对话已共享同类目标。请明确结束或替换当前共享。")
            for row in existing:
                row.status = "revoked"
            row = ComputerGrantRecord(
                id="computer_" + uuid4().hex, session_id=session_id, version=uuid4().hex,
                engine_generation=self.generation, target_kind=target.kind,
                target_json=target.model_dump_json(), permission=permission, status="active",
                created_at=self.clock(), expires_at=self.clock() + duration_minutes * 60_000,
            )
            db.add(row)
            db.flush()
            result = self._view(row)
            db.commit()
            return result

    def get(self, session_id: str, target_id: str) -> ComputerGrant:
        with self.sessions() as db:
            require_session(db, session_id)
            row = db.get(ComputerGrantRecord, target_id)
            if row is None or row.session_id != session_id:
                raise ComputerError("COMPUTER_TARGET_NOT_FOUND", "共享目标不属于此对话。", 404)
            return self._view(row)

    def require(self, session_id: str, ref: ResourceScopeRef, *, control: bool = False) -> ComputerGrant:
        with self.sessions() as db:
            return self._require(db, session_id, ref, control=control)

    def _require(self, db: Session, session_id: str, ref: ResourceScopeRef, *, control: bool) -> ComputerGrant:
        require_session(db, session_id)
        if ref.kind != TARGET_KIND:
            raise ComputerError("COMPUTER_SCOPE_INVALID", "请选择已共享的电脑目标。")
        row = db.get(ComputerGrantRecord, ref.id)
        if row is None or row.session_id != session_id:
            raise ComputerError("COMPUTER_TARGET_NOT_FOUND", "共享目标不属于此对话。", 404)
        if row.version != str(ref.version) or row.engine_generation != self.generation:
            raise ComputerError("COMPUTER_SCOPE_CHANGED", "共享目标或运行代次已变化，请重新选择目标。")
        grant = self._view(row)
        if grant.status != GrantStatus.ACTIVE:
            raise ComputerError("COMPUTER_SHARE_INACTIVE", "共享已暂停、结束或到期；操作没有执行，请重新共享并观察。")
        if control and grant.permission != "control":
            raise ComputerError("COMPUTER_OBSERVE_ONLY", "此目标仅允许观察。请由用户明确授权控制后再操作。")
        return grant

    @contextmanager
    def effect_lease(self, session_id: str, ref: ResourceScopeRef,
                     is_cancelled: Callable[[], bool]) -> Iterator[ComputerGrant]:
        with self.sessions() as db:
            begin_agent_write(db)
            grant = self._require(db, session_id, ref, control=True)
            if is_cancelled():
                raise ComputerError("COMPUTER_ACTION_CANCELLED", "操作已取消，未发送输入。")
            # Only the immediate input dispatch belongs inside this fence. UIA
            # lookup, network waits and capture happen before/after it.
            yield grant
            db.commit()

    def stop(self, session_id: str | None, *, revoke: bool = False) -> tuple[str, ...]:
        with self.sessions() as db:
            begin_agent_write(db)
            query = select(ComputerGrantRecord).where(ComputerGrantRecord.status.in_(("active", "paused")))
            if session_id is not None:
                # Retirement must also work after the conversation is deleted.
                query = query.where(ComputerGrantRecord.session_id == session_id)
            rows = tuple(db.scalars(query))
            for row in rows:
                row.status = "revoked" if revoke else "paused"
            ids = tuple(row.id for row in rows)
            db.commit()
            return ids

    def stop_target(self, session_id: str, target_id: str, *, revoke: bool = False) -> None:
        with self.sessions() as db:
            begin_agent_write(db)
            row = db.get(ComputerGrantRecord, target_id)
            if row is None or row.session_id != session_id:
                raise ComputerError("COMPUTER_TARGET_NOT_FOUND", "共享目标不属于此对话。", 404)
            if row.status in ("active", "paused"):
                row.status = "revoked" if revoke else "paused"
            db.commit()

    def resolve(self, ref: ResourceScopeRef) -> ComputerGrant:
        with self.sessions() as db:
            row = db.get(ComputerGrantRecord, ref.id)
            if row is None:
                raise ComputerError("COMPUTER_TARGET_NOT_FOUND", "共享目标不可用。", 404)
            return self._require(db, row.session_id, ref, control=False)

    def descriptors(self, session_id: str) -> tuple[ProjectResourceDescriptor, ...]:
        # Discovery receives an already validated Session from the Host. An
        # owner with no shares contributes nothing; it is not a second Session
        # existence gate. Actual reads and effects still require current scope.
        with self.sessions() as db:
            grants = self._list(db, session_id)
        return tuple(ProjectResourceDescriptor(
            kind=TARGET_KIND, id=grant.id, version=grant.version,
            name=grant.target.title, is_default=False,
        ) for grant in grants if grant.status == GrantStatus.ACTIVE)
