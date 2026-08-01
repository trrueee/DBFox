"""Durable ownership saga for credential-vault references."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from engine.errors import DBFoxError
from engine.json_codec import canonical_dumps, load_array
from engine.models import CredentialLeaseRecord, DataSource
from engine.security.credential_vault import CredentialVault, get_credential_vault


logger = logging.getLogger("dbfox.security.credential_lease")


class CredentialLeaseStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    COMMITTED = "committed"
    CLEANUP_PENDING = "cleanup_pending"
    RELEASED = "released"


class CredentialLeaseSaga:
    def __init__(self, session: Session, vault: CredentialVault | None = None) -> None:
        self.session = session
        self.vault = vault

    def issue(self, credential_ids: set[str], *, ttl_seconds: int = 3600) -> str:
        if not credential_ids:
            raise ValueError("Credential leases require at least one reference")
        now = datetime.now(UTC)
        lease_id = f"lease_{uuid4().hex}"
        self.session.add(CredentialLeaseRecord(
            id=lease_id,
            credential_ids_json=canonical_dumps(sorted(credential_ids)),
            status=CredentialLeaseStatus.PENDING.value,
            version=0,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        ))
        self.session.flush()
        return lease_id

    def claim(self, lease_id: str, credential_ids: set[str]) -> set[str]:
        row = self._locked(lease_id)
        expected = self._credential_ids(row)
        expires_at = self._aware(row.expires_at)
        if (
            row.status != CredentialLeaseStatus.PENDING.value
            or expected != credential_ids
            or expires_at <= datetime.now(UTC)
        ):
            raise self._invalid()
        row.status = CredentialLeaseStatus.CLAIMED.value
        row.claimed_at = datetime.now(UTC)
        row.version = int(row.version or 0) + 1
        self.session.flush()
        return expected

    def commit_claim(self, lease_id: str) -> None:
        row = self._locked(lease_id)
        if row.status != CredentialLeaseStatus.CLAIMED.value:
            raise self._invalid("Credential lease was not claimed.")
        row.status = CredentialLeaseStatus.COMMITTED.value
        row.committed_at = datetime.now(UTC)
        row.version = int(row.version or 0) + 1
        self.session.flush()

    def release(self, lease_id: str) -> bool:
        """Persist cleanup intent before touching the external credential vault."""
        row = self._locked(lease_id)
        if row.status == CredentialLeaseStatus.COMMITTED.value:
            raise self._invalid("Committed credential leases cannot be released.")
        if row.status == CredentialLeaseStatus.RELEASED.value:
            return True
        if row.status not in {
            CredentialLeaseStatus.PENDING.value,
            CredentialLeaseStatus.CLAIMED.value,
            CredentialLeaseStatus.CLEANUP_PENDING.value,
        }:
            raise self._invalid()
        row.status = CredentialLeaseStatus.CLEANUP_PENDING.value
        row.cleanup_started_at = row.cleanup_started_at or datetime.now(UTC)
        row.version = int(row.version or 0) + 1
        credential_ids = self._credential_ids(row)
        self.session.commit()

        complete = True
        try:
            vault = self.vault or get_credential_vault()
        except Exception:
            logger.exception("Credential vault unavailable for lease_id=%s", lease_id)
            return False
        for credential_id in credential_ids:
            try:
                vault.delete(credential_id)
            except Exception:
                complete = False
                logger.exception("Credential lease cleanup failed lease_id=%s", lease_id)

        if complete:
            row = self._locked(lease_id)
            row.status = CredentialLeaseStatus.RELEASED.value
            row.released_at = datetime.now(UTC)
            row.version = int(row.version or 0) + 1
            self.session.commit()
        return complete

    def reconcile(self, *, now: datetime | None = None) -> None:
        current_time = now or datetime.now(UTC)
        candidate_ids = list(self.session.scalars(
            select(CredentialLeaseRecord.id).where(or_(
                CredentialLeaseRecord.status.in_([
                    CredentialLeaseStatus.CLAIMED.value,
                    CredentialLeaseStatus.CLEANUP_PENDING.value,
                ]),
                (
                    (CredentialLeaseRecord.status == CredentialLeaseStatus.PENDING.value)
                    & (CredentialLeaseRecord.expires_at <= current_time)
                ),
            ))
        ))
        for lease_id in candidate_ids:
            row = self._locked(str(lease_id))
            credential_ids = self._credential_ids(row)
            if row.status == CredentialLeaseStatus.CLAIMED.value and self._is_referenced(
                credential_ids
            ):
                row.status = CredentialLeaseStatus.COMMITTED.value
                row.committed_at = current_time
                row.version = int(row.version or 0) + 1
                self.session.commit()
                continue
            self.release(str(lease_id))

    def _is_referenced(self, credential_ids: set[str]) -> bool:
        if not credential_ids:
            return False
        return self.session.execute(
            select(DataSource.id).where(or_(
                DataSource.password_credential_id.in_(credential_ids),
                DataSource.ssh_password_credential_id.in_(credential_ids),
                DataSource.ssh_key_passphrase_credential_id.in_(credential_ids),
            )).limit(1)
        ).scalar_one_or_none() is not None

    def _locked(self, lease_id: str) -> CredentialLeaseRecord:
        row = self.session.execute(
            select(CredentialLeaseRecord)
            .where(CredentialLeaseRecord.id == lease_id)
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            raise self._invalid()
        return row

    @staticmethod
    def _credential_ids(row: CredentialLeaseRecord) -> set[str]:
        return {str(value) for value in load_array(str(row.credential_ids_json))}

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def _invalid(message: str = "Credential lease is invalid or does not own these references.") -> DBFoxError:
        return DBFoxError(message, code="CREDENTIAL_LEASE_INVALID")


def reconcile_credential_leases(session_factory) -> None:
    with session_factory() as session:
        CredentialLeaseSaga(session).reconcile()
