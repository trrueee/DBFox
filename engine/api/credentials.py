"""Local-only credential enrollment routes.

This router deliberately exposes no read operation.  Consumers receive an
opaque reference which can be used by a trusted backend boundary but never a
secret value.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from uuid import uuid4

from fastapi import APIRouter, status

from engine.errors import DBFoxError
from engine.schemas.credentials import (
    CredentialEnrollmentBatchRequest,
    CredentialEnrollmentBatchResponse,
    CredentialEnrollmentRequest,
    CredentialReference,
)
from engine.security.credential_vault import CredentialVault, get_credential_vault


router = APIRouter()


@dataclass(frozen=True)
class CredentialLease:
    credential_ids: frozenset[str]


class CredentialLeaseRegistry:
    """Server-owned, one-shot ownership records for unenrolled datasource secrets.

    A browser never gets to classify an arbitrary credential ID as temporary.
    It can only present the opaque lease that this process created alongside a
    batch enrollment, and every request must claim the exact issued ID set.
    """

    def __init__(self) -> None:
        self._leases: dict[str, CredentialLease] = {}
        self._claimed: dict[str, CredentialLease] = {}
        self._lock = RLock()

    def issue(self, credential_ids: set[str]) -> str:
        if not credential_ids:
            raise ValueError("Credential leases require at least one reference")
        lease_id = f"lease_{uuid4().hex}"
        with self._lock:
            self._leases[lease_id] = CredentialLease(frozenset(credential_ids))
        return lease_id

    def claim(self, lease_id: str, credential_ids: set[str]) -> set[str]:
        expected = frozenset(credential_ids)
        with self._lock:
            lease = self._leases.get(lease_id)
            if lease is None or lease.credential_ids != expected:
                raise DBFoxError(
                    "Credential lease is invalid or does not own these references.",
                    code="CREDENTIAL_LEASE_INVALID",
                )
            self._leases.pop(lease_id)
            self._claimed[lease_id] = lease
        return set(lease.credential_ids)

    def commit(self, lease_id: str) -> None:
        with self._lock:
            if self._claimed.pop(lease_id, None) is None:
                raise DBFoxError("Credential lease was not claimed.", code="CREDENTIAL_LEASE_INVALID")

    def release(self, lease_id: str) -> set[str]:
        """Return IDs owned by an active/claimed lease, or nothing if already consumed."""
        with self._lock:
            lease = self._claimed.pop(lease_id, None) or self._leases.pop(lease_id, None)
        return set(lease.credential_ids) if lease is not None else set()


_credential_leases = CredentialLeaseRegistry()


def get_credential_lease_registry() -> CredentialLeaseRegistry:
    return _credential_leases


def release_credential_lease(
    lease_id: str,
    *,
    vault: CredentialVault | None = None,
    leases: CredentialLeaseRegistry | None = None,
) -> None:
    """Delete only references owned by an uncommitted server-issued lease."""
    credential_vault = vault or get_credential_vault()
    registry = leases or get_credential_lease_registry()
    for credential_id in registry.release(lease_id):
        credential_vault.delete(credential_id)


def enroll_credential(
    request: CredentialEnrollmentRequest,
    *,
    vault: CredentialVault | None = None,
) -> CredentialReference:
    """Store a transient secret and return its opaque keyring reference."""
    credential_vault = vault or get_credential_vault()
    credential_id = credential_vault.put(
        kind=request.kind,
        secret=request.secret.get_secret_value(),
    )
    return CredentialReference(id=credential_id, kind=request.kind)


def enroll_credentials(
    request: CredentialEnrollmentBatchRequest,
    *,
    vault: CredentialVault | None = None,
    leases: CredentialLeaseRegistry | None = None,
) -> CredentialEnrollmentBatchResponse:
    """Enroll related secrets and return the only lease allowed to consume them."""
    credential_vault = vault or get_credential_vault()
    registry = leases or get_credential_lease_registry()
    created: list[CredentialReference] = []
    try:
        for enrollment in request.credentials:
            created.append(enroll_credential(enrollment, vault=credential_vault))
    except Exception:
        for reference in created:
            try:
                credential_vault.delete(reference.id)
            except Exception:
                # The original enrollment failure remains the actionable error.
                pass
        raise
    return CredentialEnrollmentBatchResponse(
        credentials=created,
        lease_id=registry.issue({reference.id for reference in created}),
    )


@router.post("/credentials", response_model=CredentialReference, status_code=201)
def api_enroll_credential(request: CredentialEnrollmentRequest) -> CredentialReference:
    return enroll_credential(request)


@router.post("/credentials/batch", response_model=CredentialEnrollmentBatchResponse, status_code=201)
def api_enroll_credentials(
    request: CredentialEnrollmentBatchRequest,
) -> CredentialEnrollmentBatchResponse:
    return enroll_credentials(request)


@router.delete("/credentials/leases/{lease_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_release_credential_lease(lease_id: str) -> None:
    """Revoke only credentials held by this still-uncommitted server lease."""
    release_credential_lease(lease_id)
