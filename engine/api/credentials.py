"""Local-only credential enrollment routes.

This router deliberately exposes no read operation.  Consumers receive an
opaque reference which can be used by a trusted backend boundary but never a
secret value.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from engine.db import get_db
from engine.schemas.credentials import (
    CredentialEnrollmentBatchRequest,
    CredentialEnrollmentBatchResponse,
    CredentialEnrollmentRequest,
    CredentialReference,
)
from engine.security.credential_vault import (
    CredentialVault,
    create_credential_id,
    get_credential_vault,
)
from engine.security.credential_lease import CredentialLeaseSaga


router = APIRouter()


def release_credential_lease(
    lease_id: str,
    *,
    db: Session,
    vault: CredentialVault | None = None,
) -> None:
    CredentialLeaseSaga(db, vault or get_credential_vault()).release(lease_id)


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
    db: Session,
    vault: CredentialVault | None = None,
) -> CredentialEnrollmentBatchResponse:
    """Enroll related secrets and return the only lease allowed to consume them."""
    credential_vault = vault or get_credential_vault()
    created = [
        CredentialReference(id=create_credential_id(item.kind), kind=item.kind)
        for item in request.credentials
    ]
    saga = CredentialLeaseSaga(db, credential_vault)
    lease_id = saga.issue({reference.id for reference in created})
    db.commit()
    try:
        for enrollment, reference in zip(request.credentials, created, strict=True):
            credential_vault.put(
                kind=enrollment.kind,
                secret=enrollment.secret.get_secret_value(),
                credential_id=reference.id,
            )
    except Exception:
        saga.release(lease_id)
        raise
    return CredentialEnrollmentBatchResponse(credentials=created, lease_id=lease_id)


@router.post("/credentials", response_model=CredentialReference, status_code=201)
def api_enroll_credential(request: CredentialEnrollmentRequest) -> CredentialReference:
    return enroll_credential(request)


@router.post("/credentials/batch", response_model=CredentialEnrollmentBatchResponse, status_code=201)
def api_enroll_credentials(
    request: CredentialEnrollmentBatchRequest,
    db: Session = Depends(get_db),
) -> CredentialEnrollmentBatchResponse:
    return enroll_credentials(request, db=db)


@router.delete(
    "/credentials/leases/{lease_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def api_release_credential_lease(
    lease_id: str,
    db: Session = Depends(get_db),
) -> None:
    """Revoke only credentials held by this still-uncommitted server lease."""
    release_credential_lease(lease_id, db=db)
